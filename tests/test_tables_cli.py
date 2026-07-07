"""表生成と CLI のテスト。"""

from pathlib import Path

import pytest

from nwdsl.cli import main
from nwdsl.loader import load_document
from nwdsl.tables import (circuits_table, interfaces_table, render_tables,
                          segments_table, sites_table)

SAMPLE = str(Path(__file__).parent.parent / "examples" / "sample-corp" / "network.yaml")


@pytest.fixture(scope="module")
def doc():
    return load_document(SAMPLE)


def test_sites_table_counts_devices(doc):
    md = sites_table(doc)
    assert "| hq | 本社 | 東京都千代田区 | 6 |" in md


def test_interfaces_table_has_derived_peers(doc):
    md = interfaces_table(doc)
    # 接続先が links から逆引きされている
    assert "| hq-rt01 | Gi0/0/1 | 10.1.0.2/24 | - | hq-sw01 Gi1/0/1 |" in md
    # cloud への接続は網の名前で表示される
    assert "NTT Com IP-VPN網" in md


def test_circuits_table_has_landing_sites(doc):
    md = circuits_table(doc)
    assert "N-100001" in md
    assert "本社 hq-rt01 Gi0/0/0" in md  # 収容先の逆引き
    assert "利用中" in md


def test_segments_table_has_gateway(doc):
    md = segments_table(doc)
    assert "hq-sw01 Vlan10 (10.1.10.1/24)" in md


def test_render_tables_sections(doc):
    md = render_tables(doc, ["sites"])
    assert "## 拠点一覧" in md
    assert "## 機器一覧" not in md
    full = render_tables(doc)
    for title in ("拠点一覧", "機器一覧", "インターフェース一覧", "回線一覧",
                  "接続一覧", "セグメント一覧"):
        assert f"## {title}" in full


def test_cli_validate_ok(capsys):
    assert main(["validate", SAMPLE]) == 0
    assert "OK" in capsys.readouterr().out


def test_cli_validate_broken(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        'nwdsl: "0.1"\nnetwork: {name: x}\nsites: [{id: a, name: A}]\n'
        "devices: [{id: r1, site: nowhere}]\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == 1
    assert "ref.site" in capsys.readouterr().out


def test_cli_render_writes_files(tmp_path, capsys):
    assert main(["render", SAMPLE, "-o", str(tmp_path)]) == 0
    assert (tmp_path / "physical-all.d2").exists()
    assert (tmp_path / "physical-all.mmd").exists()
    assert (tmp_path / "wan-overview.d2").exists()


def test_cli_render_unknown_view(tmp_path):
    assert main(["render", SAMPLE, "-o", str(tmp_path), "--view", "ghost"]) == 1


def test_cli_tables_writes_file(tmp_path):
    out = tmp_path / "tables.md"
    assert main(["tables", SAMPLE, "-o", str(out)]) == 0
    assert "## 回線一覧" in out.read_text(encoding="utf-8")


def test_cli_schema(tmp_path):
    out = tmp_path / "schema.json"
    assert main(["schema", "-o", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert '"Document"' in text or '"nwdsl"' in text
