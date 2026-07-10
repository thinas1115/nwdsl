"""冗長グループ (ADR-0010)・ルーティング構造化 (ADR-0011)・有向logical (ADR-0012) のテスト。"""

import textwrap
from pathlib import Path

import pytest

from nwdsl.graph import resolve_view
from nwdsl.loader import load_document
from nwdsl.model import domain_display_name
from nwdsl.render_d2 import render_d2
from nwdsl.render_mermaid import render_mermaid
from nwdsl.render_svg import render_svg
from nwdsl.tables import render_tables
from nwdsl.validate import has_errors, validate_document

BASE = """
nwdsl: "0.2"
network: {name: test}
sites:
  - {id: hq, name: 本社}
devices:
  - id: rt01
    site: hq
    role: router
    interfaces:
      - {name: Gi0/0, ipv4: 10.1.0.2/24}
      - {name: Gi0/1}
  - id: rt02
    site: hq
    role: router
    interfaces:
      - {name: Gi0/0, ipv4: 10.1.0.3/24}
      - {name: Gi0/1}
  - id: core01
    site: hq
    role: l3switch
    interfaces:
      - {name: Te1/49}
      - {name: Gi1/1}
      - {name: Gi1/2}
      - {name: Vlan10, ipv4: 10.1.10.2/24, segment: seg-srv}
  - id: core02
    site: hq
    role: l3switch
    interfaces:
      - {name: Te2/49}
      - {name: Gi2/1}
      - {name: Gi2/2}
      - {name: Vlan10, ipv4: 10.1.10.3/24, segment: seg-srv}
  - id: fw01
    site: hq
    role: firewall
    interfaces: [{name: eth1}, {name: eth2}]
segments:
  - {id: seg-srv, site: hq, vlan: 10, ipv4: 10.1.10.0/24, name: サーバ}
"""

FULL = BASE + """
redundancy_groups:
  - id: hq-gw
    kind: fhrp
    protocol: hsrp
    group: 1
    vip: 10.1.0.1
    members:
      - {device: rt01, role: active}
      - {device: rt02, role: standby}
  - id: hq-core
    kind: stack
    name: hq-core
    members:
      - {device: core01}
      - {device: core02}
domains:
  - {id: area0, protocol: ospf, area: 0}
  - {id: as65k, protocol: bgp, asn: 65000}
redistributions:
  - {from: area0, to: as65k, devices: [rt01, rt02], mutual: true}
links:
  - {type: lan-cable, endpoints: ["core01:Te1/49", "core02:Te2/49"]}
  - {type: lan-cable, endpoints: ["rt01:Gi0/1", "core01:Gi1/1"]}
  - {type: lan-cable, endpoints: ["rt02:Gi0/1", "core02:Gi2/1"]}
  - {type: lan-cable, endpoints: ["fw01:eth1", "core01:Gi1/2"]}
  - {type: lan-cable, endpoints: ["fw01:eth2", "core02:Gi2/2"]}
  - {type: logical, endpoints: ["rt01", "core01"], domain: area0}
  - {type: logical, endpoints: ["rt02", "core02"], domain: area0}
  - {type: logical, endpoints: ["rt01", "rt02"], domain: as65k}
  - {type: logical, endpoints: ["core01", "fw01"], description: default, direction: forward}
views:
  - {id: phys, title: 物理図, layers: [lan-cable]}
  - {id: logi, title: 論理図, layers: [logical]}
"""


def _load(tmp_path: Path, body: str):
    f = tmp_path / "net.yaml"
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_document(f)


def _codes(issues):
    return {i.code for i in issues}


def _view(doc, view_id):
    return next(v for v in doc.views if v.id == view_id)


# ---- バリデーション ----

def test_full_sample_is_valid(tmp_path):
    assert validate_document(_load(tmp_path, FULL)) == []


def test_redundancy_member_ref(tmp_path):
    doc = _load(tmp_path, BASE + """
redundancy_groups:
  - id: g1
    members: [{device: ghost}, {device: rt01}]
""")
    assert "ref.redundancy-member" in _codes(validate_document(doc))


def test_redundancy_fhrp_only_on_stack(tmp_path):
    doc = _load(tmp_path, BASE + """
redundancy_groups:
  - id: g1
    kind: stack
    vip: 10.1.0.1
    members: [{device: core01}, {device: core02}]
""")
    assert "redundancy.fhrp-only" in _codes(validate_document(doc))


