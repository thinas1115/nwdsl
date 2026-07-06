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
    domain: Optional[str] = None     # 所属ルーティングドメイン (色分け用)
    continuation: bool = False       # via分割の後半 (domain凡例名フォールバックの重複表示を抑止。
                                      # description由来のlabelは雲の両側で意図的に揃える。ADR-0005)
    emphasis: Optional[str] = None   # None | "path" | "disabled" | "dim" | "failed"
    seq: Optional[int] = None        # 経路上のホップ番号 (1始まり)
    directed: bool = False           # True なら矢印付きで描く


@dataclass
class RenderGraph:
    title: str
    groups: list[tuple[str, str]] = field(default_factory=list)  # (site_id, 表示名)
    nodes: list[RenderNode] = field(default_factory=list)
    edges: list[RenderEdge] = field(default_factory=list)
    domains: dict[str, str] = field(default_factory=dict)  # id -> 表示名 (凡例用)
    site_order: dict[str, int] = field(default_factory=dict)  # site_id -> sites宣言順index
    order: str = "auto"  # "auto" (クロス最小化) | "declared" (site_order優先、内蔵SVGのみ)


_DOMAIN_PALETTE = ["#e8710a", "#0b8043", "#8430ce", "#00838f",
                   "#a56500", "#d01884", "#3949ab", "#5f6368"]


