"""nwdsl スキーマ定義 (pydantic モデル)。

このモジュールが DSL の構文レベルの唯一の定義。JSON Schema は
`Document.model_json_schema()` から生成する。参照整合性などの
意味的検査は validate.py が担う。
"""

from __future__ import annotations

import ipaddress
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

LinkType = Literal["lan-cable", "wan-circuit", "logical", "tunnel"]
DeviceRole = Literal[
    "router", "l3switch", "l2switch", "firewall", "loadbalancer",
    "wlc", "ap", "server", "other",
]
CloudKind = Literal["wan", "internet", "other"]
CircuitStatus = Literal["planned", "active", "decommissioned"]
RedundancyKind = Literal["fhrp", "stack"]
FhrpProtocol = Literal["hsrp", "vrrp", "glbp", "other"]
MemberRole = Literal["active", "standby"]
DomainProtocol = Literal["ospf", "bgp", "eigrp", "rip", "static", "other"]
LinkDirection = Literal["forward", "both"]

SUPPORTED_VERSIONS = ("0.1", "0.2")

PHYSICAL_LINK_TYPES: tuple[str, ...] = ("lan-cable", "wan-circuit")


def _check_cidr(value: str, field: str) -> str:
    try:
        ipaddress.ip_interface(value)
    except ValueError as exc:
        raise ValueError(f"{field} はCIDR形式 (例: 10.0.0.1/24) で指定してください: {value}") from exc
    return value


class StrictModel(BaseModel):
    """未知フィールドをエラーにする共通基底。タイポの黙殺を防ぐ。"""

    model_config = ConfigDict(extra="forbid")


class NetworkMeta(StrictModel):
    name: str = Field(description="ネットワーク(案件)名")
    description: Optional[str] = Field(default=None, description="説明")


class Site(StrictModel):
    id: str = Field(description="拠点ID (ファイル内で一意)")
    name: str = Field(description="拠点名")
    location: Optional[str] = Field(default=None, description="所在地")
    description: Optional[str] = Field(default=None, description="補足")


class Interface(StrictModel):
    name: str = Field(description="インターフェース名 (機器内で一意。例: Gi0/0/1, eth0, Tunnel0)")
    description: Optional[str] = Field(default=None, description="用途説明")
    ipv4: Optional[str] = Field(default=None, description="IPv4アドレス (CIDR形式)")
    segment: Optional[str] = Field(default=None, description="所属セグメントID (segments を参照)")

    @field_validator("ipv4")
    @classmethod
    def _ipv4_cidr(cls, v: Optional[str]) -> Optional[str]:
        return _check_cidr(v, "interface.ipv4") if v is not None else None


class Device(StrictModel):
    id: str = Field(description="機器ID (clouds と合わせて一意)")
    site: str = Field(description="設置拠点ID (sites を参照)")
    role: DeviceRole = Field(default="other", description="機器の役割 (図の配色・表の分類に使用)")
    platform: Optional[str] = Field(default=None, description="機種・型番")
    mgmt_ipv4: Optional[str] = Field(default=None, description="管理IPアドレス (CIDR形式)")
    description: Optional[str] = Field(default=None, description="補足")
    interfaces: list[Interface] = Field(default_factory=list, description="インターフェース定義")

    @field_validator("mgmt_ipv4")
    @classmethod
    def _mgmt_cidr(cls, v: Optional[str]) -> Optional[str]:
        return _check_cidr(v, "device.mgmt_ipv4") if v is not None else None


class Cloud(StrictModel):
    """事業者網・外部網 (IP-VPN網、インターネット等)。link の端点に指定できる。"""

    id: str = Field(description="網ID (devices と合わせて一意)")
    name: str = Field(description="網の表示名")
    kind: CloudKind = Field(default="wan", description="網の種別")
    description: Optional[str] = Field(default=None, description="補足")


