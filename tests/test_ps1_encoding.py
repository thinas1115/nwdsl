"""PowerShellスクリプト(.ps1)がUTF-8 BOM付きで保存されているかを検証する。

Windows PowerShell 5.1 (pwsh 7+ ではなくデフォルトの powershell.exe) はBOM無し
UTF-8の.ps1をシステムのANSIコードページ(日本語環境ではShift-JIS)として読むため、
日本語コメント/メッセージが文字化けする。BOM無しの.ps1が繰り返しコミットされた
ため、CIで機械的に検出する。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1_FILES = sorted(ROOT.glob("**/*.ps1"))
PS1_FILES = [p for p in PS1_FILES
            if ".venv" not in p.parts and ".git" not in p.parts]
UTF8_BOM = b"\xef\xbb\xbf"


@pytest.mark.parametrize("path", PS1_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_ps1_has_utf8_bom(path: Path) -> None:
    head = path.read_bytes()[:3]
    assert head == UTF8_BOM, (
        f"{path.relative_to(ROOT)} にUTF-8 BOMが無い。Windows PowerShell 5.1で"
        "日本語が文字化けする。UTF-8(BOM付き)で保存し直すこと")
