"""nwdsl playground: DSLをブラウザで試すローカルWebサーバー。

`nwdsl serve` で起動する。標準ライブラリのみで実装し、127.0.0.1 にのみ bind する。
検証・描画は CLI と同じコード (validate/graph/render_d2) + D2 バイナリを使う。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from pydantic import ValidationError

from .graph import resolve_view
from .model import Document
from .render_d2 import render_d2
from .render_mermaid import render_mermaid
from .tables import render_tables
from .validate import has_errors, validate_document

_MINIMAL_SAMPLE = """\
nwdsl: "0.1"

network:
  name: my-first-network

sites:
  - id: hq
    name: 本社

devices:
  - id: hq-rt01
    site: hq
    role: router
    platform: Cisco ISR1100
    interfaces:
      - name: Gi0/0/0
        description: WANアクセス回線
      - name: Gi0/1/0
  - id: hq-sw01
    site: hq
    role: l2switch
    platform: Cisco Catalyst 1000
    interfaces:
      - name: Gi1/0/1

clouds:
  - id: internet
    name: インターネット
    kind: internet

circuits:
  - id: cct-inet-hq
    provider: NTT東日本
    service: フレッツ光ネクスト + OCN
    bandwidth: 1G

links:
  - type: lan-cable
    endpoints: ["hq-rt01:Gi0/1/0", "hq-sw01:Gi1/0/1"]
  - type: wan-circuit
    endpoints: ["hq-rt01:Gi0/0/0", "internet"]
    circuit: cct-inet-hq

views:
  - id: physical
    title: 物理構成図
    layers: [lan-cable, wan-circuit]
"""


def find_d2() -> Path | None:
    """D2 バイナリを探す: PATH → リポジトリ .tools/ の順。"""
    on_path = shutil.which("d2")
    if on_path:
        return Path(on_path)
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        for hit in sorted(base.glob(".tools/d2-*/bin/d2*")):
            if hit.suffix in ("", ".exe"):
                return hit
    return None


def _repo_dir(name: str) -> Path | None:
    """docs/ や examples/ を cwd → パッケージ親 の順で探す。"""
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        candidate = base / name
        if candidate.is_dir():
            return candidate
    return None


def _samples() -> dict[str, Path | None]:
    result: dict[str, Path | None] = {"minimal": None}
    examples = _repo_dir("examples")
    if examples:
        for entry in sorted(examples.iterdir()):
            network = entry / "network.yaml"
            if network.is_file():
                result[entry.name] = network
    return result


_DOC_ORDER = ["tutorial.md", "reference.md", "openspec-integration.md"]


def _doc_title(path: Path) -> str:
    """先頭の H1 をタイトルとして使う (無ければファイル名)。"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:10]:
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.stem


def _doc_list() -> list[dict[str, str]]:
    docs = _repo_dir("docs")
    if not docs:
        return []
    entries: list[dict[str, str]] = []
    for pattern in ("*.md", "adr/*.md"):
        for path in sorted(docs.glob(pattern)):
            rel = path.relative_to(docs).as_posix()
            entries.append({"name": rel, "title": _doc_title(path)})
    guide_rank = {name: i for i, name in enumerate(_DOC_ORDER)}
    entries.sort(key=lambda e: (e["name"].startswith("adr/"),
                                guide_rank.get(e["name"], 99), e["name"]))
    return entries


def _render_svg(d2_source: str, d2_bin: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="nwdsl-play-") as tmp:
        src = Path(tmp) / "view.d2"
        out = Path(tmp) / "view.svg"
        src.write_text(d2_source, encoding="utf-8")
        proc = subprocess.run(
            [str(d2_bin), "--layout=elk", str(src), str(out)],
            capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(f"d2 の実行に失敗しました:\n{proc.stderr[-2000:]}")
        return out.read_text(encoding="utf-8")


def handle_render(payload: dict, d2_bin: Path | None) -> dict:
    """POST /api/render の本体。テストから直接呼べるよう分離してある。"""
    source = payload.get("yaml", "")
    try:
        raw = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        return {"ok": False, "errors": [f"YAML構文エラー: {exc}"]}
    if not isinstance(raw, dict):
        return {"ok": False, "errors": ["トップレベルはマッピングである必要があります"]}
    try:
        doc = Document.model_validate(raw)
    except ValidationError as exc:
        errors = [f"{' > '.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return {"ok": False, "errors": errors}

    issues = [{"level": i.level, "code": i.code, "message": i.message}
              for i in validate_document(doc)]
    result: dict = {
        "ok": True,
        "issues": issues,
        "views": [{"id": v.id, "title": v.title, "type": v.type} for v in doc.views],
        "svg": None, "d2": None, "mermaid": None, "tables": None, "view": None,
        "d2_available": d2_bin is not None,
    }
    if any(i["level"] == "error" for i in issues):
        return result

    result["tables"] = render_tables(doc)
    if not doc.views:
        result["errors"] = ["views が定義されていません (図を描くには views を1つ以上定義してください)"]
        return result

    view_id = payload.get("view") or doc.views[0].id
    view = next((v for v in doc.views if v.id == view_id), doc.views[0])
    result["view"] = view.id
    graph = resolve_view(doc, view)
    result["d2"] = render_d2(graph)
    result["mermaid"] = render_mermaid(graph)
    engine = payload.get("engine") or "auto"
    use_d2 = d2_bin is not None and engine in ("auto", "d2")
    if use_d2:
        try:
            result["svg"] = _render_svg(result["d2"], d2_bin)
            result["engine"] = "d2"
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            result["errors"] = [str(exc)]
    else:
        from .render_svg import render_svg
        result["svg"] = render_svg(graph)
        result["engine"] = "svg"
    return result


class PlaygroundHandler(BaseHTTPRequestHandler):
    d2_bin: Path | None = None

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj: object, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler の規約)
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            page = (Path(__file__).parent / "static" / "playground.html").read_bytes()
            self._send(200, page, "text/html; charset=utf-8")
        elif url.path == "/api/samples":
            self._send_json({"samples": list(_samples().keys())})
        elif url.path == "/api/sample":
            name = parse_qs(url.query).get("name", ["minimal"])[0]
            path = _samples().get(name)
            text = path.read_text(encoding="utf-8") if path else _MINIMAL_SAMPLE
            self._send_json({"name": name, "yaml": text})
        elif url.path == "/api/docs":
            self._send_json({"docs": _doc_list()})
        elif url.path == "/api/doc":
            name = parse_qs(url.query).get("name", [""])[0]
            if name not in {d["name"] for d in _doc_list()}:
                self._send_json({"error": f"unknown doc: {name}"}, 404)
                return
            docs = _repo_dir("docs")
            text = (docs / name).read_text(encoding="utf-8")
            self._send_json({"name": name, "markdown": text})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/render":
            self._send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"ok": False, "errors": ["不正なリクエストです"]}, 400)
            return
        self._send_json(handle_render(payload, self.d2_bin))

    def log_message(self, fmt: str, *args) -> None:  # アクセスログは静かに
        pass


def serve(port: int = 8321, open_browser: bool = True) -> None:
    PlaygroundHandler.d2_bin = find_d2()
    server = ThreadingHTTPServer(("127.0.0.1", port), PlaygroundHandler)
    url = f"http://127.0.0.1:{port}/"
    d2_note = PlaygroundHandler.d2_bin or "見つかりません (SVGプレビュー無効。D2を導入してください)"
    print(f"nwdsl playground: {url}")
    print(f"D2: {d2_note}")
    print("Ctrl+C で停止します")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("停止しました")
