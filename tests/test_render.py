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


def test_wan_circuit_edge_label_and_endpoint_labels(doc):
    g = resolve_view(doc, _view(doc, "physical-all"))
    wan = [e for e in g.edges if e.type == "wan-circuit"]
    labeled = next(e for e in wan if "IP-VPN" in (e.label or "") and "100M" in e.label)
    assert "\n" not in labeled.label  # 回線ラベルは1行
    assert "Gi0/0/0" in (labeled.src_label or "") or "Gi0/0/0" in (labeled.dst_label or "")


def test_d2_output_structure(doc):
    out = render_d2(resolve_view(doc, _view(doc, "physical-all")))
    assert "direction: right" in out
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
    assert out.startswith("flowchart LR")
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
