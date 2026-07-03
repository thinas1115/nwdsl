"""ビュー解決: Document + View から描画用中間グラフ (RenderGraph) を作る。

出力フォーマット (D2 / Mermaid) に依存しない層。ここで
- layers による接続種別フィルタ
- include_sites / exclude_sites による範囲フィルタ
- collapse_sites による拠点の畳み込み
を解決し、シリアライザは RenderGraph を書き出すだけにする。
"""

from __future__ import annotations

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


@dataclass
class RenderEdge:
    src: str
    dst: str
    type: str                    # link type (線種スタイルの決定に使う)
    label: Optional[str] = None
    src_label: Optional[str] = None  # 端点付近に描く小ラベル (IF名)
    dst_label: Optional[str] = None


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
        names = [n for n in ifnames.values() if n]
        return " - ".join(names) if names else link.description
    if link.type == "wan-circuit":
        circuit = next((c for c in doc.circuits if c.id == link.circuit), None)
        return _circuit_label(circuit) if circuit else (link.circuit or "")
    # tunnel / logical
    return link.description or link.type


def resolve_view(doc: Document, view: View) -> RenderGraph:
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
                              _edge_label(doc, link, ifnames))
            if link.type == "wan-circuit":
                # IF名は中央ラベルに混ぜず機器側端点の小ラベルにする (ラベル重なり対策)
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
    return graph
