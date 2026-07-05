"""RenderGraph を Mermaid flowchart に変換する (セカンダリ出力先)。

GitHub / Obsidian がネイティブ描画できることが利点。レイアウト品質は
D2 に劣るため、設計書に埋め込む簡易図・レビュー用途を想定する。
"""

from __future__ import annotations

import re

from .graph import RenderGraph, RenderNode, domain_colors

_EDGE_STYLES = {
    "lan-cable": "stroke:#4a4a4a,stroke-width:2px",
    "wan-circuit": "stroke:#1a73e8,stroke-width:4px",
    "tunnel": "stroke:#7b1fa2,stroke-width:2px,stroke-dasharray:6 4",
    "logical": "stroke:#188038,stroke-width:2px,stroke-dasharray:3 3",
    "segment": "stroke:#0f766e,stroke-width:1.5px",
}

_EDGE_EMPHASIS_STYLES = {
    "path": "stroke:#c5221f,stroke-width:4px",
    "disabled": "stroke:#9aa0a6,stroke-width:2px,stroke-dasharray:4 4",
    "dim": "stroke:#e8eaed,stroke-width:1px",
    "failed": "stroke:#c5221f,stroke-width:2px,stroke-dasharray:4 4",
}

_CLASS_DEFS = """\
classDef node_dim fill:#f8f9fa,stroke:#dadce0,color:#bdc1c6
classDef node_failed fill:#fce8e6,stroke:#c5221f,color:#3c1a19
classDef role_router fill:#e8f0fe,stroke:#1a56b0,color:#1a2340
classDef role_l3switch fill:#d2e3fc,stroke:#1a56b0,color:#1a2340
classDef role_l2switch fill:#e6f4ea,stroke:#137333,color:#1a2e1f
classDef role_firewall fill:#fce8e6,stroke:#c5221f,color:#3c1a19
classDef role_other fill:#f1f3f4,stroke:#5f6368,color:#202124
classDef node_cloud fill:#f1f3f4,stroke:#5f6368,color:#202124
classDef node_site fill:#fff8e1,stroke:#b58105,color:#4a3a08
classDef node_segment fill:#e2f5f0,stroke:#0f766e,color:#0b3d38
classDef node_external fill:#ffffff,stroke:#9aa0a6,stroke-dasharray:3 3,color:#5f6368"""

_KNOWN_ROLES = {"router", "l3switch", "l2switch", "firewall"}


def _key(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", raw)


def _label(text: str) -> str:
    return text.replace('"', "#quot;").replace("\n", "<br>")


def _node_class(node: RenderNode) -> str:
    if node.emphasis == "dim":
        return "node_dim"
    if node.emphasis == "failed":
        return "node_failed"
    if node.kind == "cloud":
        return "node_cloud"
    if node.kind == "segment":
        return "node_segment"
    if node.kind == "site":
        return "node_site"
    if node.kind == "external-device":
        return "node_external"
    role = node.role if node.role in _KNOWN_ROLES else "other"
    return f"role_{role}"


def _node_decl(node: RenderNode) -> str:
    key = _key(node.id)
    raw = f"✕障害\n{node.label}" if node.emphasis == "failed" else node.label
    label = _label(raw)
    if node.kind == "cloud":
        return f'{key}(("{label}"))'
    if node.kind == "segment":
        return f'{key}(["{label}"])'
    return f'{key}["{label}"]'


def render_mermaid(graph: RenderGraph) -> str:
    lines: list[str] = ["flowchart TB"]

    grouped: dict[str, list[RenderNode]] = {}
    ungrouped: list[RenderNode] = []
    for node in graph.nodes:
        (grouped.setdefault(node.site, []) if node.site else ungrouped).append(node)

    for site_id, site_label in graph.groups:
        members = grouped.get(site_id, [])
        if not members:
            continue
        lines.append(f'  subgraph sg_{_key(site_id)}["{_label(site_label)}"]')
        for node in members:
            lines.append(f"    {_node_decl(node)}")
        lines.append("  end")

    for node in ungrouped:
        lines.append(f"  {_node_decl(node)}")

    class_members: dict[str, list[str]] = {}
    for node in graph.nodes:
        class_members.setdefault(_node_class(node), []).append(_key(node.id))

    dmap = domain_colors(graph)
    edge_indices: dict[str, list[int]] = {}
    emphasis_indices: dict[str, list[int]] = {}
    domain_indices: dict[str, list[int]] = {}
    for i, edge in enumerate(graph.edges):
        label_text = edge.label
        if not label_text and edge.domain and not edge.continuation:
            label_text = graph.domains.get(edge.domain)
        label = f'|"{_label(label_text)}"|' if label_text else ""
        connector = "-->" if edge.directed else "---"
        lines.append(f"  {_key(edge.src)} {connector}{label} {_key(edge.dst)}")
        if edge.emphasis is not None:
            emphasis_indices.setdefault(edge.emphasis, []).append(i)
        elif edge.domain is not None:
            domain_indices.setdefault(edge.domain, []).append(i)
        else:
            edge_indices.setdefault(edge.type, []).append(i)

    if graph.domains:  # 凡例 (ドメイン=色の対応)
        lines.append('  subgraph legend["凡例"]')
        for k, dom in enumerate(sorted(graph.domains)):
            lines.append(f'    lg{k}(["{_label(graph.domains[dom])}"])')
        lines.append("  end")

    lines.append("")
    lines.extend(f"  {line}" for line in _CLASS_DEFS.splitlines())
    for cls, members in class_members.items():
        lines.append(f"  class {','.join(members)} {cls}")
    for etype, idxs in edge_indices.items():
        lines.append(f"  linkStyle {','.join(map(str, idxs))} {_EDGE_STYLES[etype]}")
    for emphasis, idxs in emphasis_indices.items():
        lines.append(f"  linkStyle {','.join(map(str, idxs))} {_EDGE_EMPHASIS_STYLES[emphasis]}")
    for k, dom in enumerate(sorted(graph.domains)):
        color = dmap[dom]
        if dom in domain_indices:
            lines.append(f"  linkStyle {','.join(map(str, domain_indices[dom]))} "
                         f"stroke:{color},stroke-width:2px,stroke-dasharray:3 3")
        lines.append(f"  classDef dom{k} fill:#ffffff,stroke:{color},color:{color}")
        lines.append(f"  class lg{k} dom{k}")

    return "\n".join(lines) + "\n"
