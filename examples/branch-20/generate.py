"""branch-20: 20拠点ハブ&スポーク構成を生成する。

    python examples/branch-20/generate.py

東西2ハブ (DR構成) + 18支店。WAN は IP-VPN、うち6支店はモバイル閉域網の
バックアップ回線あり。BGPは各支店から両ハブへのデュアルホーム。
「拠点数が多い」方向のスケール検証 (scale-50 は「1拠点が深い」方向)。
"""

from pathlib import Path

import yaml

devices: list[dict] = []
links: list[dict] = []
circuits: list[dict] = []
sites: list[dict] = []
_pn: dict[str, int] = {}


def port(dev: str) -> str:
    _pn[dev] = _pn.get(dev, 0) + 1
    return f"Gi0/{_pn[dev]}"


def dev(dev_id: str, site: str, role: str, platform: str, **kw) -> None:
    devices.append({"id": dev_id, "site": site, "role": role,
                    "platform": platform, "interfaces": [], **kw})


def add_if(dev_id: str, **kw) -> str:
    name = port(dev_id)
    rec = next(d for d in devices if d["id"] == dev_id)
    rec["interfaces"].append({"name": name, **kw})
    return name


def cable(a: str, b: str) -> None:
    links.append({"type": "lan-cable",
                  "endpoints": [f"{a}:{add_if(a)}", f"{b}:{add_if(b)}"]})


def wan(dev_id: str, cloud: str, cct_id: str, provider: str, service: str,
        bw: str) -> None:
    circuits.append({"id": cct_id, "provider": provider, "service": service,
                     "bandwidth": bw})
    name = add_if(dev_id, description=f"{service}アクセス回線")
    links.append({"type": "wan-circuit", "endpoints": [f"{dev_id}:{name}", cloud],
                  "circuit": cct_id})


# ---- 東西ハブ (DR構成) ----
for hub, name, city in (("hube", "東日本ハブ", "東京"), ("hubw", "西日本ハブ", "大阪")):
    sites.append({"id": hub, "name": name, "location": city})
    dev(f"{hub}-rt01", hub, "router", "Cisco C8300", redundancy_group=f"{hub}-wan")
    dev(f"{hub}-rt02", hub, "router", "Cisco C8300", redundancy_group=f"{hub}-wan")
    dev(f"{hub}-core01", hub, "l3switch", "Catalyst 9500")
    dev(f"{hub}-srv01", hub, "server", "基幹サーバ")
    cable(f"{hub}-rt01", f"{hub}-core01")
    cable(f"{hub}-rt02", f"{hub}-core01")
    cable(f"{hub}-core01", f"{hub}-srv01")
    wan(f"{hub}-rt01", "ipvpn", f"cct-v-{hub}1", "NTT Com", "IP-VPN", "1G")
    wan(f"{hub}-rt02", "ipvpn", f"cct-v-{hub}2", "NTT Com", "IP-VPN", "1G")
    wan(f"{hub}-rt02", "mobile", f"cct-m-{hub}", "SB", "モバイル閉域網", "100M")

# ---- 18支店 (br03〜br20。6拠点はモバイルバックアップつき) ----
for n in range(3, 21):
    sid = f"br{n:02d}"
    sites.append({"id": sid, "name": f"支店{n:02d}"})
    dev(f"{sid}-rt01", sid, "router", "Cisco C1121")
    dev(f"{sid}-sw01", sid, "l2switch", "Catalyst 1000")
    cable(f"{sid}-rt01", f"{sid}-sw01")
    wan(f"{sid}-rt01", "ipvpn", f"cct-v-{sid}", "NTT Com", "IP-VPN", "100M")
    if n % 3 == 0:  # 3の倍数の支店はモバイルバックアップあり
        wan(f"{sid}-rt01", "mobile", f"cct-m-{sid}", "SB", "モバイル閉域網", "50M")
    for hub in ("hube", "hubw"):
        links.append({"type": "logical", "endpoints": [f"{hub}-rt01", f"{sid}-rt01"],
                      "description": "BGP"})

doc = {
    "nwdsl": "0.1",
    "network": {"name": "branch-20",
                "description": "20拠点ハブ&スポーク (東西DRハブ + モバイルバックアップ)"},
    "sites": sites,
    "devices": devices,
    "clouds": [
        {"id": "ipvpn", "name": "IP-VPN網", "kind": "wan"},
        {"id": "mobile", "name": "モバイル閉域網", "kind": "wan"},
    ],
    "circuits": circuits,
    "links": links,
    "paths": [
        {"id": "br05-normal", "title": "支店05→東日本ハブ (正常時)",
         "hops": [{"node": "br05-sw01"}, {"node": "br05-rt01"},
                  {"node": "ipvpn", "protocol": "BGP"},
                  {"node": "hube-rt01"}, {"node": "hube-core01"},
                  {"node": "hube-srv01"}]},
        {"id": "br06-mobile", "title": "支店06→東日本ハブ (IP-VPN障害時)",
         "failure": ["cct-v-br06"],
         "hops": [{"node": "br06-sw01"}, {"node": "br06-rt01"},
                  {"node": "mobile", "protocol": "BGP", "note": "モバイル閉域網へ切替"},
                  {"node": "hube-rt02"}, {"node": "hube-core01"},
                  {"node": "hube-srv01"}]},
    ],
    "views": [
        {"id": "wan-overview", "title": "20拠点 WAN概要図",
         "layers": ["wan-circuit"], "collapse_sites": True},
        {"id": "logical-overview", "title": "BGP論理概要図 (ハブ&スポーク)",
         "layers": ["logical"], "collapse_sites": True},
        {"id": "hube-physical", "title": "東日本ハブ 物理構成図",
         "layers": ["lan-cable", "wan-circuit"], "include_sites": ["hube"]},
        {"id": "path-br06-mobile", "title": "支店06 IP-VPN障害時経路",
         "type": "path", "path": "br06-mobile"},
    ],
}

out = Path(__file__).parent / "network.yaml"
out.write_text("# このファイルは generate.py により生成 (手編集しない)\n" +
               yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
               encoding="utf-8")
print(f"wrote {out} (sites={len(sites)}, devices={len(devices)}, links={len(links)})")
