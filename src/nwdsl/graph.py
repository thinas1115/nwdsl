"""ビュー解決: Document + View から描画用中間グラフ (RenderGraph) を作る。

出力フォーマット (D2 / Mermaid) に依存しない層。ここで
- layers による接続種別フィルタ
- include_sites / exclude_sites による範囲フィルタ
- collapse_sites による拠点の畳み込み
を解決し、シリアライザは RenderGraph を書き出すだけにする。
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from .model import Circuit, Document, View, parse_endpoint


@dataclass
class RenderNode:
    id: str                      # グラフ内で一意
    label: str                   # 表示名 (改行 \n 可)
    kind: str                    # "device" | "cloud" | "site" | "external-device"
    role: Optional[str] = None   # device の role / cloud の kind
    site: Optional[str] = None   # 所属拠点 (コンテナ描画用。None はグループ外)
    emphasis: Optional[str] = None  # 経路ビュー用: None(通常) | "dim" | "failed"


@dataclass
class RenderEdge:
    src: str
    dst: str
    type: str                    # link type (線種スタイルの決定に使う)
    label: Optional[str] = None
    src_label: Optional[str] = None  # 端点付近に描く小ラベル (IF名)
    dst_label: Optional[str] = None
    circuit: Optional[str] = None    # 経由回線ID (障害マーク用)
    emphasis: Optional[str] = None   # None | "path" | "disabled" | "dim" | "failed"
    seq: Optional[int] = None        # 経路上のホップ番号 (1始まり)
    directed: bool = False           # True なら矢印付きで描く


@dataclass
class RenderGraph:
    title: str
    groups: list[tuple[str, str]] = field(default_factory=list)  # (site_id, 表示名)
    nodes: list[RenderNode] = field(default_factory=list)
    edges: list[RenderEdge] = field(default_factory=list)


def _circuit_label(circuit: Circuit) -> str:
    # 複数行ラベルは隣接エッジと重なりやすいため1行に収める
    parts = [circuit.provider, circuit.service]
    if circuit.bandwidth:
        parts.append(circuit.bandwidth)
    return " ".join(parts)


def _device_label(doc: Document, device_id: str) -> str:
    dev = next(d for d in doc.devices if d.id == device_id)
    return f"{dev.id}\n{dev.platform}" if dev.platform else dev.id


def _edge_label(doc: Document, link, ifnames: dict[str, Optional[str]]) -> Optional[str]:
    if link.type == "lan-cable":
        # IF名は両端の機器側小ラベルに置くため中央ラベルは説明のみ
        return link.description
    if link.type == "wan-circuit":
        circuit = next((c for c in doc.circuits if c.id == link.circuit), None)
        label = _circuit_label(circuit) if circuit else (link.circuit or "")
        dev_if = [n for n in ifnames.values() if n]
        if dev_if:
            # 縦レイアウトではWAN線同士が空間的に分離するため2行目にIFを添えられる
            label += f"\n({' - '.join(dev_if)})"
        return label
    # tunnel / logical
    return link.description or link.type


def resolve_view(doc: Document, view: View) -> RenderGraph:
    """View を描画用中間グラフに解決する (type により分岐)。"""
    if view.type == "path":
        return _resolve_path_view(doc, view)
    return _resolve_topology_view(doc, view)


def _resolve_topology_view(doc: Document, view: View) -> RenderGraph:
    site_by_id = {s.id: s for s in doc.sites}
    device_by_id = {d.id: d for d in doc.devices}
    cloud_by_id = {c.id: c for c in doc.clouds}

    in_scope = {s.id for s in doc.sites}
    if view.include_sites is not None:
        in_scope = set(view.include_sites)
    if view.exclude_sites:
        in_scope -= set(view.exclude_sites)

    selected = [l for l in doc.links if l.type in view.layers]

    graph = RenderGraph(title=view.title)
    nodes: dict[str, RenderNode] = {}
    used_sites: list[str] = []

    def add_node(node: RenderNode) -> None:
        if node.id not in nodes:
            nodes[node.id] = node
            if node.site and node.site not in used_sites:
                used_sites.append(node.site)

    if view.collapse_sites:
        # ---- 拠点を1ノードに畳む ----
        for link in selected:
            mapped: list[str] = []
            for ep in link.endpoints:
                node_id, _ = parse_endpoint(ep)
                if node_id in device_by_id:
                    mapped.append(f"site__{device_by_id[node_id].site}")
                elif node_id in cloud_by_id:
                    mapped.append(f"cloud__{node_id}")
            if len(mapped) != 2 or mapped[0] == mapped[1]:
                continue  # 拠点内で閉じる接続は畳み込みで消える
            sids = [m.removeprefix("site__") for m in mapped if m.startswith("site__")]
            if in_scope and not any(s in in_scope for s in sids):
                continue
            for m in mapped:
                if m.startswith("site__"):
                    site = site_by_id[m.removeprefix("site__")]
                    add_node(RenderNode(id=m, label=site.name, kind="site"))
                else:
                    cloud = cloud_by_id[m.removeprefix("cloud__")]
                    add_node(RenderNode(id=m, label=cloud.name, kind="cloud", role=cloud.kind))
            label = _edge_label(doc, link, {})
            if link.type == "wan-circuit":
                circuit = next((c for c in doc.circuits if c.id == link.circuit), None)
                label = _circuit_label(circuit) if circuit else link.circuit
            graph.edges.append(RenderEdge(mapped[0], mapped[1], link.type, label))
    else:
        # ---- 機器レベルの図 ----
        for link in selected:
            ep_nodes: list[str] = []
            ifnames: dict[str, Optional[str]] = {}
            dev_sites: list[str] = []
            for ep in link.endpoints:
                node_id, ifname = parse_endpoint(ep)
                ep_nodes.append(node_id)
                ifnames[node_id] = ifname
                if node_id in device_by_id:
                    dev_sites.append(device_by_id[node_id].site)
            # 機器端点が1つも範囲内になければ除外
            if dev_sites and not any(s in in_scope for s in dev_sites):
                continue
            for node_id in ep_nodes:
                if node_id in device_by_id:
                    dev = device_by_id[node_id]
                    if dev.site in in_scope:
                        add_node(RenderNode(id=node_id, label=_device_label(doc, node_id),
                                            kind="device", role=dev.role, site=dev.site))
                    else:
                        # 範囲外の対向機器は拠点名を添えた境界ノードとして表示
                        site_name = site_by_id[dev.site].name if dev.site in site_by_id else dev.site
                        add_node(RenderNode(id=node_id, label=f"{node_id}\n({site_name})",
                                            kind="external-device", role=dev.role))
                elif node_id in cloud_by_id:
                    cloud = cloud_by_id[node_id]
                    add_node(RenderNode(id=node_id, label=cloud.name, kind="cloud", role=cloud.kind))
            edge = RenderEdge(ep_nodes[0], ep_nodes[1], link.type,
                              _edge_label(doc, link, ifnames), circuit=link.circuit)
            if link.type == "lan-cable":
                # IF名は各機器の接続点そばに分散配置する (平行エッジの中央ラベル同士の
                # 衝突、および1機器に複数WANが刺さる場合の端点ラベル密着を実測して選択)
                edge.src_label = ifnames.get(ep_nodes[0])
                edge.dst_label = ifnames.get(ep_nodes[1])
            graph.edges.append(edge)

        # 接続を持たない範囲内の機器も孤立ノードとして表示する
        for dev in doc.devices:
            if dev.site in in_scope and dev.id not in nodes:
                add_node(RenderNode(id=dev.id, label=_device_label(doc, dev.id),
                                    kind="device", role=dev.role, site=dev.site))

    graph.nodes = list(nodes.values())
    graph.groups = [(sid, site_by_id[sid].name) for sid in used_sites if sid in site_by_id]
    _bundle_parallel_cables(graph)
    _orient_edges(doc, graph)
    return graph


def _bundle_parallel_cables(graph: RenderGraph) -> None:
    """同一機器ペア間の平行な構内配線 (LAG等) を1本に束ね「×N」表示にする。

    メンバー個別のIF対応は表 (接続一覧) が持つため、図では本数情報に集約する。
    """
    seen: dict[frozenset[str], RenderEdge] = {}
    bundled: list[RenderEdge] = []
    counts: dict[frozenset[str], int] = {}
    for edge in graph.edges:
        if edge.type != "lan-cable":
            bundled.append(edge)
            continue
        key = frozenset((edge.src, edge.dst))
        if key in seen:
            counts[key] = counts.get(key, 1) + 1
        else:
            seen[key] = edge
            bundled.append(edge)
    for key, n in counts.items():  # n は束ねた総本数
        edge = seen[key]
        edge.label = f"×{n}" + (f" {edge.label}" if edge.label else "")
        edge.src_label = None  # 束ねた場合、端点IFは1組に定まらないため表に委ねる
        edge.dst_label = None
    graph.edges = bundled


def _orient_edges(doc: Document, graph: RenderGraph) -> None:
    """全エッジを「WAN側 → LAN側」の順に揃える。

    ELK (layered) は無向エッジでも記述順 (source→target) をランク方向として
    使うことを実測で確認済み (ADR-0005)。クラウドを起点にマルチソースBFSで
    各ノードのWAN距離を求め、エッジの端点を距離の小さい側→大きい側に並べる。
    これと direction: down の組み合わせで「WANが上・LANが下へ降りる」層構造が
    tier 指定なしで保証される。
    """
    sources = [n.id for n in graph.nodes if n.kind == "cloud"]
    if not sources:
        # クラウドが図に無いビュー (論理図等) では WAN 境界機器を起点にする
        wan_devices: set[str] = set()
        for link in doc.links:
            if link.type == "wan-circuit":
                for ep in link.endpoints:
                    node_id, _ = parse_endpoint(ep)
                    wan_devices.add(node_id)
        node_ids = {n.id for n in graph.nodes}
        sources = sorted(wan_devices & node_ids)
    if not sources:
        return

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.src].add(edge.dst)
        adjacency[edge.dst].add(edge.src)

    dist: dict[str, int] = {s: 0 for s in sources}
    queue = deque(sources)
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in dist:
                dist[neighbor] = dist[current] + 1
                queue.append(neighbor)

    unreachable = float("inf")
    for edge in graph.edges:
        if dist.get(edge.src, unreachable) > dist.get(edge.dst, unreachable):
            edge.src, edge.dst = edge.dst, edge.src
            edge.src_label, edge.dst_label = edge.dst_label, edge.src_label


_SEQ_MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _seq_mark(index: int) -> str:
    return _SEQ_MARKS[index] if index < len(_SEQ_MARKS) else f"({index + 1})"


def _resolve_path_view(doc: Document, view: View) -> RenderGraph:
    """経路ビュー: トポロジ図の上に経路ハイライトを重ねる。

    - 経路上のノード/エッジ: 通常表示 + 赤太線・ホップ番号・注記
    - fallback_of の経路 (無効化された正常経路): 灰破線
    - failure のコンポーネント: 赤✕ (回線なら該当エッジを赤破線)
    - それ以外: 淡色化
    """
    path = next(p for p in doc.paths if p.id == view.path)
    fallback = next((p for p in doc.paths if p.id == path.fallback_of), None)

    device_by_id = {d.id: d for d in doc.devices}
    hop_nodes: list[str] = [h.node for h in path.hops]
    all_path_nodes = set(hop_nodes) | ({h.node for h in fallback.hops} if fallback else set())

    # 経路・障害に関係する拠点だけを描く (無関係拠点のノイズを避ける)
    involved_sites = {device_by_id[n].site for n in all_path_nodes if n in device_by_id}
    involved_sites |= {device_by_id[c].site for c in path.failure if c in device_by_id}

    base_view = View(
        id=view.id, title=view.title,
        layers=["lan-cable", "wan-circuit", "logical", "tunnel"],
        include_sites=sorted(involved_sites) or None)
    graph = _resolve_topology_view(doc, base_view)
    graph.title = view.title

    # --- ノードの強調/淡色化 ---
    failed_nodes = set(path.failure)
    for node in graph.nodes:
        if node.id in failed_nodes:
            node.emphasis = "failed"
        elif node.id not in all_path_nodes:
            node.emphasis = "dim"

    # --- エッジ索引 (無向) ---
    edges_by_pair: dict[frozenset[str], list[RenderEdge]] = {}
    for edge in graph.edges:
        edges_by_pair.setdefault(frozenset((edge.src, edge.dst)), []).append(edge)

    def _mark_pair(a: str, b: str, emphasis: str) -> Optional[RenderEdge]:
        for candidate in edges_by_pair.get(frozenset((a, b)), []):
            if candidate.emphasis is None:
                candidate.emphasis = emphasis
                return candidate
        return None

    # --- 障害回線・障害ノードに接続するWANエッジを赤破線に ---
    failed_circuits = {c for c in path.failure}
    for edge in graph.edges:
        if edge.circuit is not None and edge.circuit in failed_circuits:
            edge.emphasis = "failed"
        elif failed_nodes and (edge.src in failed_nodes or edge.dst in failed_nodes):
            edge.emphasis = "failed"

    # --- fallback (無効化された正常経路) を灰破線に ---
    if fallback is not None:
        for prev, nxt in zip(fallback.hops, fallback.hops[1:]):
            _mark_pair(prev.node, nxt.node, "disabled")

    # --- 経路本体を強調 (向き・ホップ番号・注記付き) ---
    for i, (prev, nxt) in enumerate(zip(path.hops, path.hops[1:])):
        edge = None
        for candidate in edges_by_pair.get(frozenset((prev.node, nxt.node)), []):
            if candidate.emphasis in (None, "failed", "disabled"):
                edge = candidate
                break
        if edge is None:
            continue  # バリデータが隣接性を保証するため通常到達しない
        edge.emphasis = "path"
        edge.seq = i + 1
        edge.directed = True
        if edge.src != prev.node:  # 経路の進行方向に向きを合わせる
            edge.src, edge.dst = edge.dst, edge.src
            edge.src_label, edge.dst_label = edge.dst_label, edge.src_label
        annotation = " ".join(x for x in (nxt.protocol, nxt.note) if x)
        edge.label = f"{_seq_mark(i)} {annotation}".strip()

    # --- 残りのエッジは淡色化 ---
    for edge in graph.edges:
        if edge.emphasis is None:
            edge.emphasis = "dim"
    return graph
