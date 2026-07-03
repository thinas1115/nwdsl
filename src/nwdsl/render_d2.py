"""RenderGraph を D2 ソースに変換する (プライマリ出力先)。

スタイルは機器ロール・接続種別から機械的に決める。DSL側は色・座標を持たない。
生成した .d2 は `d2 --layout=elk in.d2 out.svg` で描画する。
"""

from __future__ import annotations

import re

from .graph import RenderGraph, RenderNode

_NODE_CLASSES = """\
classes: {
  role-router: {style.fill: "#e8f0fe"; style.stroke: "#1a56b0"; style.font-color: "#1a2340"}
  role-l3switch: {style.fill: "#d2e3fc"; style.stroke: "#1a56b0"; style.font-color: "#1a2340"}
  role-l2switch: {style.fill: "#e6f4ea"; style.stroke: "#137333"; style.font-color: "#1a2e1f"}
  role-firewall: {style.fill: "#fce8e6"; style.stroke: "#c5221f"; style.font-color: "#3c1a19"}
  role-other: {style.fill: "#f1f3f4"; style.stroke: "#5f6368"; style.font-color: "#202124"}
  node-cloud: {shape: cloud; style.fill: "#f1f3f4"; style.stroke: "#5f6368"}
  node-site: {style.fill: "#fff8e1"; style.stroke: "#b58105"; style.font-color: "#4a3a08"}
  node-external: {style.fill: "#ffffff"; style.stroke: "#9aa0a6"; style.stroke-dash: 3}
  group-site: {style.fill: "#f7f9fc"; style.stroke: "#8fa8c4"; style.font-color: "#33475b"}
  edge-lan-cable: {style.stroke: "#4a4a4a"; style.stroke-width: 2}
  edge-wan-circuit: {style.stroke: "#1a73e8"; style.stroke-width: 4}
  edge-tunnel: {style.stroke: "#7b1fa2"; style.stroke-width: 2; style.stroke-dash: 5}
  edge-logical: {style.stroke: "#188038"; style.stroke-width: 2; style.stroke-dash: 3}
}
"""

_KNOWN_ROLES = {"router", "l3switch", "l2switch", "firewall"}


def _key(raw: str) -> str:
    """D2 のキーとして安全な識別子に変換する。"""
    return re.sub(r"[^0-9A-Za-z_]", "_", raw)


def _label(text: str) -> str:
    return text.replace('"', "'").replace("\n", "\\n")


def _node_label(node: RenderNode) -> str:
    # cloud 形状はCJKラベルの幅を詰めすぎて文字がはみ出すため余白を足す
    if node.kind == "cloud":
        return f"　{node.label}　"
    return node.label


def _node_class(node: RenderNode) -> str:
    if node.kind == "cloud":
        return "node-cloud"
    if node.kind == "site":
        return "node-site"
    if node.kind == "external-device":
        return "node-external"
    role = node.role if node.role in _KNOWN_ROLES else "other"
    return f"role-{role}"


def render_d2(graph: RenderGraph) -> str:
    lines: list[str] = []
    lines.append(f'title: |md\n  # {graph.title}\n| {{near: top-center}}')
    lines.append("direction: right")
    lines.append("")
    lines.append(_NODE_CLASSES)

    node_path: dict[str, str] = {}  # node.id -> D2 参照パス

    grouped: dict[str, list[RenderNode]] = {}
    ungrouped: list[RenderNode] = []
    for node in graph.nodes:
        if node.site is not None:
            grouped.setdefault(node.site, []).append(node)
        else:
            ungrouped.append(node)

    for site_id, site_label in graph.groups:
        members = grouped.get(site_id, [])
        if not members:
            continue
        gkey = f"s_{_key(site_id)}"
        lines.append(f'{gkey}: "{_label(site_label)}" {{')
        lines.append("  class: group-site")
        for node in members:
            nkey = f"n_{_key(node.id)}"
            node_path[node.id] = f"{gkey}.{nkey}"
            lines.append(f'  {nkey}: "{_label(_node_label(node))}" {{class: {_node_class(node)}}}')
        lines.append("}")
        lines.append("")

    for node in ungrouped:
        nkey = f"n_{_key(node.id)}"
        node_path[node.id] = nkey
        lines.append(f'{nkey}: "{_label(_node_label(node))}" {{class: {_node_class(node)}}}')
    if ungrouped:
        lines.append("")

    for edge in graph.edges:
        src = node_path.get(edge.src)
        dst = node_path.get(edge.dst)
        if src is None or dst is None:
            continue
        label = f': "{_label(edge.label)}"' if edge.label else ""
        attrs = [f"class: edge-{edge.type}"]
        if edge.src_label:
            attrs.append(f'source-arrowhead.label: "{_label(edge.src_label)}"')
        if edge.dst_label:
            attrs.append(f'target-arrowhead.label: "{_label(edge.dst_label)}"')
        lines.append(f"{src} -- {dst}{label} {{{'; '.join(attrs)}}}")

    return "\n".join(lines) + "\n"