def test_redundancy_multi_stack_rejected(tmp_path):
    doc = _load(tmp_path, BASE + """
redundancy_groups:
  - id: g1
    kind: stack
    members: [{device: core01}, {device: core02}]
  - id: g2
    kind: stack
    members: [{device: core01}, {device: rt01}]
""")
    assert "redundancy.multi-stack" in _codes(validate_document(doc))


def test_redundancy_vip_outside_networks_warns(tmp_path):
    doc = _load(tmp_path, BASE + """
redundancy_groups:
  - id: g1
    vip: 192.0.2.1
    members: [{device: rt01}, {device: rt02}]
""")
    issues = validate_document(doc)
    assert "redundancy.vip-segment" in _codes(issues)
    assert not has_errors(issues)


def test_domain_name_or_protocol_required(tmp_path):
    doc = _load(tmp_path, BASE + """
domains:
  - {id: d1}
""")
    assert "domain.name-required" in _codes(validate_document(doc))


def test_domain_attr_mismatch(tmp_path):
    doc = _load(tmp_path, BASE + """
domains:
  - {id: d1, protocol: bgp, area: 0}
  - {id: d2, protocol: ospf, asn: 65000}
""")
    issues = [i for i in validate_document(doc) if i.code == "domain.attr-mismatch"]
    assert len(issues) == 2


def test_redistribution_refs_and_same_domain(tmp_path):
    doc = _load(tmp_path, BASE + """
domains:
  - {id: area0, protocol: ospf, area: 0}
redistributions:
  - {from: area0, to: area0, devices: [ghost]}
  - {from: nowhere, to: area0, devices: [rt01]}
""")
    codes = _codes(validate_document(doc))
    assert {"redistribution.same-domain", "ref.redistribution-device",
            "ref.redistribution-domain"} <= codes


def test_direction_forbidden_on_lan_cable(tmp_path):
    doc = _load(tmp_path, BASE + """
links:
  - {type: lan-cable, endpoints: ["rt01:Gi0/1", "core01:Gi1/1"], direction: forward}
""")
    assert "link.direction-forbidden" in _codes(validate_document(doc))


def test_domain_display_name(tmp_path):
    doc = _load(tmp_path, BASE + """
domains:
  - {id: a, protocol: ospf, area: 0}
  - {id: b, protocol: bgp, asn: 65000}
  - {id: c, protocol: ospf, area: 1, name: カスタム名}
""")
    names = [domain_display_name(d) for d in doc.domains]
    assert names == ["OSPF Area 0", "BGP AS65000", "カスタム名"]


# ---- 図 (graph / レンダラ) ----

def test_stack_merged_in_logical_view(tmp_path):
    doc = _load(tmp_path, FULL)
    g = resolve_view(doc, _view(doc, "logi"))
    ids = {n.id for n in g.nodes}
    assert "stack__hq-core" in ids
    assert "core01" not in ids and "core02" not in ids
    stack = next(n for n in g.nodes if n.id == "stack__hq-core")
    assert "スタック×2" in stack.label
    # 両筐体のSVIが集約表示される
    assert stack.label.count("Vlan10") == 2


def test_stack_not_merged_in_physical_view(tmp_path):
    doc = _load(tmp_path, FULL)
    g = resolve_view(doc, _view(doc, "phys"))
    ids = {n.id for n in g.nodes}
    assert {"core01", "core02"} <= ids and "stack__hq-core" not in ids
    # 物理図では fhrp と stack の枠が2つ
    assert {r.id for r in g.redundancy} == {"hq-gw", "hq-core"}
    assert any("HSRP grp1 VIP 10.1.0.1" == r.label for r in g.redundancy)


def test_cross_stack_lag_bundles_after_merge(tmp_path):
    doc = _load(tmp_path, FULL)
    view = _view(doc, "phys").model_copy(update={"merge_stacks": True})
    g = resolve_view(doc, view)
    # rt01/rt02→両筐体 と fw01→両筐体 は畳み後もそれぞれ別ペアなので束ならないが、
    # fw01 の2本は同一ペア (fw01–stack) になり ×2 に束なる
    fw_edges = [e for e in g.edges
                if {e.src, e.dst} == {"fw01", "stack__hq-core"}]
    assert len(fw_edges) == 1 and "×2" in fw_edges[0].label
    # スタック間リンクは自己ループとして消える
    assert all(e.src != e.dst for e in g.edges)


