"""nwdsl CLI。

  nwdsl validate network.yaml            構文+意味的整合性の検査
  nwdsl render network.yaml -o out/      全ビューを .d2/.mmd に書き出し
  nwdsl tables network.yaml -o tables.md 設計書向けMarkdown表の生成
  nwdsl schema -o nwdsl.schema.json      JSON Schema の出力 (エディタ補完用)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .graph import resolve_view
from .loader import LoadError, load_document
from .model import Document
from .render_d2 import render_d2
from .render_mermaid import render_mermaid
from .tables import SECTION_IDS, render_tables
from .validate import has_errors, validate_document


def _load_or_exit(path: str) -> Document:
    try:
        return load_document(path)
    except LoadError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"ファイルが見つかりません: {path}", file=sys.stderr)
        sys.exit(1)


def cmd_validate(args: argparse.Namespace) -> int:
    doc = _load_or_exit(args.file)
    issues = validate_document(doc)
    for issue in issues:
        print(issue)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    ng = has_errors(issues) or (args.strict and warnings)
    print(f"{'NG' if ng else 'OK'}: エラー {len(errors)}件 / 警告 {len(warnings)}件")
    return 1 if ng else 0


def cmd_render(args: argparse.Namespace) -> int:
    doc = _load_or_exit(args.file)
    issues = validate_document(doc)
    if has_errors(issues):
        for issue in issues:
            print(issue, file=sys.stderr)
        print("バリデーションエラーがあるため描画を中止しました", file=sys.stderr)
        return 1
    if not doc.views:
        print("views が定義されていません", file=sys.stderr)
        return 1
    view_ids = {v.id for v in doc.views}
    targets = args.view or sorted(view_ids)
    unknown = [v for v in targets if v not in view_ids]
    if unknown:
        print(f"未定義のビュー: {', '.join(unknown)} (定義済み: {', '.join(sorted(view_ids))})",
              file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    formats = ["d2", "mermaid"] if args.format == "all" else [args.format]
    for view in doc.views:
        if view.id not in targets:
            continue
        graph = resolve_view(doc, view)
        if "d2" in formats:
            path = out_dir / f"{view.id}.d2"
            path.write_text(render_d2(graph), encoding="utf-8")
            print(f"wrote {path}")
        if "mermaid" in formats:
            path = out_dir / f"{view.id}.mmd"
            path.write_text(render_mermaid(graph), encoding="utf-8")
            print(f"wrote {path}")
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    doc = _load_or_exit(args.file)
    issues = validate_document(doc)
    if has_errors(issues):
        for issue in issues:
            print(issue, file=sys.stderr)
        print("バリデーションエラーがあるため表生成を中止しました", file=sys.stderr)
        return 1
    md = render_tables(doc, args.section or None)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .webapp import serve
    serve(port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    schema = json.dumps(Document.model_json_schema(), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(schema + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(schema)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nwdsl", description="ネットワーク構成記述DSLツール")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="構文と整合性を検査する")
    p.add_argument("file")
    p.add_argument("--strict", action="store_true", help="警告もエラー扱いにする")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("render", help="ビュー定義に従って図ソース (.d2/.mmd) を書き出す")
    p.add_argument("file")
    p.add_argument("-o", "--out", default="diagrams", help="出力ディレクトリ (default: diagrams)")
    p.add_argument("--view", action="append", help="対象ビューID (複数指定可、省略時は全ビュー)")
    p.add_argument("--format", choices=["d2", "mermaid", "all"], default="all")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("tables", help="設計書向けMarkdown表を生成する")
    p.add_argument("file")
    p.add_argument("-o", "--out", help="出力ファイル (省略時は標準出力)")
    p.add_argument("--section", action="append", choices=SECTION_IDS,
                   help="出力する表 (複数指定可、省略時は全部)")
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser("schema", help="JSON Schema を出力する")
    p.add_argument("-o", "--out", help="出力ファイル (省略時は標準出力)")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("serve", help="ブラウザで試せる playground を起動する")
    p.add_argument("--port", type=int, default=8321)
    p.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
