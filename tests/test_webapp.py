"""playground サーバーの描画APIロジックのテスト (HTTPを介さず直接呼ぶ)。"""

from nwdsl.webapp import _MINIMAL_SAMPLE, handle_render


def test_render_minimal_sample_without_d2():
    r = handle_render({"yaml": _MINIMAL_SAMPLE}, d2_bin=None)
    assert r["ok"] is True
    assert r["issues"] == []
    assert r["view"] == "physical"
    assert "direction: down" in r["d2"]
    assert r["mermaid"].startswith("flowchart TB")
    assert "## 回線一覧" in r["tables"]
    assert r["svg"] is None and r["d2_available"] is False


def test_render_yaml_syntax_error():
    r = handle_render({"yaml": "nwdsl: [unclosed"}, d2_bin=None)
    assert r["ok"] is False
    assert any("YAML構文エラー" in e for e in r["errors"])


def test_render_schema_error():
    r = handle_render({"yaml": 'nwdsl: "0.1"\nnetwork: {name: x}\nbogus_field: 1\n'},
                      d2_bin=None)
    assert r["ok"] is False
    assert any("bogus_field" in e for e in r["errors"])


def test_render_semantic_error_blocks_diagram():
    src = ('nwdsl: "0.1"\nnetwork: {name: x}\n'
           "sites: [{id: hq, name: HQ}]\n"
           "devices: [{id: r1, site: nowhere}]\n"
           "views: [{id: v, title: t}]\n")
    r = handle_render({"yaml": src}, d2_bin=None)
    assert r["ok"] is True
    assert any(i["level"] == "error" for i in r["issues"])
    assert r["d2"] is None and r["tables"] is None


def test_render_view_selection():
    src = _MINIMAL_SAMPLE + (
        "  - id: second\n    title: 2つ目のビュー\n    layers: [wan-circuit]\n")
    r = handle_render({"yaml": src, "view": "second"}, d2_bin=None)
    assert r["view"] == "second"
    assert len(r["views"]) == 2