class Circuit(StrictModel):
    """キャリア回線契約。結線 (link) とは分離して契約情報を保持する。"""

    id: str = Field(description="回線ID (ファイル内で一意)")
    provider: str = Field(description="回線事業者")
    service: str = Field(description="サービス名 (例: IP-VPN, フレッツ光ネクスト)")
    circuit_id: Optional[str] = Field(default=None, description="事業者発行の回線番号")
    bandwidth: Optional[str] = Field(default=None, description="契約帯域 (例: 100M, 1G)")
    status: CircuitStatus = Field(default="active", description="回線の状態")
    description: Optional[str] = Field(default=None, description="補足")


class RedundancyMember(StrictModel):
    """冗長グループの1メンバー。"""

    device: str = Field(description="メンバー機器ID (devices を参照)")
    role: Optional[MemberRole] = Field(
        default=None,
        description="FHRPでの役割 (active / standby)。図でノードに (Act)/(Sby) を表示")


class RedundancyGroup(StrictModel):
    """冗長グループ (HSRP/VRRPペア / スタック)。ADR-0010。

    kind: fhrp は図で点線枠+Act/Sbyバッジ、kind: stack は論理ビューで
    1ノードに畳める (View.merge_stacks)。priority値・preempt等のコンフィグ
    詳細はスコープ外。
    """

    id: str = Field(description="冗長グループID (ファイル内で一意)")
    kind: RedundancyKind = Field(
        default="fhrp", description="fhrp=HSRP/VRRP等のGW冗長 / stack=スタック・シャーシ冗長")
    name: Optional[str] = Field(
        default=None, description="表示名 (stack を畳んだときのノード名。省略時は id)")
    protocol: Optional[FhrpProtocol] = Field(
        default=None, description="FHRPプロトコル (kind: fhrp のみ)。枠ラベルに表示")
    group: Optional[int] = Field(
        default=None, ge=0, description="FHRPグループ番号 (kind: fhrp のみ、任意)")
    vip: Optional[str] = Field(
        default=None,
        description="仮想IP (kind: fhrp のみ。CIDRなしの単一アドレス。"
                    "所属セグメントはCIDR包含で自動導出される)")
    members: list[RedundancyMember] = Field(
        min_length=2, description="メンバー機器 (2台以上)")
    description: Optional[str] = Field(default=None, description="補足")

    @field_validator("vip")
    @classmethod
    def _vip_addr(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            ipaddress.ip_address(v)
        except ValueError as exc:
            raise ValueError(
                f"vip は単一IPアドレス (例: 10.1.0.1、CIDRなし) で指定してください: {v}") from exc
        return v


class Domain(StrictModel):
    """ルーティングドメイン (OSPFエリア / BGP AS / VRF等)。

    図では所属エッジの色分け+凡例で表現される (エリア名を線1本ずつにラベル
    しない、実務の描き方に合わせるため)。内蔵SVGエンジンでは所属機器を囲む
    半透明の面塗りとしても描かれる。色はレンダラが自動割当し、DSLでは指定しない。
    表示名は name、または protocol/area/asn から自動生成 (ADR-0011)。
    """

    id: str = Field(description="ドメインID (ファイル内で一意)")
    name: Optional[str] = Field(
        default=None,
        description="表示名 (例: OSPF Area 0)。省略時は protocol/area/asn から自動生成")
    protocol: Optional[DomainProtocol] = Field(
        default=None, description="ルーティングプロトコル種別")
    area: Optional[Union[int, str]] = Field(
        default=None, description="OSPFエリア識別子 (protocol: ospf のみ。'0' / '0.0.0.0' 両形式可)")
    asn: Optional[int] = Field(
        default=None, ge=0, description="BGP AS番号 (protocol: bgp のみ)")
    description: Optional[str] = Field(default=None, description="補足")

    @field_validator("area")
    @classmethod
    def _area_str(cls, v: Optional[Union[int, str]]) -> Optional[str]:
        return str(v) if v is not None else None


def domain_display_name(domain: Domain) -> str:
    """凡例・面塗り・表で使う表示名。name 優先、無ければ構造化フィールドから生成。"""
    if domain.name:
        return domain.name
    if domain.protocol == "ospf" and domain.area is not None:
        return f"OSPF Area {domain.area}"
    if domain.protocol == "bgp" and domain.asn is not None:
        return f"BGP AS{domain.asn}"
    if domain.protocol:
        return f"{domain.protocol.upper()} ({domain.id})"
    return domain.id


class Redistribution(StrictModel):
    """ルート再配布 (ドメイン間の関係)。ADR-0011。

    図では on の機器ノードに『再配布: A → B』(mutual なら ⇄) のバッジ行が付く。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from", description="再配布元ドメインID (domains を参照)")
    to: str = Field(description="再配布先ドメインID (domains を参照)")
    # フィールド名を on にしない: YAML 1.1 では裸の on が真偽値になる (PyYAML)
    devices: list[str] = Field(
        min_length=1, description="再配布を実施する機器ID (複数可 = 冗長ASBR)")
    mutual: bool = Field(
        default=False, description="true なら相互再配布 (from⇄to)。既定は from→to の一方向")
    description: Optional[str] = Field(default=None, description="補足")


class Link(StrictModel):
    """機器間・機器-網間の接続。type が線の意味を決める。

    endpoints の記法:
      - "device-id:interface-name" … 機器のIF (lan-cable / wan-circuit では必須)
      - "device-id"                … 機器そのもの (logical / tunnel で許可)
      - "cloud-id"                 … 網 (wan-circuit でのみ許可)
    """

    id: Optional[str] = Field(default=None, description="接続ID (省略可。指定時は一意)")
    type: LinkType = Field(description="接続の種別 (線の意味)")
    endpoints: list[str] = Field(min_length=2, max_length=2, description="両端点")
    circuit: Optional[str] = Field(
        default=None, description="経由する回線契約ID (wan-circuit では必須、他typeでは指定不可)")
    domain: Optional[str] = Field(
        default=None,
        description="所属ルーティングドメインID (domains を参照)。指定すると図では"
                    "色分け+凡例で表現され、エッジ個別のラベルは不要になる")
    via: Optional[str] = Field(
        default=None,
        description="経由する網のID (clouds を参照。logical/tunnel のみ)。"
                    "論理図で『網の雲を通るピアリング』として描かれる")
    direction: LinkDirection = Field(
        default="both",
        description="forward=endpoints[0]→endpoints[1] の矢印で描く (logical のみ。"
                    "デフォルトルート等の向きの表現、ADR-0012) / both=無向 (既定)")
    description: Optional[str] = Field(default=None, description="補足 (logical/tunnel では図のラベルになる)")


class Segment(StrictModel):
    """L3セグメント (VLAN / サブネット)。論理構成図とIP設計表の情報源。"""

    id: str = Field(description="セグメントID (ファイル内で一意)")
    site: str = Field(description="所属拠点ID (sites を参照)")
    name: Optional[str] = Field(default=None, description="セグメント名")
    vlan: Optional[int] = Field(default=None, ge=1, le=4094, description="VLAN ID")
    ipv4: Optional[str] = Field(default=None, description="ネットワークアドレス (CIDR形式)")
    description: Optional[str] = Field(default=None, description="補足")

    @field_validator("ipv4")
    @classmethod
    def _ipv4_prefix(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            ipaddress.ip_network(v, strict=True)
        except ValueError as exc:
            raise ValueError(f"segment.ipv4 はネットワークアドレス (例: 10.1.10.0/24) で指定してください: {v}") from exc
        return v


class PathHop(StrictModel):
    """通信経路の1ホップ。node は devices / clouds の ID。"""

    node: str = Field(description="ホップのノードID (device または cloud)")
    protocol: Optional[str] = Field(
        default=None, description="このホップへの到達を決めるプロトコル (例: HSRP, BGP, OSPF)")
    note: Optional[str] = Field(
        default=None, description="経路選択の理由・補足 (図のラベルに表示)")


class Path(StrictModel):
    """通信経路 (正常時/障害時のトラフィックの通り道)。

    経路は作成者が明示する (ルーティング計算による自動導出はしない)。
    隣接ホップ間に実在の link があることをバリデータが検査する。
    """

    id: str = Field(description="経路ID (ファイル内で一意)")
    title: Optional[str] = Field(default=None, description="経路の表示名")
    failure: list[str] = Field(
        default_factory=list,
        description="この経路が前提とする障害コンポーネント (device/cloud/circuit のID)。図で赤✕表示")
    fallback_of: Optional[str] = Field(
        default=None, description="正常時経路のID。指定すると当該経路が灰破線で併記される")
    hops: list[PathHop] = Field(min_length=2, description="始点から終点までの順序付きホップ列")
    description: Optional[str] = Field(default=None, description="補足")


class View(StrictModel):
    """図の描き分け定義。フィルタと抽象度のみを宣言し、座標・色は持たない。"""

    id: str = Field(description="ビューID (ファイル内で一意)")
    title: str = Field(description="図のタイトル")
    type: Literal["topology", "path"] = Field(
        default="topology", description="topology=構成図 / path=経路ハイライト図")
    path: Optional[str] = Field(
        default=None, description="type: path のとき対象の経路ID (paths を参照)")
    layers: list[LinkType] = Field(
        default_factory=lambda: ["lan-cable", "wan-circuit", "logical", "tunnel"],
        description="図に含める接続種別")
    include_sites: Optional[list[str]] = Field(
        default=None, description="この拠点のみ描画 (省略時は全拠点)")
    exclude_sites: Optional[list[str]] = Field(default=None, description="除外する拠点")
    collapse_sites: bool = Field(
        default=False, description="true のとき拠点を1ノードに畳む (全社概要図向け)")
    show_l3: Optional[Union[bool, Literal["view", "used", "all"]]] = Field(
        default=None,
        description="L3情報 (IFのIPv4一覧とセグメントノード) の表示。"
                    "view=このビューに現れる接続のIFのみ (true と同義) / "
                    "used=いずれかのlinkで使用中のIF / all=IPv4を持つ全IF / false=非表示。"
                    "省略時は layers に logical を含むビューで view モードが自動有効")
    merge_stacks: Optional[bool] = Field(
        default=None,
        description="kind: stack の冗長グループを1ノードに畳む (ADR-0010)。"
                    "省略時は純粋なL3ビュー (show_l3 の自動判定と同条件) で自動有効。"
                    "物理図では通常 false (2筐体+点線枠で描く)")
    description: Optional[str] = Field(default=None, description="補足")
    order: Literal["auto", "declared"] = Field(
        default="auto",
        description="拠点の左右順序。auto=クロス最小化で見た目を最適化 (既定) / "
                    "declared=sites の宣言順で固定しビュー間の順序を一致させる。"
                    "内蔵SVGエンジンのみ有効、D2(ELK)では保証されない")


class Document(StrictModel):
    """DSL ファイル全体。"""

    nwdsl: str = Field(description="スキーマバージョン (現在は '0.2'。'0.1' も受理)")
    network: NetworkMeta
    sites: list[Site] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)
    clouds: list[Cloud] = Field(default_factory=list)
    circuits: list[Circuit] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    redundancy_groups: list[RedundancyGroup] = Field(default_factory=list)
    domains: list[Domain] = Field(default_factory=list)
    redistributions: list[Redistribution] = Field(default_factory=list)
    paths: list[Path] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)

    @field_validator("nwdsl")
    @classmethod
    def _version(cls, v: str) -> str:
        if v not in SUPPORTED_VERSIONS:
            raise ValueError(
                f"未対応のスキーマバージョンです: {v} (対応: {' / '.join(SUPPORTED_VERSIONS)})")
        return v


def parse_endpoint(endpoint: str) -> tuple[str, Optional[str]]:
    """端点文字列を (ノードID, インターフェース名 or None) に分解する。"""
    if ":" in endpoint:
        node, ifname = endpoint.split(":", 1)
        return node, ifname
    return endpoint, None
