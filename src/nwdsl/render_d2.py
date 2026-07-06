"""RenderGraph を D2 ソースに変換する (プライマリ出力先)。

スタイルは機器ロール・接続種別から機械的に決める。DSL側は色・座標を持たない。
生成した .d2 は `d2 --layout=elk in.d2 out.svg` で描画する。
"""

from __future__ import annotations

import re

from .graph import RenderGraph, RenderNode, domain_colors

_NODE_CLASSES = """\
classes: {
  role-router: {style.fill: "#e8f0fe"; style.stroke: "#1a56b0"; style.font-color: "#1a2340"}
  role-l3switch: {style.fill: "#d2e3fc"; style.stroke: "#1a56b0"; style.font-color: "#1a2340"}
  role-l2switch: {style.fill: "#e6f4ea"; style.stroke: "#137333"; style.font-color: "#1a2e1f"}
  role-firewall: {style.fill: "#fce8e6"; style.stroke: "#c5221f"; style.font-color: "#3c1a19"}
  role-other: {style.fill: "#f1f3f4"; style.stroke: "#5f6368"; style.font-color: "#202124"}
  node-cloud: {shape: cloud; style.fill: "#f1f3f4"; style.stroke: "#5f6368"}
  node-site: {style.fill: "#fff8e1"; style.stroke: "#b58105"; style.font-color: "#4a3a08"}
  node-segment: {style.fill: "#e2f5f0"; style.stroke: "#0f766e"; style.font-color: "#0b3d38"; style.border-radius: 12}
  node-external: {style.fill: "#ffffff"; style.stroke: "#9aa0a6"; style.stroke-dash: 3}
  group-site: {style.fill: "#f7f9fc"; style.stroke: "#8fa8c4"; style.font-color: "#33475b"}
  edge-label: {style.fill: "transparent"; style.stroke: "transparent"; style.font-size: 14; style.font-color: "#5f6368"; style.italic: true}
  edge-lan-cable: {style.stroke: "#4a4a4a"; style.stroke-width: 2}
  edge-wan-circuit: {style.stroke: "#1a73e8"; style.stroke-width: 4}
  edge-tunnel: {style.stroke: "#7b1fa2"; style.stroke-width: 2; style.stroke-dash: 5}
  edge-logical: {style.stroke: "#188038"; style.stroke-width: 2; style.stroke-dash: 3}
  edge-segment: {style.stroke: "#0f766e"; style.stroke-width: 1}
}
"""

_KNOWN_ROLES = {"router", "l3switch", "l2switch", "firewall"}


def _key(raw: str) -> str:
    """D2 のキーとして安全な識別子に変換する。"""
    return re.sub(r"[^0-9A-Za-z_]", "_", raw)


def _label(text: str) -> str:
    return text.replace('"', "'").replace("\n", "\\n")


def _node_label(node: RenderNode) -> str:
    label = node.label
    if node.emphasis == "failed":
        label = f"✕障害\n{label}"
    # cloud 形状はCJKラベルの幅を詰めすぎて文字がはみ出すため余白を足す
    if node.kind == "cloud":
        return f"　{label}　"
    return label


def _node_attrs(node: RenderNode, min_width: int | None = None) -> str:
    attrs = [f"class: {_node_class(node)}"]
    if min_width is not None:
        attrs.append(f"width: {min_width}")
    if node.emphasis == "dim":
        attrs.append("style.opacity: 0.3")
    elif node.emphasis == "failed":
        attrs.append('style.stroke: "#c5221f"')
        attrs.append('style.fill: "#fce8e6"')
        attrs.append("style.stroke-width: 3")
    return "; ".join(attrs)


_EDGE_EMPHASIS_STYLES = {
    "path": ['style.stroke: "#c5221f"', "style.stroke-width: 4", "style.animated: true"],
    "disabled": ['style.stroke: "#9aa0a6"', "style.stroke-dash: 4", "style.opacity: 0.4"],
    "dim": ["style.opacity: 0.15"],
    "failed": ['style.stroke: "#c5221f"', "style.stroke-dash: 4", "style.opacity: 0.55"],
}