def domain_colors(graph: RenderGraph) -> dict[str, str]:
    """ドメインIDへ決定的に色を割り当てる (DSLには色を書かせない方針)。"""
    return {d: _DOMAIN_PALETTE[i % len(_DOMAIN_PALETTE)]
            for i, d in enumerate(sorted(graph.domains))}


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
    # tunnel / logical: domain指定時は凡例が意味を伝えるため個別ラベルを出さない
    if link.description:
        return link.description
    return None if link.domain else link.type


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

    graph = RenderGraph(title=view.title, order=view.order,
                       site_order={s.id: i for i, s in enumerate(doc.sites)})
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
            if link.via and link.via in cloud_by_id and all(
                    m.startswith("site__") for m in mapped):
                via_cloud = cloud_by_id[link.via]
                via_id = f"cloud__{via_cloud.id}"
                add_node(RenderNode(id=via_id, label=via_cloud.name, kind="cloud",
                                    role=via_cloud.kind))
                graph.edges.append(RenderEdge(mapped[0], via_id, link.type, label,
                                              domain=link.domain))
                graph.edges.append(RenderEdge(via_id, mapped[1], link.type, label,
                                              domain=link.domain, continuation=True))
            else:
                graph.edges.append(RenderEdge(mapped[0], mapped[1], link.type, label,
                                              circuit=link.circuit, domain=link.domain))
    else:
        # ---- 機器レベルの図 ----
        view_ifs: set[tuple[str, str]] = set()  # このビューに現れた接続のIF
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
            label = _edge_label(doc, link, ifnames)
            if link.via and link.via in cloud_by_id:
                # 網経由のピアリング: 雲を通して2分割で描く (論理図の実務表現)
                cloud = cloud_by_id[link.via]
                add_node(RenderNode(id=cloud.id, label=cloud.name, kind="cloud",
                                    role=cloud.kind))
                graph.edges.append(RenderEdge(ep_nodes[0], cloud.id, link.type, label,
                                              domain=link.domain))
                graph.edges.append(RenderEdge(cloud.id, ep_nodes[1], link.type, label,
                                              domain=link.domain, continuation=True))
            else:
                edge = RenderEdge(ep_nodes[0], ep_nodes[1], link.type, label,
                                  circuit=link.circuit, domain=link.domain)
                if link.type == "lan-cable":
                    # IF名は各機器の接続点そばに分散配置する (平行エッジの中央ラベルの
                    # 衝突、複数WAN機器での端点ラベル密着を実測して選択)
                    edge.src_label = ifnames.get(ep_nodes[0])
                    edge.dst_label = ifnames.get(ep_nodes[1])
                graph.edges.append(edge)
            view_ifs.update((n, i) for n, i in ifnames.items() if i is not None)

        # 純粋なL3ビュー (logicalを含む、または物理レイヤ抜きのtunnelのみ) か
        pure_l3 = ("logical" in view.layers
                   or ("tunnel" in view.layers
                       and not {"lan-cable", "wan-circuit"} & set(view.layers)))

        # 接続を持たない範囲内の機器も孤立ノードとして表示する。
        # ただし純L3ビューでは、L3情報を持たない機器 (L2アクセスSW等) は省く
        for dev in doc.devices:
            if dev.site in in_scope and dev.id not in nodes:
                if pure_l3 and not any(i.ipv4 or i.segment for i in dev.interfaces):
                    continue
                add_node(RenderNode(id=dev.id, label=_device_label(doc, dev.id),
                                    kind="device", role=dev.role, site=dev.site))

        # ---- 孤立機器を実在のlan-cableで補完接続 ----
        # 上のループで追加された機器 (例: L3スイッチ) が現ビューのlayersでは
        # 誰とも繋がらず「外部から浮いている」ように見えることがある。実際には
        # lan-cableで他機器と繋がっているはずなので、その配線を通常のlan-cable
        # 描画 (黒細線+IF名) で補って「どう到達するか」を示す。
        connected = {n for e in graph.edges for n in (e.src, e.dst)}
        for dev in doc.devices:
            if dev.id not in nodes or dev.id in connected:
                continue
            for link in doc.links:
                if link.type != "lan-cable":
                    continue
                ep_ids = [parse_endpoint(ep)[0] for ep in link.endpoints]
                if dev.id not in ep_ids:
                    continue
                other = next((e for e in ep_ids if e != dev.id), None)
                if other is None or other not in nodes:
                    continue
                ifnames = {parse_endpoint(ep)[0]: parse_endpoint(ep)[1]
                          for ep in link.endpoints}
                edge = RenderEdge(ep_ids[0], ep_ids[1], link.type,
                                  _edge_label(doc, link, ifnames))
                edge.src_label = ifnames.get(ep_ids[0])
                edge.dst_label = ifnames.get(ep_ids[1])
                graph.edges.append(edge)
                connected.add(dev.id)
                connected.add(other)

        # ---- L3情報の表示 (論理ビューでは自動有効、show_l3 で表示範囲を制御) ----
        raw_l3 = view.show_l3
        if raw_l3 is None:
            l3_mode = "view" if pure_l3 else None
        elif raw_l3 is True:
            l3_mode = "view"
        elif raw_l3 is False:
            l3_mode = None
        else:
            l3_mode = raw_l3
        if l3_mode:
            used_ifs: set[tuple[str, str]] = set()
            for link in doc.links:
                for ep in link.endpoints:
                    ep_node, ep_if = parse_endpoint(ep)
                    if ep_if is not None:
                        used_ifs.add((ep_node, ep_if))

            def _l3_visible(dev_id: str, intf) -> bool:
                if not intf.ipv4:
                    return False
                if l3_mode == "all":
                    return True
                if intf.segment:  # 表示されるセグメントのGWは常に対象
                    return True
                if l3_mode == "view":
                    return (dev_id, intf.name) in view_ifs
                return (dev_id, intf.name) in used_ifs  # "used"

            for node in nodes.values():
                if node.kind != "device":
                    continue
                dev = device_by_id[node.id]
                ips = [f"{i.name}: {i.ipv4}" for i in dev.interfaces
                       if _l3_visible(dev.id, i)]
                if len(ips) > 5:
                    ips = ips[:5] + [f"…他{len(ips) - 5}件"]
                if ips:
                    node.label += "\n" + "\n".join(ips)
            for seg in doc.segments:
                if seg.site not in in_scope:
                    continue
                lines = [seg.name or seg.id]
                detail = " / ".join(x for x in (
                    f"VLAN {seg.vlan}" if seg.vlan else None, seg.ipv4) if x)
                if detail:
                    lines.append(detail)
                seg_node_id = f"seg__{seg.id}"
                add_node(RenderNode(id=seg_node_id, label="\n".join(lines),
                                    kind="segment", site=seg.site))
                for dev in doc.devices:
                    if dev.id not in nodes:
                        continue
                    for intf in dev.interfaces:
                        if intf.segment == seg.id:
                            graph.edges.append(RenderEdge(
                                dev.id, seg_node_id, "segment", src_label=intf.name))

    graph.nodes = list(nodes.values())
    if view.order == "declared":
        site_ids = sorted((s for s in used_sites if s in site_by_id),
                          key=lambda s: graph.site_order.get(s, 0))
    else:
        site_ids = [s for s in used_sites if s in site_by_id]
    graph.groups = [(sid, site_by_id[sid].name) for sid in site_ids]
    used_domains = {e.domain for e in graph.edges if e.domain}
    graph.domains = {d.id: d.name for d in doc.domains if d.id in used_domains}
    _bundle_parallel_cables(graph)
    _dedupe_duplicate_edges(graph)
    _orient_edges(doc, graph)
    return graph


