"""YAML ファイルの読み込みと構文レベル検証。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .model import Document


class LoadError(Exception):
    """YAML 構文エラーまたはスキーマ違反。人間可読なメッセージを持つ。"""


def load_document(path: str | Path) -> Document:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LoadError(f"YAML構文エラー: {path}\n{exc}") from exc
    if not isinstance(raw, dict):
        raise LoadError(f"トップレベルはマッピングである必要があります: {path}")
    try:
        return Document.model_validate(raw)
    except ValidationError as exc:
        lines = [f"スキーマ違反: {path} ({exc.error_count()}件)"]
        for err in exc.errors():
            loc = " > ".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        raise LoadError("\n".join(lines)) from exc
