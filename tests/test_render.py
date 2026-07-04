"""ビュー解決とD2/Mermaidシリアライザのテスト。"""

from pathlib import Path

import pytest

from nwdsl.graph import resolve_view
from nwdsl.loader import load_document
from nwdsl.render_d2 import render_d2
from nwdsl.render_mermaid import render_mermaid

SAMPLE = Path(__file__).parent.parent / "examples" / "sample-corp" / "network.yaml"


@pytest.fixture(scope="module")
def doc():
    return load_document(SAMPLE)


def _view(doc, view_id):
    return next(v for v in doc.views if v.id == view_id)


def test_physical_all_has_all_devices_and_clouds(doc):
    g = resolve_view(doc, _view(doc, "physical-all"))
    ids = {n.id for n in g.nodes}
    assert {"hq-rt01", "hq-rt02", "hq-sw01", "osk-rt01", "osk-sw01",
            "ngy-rt01", "ngy-sw01", "ipvpn", "internet"} == ids
    assert len(g.groups) == 3
    # 物理図に logical / tunnel は含まれない
    assert all(e.type in ("lan-cable", "wan-circuit") for e in g.edges)


def test_collapse_sites_folds_devices(doc):
    g = resolve_view(doc, _view(doc, "wan-overview"))
    kinds = {n.kind for n in g.nodes}
    assert kinds == {"site", "cloud"}
    # 拠点内で閉じる lan-cable 由来のエッジは存在しない (layersにも含まれない)
    assert len([e for e in g.edges if e.type == "wan-circuit"]) == 5
    # 本社-大阪の IPsec トンネルは拠点間エッジとして残る
    assert len([e for e in g.edges if e.type == "tunnel"]) == 1


def test_include_sites_filters_and_keeps_clouds(doc):
    g = resolve_view(doc, _view(doc, "hq-physical"))
    ids = {n.id for n in g.nodes}
    assert "osk-rt01" not in ids and "ngy-rt01" not in ids
    assert {"hq-rt01", "hq-rt02", "hq-sw01", "ipvpn", "internet"} == ids


def test_cross_boundary_link_shows_external_device(doc):
    # 本社のみのビューに tunnel レイヤを足すと、対向の osk-rt01 が境界ノードになる
    view = _view(doc, "hq-physical").model_copy(
        update={"layers": ["lan-cable", "wan-circuit", "tunnel"]})
    g = resolve_view(doc, view)
    ext = [n for n in g.nodes if n.kind == "external-device"]
    assert len(ext) == 1 and ext[0].id == "osk-rt01"
    assert "大阪支店" in ext[0].label


def test_wan_circuit_edge_label_format(doc):
    g = resolve_view(doc, _view(doc, "physical-all"))
    wan = [e for e in g.edges if e.type == "wan-circuit"]
    labeled = next(e for e in wan if "IP-VPN" in (e.label or "") and "100M" in e.label)
    line1, line2 = labeled.label.split("\n")
    assert "\n" not in line1          # 回線情報は1行
    assert line2 == "(Gi0/0/0)"       # 2行目に機器側IF


def test_edges_oriented_wan_to_lan(doc):
    """全エッジがWAN側→LAN側に向き付けされる (ADR-0005)。"""
    g = resolve_view(doc, _view(doc, "physical-all"))
    # クラウドが端点のエッジは必ずクラウドが src
    for e in g.edges:
        if e.dst in ("ipvpn", "internet"):
            raise AssertionError(f"cloud must be src: {e.src} -- {e.dst}")
    # LAN配線はルーター(WAN距離1)が src、スイッチ(距離2)が dst
    lan = [e for e in g.edges if e.type == "lan-cable"]
    assert ("hq-rt01", "hq-sw01") in [(e.src, e.dst) for e in lan]
    # LAN配線のIF名は両端の機器側小ラベルに分散配置される
    rt_sw = next(e for e in lan if (e.src, e.dst) == ("hq-rt01", "hq-sw01"))
    assert rt_sw.src_label == "Gi0/0/1" and rt_sw.dst_label == "Gi1/0/1"
    # WAN回線のIF名は中央ラベルの2行目 (端点ラベルは使わない)
    wan = next(e for e in g.edges if e.src == "ipvpn" and e.dst == "hq-rt01")
    assert "(Gi0/0/0)" in wan.label
    assert wan.src_label is None and wan.dst_label is None


def test_orientation_fallback_without_clouds(doc):
    """クラウドを含まないビューではWAN境界機器を起点に向き付けする。"""
    g = resolve_view(doc, _view(doc, "logical-all"))
    tunnel = next(e for e in g.edges if e.type == "tunnel")
    # hq-rt02 / osk-rt01 はともにWAN境界(距離0)なので向きは安定 (入替なし)
    assert {tunnel.src, tunnel.dst} == {"hq-rt02", "osk-rt01"}


def test_d2_output_structure(doc):
    out = render_d2(resolve_view(doc, _view(doc, "physical-all")))
    assert "direction: down" in out
    assert "label.near: outside-top-left" in out  # 拠点タイトルを線の通り道から退避
    assert 's_hq: "本社"' in out
    assert "class: edge-wan-circuit" in out
    assert "shape: cloud" in out
    assert "source-arrowhead.label" in out or "target-arrowhead.label" in out
    # D2のキーに使えない文字が残っていないこと (ラベル・クラス定義以外の行頭キー)
    for line in out.splitlines():
        if "--" in line and "style" not in line:
            key = line.split(" -- ")[0].strip()
            assert all(c.isalnum() or c in "._" for c in key), key


