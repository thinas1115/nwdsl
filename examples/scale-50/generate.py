"""scale-50: 3拠点・機器50台の描画スケール検証用サンプルを生成する。

    python examples/scale-50/generate.py

で network.yaml を再生成できる。トポロジ: 本社29台 (WANルーター/FW/コア各冗長 +
ディストリ4 + アクセス10 + サーバSW2 + サーバ4 + DMZ)、大阪12台、名古屋9台。
"""

from pathlib import Path

import yaml

devices: list[dict] = []
links: list[dict] = []
_port_no: dict[str, int] = {}


def port(dev: str) -> str:
    _port_no[dev] = _port_no.get(dev, 0) + 1
    return f"Gi0/{_port_no[dev]}"


def add_device(dev_id: str, site: str, role: str, platform: str, **kw) -> None:
    devices.append({"id": dev_id, "site": site, "role": role,
                    "platform": platform, "interfaces": [], **kw})


def cable(a: str, b: str) -> None:
    pa, pb = port(a), port(b)
    for dev_id, name in ((a, pa), (b, pb)):
        dev = next(d for d in devices if d["id"] == dev_id)
        dev["interfaces"].append({"name": name})
    links.append({"type": "lan-cable", "endpoints": [f"{a}:{pa}", f"{b}:{pb}"]})


def wan(dev_id: str, cloud: str, circuit: str) -> None:
    name = port(dev_id)
    dev = next(d for d in devices if d["id"] == dev_id)
    dev["interfaces"].append({"name": name, "description": "WANアクセス回線"})
    links.append({"type": "wan-circuit", "endpoints": [f"{dev_id}:{name}", cloud],
                  "circuit": circuit})


# ---- 本社 (29台) ----
for n in ("01", "02"):
    add_device(f"hq-rt{n}", "hq", "router", "Cisco ISR4451", redundancy_group="hq-wan")
    add_device(f"hq-fw{n}", "hq", "firewall", "PA-3410", redundancy_group="hq-fw")
    add_device(f"hq-core{n}", "hq", "l3switch", "Catalyst 9500", redundancy_group="hq-core")
    add_device(f"hq-srvsw{n}", "hq", "l2switch", "Catalyst 9200")
for n in range(1, 5):
    add_device(f"hq-dist0{n}", "hq", "l3switch", "Catalyst 9300")
for n in range(1, 11):
    add_device(f"hq-acc{n:02d}", "hq", "l2switch", "Catalyst 1000")
for n in range(1, 5):
    add_device(f"hq-srv0{n}", "hq", "server", "PowerEdge R660")
add_device("hq-dmzsw01", "hq", "l2switch", "Catalyst 1000")
add_device("hq-dmzsrv01", "hq", "server", "公開Web")
add_device("hq-dmzsrv02", "hq", "server", "公開DNS")

cable("hq-rt01", "hq-fw01")
cable("hq-rt02", "hq-fw02")
cable("hq-fw01", "hq-core01")
cable("hq-fw02", "hq-core02")
cable("hq-core01", "hq-core02")
for n in range(1, 5):
    cable("hq-core01", f"hq-dist0{n}")
    cable("hq-core02", f"hq-dist0{n}")
for n in range(1, 11):
    # フロア単位の連続割当 (acc01-03→dist01, 04-06→dist02, 07-09→dist03, 10→dist04)
    cable(f"hq-dist0{min((n - 1) // 3 + 1, 4)}", f"hq-acc{n:02d}")
cable("hq-core01", "hq-srvsw01")
cable("hq-core02", "hq-srvsw02")
cable("hq-srvsw01", "hq-srvsw02")
for n in range(1, 5):
    cable(f"hq-srvsw0{1 if n <= 2 else 2}", f"hq-srv0{n}")
cable("hq-fw01", "hq-dmzsw01")
cable("hq-dmzsw01", "hq-dmzsrv01")
cable("hq-dmzsw01", "hq-dmzsrv02")

# ---- 大阪 (12台) ----
add_device("osk-rt01", "osk", "router", "Cisco ISR4331")
add_device("osk-rt02", "osk", "router", "Cisco ISR4331")
add_device("osk-core01", "osk", "l3switch", "Catalyst 9300")
for n in range(1, 7):
    add_device(f"osk-acc0{n}", "osk", "l2switch", "Catalyst 1000")
for n in range(1, 4):
    add_device(f"osk-srv0{n}", "osk", "server", "PowerEdge R450")
cable("osk-rt01", "osk-core01")
cable("osk-rt02", "osk-core01")
for n in range(1, 7):
    cable("osk-core01", f"osk-acc0{n}")
for n in range(1, 4):
    cable("osk-core01", f"osk-srv0{n}")

