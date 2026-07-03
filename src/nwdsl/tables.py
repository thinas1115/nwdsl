"""設計書向け Markdown 表の生成。

すべての表はトポロジ定義から導出する。特に「接続先」「収容拠点」の列は
links から逆引きしており、図と表の不整合が構造的に起きないことの実証部分。
"""

from __future__ import annotations

from .model import Document, PHYSICAL_LINK_TYPES, parse_endpoint

_ROLE_LABELS = {
    "router": "ルーター",
    "l3switch": "L3スイッチ",
    "l2switch": "L2スイッチ",
    "firewall": "ファイアウォール",
    "loadbalancer": "ロードバランサ",
    "wlc": "無線LANコントローラ",
    "ap": "アクセスポイント",
    "server": "サーバー",
    "other": "その他",
}

_LINK_TYPE_LABELS = {
    "lan-cable": "構内配線",
    "wan-circuit": "WAN回線",
    "logical": "論理隣接",
    "tunnel": "トンネル",
}

_STATUS_LABELS = {"planned": "計画中", "active": "利用中", "decommissioned": "廃止"}


def _cell(value: object) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)


def _peer_map(doc: Document) -> dict[str, list[str]]:
    """'device:if' -> 接続先表示のリスト (物理linkのみ)。"""
    peers: dict[str, list[str]] = {}
    cloud_names = {c.id: c.name for c in doc.clouds}
    for link in doc.links:
        if link.type not in PHYSICAL_LINK_TYPES:
            continue
        a, b = link.endpoints
        for me, other in ((a, b), (b, a)):
            node, ifname = parse_endpoint(me)
            if ifname is None:
                continue
            other_node, other_if = parse_endpoint(other)
            if other_node in cloud_names:
                display = cloud_names[other_node]
            else:
                display = f"{other_node} {other_if}" if other_if else other_node
            peers.setdefault(me, []).append(display)
    return peers


def sites_table(doc: Document) -> str:
    dev_count = {s.id: 0 for s in doc.sites}
    for dev in doc.devices:
        dev_count[dev.site] = dev_count.get(dev.site, 0) + 1
    rows = [[s.id, s.name, s.location, dev_count.get(s.id, 0), s.description]
            for s in doc.sites]
    return _table(["拠点ID", "拠点名", "所在地", "機器数", "備考"], rows)


def devices_table(doc: Document) -> str:
    site_names = {s.id: s.name for s in doc.sites}
    rows = [[d.id, site_names.get(d.site, d.site), _ROLE_LABELS.get(d.role, d.role),
             d.platform, d.redundancy_group, d.mgmt_ipv4, d.description]
            for d in doc.devices]
    return _table(["機器ID", "拠点", "役割", "機種", "冗長グループ", "管理IP", "備考"], rows)


def interfaces_table(doc: Document) -> str:
    peers = _peer_map(doc)
    rows = []
    for dev in doc.devices:
        for intf in dev.interfaces:
            peer = " / ".join(peers.get(f"{dev.id}:{intf.name}", []))
            rows.append([dev.id, intf.name, intf.ipv4, intf.segment, peer, intf.description])
    return _table(["機器", "インターフェース", "IPv4", "セグメント", "接続先", "説明"], rows)


def circuits_table(doc: Document) -> str:
    site_names = {s.id: s.name for s in doc.sites}
    # 回線 -> 収容先 (wan-circuit link の機器側端点) を逆引き
    landing: dict[str, list[str]] = {}
    for link in doc.links:
        if link.type != "wan-circuit" or not link.circuit:
            continue
        for ep in link.endpoints:
            node, ifname = parse_endpoint(ep)
            dev = next((d for d in doc.devices if d.id == node), None)
            if dev is not None:
                site = site_names.get(dev.site, dev.site)
                landing.setdefault(link.circuit, []).append(
                    f"{site} {dev.id}" + (f" {ifname}" if ifname else ""))
    rows = [[c.id, c.provider, c.service, c.circuit_id, c.bandwidth,
             _STATUS_LABELS.get(c.status, c.status),
             " / ".join(landing.get(c.id, [])), c.description]
            for c in doc.circuits]
    return _table(["回線ID", "事業者", "サービス", "回線番号", "帯域", "状態", "収容先", "備考"], rows)


def links_table(doc: Document) -> str:
    rows = [[_LINK_TYPE_LABELS.get(l.type, l.type), l.endpoints[0], l.endpoints[1],
             l.circuit, l.description]
            for l in doc.links]
    return _table(["種別", "端点1", "端点2", "回線", "備考"], rows)


def segments_table(doc: Document) -> str:
    site_names = {s.id: s.name for s in doc.sites}
    # セグメントのGW候補: そのセグメントを参照するIF
    gw: dict[str, list[str]] = {}
    for dev in doc.devices:
        for intf in dev.interfaces:
            if intf.segment:
                gw.setdefault(intf.segment, []).append(
                    f"{dev.id} {intf.name}" + (f" ({intf.ipv4})" if intf.ipv4 else ""))
    rows = [[s.id, site_names.get(s.site, s.site), s.vlan, s.ipv4, s.name,
             " / ".join(gw.get(s.id, [])), s.description]
            for s in doc.segments]
    return _table(["セグメントID", "拠点", "VLAN", "ネットワーク", "名称", "ゲートウェイ", "備考"], rows)


_SECTIONS = [
    ("sites", "拠点一覧", sites_table),
    ("devices", "機器一覧", devices_table),
    ("interfaces", "インターフェース一覧", interfaces_table),
    ("circuits", "回線一覧", circuits_table),
    ("links", "接続一覧", links_table),
    ("segments", "セグメント一覧", segments_table),
]

SECTION_IDS = [s[0] for s in _SECTIONS]


def render_tables(doc: Document, sections: list[str] | None = None) -> str:
    """指定セクション (省略時は全部) の Markdown を返す。"""
    selected = sections or SECTION_IDS
    parts = [f"# {doc.network.name} 構成表"]
    if doc.network.description:
        parts.append(doc.network.description)
    for sec_id, title, fn in _SECTIONS:
        if sec_id in selected:
            parts.append(f"## {title}\n\n{fn(doc)}")
    return "\n\n".join(parts) + "\n"
