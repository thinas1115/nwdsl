"""自前SVGレンダラ (ADR-0008)。svg_layout の座標をそのまま描くだけの薄い層。

配色・線種の意味論は render_d2 と同一。D2バイナリ不要でSVGまで到達できる。
"""

from __future__ import annotations

from .graph import RenderEdge, RenderGraph, RenderNode
from .svg_layout import Placed, RoutedEdge, layout_view, text_w

_ROLE_FILL = {
    "router": ("#e8f0fe", "#1a56b0"), "l3switch": ("#d2e3fc", "#1a56b0"),
    "l2switch": ("#e6f4ea", "#137333"), "firewall": ("#fce8e6", "#c5221f"),
}
_EDGE_STYLE = {
    "lan-cable": ("#4a4a4a", 2.0, None),
    "wan-circuit": ("#1a73e8", 3.5, None),
    "tunnel": ("#7b1fa2", 2.0, "7 4"),
    "logical": ("#188038", 2.0, "3 3"),
}


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _edge_attrs(edge: RenderEdge) -> tuple[str, float, str | None, float, bool]:
    """(色, 太さ, dasharray, opacity, animated)"""
    color, width, dash = _EDGE_STYLE.get(edge.type, ("#4a4a4a", 2.0, None))
    opacity, animated = 1.0, False
    if edge.emphasis == "path":
        color, width, dash, animated = "#c5221f", 4.0, "10 6", True
    elif edge.emphasis == "disabled":
        color, width, dash, opacity = "#9aa0a6", 2.0, "5 5", 0.55
    elif edge.emphasis == "failed":
        color, dash, opacity = "#c5221f", "5 4", 0.55
    elif edge.emphasis == "dim":
        opacity = 0.15
    return color, width, dash, opacity, animated


def _node_svg(p: Placed) -> list[str]:
    n: RenderNode = p.node
    parts: list[str] = []
    opacity = ' opacity="0.3"' if n.emphasis == "dim" else ""
    label = n.label
    if n.kind == "cloud":
        fill, stroke, sw = "#f1f3f4", "#5f6368", 1.6
        if n.emphasis == "failed":
            fill, stroke, sw, label = "#fce8e6", "#c5221f", 3, f"✕障害\n{label}"
        parts.append(
            f'<ellipse cx="{p.cx:.1f}" cy="{p.y + p.h / 2:.1f}" rx="{p.w / 2:.1f}" '
            f'ry="{p.h / 2:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{opacity}/>')
    else:
        if n.emphasis == "failed":
            fill, stroke, sw = "#fce8e6", "#c5221f", 3.0
            label = f"✕障害\n{label}"
        elif n.kind == "site":
            fill, stroke, sw = "#fff8e1", "#b58105", 1.4
        elif n.kind == "external-device":
            fill, stroke, sw = "#ffffff", "#9aa0a6", 1.4
        else:
            fill, stroke = _ROLE_FILL.get(n.role or "", ("#f1f3f4", "#5f6368"))
            sw = 1.4
        dash = ' stroke-dasharray="4 3"' if n.kind == "external-device" else ""
        parts.append(
            f'<rect x="{p.x:.1f}" y="{p.y:.1f}" width="{p.w:.1f}" height="{p.h:.1f}" '
            f'rx="4" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}{opacity}/>')
    lines = label.split("\n")
    total = len(lines)
    y0 = p.y + p.h / 2 - (total - 1) * 8
    for i, line in enumerate(lines):
        weight = "600" if i == 0 else "400"
        parts.append(
            f'<text x="{p.cx:.1f}" y="{y0 + i * 16:.1f}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="12.5" font-weight="{weight}" '
            f'fill="#1e293b"{opacity}>{_esc(line)}</text>')
    return parts


def _edge_svg(r: RoutedEdge, marker_ids: set[str]) -> list[str]:
    color, width, dash, opacity, animated = _edge_attrs(r.edge)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in r.points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    marker = ""
    if r.edge.directed:
        mid = f"arrow-{color.lstrip('#')}"
        marker_ids.add(mid)
        marker = f' marker-end="url(#{mid})"'
    anim = ('<animate attributeName="stroke-dashoffset" from="32" to="0" '
            'dur="1.2s" repeatCount="indefinite"/>') if animated else ""
    parts = [f'<polyline points="{pts}" fill="none" stroke="{color}" '
             f'stroke-width="{width}" opacity="{opacity}"{dash_attr}{marker}>{anim}</polyline>']
    for plabel, above in ((r.src_port_label, False), (r.dst_port_label, True)):
        if plabel:
            x, y, text = plabel
            dy = -5 if above else 13
            parts.append(
                f'<text x="{x + 4:.1f}" y="{y + dy:.1f}" font-size="10.5" '
                f'font-style="italic" fill="#5f6368" opacity="{opacity}">{_esc(text)}</text>')
    if r.label_box and r.edge.label:
        x, y, w, h = r.label_box
        lines = r.edge.label.split("\n")
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                     f'rx="4" fill="#ffffff" fill-opacity="0.92" opacity="{opacity}"/>')
        for i, line in enumerate(lines):
            bold = "600" if r.edge.emphasis == "path" else "400"
            fill = "#c5221f" if r.edge.emphasis == "path" else "#5f6368"
            parts.append(
                f'<text x="{x + w / 2:.1f}" y="{y + 13 + i * 17:.1f}" text-anchor="middle" '
                f'font-size="12" font-style="italic" font-weight="{bold}" fill="{fill}" '
                f'opacity="{opacity}">{_esc(line)}</text>')
    return parts


def render_svg(graph: RenderGraph) -> str:
    layout = layout_view(graph)
    w, h = layout.width, layout.height
    parts: list[str] = []
    parts.append(f'<text x="24" y="30" font-size="19" font-weight="700" '
                 f'fill="#1e293b">{_esc(layout.title)}</text>')
    for box in layout.site_boxes:
        parts.append(
            f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="{box.w:.1f}" '
            f'height="{box.h:.1f}" rx="6" fill="#f7f9fc" stroke="#8fa8c4"/>')
        parts.append(
            f'<text x="{box.x + 4:.1f}" y="{box.y - 8:.1f}" font-size="14.5" '
            f'font-weight="600" fill="#33475b">{_esc(box.label)}</text>')
    marker_ids: set[str] = set()
    edge_parts: list[str] = []
    for r in sorted(layout.routed, key=lambda r: 1 if r.edge.emphasis == "path" else 0):
        edge_parts.extend(_edge_svg(r, marker_ids))
    parts.extend(edge_parts)
    for p in layout.placed.values():
        parts.extend(_node_svg(p))
    markers = "".join(
        f'<marker id="arrow-{c}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="#{c}"/></marker>'
        for c in sorted(m.removeprefix("arrow-") for m in marker_ids))
    font = "'Segoe UI','Hiragino Sans','Noto Sans JP',Meiryo,sans-serif"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.0f} {h:.0f}" font-family="{font}">'
            f'<defs>{markers}</defs>'
            f'<rect width="100%" height="100%" fill="#ffffff"/>'
            + "".join(parts) + "</svg>")
