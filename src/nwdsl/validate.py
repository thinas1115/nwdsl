"""意味的整合性の検査。

構文 (型・必須フィールド) は model.py の pydantic が保証するため、
ここでは ID 参照の整合性と link type ごとの制約を検査する。
検査結果は Issue のリストで返し、error が1件でもあれば不合格。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from .model import Document, Link, PHYSICAL_LINK_TYPES, parse_endpoint


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    code: str
    message: str

    def __str__(self) -> str:
        mark = "ERROR" if self.level == "error" else "WARN "
        return f"[{mark}] {self.code}: {self.message}"


def _link_label(index: int, link: Link) -> str:
    name = link.id or f"links[{index}]"
    return f"{name} ({link.endpoints[0]} -- {link.endpoints[1]})"


def _check_duplicates(issues: list[Issue], ids: list[str], kind: str) -> None:
    for dup, n in Counter(ids).items():
        if n > 1:
            issues.append(Issue("error", "dup.id", f"{kind} の id '{dup}' が{n}回定義されています"))


def validate_document(doc: Document) -> list[Issue]:
    issues: list[Issue] = []

    site_ids = {s.id for s in doc.sites}
    device_by_id = {d.id: d for d in doc.devices}
    cloud_ids = {c.id for c in doc.clouds}
    circuit_by_id = {c.id: c for c in doc.circuits}
    segment_ids = {s.id for s in doc.segments}

    # ---- ID 重複 ----
    _check_duplicates(issues, [s.id for s in doc.sites], "sites")
    _check_duplicates(issues, [c.id for c in doc.circuits], "circuits")
    _check_duplicates(issues, [s.id for s in doc.segments], "segments")
    _check_duplicates(issues, [v.id for v in doc.views], "views")
    # devices と clouds は link 端点の名前空間を共有するため、まとめて一意
    _check_duplicates(issues, [d.id for d in doc.devices] + [c.id for c in doc.clouds],
                      "devices/clouds")
    link_ids = [l.id for l in doc.links if l.id is not None]
    _check_duplicates(issues, link_ids, "links")

    # ---- devices ----
    for dev in doc.devices:
        if dev.site not in site_ids:
            issues.append(Issue("error", "ref.site",
                                f"device '{dev.id}' の site '{dev.site}' が sites に存在しません"))
        for name, n in Counter(i.name for i in dev.interfaces).items():
            if n > 1:
                issues.append(Issue("error", "dup.interface",
                                    f"device '{dev.id}' の interface '{name}' が{n}回定義されています"))
        for intf in dev.interfaces:
            if intf.segment is not None and intf.segment not in segment_ids:
                issues.append(Issue("error", "ref.segment",
                                    f"device '{dev.id}' interface '{intf.name}' の segment "
                                    f"'{intf.segment}' が segments に存在しません"))

    # ---- segments ----
    for seg in doc.segments:
        if seg.site not in site_ids:
            issues.append(Issue("error", "ref.site",
                                f"segment '{seg.id}' の site '{seg.site}' が sites に存在しません"))

    # ---- links ----
    used_ports: Counter[str] = Counter()  # 物理linkでのIF使用回数
    used_circuits: Counter[str] = Counter()

    for i, link in enumerate(doc.links):
        label = _link_label(i, link)
        endpoint_sites: list[str] = []
        endpoint_kinds: list[str] = []  # "interface" | "device" | "cloud"

        for ep in link.endpoints:
            node, ifname = parse_endpoint(ep)
            if node in device_by_id:
                dev = device_by_id[node]
                endpoint_sites.append(dev.site)
                if ifname is not None:
                    endpoint_kinds.append("interface")
                    if ifname not in {x.name for x in dev.interfaces}:
                        issues.append(Issue("error", "ref.interface",
                                            f"link {label}: device '{node}' に interface "
                                            f"'{ifname}' が宣言されていません"))
                else:
                    endpoint_kinds.append("device")
            elif node in cloud_ids:
                endpoint_kinds.append("cloud")
                if ifname is not None:
                    issues.append(Issue("error", "endpoint.cloud-interface",
                                        f"link {label}: cloud '{node}' にインターフェース指定はできません"))
            else:
                endpoint_kinds.append("unknown")
                issues.append(Issue("error", "ref.endpoint",
                                    f"link {label}: 端点 '{node}' が devices/clouds に存在しません"))

        # --- type 別の制約 ---
        if link.type == "lan-cable":
            if link.circuit is not None:
                issues.append(Issue("error", "link.circuit-forbidden",
                                    f"link {label}: lan-cable に circuit は指定できません"))
            if "cloud" in endpoint_kinds:
                issues.append(Issue("error", "link.lan-endpoint",
                                    f"link {label}: lan-cable の端点に cloud は指定できません"))
            elif "device" in endpoint_kinds:
                issues.append(Issue("error", "link.lan-endpoint",
                                    f"link {label}: lan-cable の端点は 'device:interface' 形式で指定してください"))
            elif len(set(endpoint_sites)) > 1:
                issues.append(Issue("error", "link.lan-cross-site",
                                    f"link {label}: lan-cable が異なる拠点をまたいでいます "
                                    f"({' / '.join(endpoint_sites)})。拠点間は wan-circuit 等を使用してください"))

        elif link.type == "wan-circuit":
            if link.circuit is None:
                issues.append(Issue("error", "link.circuit-required",
                                    f"link {label}: wan-circuit には circuit (回線契約ID) が必須です"))
            elif link.circuit not in circuit_by_id:
                issues.append(Issue("error", "ref.circuit",
                                    f"link {label}: circuit '{link.circuit}' が circuits に存在しません"))
            else:
                used_circuits[link.circuit] += 1
                if circuit_by_id[link.circuit].status == "decommissioned":
                    issues.append(Issue("warning", "circuit.decommissioned",
                                        f"link {label}: 廃止済み回線 '{link.circuit}' を参照しています"))
            if "device" in endpoint_kinds:
                issues.append(Issue("error", "link.wan-endpoint",
                                    f"link {label}: wan-circuit の機器側端点は 'device:interface' 形式で指定してください"))
            if endpoint_kinds.count("cloud") == 0 and len(set(endpoint_sites)) == 1 and "unknown" not in endpoint_kinds:
                issues.append(Issue("error", "link.wan-same-site",
                                    f"link {label}: wan-circuit の両端が同一拠点です。構内配線は lan-cable を使用してください"))
            if endpoint_kinds.count("cloud") == 2:
                issues.append(Issue("error", "link.wan-endpoint",
                                    f"link {label}: wan-circuit の両端を cloud にはできません"))

        else:  # logical / tunnel
            if link.circuit is not None:
                issues.append(Issue("error", "link.circuit-forbidden",
                                    f"link {label}: {link.type} に circuit は指定できません "
                                    f"(回線はアクセス回線側の wan-circuit link で表現します)"))
            if "cloud" in endpoint_kinds:
                issues.append(Issue("error", "link.overlay-endpoint",
                                    f"link {label}: {link.type} の端点に cloud は指定できません"))

        if link.via is not None:
            if link.type not in ("logical", "tunnel"):
                issues.append(Issue("error", "link.via-forbidden",
                                    f"link {label}: via は logical/tunnel でのみ指定できます"))
            elif link.via not in cloud_ids:
                issues.append(Issue("error", "ref.via",
                                    f"link {label}: via '{link.via}' が clouds に存在しません"))

        # --- 物理ポートの二重使用 ---
        if link.type in PHYSICAL_LINK_TYPES:
            for ep in link.endpoints:
                node, ifname = parse_endpoint(ep)
                if node in device_by_id and ifname is not None:
                    used_ports[ep] += 1

    for port, n in used_ports.items():
        if n > 1:
            issues.append(Issue("error", "link.port-reuse",
                                f"物理ポート '{port}' が{n}本の物理接続 (lan-cable/wan-circuit) で使用されています"))

    # ---- circuits の使用状況 ----
    for cct in doc.circuits:
        n = used_circuits.get(cct.id, 0)
        if n == 0 and cct.status == "active":
            issues.append(Issue("warning", "circuit.unused",
                                f"circuit '{cct.id}' はどの link からも参照されていません"))
        elif n > 1:
            issues.append(Issue("error", "circuit.multi-use",
                                f"circuit '{cct.id}' が{n}本の link から参照されています "
                                f"(1契約=1結線。複数回線は circuits を分けてください)"))

    # ---- domains ----
    _check_duplicates(issues, [d.id for d in doc.domains], "domains")
    domain_ids = {d.id for d in doc.domains}
    for i, link in enumerate(doc.links):
        if link.domain is not None and link.domain not in domain_ids:
            issues.append(Issue("error", "ref.domain",
                                f"link {_link_label(i, link)}: domain '{link.domain}' が "
                                f"domains に存在しません"))

    # ---- paths ----
    _check_duplicates(issues, [p.id for p in doc.paths], "paths")
    path_ids = {p.id for p in doc.paths}
    node_ids = set(device_by_id) | cloud_ids
    # 隣接判定用: 全link (全type) のノードペア
    adjacent: set[frozenset[str]] = set()
    for link in doc.links:
        a, _ = parse_endpoint(link.endpoints[0])
        b, _ = parse_endpoint(link.endpoints[1])
        adjacent.add(frozenset((a, b)))

    for path in doc.paths:
        for hop in path.hops:
            if hop.node not in node_ids:
                issues.append(Issue("error", "ref.path-node",
                                    f"path '{path.id}' のホップ '{hop.node}' が devices/clouds に存在しません"))
        for prev, nxt in zip(path.hops, path.hops[1:]):
            pair = frozenset((prev.node, nxt.node))
            if prev.node == nxt.node:
                issues.append(Issue("error", "path.hop-duplicate",
                                    f"path '{path.id}': 連続ホップが同一ノードです ({prev.node})"))
            elif prev.node in node_ids and nxt.node in node_ids and pair not in adjacent:
                issues.append(Issue("error", "path.hop-not-adjacent",
                                    f"path '{path.id}': '{prev.node}' と '{nxt.node}' を直接結ぶ link がありません"))
        for comp in path.failure:
            if comp not in node_ids and comp not in circuit_by_id:
                issues.append(Issue("error", "ref.path-failure",
                                    f"path '{path.id}' の failure '{comp}' が devices/clouds/circuits に存在しません"))
        if path.fallback_of is not None:
            if path.fallback_of not in path_ids:
                issues.append(Issue("error", "ref.path-fallback",
                                    f"path '{path.id}' の fallback_of '{path.fallback_of}' が paths に存在しません"))
            elif path.fallback_of == path.id:
                issues.append(Issue("error", "ref.path-fallback",
                                    f"path '{path.id}' の fallback_of が自分自身を指しています"))

    # ---- views ----
    for view in doc.views:
        for attr in ("include_sites", "exclude_sites"):
            targets = getattr(view, attr) or []
            for sid in targets:
                if sid not in site_ids:
                    issues.append(Issue("error", "ref.view-site",
                                        f"view '{view.id}' の {attr} '{sid}' が sites に存在しません"))
        if view.type == "path":
            if view.path is None:
                issues.append(Issue("error", "view.path-required",
                                    f"view '{view.id}': type: path には path (経路ID) が必須です"))
            elif view.path not in path_ids:
                issues.append(Issue("error", "ref.view-path",
                                    f"view '{view.id}' の path '{view.path}' が paths に存在しません"))
        elif view.path is not None:
            issues.append(Issue("error", "view.path-forbidden",
                                f"view '{view.id}': path は type: path のビューでのみ指定できます"))

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