def _node_class(node: RenderNode) -> str:
    if node.kind == "cloud":
        return "node-cloud"
    if node.kind == "segment":
        return "node-segment"
    if node.kind == "site":
        return "node-site"
    if node.kind == "external-device":
        return "node-external"
    role = node.role if node.role in _KNOWN_ROLES else "other"
    return f"role-{role}"


def _min_widths(graph: RenderGraph) -> dict[str, int]:
    """接続本数に応じたノードの最小幅。

    direction: down では流入エッジが上辺・流出エッジが下辺に付き、D2は端点
    ラベル (IF名) を接続点そばに置く。辺の幅が足りないとラベル同士が密着する
    ことを実測で確認したため、片辺のエッジ数 × ラベル幅ぶんの幅を確保する。
    """
    in_deg: dict[str, int] = {}
    out_deg: dict[str, int] = {}
    for edge in graph.edges:
        if edge.src_label or edge.dst_label:
            out_deg[edge.src] = out_deg.get(edge.src, 0) + 1
            in_deg[edge.dst] = in_deg.get(edge.dst, 0) + 1
    widths: dict[str, int] = {}
    for node in graph.nodes:
        lanes = max(in_deg.get(node.id, 0), out_deg.get(node.id, 0))
        if lanes >= 2:
            widths[node.id] = max(170, 90 * lanes)
    return widths


