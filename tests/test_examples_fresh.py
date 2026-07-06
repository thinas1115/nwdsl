"""examples/ の成果物が現在のコードと一致するかを検証する。

graph.py/レンダラを変更した際に examples 再生成 (scripts/regen_examples.py) を
忘れると、README や generated-svg が古い図を参照したまま残ってしまう事故が
繰り返し発生したため、CIで機械的に検出する。

d2/mmd/tables.md/内蔵SVG (generated-svg/) はD2バイナリ不要で常に検証できる。
generated/*.svg (README埋め込み用、D2コンパイル済み) の鮮度検証だけは実際に
D2バイナリを呼ぶため、D2が無い環境ではスキップする (ADR-0008の方針に合わせる)。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from nwdsl.graph import resolve_view
from nwdsl.loader import load_document
from nwdsl.render_d2 import render_d2
from nwdsl.render_mermaid import render_mermaid
from nwdsl.render_svg import render_svg
from nwdsl.tables import render_tables
from nwdsl.webapp import find_d2

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIRS = sorted(p.parent for p in (ROOT / "examples").glob("*/network.yaml"))
STALE_HINT = "scripts/regen_examples.py を実行して再生成し、差分をコミットすること"


@pytest.mark.parametrize("example_dir", EXAMPLE_DIRS, ids=lambda p: p.name)
def test_d2_and_mermaid_up_to_date(example_dir: Path) -> None:
    gen_dir = example_dir / "generated"
    if not gen_dir.is_dir():
        pytest.skip("generated/ なし")
    doc = load_document(example_dir / "network.yaml")

    tables_path = gen_dir / "tables.md"
    if tables_path.exists():
        assert tables_path.read_text(encoding="utf-8") == render_tables(doc), (
            f"{tables_path} が古い。{STALE_HINT}")

    for view in doc.views:
        graph = resolve_view(doc, view)
        d2_path = gen_dir / f"{view.id}.d2"
        mmd_path = gen_dir / f"{view.id}.mmd"
        if d2_path.exists():
            assert d2_path.read_text(encoding="utf-8") == render_d2(graph), (
                f"{d2_path} が古い。{STALE_HINT}")
        if mmd_path.exists():
            assert mmd_path.read_text(encoding="utf-8") == render_mermaid(graph), (
                f"{mmd_path} が古い。{STALE_HINT}")


@pytest.mark.parametrize("example_dir", EXAMPLE_DIRS, ids=lambda p: p.name)
def test_builtin_svg_up_to_date(example_dir: Path) -> None:
    svg_dir = example_dir / "generated-svg"
    if not svg_dir.is_dir():
        pytest.skip("generated-svg/ なし")
    doc = load_document(example_dir / "network.yaml")

    for view in doc.views:
        svg_path = svg_dir / f"{view.id}.svg"
        if not svg_path.exists():
            continue
        graph = resolve_view(doc, view)
        assert svg_path.read_text(encoding="utf-8") == render_svg(graph), (
            f"{svg_path} が古い(内蔵SVGエンジン)。{STALE_HINT}")


@pytest.mark.parametrize("example_dir", EXAMPLE_DIRS, ids=lambda p: p.name)
def test_d2_compiled_svg_up_to_date(example_dir: Path) -> None:
    d2_bin = find_d2()
    if d2_bin is None:
        pytest.skip("D2バイナリが見つからないためスキップ (ADR-0008: D2なし環境は内蔵SVGにフォールバック)")
    gen_dir = example_dir / "generated"
    if not gen_dir.is_dir():
        pytest.skip("generated/ なし")
    doc = load_document(example_dir / "network.yaml")

    for view in doc.views:
        svg_path = gen_dir / f"{view.id}.svg"
        if not svg_path.exists():
            continue
        graph = resolve_view(doc, view)
        d2_source = render_d2(graph)
        with tempfile.TemporaryDirectory(prefix="nwdsl-freshness-") as tmp:
            src = Path(tmp) / "view.d2"
            out = Path(tmp) / "view.svg"
            src.write_text(d2_source, encoding="utf-8")
            proc = subprocess.run(
                [str(d2_bin), "--layout=elk", str(src), str(out)],
                capture_output=True, text=True, timeout=60)
            assert proc.returncode == 0, f"d2 コンパイル失敗: {proc.stderr[-500:]}"
            fresh = out.read_text(encoding="utf-8")
        assert fresh == svg_path.read_text(encoding="utf-8"), (
            f"{svg_path} が古い(D2コンパイル済み、README埋め込み用)。{STALE_HINT}")
