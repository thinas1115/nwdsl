<#
D2 (v0.7.1, Windows amd64) を .tools/ にダウンロードして展開する。
.tools/ は .gitignore 対象のため、clone直後は誰の環境にも存在しない。

D2は無くても内蔵SVGエンジンでplaygroundは動く (ADR-0008)。ELKレイアウトの
D2出力やSVGコンパイルを使いたい場合だけ実行すればよい (必須ではない)。

使い方: .\scripts\install_d2.ps1
#>

$ErrorActionPreference = "Stop"

$Version = "v0.7.1"
$Url = "https://github.com/terrastruct/d2/releases/download/$Version/d2-$Version-windows-amd64.tar.gz"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $RepoRoot ".tools"
$ArchivePath = Join-Path $ToolsDir "d2.tar.gz"
$BinPath = Join-Path $ToolsDir "d2-$Version\bin\d2.exe"

if (Test-Path $BinPath) {
    Write-Host "既にインストール済みです: $BinPath"
    exit 0
}

New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

Write-Host "ダウンロード中: $Url"
Invoke-WebRequest -Uri $Url -OutFile $ArchivePath

Write-Host "展開中: $ToolsDir"
tar -xzf $ArchivePath -C $ToolsDir

if (Test-Path $BinPath) {
    Write-Host "完了: $BinPath"
} else {
    Write-Error "展開後に d2.exe が見つかりません: $BinPath"
}