def render_d2(graph: RenderGraph) -> str:
    lines: list[str] = []
    lines.append(f'title: |md\n  # {graph.title}\n| {{near: top-center}}')
    # WAN(クラウド)を上・LANを下に描く。エッジは graph 側で WAN側→LAN側 に
    # 向き付けされており、ELK がその向きをランクに使う (ADR-0005)
    lines.append("direction: down")
    lines.append("")
    lines.append(_NODE_CLASSES)

    node_path: dict[str, str] = {}  # node.id -> D2 参照パス
    min_widths = _min_widths(graph)
    dmap = domain_colors(graph)

    grouped: dict[str, list[RenderNode]] = {}
    ungrouped: list[RenderNode] = []
    for node in graph.nodes:
        if node.site is not None:
            grouped.setdefault(node.site, []).append(node)
        else:
            ungrouped.append(node)

    nodes_by_id = {n.id: n for n in graph.nodes}
    # セグメントに内包される端末は、拠点直下ではなくセグメントのサブコンテナに
    # 描くため、拠点の平坦なメンバー一覧からは除外する
    nested_device_ids = {dev_id for members in graph.segment_members.values()
                         for dev_id in members}

    for site_id, site_label in graph.groups:
        members = grouped.get(site_id, [])
        if not members:
            continue
        gkey = f"s_{_key(site_id)}"
        lines.append(f'{gkey}: "{_label(site_label)}" {{')
        lines.append("  class: group-site")
        # WAN線が上からコンテナに入るため、タイトルは線の通り道の外 (外側左上) に置く。
        # 内側配置や外側中央では狭い拠点でIFラベル・回線と衝突することを実測で確認済み
        lines.append("  label.near: outside-top-left")
        for node in members:
            if node.id in nested_device_ids:
                continue
            nkey = f"n_{_key(node.id)}"
            node_path[node.id] = f"{gkey}.{nkey}"
            if node.kind == "segment" and node.id in graph.segment_members:
                # 末端機器 (role: server で単一セグメント所属) を子として持つ
                # サブコンテナとして描く。GW側からの接続は今まで通り箱自体を指す
                lines.append(f'  {nkey}: "{_label(_node_label(node))}" {{')
                lines.append(f"    class: {_node_class(node)}")
                lines.append("    label.near: outside-top-left")
                for member_id in graph.segment_members[node.id]:
                    member = nodes_by_id.get(member_id)
                    if member is None:
                        continue
                    mkey = f"n_{_key(member_id)}"
                    node_path[member_id] = f"{gkey}.{nkey}.{mkey}"
                    lines.append(f'    {mkey}: "{_label(_node_label(member))}" '
                                f'{{{_node_attrs(member, min_widths.get(member_id))}}}')
                lines.append("  }")
            else:
                lines.append(f'  {nkey}: "{_label(_node_label(node))}" {{{_node_attrs(node, min_widths.get(node.id))}}}')
        lines.append("}")
        lines.append("")

    for node in ungrouped:
        nkey = f"n_{_key(node.id)}"
        node_path[node.id] = nkey
        lines.append(f'{nkey}: "{_label(_node_label(node))}" {{{_node_attrs(node, min_widths.get(node.id))}}}')
    if ungrouped:
        lines.append("")

    for i, edge in enumerate(graph.edges):
        src = node_path.get(edge.src)
        dst = node_path.get(edge.dst)
        if src is None or dst is None:
            continue
        attrs = [f"class: edge-{edge.type}"]
        if edge.src_label:
            attrs.append(f'source-arrowhead.label: "{_label(edge.src_label)}"')
        if edge.dst_label:
            attrs.append(f'target-arrowhead.label: "{_label(edge.dst_label)}"')
        if edge.domain and edge.emphasis is None:
            attrs.append(f'style.stroke: "{dmap[edge.domain]}"')
        attrs.extend(_EDGE_EMPHASIS_STYLES.get(edge.emphasis, []))

        if edge.type == "wan-circuit" and edge.label:
            # 回線ラベルはエッジ中央ラベルではなく透明枠ノードとして実体化する。
            # ELK はエッジラベルの領域を予約しないため隣接エッジのラベル同士が
            # 衝突しうるが、ノードにすればノード間隔が保証される (ADR-0005 補遺)
            lkey = f"lbl_{i}"
            lbl_attrs = ["class: edge-label"]
            if edge.emphasis == "dim":
                lbl_attrs.append("style.opacity: 0.15")
            elif edge.emphasis in ("disabled", "failed"):
                lbl_attrs.append("style.opacity: 0.5")
            elif edge.emphasis == "path":
                lbl_attrs.append('style.font-color: "#c5221f"')
                lbl_attrs.append("style.bold: true")
            lines.append(f'{lkey}: "{_label(edge.label)}" {{{"; ".join(lbl_attrs)}}}')
            tail = "->" if edge.directed else "--"
            joined = "; ".join(attrs)
            lines.append(f"{src} -- {lkey} {{{joined}}}")
            lines.append(f"{lkey} {tail} {dst} {{{joined}}}")
            continue

        # 色分けのみのD2/Mermaidでは、domainのエリア名をラベルとして残す
        # (面塗りを持つ内蔵SVGは凡例+領域で伝えるためラベル無し)
        label_text = edge.label
        if not label_text and edge.domain and not edge.continuation:
            label_text = graph.domains.get(edge.domain)
        label = f': "{_label(label_text)}"' if label_text else ""
        connector = "->" if edge.directed else "--"
        lines.append(f"{src} {connector} {dst}{label} {{{'; '.join(attrs)}}}")

    if graph.domains:
        lines.append("")
        lines.append('_legend: "凡例" {')
        lines.append("  near: bottom-center")
        lines.append('  style.fill: "#ffffff"; style.stroke: "#c3ccd6"')
        for i, dom in enumerate(sorted(graph.domains)):
            lines.append(f'  d{i}: "━━ {_label(graph.domains[dom])}" '
                         f'{{shape: text; style.font-color: "{dmap[dom]}"; '
                         f"style.bold: true}}")
        lines.append("}")

    return "\n".join(lines) + "\n"