def test_act_sby_badge_and_redistribution_badge(tmp_path):
    doc = _load(tmp_path, FULL)
    g = resolve_view(doc, _view(doc, "logi"))
    rt01 = next(n for n in g.nodes if n.id == "rt01")
    rt02 = next(n for n in g.nodes if n.id == "rt02")
    assert rt01.label.splitlines()[0].endswith("(Act)")
    assert rt02.label.splitlines()[0].endswith("(Sby)")
    assert "再配布: OSPF Area 0 ⇄ BGP AS65000" in rt01.label


def test_redistribution_badge_absent_in_physical(tmp_path):
    doc = _load(tmp_path, FULL)
    g = resolve_view(doc, _view(doc, "phys"))
    rt01 = next(n for n in g.nodes if n.id == "rt01")
    assert "再配布" not in rt01.label


def test_directed_logical_edge(tmp_path):
    doc = _load(tmp_path, FULL)
    g = resolve_view(doc, _view(doc, "logi"))
    default = next(e for e in g.edges if e.label == "default")
    assert default.directed
    assert (default.src, default.dst) == ("stack__hq-core", "fw01")  # 向き付けで反転しない
    assert "-> " in render_d2(g) or " -> " in render_d2(g)
    assert "-->" in render_mermaid(g)


def test_renderers_emit_redundancy_frames(tmp_path):
    doc = _load(tmp_path, FULL)
    g = resolve_view(doc, _view(doc, "phys"))
    d2 = render_d2(g)
    assert "rg_hq_gw" in d2 and "group-redundancy" in d2
    mmd = render_mermaid(g)
    assert 'subgraph rg_hq_gw["HSRP grp1 VIP 10.1.0.1"]' in mmd
    svg = render_svg(g)
    assert 'stroke-dasharray="5 4"' in svg and "HSRP grp1 VIP 10.1.0.1" in svg


def test_overlapping_fhrp_groups_merge_into_one_frame(tmp_path):
    doc = _load(tmp_path, BASE + """
redundancy_groups:
  - id: v10
    protocol: hsrp
    group: 10
    vip: 10.1.10.1
    members: [{device: core01}, {device: core02}]
  - id: v20
    protocol: hsrp
    group: 20
    members: [{device: core01}, {device: core02}]
links:
  - {type: lan-cable, endpoints: ["core01:Te1/49", "core02:Te2/49"]}
views:
  - {id: phys, title: 物理図, layers: [lan-cable]}
""")
    g = resolve_view(doc, _view(doc, "phys"))
    assert len(g.redundancy) == 1
    frame = g.redundancy[0]
    assert "HSRP grp10 VIP 10.1.10.1" in frame.label and "HSRP grp20" in frame.label


# ---- 表 ----

def test_tables_include_redundancy_and_routing(tmp_path):
    doc = _load(tmp_path, FULL)
    md = render_tables(doc)
    assert "## 冗長グループ一覧" in md
    assert "| hq-gw | FHRP | HSRP | 1 | 10.1.0.1 |" in md
    assert "## ルーティング一覧" in md
    assert "| OSPF Area 0 | BGP AS65000 | 相互 | rt01 / rt02 |" in md
    # VIPはCIDR包含でセグメントGW列に載る (10.1.0.1はセグメント未定義なので載らない)
    assert "VIP 10.1.0.1" not in md.split("## セグメント一覧")[1]


def test_tables_vip_in_segment_gateway(tmp_path):
    doc = _load(tmp_path, BASE + """
redundancy_groups:
  - id: core-gw
    protocol: hsrp
    vip: 10.1.10.1
    members: [{device: core01}, {device: core02}]
""")
    md = render_tables(doc)
    seg_section = md.split("## セグメント一覧")[1]
    assert "VIP 10.1.10.1 (core-gw)" in seg_section


def test_optional_sections_hidden_without_data(tmp_path):
    doc = _load(tmp_path, BASE)
    md = render_tables(doc)
    assert "## 冗長グループ一覧" not in md
    assert "## ルーティング一覧" not in md
