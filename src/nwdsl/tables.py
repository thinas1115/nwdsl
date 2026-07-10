"""設計書向け Markdown 表の生成。

すべての表はトポロジ定義から導出する。特に「接続先」「収容拠点」の列は
links から逆引きしており、図と表の不整合が構造的に起きないことの実証部分。
"""

from __future__ import annotations

import ipaddress

from .model import (Document, PHYSICAL_LINK_TYPES, domain_display_name,
                    parse_endpoint)

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


_KIND_LABELS = {"fhrp": "FHRP", "stack": "スタック"}
_MEMBER_ROLE_LABELS = {"active": "active", "standby": "standby"}


def _redundancy_by_device(doc: Document) -> dict[str, list[str]]:
    """機器ID -> 所属冗長グループの表示 (グループID + 役割) の逆引き。"""
    result: dict[str, list[str]] = {}
    for grp in doc.redundancy_groups:
        for m in grp.members:
            display = grp.id + (f" ({m.role})" if m.role else "")
            result.setdefault(m.device, []).append(display)
    return result


def devices_table(doc: Document) -> str:
    site_names = {s.id: s.name for s in doc.sites}
    red = _redundancy_by_device(doc)
    rows = [[d.id, site_names.get(d.site, d.site), _ROLE_LABELS.get(d.role, d.role),
             d.platform, " / ".join(red.get(d.id, [])), d.mgmt_ipv4, d.description]
            for d in doc.devices]
    return _table(["機器ID", "拠点", "役割", "機種", "冗長グループ", "管理IP", "備考"], rows)


def redundancy_table(doc: Document) -> str:
    rows = []
    for g in doc.redundancy_groups:
        members = " / ".join(
            m.device + (f" ({_MEMBER_ROLE_LABELS.get(m.role, m.role)})" if m.role else "")
            for m in g.members)
        rows.append([g.id, _KIND_LABELS.get(g.kind, g.kind),
                     g.protocol.upper() if g.protocol else None,
                     g.group, g.vip, members, g.description])
    return _table(["グループID", "種別", "プロトコル", "グループ番号", "VIP", "メンバー", "備考"], rows)


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
    domain_names = {d.id: domain_display_name(d) for d in doc.domains}
    rows = [[_LINK_TYPE_LABELS.get(l.type, l.type), l.endpoints[0], l.endpoints[1],
             l.circuit, domain_names.get(l.domain, l.domain), l.description]
            for l in doc.links]
    return _table(["種別", "端点1", "端点2", "回線", "ドメイン", "備考"], rows)


def segments_table(doc: Document) -> str:
    site_names = {s.id: s.name for s in doc.sites}
    # セグメントのGW候補: そのセグメントを参照するIF
    gw: dict[str, list[str]] = {}
    for dev in doc.devices:
        for intf in dev.interfaces:
            if intf.segment:
                gw.setdefault(intf.segment, []).append(
                    f"{dev.id} {intf.name}" + (f" ({intf.ipv4})" if intf.ipv4 else ""))
    # FHRPのVIPはCIDR包含で所属セグメントを導出し、GW列の先頭に出す (ADR-0010)
    for grp in doc.redundancy_groups:
        if not grp.vip:
            continue
        vip = ipaddress.ip_address(grp.vip)
        for seg in doc.segments:
            if seg.ipv4 and vip in ipaddress.ip_network(seg.ipv4):
                gw.setdefault(seg.id, []).insert(0, f"VIP {grp.vip} ({grp.id})")
                break
    rows = [[s.id, site_names.get(s.site, s.site), s.vlan, s.ipv4, s.name,
             " / ".join(gw.get(s.id, [])), s.description]
            for s in doc.segments]
    return _table(["セグメントID", "拠点", "VLAN", "ネットワーク", "名称", "ゲートウェイ", "備考"], rows)


def routing_table(doc: Document) -> str:
    """ドメイン一覧と再配布一覧 (ADR-0011)。"""
    link_count: dict[str, int] = {}
    for link in doc.links:
        if link.domain:
            link_count[link.domain] = link_count.get(link.domain, 0) + 1
    dom_rows = [[d.id, domain_display_name(d),
                 d.protocol.upper() if d.protocol else None,
                 d.area if d.area is not None else d.asn,
                 link_count.get(d.id, 0), d.description]
                for d in doc.domains]
    parts = ["### ドメイン\n\n" + _table(
        ["ドメインID", "表示名", "プロトコル", "エリア/AS", "所属接続数", "備考"], dom_rows)]
    if doc.redistributions:
        dom_disp = {d.id: domain_display_name(d) for d in doc.domains}
        red_rows = [[dom_disp.get(r.from_, r.from_), dom_disp.get(r.to, r.to),
                     "相互" if r.mutual else "一方向",
                     " / ".join(r.devices), r.description]
                    for r in doc.redistributions]
        parts.append("### 再配布\n\n" + _table(
            ["再配布元", "再配布先", "方向", "実施機器", "備考"], red_rows))
    return "\n\n".join(parts)


_SECTIONS = [
    ("sites", "拠点一覧", sites_table),
    ("devices", "機器一覧", devices_table),
    ("redundancy", "冗長グループ一覧", redundancy_table),
    ("interfaces", "インターフェース一覧", interfaces_table),
    ("circuits", "回線一覧", circuits_table),
    ("links", "接続一覧", links_table),
    ("segments", "セグメント一覧", segments_table),
    ("routing", "ルーティング一覧", routing_table),
]

SECTION_IDS = [s[0] for s in _SECTIONS]

# データが無ければ既定出力から省くセクション (明示指定時は空でも出す)
_OPTIONAL_SECTIONS = {
    "redundancy": lambda doc: bool(doc.redundancy_groups),
    "routing": lambda doc: bool(doc.domains or doc.redistributions),
}


def render_tables(doc: Document, sections: list[str] | None = None) -> str:
    """指定セクション (省略時は全部) の Markdown を返す。"""
    selected = sections or SECTION_IDS
    explicit = sections is not None
    parts = [f"# {doc.network.name} 構成表"]
    if doc.network.description:
        parts.append(doc.network.description)
    for sec_id, title, fn in _SECTIONS:
        if sec_id not in selected:
            continue
        has_data = _OPTIONAL_SECTIONS.get(sec_id, lambda _: True)(doc)
        if not has_data and not explicit:
            continue
        parts.append(f"## {title}\n\n{fn(doc)}")
    return "\n\n".join(parts) + "\n"
