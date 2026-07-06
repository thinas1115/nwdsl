"""examples/ 配下の全成果物 (d2/mmd/tables.md/内蔵SVG/D2コンパイル済みSVG) を
現在のコードで一括再生成する。

レンダラ/graph.py を変更したら、コミット前に必ずこれを実行すること。
`generated/`(d2コンパイル込み)・`generated-svg/`(内蔵SVGエンジン)のどちらか
一方だけを再生成して他方が古いまま残る事故が繰り返されたため、1コマンドに
まとめてある (tests/test_examples_fresh.py が再生成漏れを検出する)。

使い方: python scripts/regen_examples.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nwdsl.loader import load_document  # noqa: E402
from nwdsl.graph import resolve_view  # noqa: E402
from nwdsl.render_d2 import render_d2  # noqa: E402
from nwdsl.render_mermaid import render_mermaid  # noqa: E402
from nwdsl.render_svg import render_svg  # noqa: E402
from nwdsl.tables import render_tables  # noqa: E402
from nwdsl.webapp import find_d2  # noqa: E402


def regen_example(example_dir: Path, d2_bin: Path | None) -> None:
    yaml_file = example_dir / "network.yaml"
    doc = load_document(yaml_file)
    gen_dir = example_dir / "generated"
    svg_dir = example_dir / "generated-svg"
    gen_dir.mkdir(exist_ok=True)

    tables_path = gen_dir / "tables.md"
    if tables_path.exists():
        tables_path.write_text(render_tables(doc), encoding="utf-8")

    for view in doc.views:
        graph = resolve_view(doc, view)
        d2_source = render_d2(graph)
        mmd_source = render_mermaid(graph)
        (gen_dir / f"{view.id}.d2").write_text(d2_source, encoding="utf-8")
        (gen_dir / f"{view.id}.mmd").write_text(mmd_source, encoding="utf-8")

        # 内蔵SVGエンジン (D2バイナリ不要、常に再生成可能)
        builtin_svg_path = svg_dir / f"{view.id}.svg"
        if svg_dir.is_dir():
            builtin_svg_path.write_text(render_svg(graph), encoding="utf-8")

        # README埋め込み用の D2 コンパイル済み SVG (README が参照するファイルだけ更新)
        compiled_svg_path = gen_dir / f"{view.id}.svg"
        if compiled_svg_path.exists() and d2_bin is not None:
            proc = subprocess.run(
                [str(d2_bin), "--layout=elk", str(gen_dir / f"{view.id}.d2"),
                 str(compiled_svg_path)],
                capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                print(f"  ! {compiled_svg_path}: d2 compile failed\n{proc.stderr[-500:]}")


def main() -> None:
    d2_bin = find_d2()
    if d2_bin is None:
        print("警告: D2バイナリが見つかりません。generated/*.svg (README埋め込み用) はスキップします。")
    else:
        print(f"D2: {d2_bin}")

    for yaml_file in sorted((ROOT / "examples").glob("*/network.yaml")):
        example_dir = yaml_file.parent
        print(f"=== {example_dir.name} ===")
        regen_example(example_dir, d2_bin)

    print("完了。`git status` で差分を確認してください。")


if __name__ == "__main__":
    main()
