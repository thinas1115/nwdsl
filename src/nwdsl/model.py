"""nwdsl スキーマ定義 (pydantic モデル)。

このモジュールが DSL の構文レベルの唯一の定義。JSON Schema は
`Document.model_json_schema()` から生成する。参照整合性などの
意味的検査は validate.py が担う。
"""

from __future__ import annotations

import ipaddress
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

LinkType = Literal["lan-cable", "wan-circuit", "logical", "tunnel"]
DeviceRole = Literal[
    "router", "l3switch", "l2switch", "firewall", "loadbalancer",
    "wlc", "ap", "server", "other",
]
CloudKind = Literal["wan", "internet", "other"]
CircuitStatus = Literal["planned", "active", "decommissioned"]

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
    redundancy_group: Optional[str] = Field(
        default=None, description="冗長グループ名 (HSRP/VRRPペア・スタック等で同名を指定)")
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


class View(StrictModel):
    """図の描き分け定義。フィルタと抽象度のみを宣言し、座標・色は持たない。"""

    id: str = Field(description="ビューID (ファイル内で一意)")
    title: str = Field(description="図のタイトル")
    layers: list[LinkType] = Field(
        default_factory=lambda: ["lan-cable", "wan-circuit", "logical", "tunnel"],
        description="図に含める接続種別")
    include_sites: Optional[list[str]] = Field(
        default=None, description="この拠点のみ描画 (省略時は全拠点)")
    exclude_sites: Optional[list[str]] = Field(default=None, description="除外する拠点")
    collapse_sites: bool = Field(
        default=False, description="true のとき拠点を1ノードに畳む (全社概要図向け)")
    description: Optional[str] = Field(default=None, description="補足")


class Document(StrictModel):
    """DSL ファイル全体。"""

    nwdsl: str = Field(description="スキーマバージョン (現在は '0.1')")
    network: NetworkMeta
    sites: list[Site] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)
    clouds: list[Cloud] = Field(default_factory=list)
    circuits: list[Circuit] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)

    @field_validator("nwdsl")
    @classmethod
    def _version(cls, v: str) -> str:
        if v != "0.1":
            raise ValueError(f"未対応のスキーマバージョンです: {v} (対応: 0.1)")
        return v


def parse_endpoint(endpoint: str) -> tuple[str, Optional[str]]:
    """端点文字列を (ノードID, インターフェース名 or None) に分解する。"""
    if ":" in endpoint:
        node, ifname = endpoint.split(":", 1)
        return node, ifname
    return endpoint, None