def _dedupe_duplicate_edges(graph: RenderGraph) -> None:
    """viaで雲越えに分割した際、複数の別リンクが同じ雲側スタブに収束すると
    見た目上完全に同一なエッジが重複して描かれる (例: 同じ雲を経由する複数の
    BGPピアは、雲から見て手前側では同じ1本の線のはずが、リンクごとに別
    エッジとして生成されるため2本重なって描かれる)。lan-cableはLAG本数を
    ×N表示する_bundle_parallel_cablesに任せ、それ以外の型で見た目上完全に
    区別できないエッジは1本に統合する。
    """
    seen: set[tuple] = set()
    deduped: list[RenderEdge] = []
    for edge in graph.edges:
        if edge.type == "lan-cable":
            deduped.append(edge)
            continue
        key = (frozenset((edge.src, edge.dst)), edge.type, edge.label, edge.domain,
              edge.continuation, edge.src_label, edge.dst_label, edge.circuit)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    graph.edges = deduped


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
    # 起点は2段シード: クラウド=距離0、WAN境界機器=距離1。
    # クラウドのみだと、WAN回線を表示しない論理ビューで冗長側ルーターが
    # 「下流」と誤認され最下段に落ちる。同格にすると物理図で雲が上に固定されない
    node_ids = {n.id for n in graph.nodes}
    clouds = sorted(n.id for n in graph.nodes if n.kind == "cloud")
    wan_devices: set[str] = set()
    for link in doc.links:
        if link.type == "wan-circuit":
            for ep in link.endpoints:
                ep_node, _ = parse_endpoint(ep)
                wan_devices.add(ep_node)
    wan_seeds = sorted((wan_devices & node_ids) - set(clouds))
    if not clouds and not wan_seeds:
        return

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.src].add(edge.dst)
        adjacency[edge.dst].add(edge.src)

    dist: dict[str, int] = {c: 0 for c in clouds}
    for w in wan_seeds:
        dist.setdefault(w, 1)
    queue = deque(clouds + [w for w in wan_seeds if dist[w] == 1])
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
        # 矢印の向きは常にレイアウトの向き付け (ADR-0005) 通りの src/dst を維持する。
        # ホップ進行方向に合わせて src/dst を入れ替えると、D2/Mermaid/内蔵SVG いずれも
        # 記述順をランク(階層位置)に使うため、経路ごとに階層が変わり正常時/障害時で
        # 拠点・クラウドの位置がズレる原因になっていた。実際の進行方向はホップ番号
        # (①②③...) で示す。
        annotation = " ".join(x for x in (nxt.protocol, nxt.note) if x)
        edge.label = f"{_seq_mark(i)} {annotation}".strip()

    # --- 残りのエッジは淡色化 ---
    for edge in graph.edges:
        if edge.emphasis is None:
            edge.emphasis = "dim"
    return graph