def test_mermaid_output_structure(doc):
    out = render_mermaid(resolve_view(doc, _view(doc, "wan-overview")))
    assert out.startswith("flowchart TB")
    assert 'site__hq["本社"]' in out
    assert "linkStyle" in out and "stroke:#1a73e8" in out
    assert "((" in out  # cloud ノード
    # エッジ数と linkStyle の index 整合
    edge_lines = [l for l in out.splitlines() if " --- " in l or " ---|" in l]
    max_idx = max(int(i) for l in out.splitlines() if l.strip().startswith("linkStyle")
                  for i in l.strip().split()[1].split(","))
    assert max_idx == len(edge_lines) - 1


def test_all_views_render_without_error(doc):
    for view in doc.views:
        g = resolve_view(doc, view)
        assert render_d2(g) and render_mermaid(g)


def test_path_view_overlay(doc):
    g = resolve_view(doc, _view(doc, "path-ipvpn-fail"))
    nodes = {n.id: n for n in g.nodes}
    # 障害コンポーネントは failed、経路外は dim、経路上は通常
    assert nodes["ipvpn"].emphasis == "failed"
    assert nodes["internet"].emphasis == "dim"      # 経路外
    assert nodes["hq-rt01"].emphasis is None        # fallback経路上は淡色化しない
    assert nodes["hq-rt02"].emphasis is None
    # 経路エッジ: ホップ順に directed + seq
    path_edges = sorted((e for e in g.edges if e.emphasis == "path"), key=lambda e: e.seq)
    assert [(e.src, e.dst) for e in path_edges] == [
        ("hq-sw01", "hq-rt02"), ("hq-rt02", "osk-rt01"), ("osk-rt01", "osk-sw01")]
    assert all(e.directed for e in path_edges)
    assert "HSRP" in path_edges[0].label
    # 無効化された正常経路 (fallback_of) は disabled
    assert any(e.emphasis == "disabled" for e in g.edges)
    # 障害回線のエッジは failed
    assert any(e.emphasis == "failed" and e.circuit == "cct-ipvpn-hq" for e in g.edges)


def test_l3_hides_unused_interface_address():
    """linkにもsegmentにも使われていないIFのアドレスはL3表示に出さない。"""
    from nwdsl.model import Document
    raw = {
        "nwdsl": "0.1", "network": {"name": "t"},
        "sites": [{"id": "s1", "name": "S1"}],
        "devices": [
            {"id": "r1", "site": "s1", "role": "router", "interfaces": [
                {"name": "ge0", "ipv4": "10.0.0.1/30"},          # link使用 → 表示
                {"name": "ge9", "ipv4": "192.168.99.1/24"},      # 未使用 → 非表示
            ]},
            {"id": "r2", "site": "s1", "role": "router",
             "interfaces": [{"name": "ge0", "ipv4": "10.0.0.2/30"}]},
        ],
        "links": [{"type": "logical", "endpoints": ["r1:ge0", "r2:ge0"]}],
        "views": [{"id": "v", "title": "t", "layers": ["logical"]}],
    }
    d = Document.model_validate(raw)
    g = resolve_view(d, d.views[0])
    label = next(n for n in g.nodes if n.id == "r1").label
    assert "ge0: 10.0.0.1/30" in label
    assert "192.168.99.1" not in label


def test_logical_view_shows_l3_info(doc):
    """logicalレイヤを含むビューではIF IPv4とセグメントノードが自動表示される。"""
    g = resolve_view(doc, _view(doc, "logical-all"))
    nodes = {n.id: n for n in g.nodes}
    assert "Gi0/0/1: 10.1.0.2/24" in nodes["hq-rt01"].label   # IF一覧
    assert nodes["seg__hq-server"].kind == "segment"          # セグメントノード
    assert "VLAN 10 / 10.1.10.0/24" in nodes["seg__hq-server"].label
    # GW機器 (segment参照IFを持つhq-sw01) からセグメントへのエッジ
    seg_edges = [e for e in g.edges if e.type == "segment"]
    assert ("hq-sw01", "seg__hq-server") in [(e.src, e.dst) for e in seg_edges]
    # 物理ビューではL3は出ない (既定)
    g2 = resolve_view(doc, _view(doc, "physical-all"))
    assert all(n.kind != "segment" for n in g2.nodes)


def test_parallel_lan_cables_bundled():
    """LAG等の平行リンクは1本に束ねて ×N 表示になる。"""
    from nwdsl.model import Document
    raw = {
        "nwdsl": "0.1", "network": {"name": "t"},
        "sites": [{"id": "dc", "name": "DC"}],
        "devices": [
            {"id": "a", "site": "dc", "role": "l3switch",
             "interfaces": [{"name": f"e{i}"} for i in range(1, 5)]},
            {"id": "b", "site": "dc", "role": "l3switch",
             "interfaces": [{"name": f"e{i}"} for i in range(1, 5)]},
        ],
        "links": [{"type": "lan-cable", "endpoints": [f"a:e{i}", f"b:e{i}"]}
                  for i in range(1, 5)],
        "views": [{"id": "v", "title": "t", "layers": ["lan-cable"]}],
    }
    d = Document.model_validate(raw)
    g = resolve_view(d, d.views[0])
    assert len(g.edges) == 1
    assert g.edges[0].label == "×4"
    assert g.edges[0].src_label is None


def test_path_view_d2_output(doc):
    out = render_d2(resolve_view(doc, _view(doc, "path-ipvpn-fail")))
    assert "style.animated: true" in out
    assert " -> " in out          # 経路は矢印付き
    assert "✕障害" in out          # 障害ラベル
    assert "style.opacity: 0.3" in out  # 淡色化ノード
