"""D2のノックアウトファクタ探し用の敵対的トポロジ4種を生成する。"""
import copy
from pathlib import Path

import yaml

OUT = Path(__file__).parent


def new_doc(name):
    return {"nwdsl": "0.1", "network": {"name": name}, "sites": [], "devices": [],
            "clouds": [], "circuits": [], "links": [], "views": []}


class B:
    def __init__(self, doc):
        self.doc = doc
        self.ports = {}

    def dev(self, id_, site, role, platform="x"):
        self.doc["devices"].append({"id": id_, "site": site, "role": role,
                                    "platform": platform, "interfaces": []})

    def port(self, dev):
        self.ports[dev] = self.ports.get(dev, 0) + 1
        name = f"e{self.ports[dev]}"
        next(d for d in self.doc["devices"] if d["id"] == dev)["interfaces"].append(
            {"name": name})
        return name

    def cable(self, a, b):
        self.doc["links"].append({"type": "lan-cable",
                                  "endpoints": [f"{a}:{self.port(a)}", f"{b}:{self.port(b)}"]})

    def wan(self, dev, other, cct_id, provider="キャリア", service="回線", bw="1G"):
        self.doc["circuits"].append({"id": cct_id, "provider": provider,
                                     "service": service, "bandwidth": bw})
        ep2 = other if other in [c["id"] for c in self.doc["clouds"]] \
            else f"{other}:{self.port(other)}"
        self.doc["links"].append({"type": "wan-circuit",
                                  "endpoints": [f"{dev}:{self.port(dev)}", ep2],
                                  "circuit": cct_id})


# ---- A: leaf-spine (完全二部グラフ K4,12) ----
doc = new_doc("stress-leafspine")
doc["sites"] = [{"id": "dc", "name": "DC"}]
doc["clouds"] = [{"id": "wan", "name": "WAN網", "kind": "wan"}]
b = B(doc)
for s in range(1, 5):
    b.dev(f"spine{s:02d}", "dc", "l3switch", "9500-32C")
for l in range(1, 13):
    b.dev(f"leaf{l:02d}", "dc", "l3switch", "9300")
b.dev("border01", "dc", "router", "ASR1001")
b.dev("border02", "dc", "router", "ASR1001")
for s in range(1, 5):
    for l in range(1, 13):
        b.cable(f"spine{s:02d}", f"leaf{l:02d}")
for s in range(1, 5):
    b.cable(f"spine{s:02d}", "border01")
    b.cable(f"spine{s:02d}", "border02")
b.wan("border01", "wan", "cct-a1")
b.wan("border02", "wan", "cct-a2")
doc["views"] = [{"id": "dc", "title": "DCファブリック物理図 (K4x12)",
                 "layers": ["lan-cable", "wan-circuit"]}]
(OUT / "leafspine.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True,
                                                   sort_keys=False), encoding="utf-8")

# ---- B: 12拠点 + 2クラウド + トンネル/論理メッシュ (概要図ストレス) ----
doc = new_doc("stress-multisite")
b = B(doc)
doc["clouds"] = [{"id": "ipvpn", "name": "IP-VPN網", "kind": "wan"},
                 {"id": "inet", "name": "インターネット", "kind": "internet"}]
for i in range(1, 13):
    sid = f"s{i:02d}"
    doc["sites"].append({"id": sid, "name": f"拠点{i:02d}"})
    b.dev(f"{sid}-rt01", sid, "router")
    b.dev(f"{sid}-sw01", sid, "l2switch")
    b.cable(f"{sid}-rt01", f"{sid}-sw01")
    b.wan(f"{sid}-rt01", "ipvpn", f"cct-v{i:02d}", service="IP-VPN")
    if i <= 6:
        b.dev(f"{sid}-rt02", sid, "router")
        b.cable(f"{sid}-rt02", f"{sid}-sw01")
        b.wan(f"{sid}-rt02", "inet", f"cct-i{i:02d}", service="フレッツ光")
for i in range(2, 7):  # ハブ(s01)から各インターネット拠点へIPsec
    doc["links"].append({"type": "tunnel",
                         "endpoints": ["s01-rt02", f"s{i:02d}-rt02"],
                         "description": f"IPsec s01-s{i:02d}"})
for i in range(2, 13):  # BGP ハブ&スポーク
    doc["links"].append({"type": "logical",
                         "endpoints": ["s01-rt01", f"s{i:02d}-rt01"],
                         "description": "BGP"})
doc["views"] = [
    {"id": "wan-overview", "title": "12拠点 WAN概要図", "collapse_sites": True,
     "layers": ["wan-circuit", "tunnel"]},
    {"id": "physical-all", "title": "12拠点 全社物理図",
     "layers": ["lan-cable", "wan-circuit"]}]
(OUT / "multisite.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True,
                                                   sort_keys=False), encoding="utf-8")

# ---- C: 8拠点メトロリング (専用線でリング閉路) ----
doc = new_doc("stress-ring")
b = B(doc)
for i in range(1, 9):
    sid = f"r{i}"
    doc["sites"].append({"id": sid, "name": f"リング拠点{i}"})
    b.dev(f"{sid}-rt", sid, "router")
    b.dev(f"{sid}-sw", sid, "l2switch")
    b.cable(f"{sid}-rt", f"{sid}-sw")
for i in range(1, 9):
    nxt = i % 8 + 1
    b.wan(f"r{i}-rt", f"r{nxt}-rt", f"cct-ring{i}", service="広域Ether専用線")
doc["views"] = [
    {"id": "ring-collapsed", "title": "リング概要図", "collapse_sites": True,
     "layers": ["wan-circuit"]},
    {"id": "ring-physical", "title": "リング物理図", "layers": ["lan-cable", "wan-circuit"]}]
(OUT / "ring.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True,
                                              sort_keys=False), encoding="utf-8")

# ---- D: LAG並列リンク + デュアルホーム ----
doc = new_doc("stress-lag")
doc["sites"] = [{"id": "dc", "name": "サーバ室"}]
doc["clouds"] = [{"id": "wan", "name": "WAN網", "kind": "wan"}]
b = B(doc)
b.dev("rt01", "dc", "router")
b.dev("core01", "dc", "l3switch")
b.dev("core02", "dc", "l3switch")
b.wan("rt01", "wan", "cct-d1")
b.cable("rt01", "core01")
b.cable("rt01", "core02")
for _ in range(4):          # コア間 4本LAG
    b.cable("core01", "core02")
for n in range(1, 7):       # サーバ6台デュアルホーム
    b.dev(f"srv{n:02d}", "dc", "server")
    b.cable("core01", f"srv{n:02d}")
    b.cable("core02", f"srv{n:02d}")
doc["views"] = [{"id": "lag", "title": "LAG並列リンク物理図",
                 "layers": ["lan-cable", "wan-circuit"]}]
(OUT / "lag.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True,
                                             sort_keys=False), encoding="utf-8")

print("generated:", [p.name for p in OUT.glob("*.yaml")])