# ---- 名古屋 (9台) ----
add_device("ngy-rt01", "ngy", "router", "Cisco ISR1100")
add_device("ngy-sw01", "ngy", "l2switch", "Catalyst 1000")
for n in range(1, 6):
    add_device(f"ngy-acc0{n}", "ngy", "l2switch", "Catalyst 1000")
for n in range(1, 3):
    add_device(f"ngy-srv0{n}", "ngy", "server", "PowerEdge R450")
cable("ngy-rt01", "ngy-sw01")
for n in range(1, 6):
    cable("ngy-sw01", f"ngy-acc0{n}")
for n in range(1, 3):
    cable("ngy-sw01", f"ngy-srv0{n}")

# ---- L3: セグメントとGW (論理構成図用) ----
segments = [
    {"id": "hq-lan", "site": "hq", "vlan": 100, "ipv4": "10.50.10.0/24", "name": "本社ユーザ"},
    {"id": "osk-lan", "site": "osk", "vlan": 100, "ipv4": "10.51.10.0/24", "name": "大阪ユーザ"},
    {"id": "ngy-lan", "site": "ngy", "vlan": 100, "ipv4": "10.52.10.0/24", "name": "名古屋ユーザ"},
]
for dev_id, seg_id, gw_ip in (
        ("hq-core01", "hq-lan", "10.50.10.2/24"),
        ("hq-core02", "hq-lan", "10.50.10.3/24"),
        ("osk-core01", "osk-lan", "10.51.10.1/24"),
        ("ngy-rt01", "ngy-lan", "10.52.10.1/24")):
    rec = next(d for d in devices if d["id"] == dev_id)
    rec["interfaces"].append({"name": "Vlan100", "description": "ユーザセグメントGW",
                              "ipv4": gw_ip, "segment": seg_id})

# ---- WAN ----
wan("hq-rt01", "ipvpn", "cct-ipvpn-hq")
wan("osk-rt01", "ipvpn", "cct-ipvpn-osk")
wan("ngy-rt01", "ipvpn", "cct-ipvpn-ngy")
wan("hq-rt02", "internet", "cct-inet-hq")
wan("osk-rt02", "internet", "cct-inet-osk")
links.append({"type": "logical", "endpoints": ["hq-rt01", "osk-rt01"], "description": "BGP"})
links.append({"type": "logical", "endpoints": ["hq-rt01", "ngy-rt01"], "description": "BGP"})

doc = {
    "nwdsl": "0.1",
    "network": {"name": "scale-50", "description": "3拠点・50台の描画スケール検証"},
    "sites": [
        {"id": "hq", "name": "本社", "location": "東京"},
        {"id": "osk", "name": "大阪支社", "location": "大阪"},
        {"id": "ngy", "name": "名古屋営業所", "location": "名古屋"},
    ],
    "devices": devices,
    "clouds": [
        {"id": "ipvpn", "name": "IP-VPN網", "kind": "wan"},
        {"id": "internet", "name": "インターネット", "kind": "internet"},
    ],
    "circuits": [
        {"id": "cct-ipvpn-hq", "provider": "NTT Com", "service": "IP-VPN", "bandwidth": "1G"},
        {"id": "cct-ipvpn-osk", "provider": "NTT Com", "service": "IP-VPN", "bandwidth": "200M"},
        {"id": "cct-ipvpn-ngy", "provider": "NTT Com", "service": "IP-VPN", "bandwidth": "100M"},
        {"id": "cct-inet-hq", "provider": "NTT東", "service": "フレッツ光 + OCN", "bandwidth": "1G"},
        {"id": "cct-inet-osk", "provider": "NTT西", "service": "フレッツ光 + OCN", "bandwidth": "1G"},
    ],
    "links": links,
    "segments": segments,
    "views": [
        {"id": "physical-all", "title": "全社物理構成図 (50台)",
         "layers": ["lan-cable", "wan-circuit"]},
        {"id": "logical-all", "title": "全社論理構成図",
         "layers": ["logical"]},
        {"id": "hq-physical", "title": "本社 物理構成図 (29台)",
         "layers": ["lan-cable", "wan-circuit"], "include_sites": ["hq"]},
        {"id": "osk-physical", "title": "大阪支社 物理構成図",
         "layers": ["lan-cable", "wan-circuit"], "include_sites": ["osk"]},
        {"id": "wan-overview", "title": "全社WAN概要図",
         "layers": ["wan-circuit", "logical"], "collapse_sites": True},
    ],
}

out = Path(__file__).parent / "network.yaml"
out.write_text("# このファイルは generate.py により生成 (手編集しない)\n" +
               yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
               encoding="utf-8")
print(f"wrote {out} (devices={len(devices)}, links={len(links)})")
