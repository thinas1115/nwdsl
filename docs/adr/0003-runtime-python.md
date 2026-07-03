# ADR-0003: 実行環境として Python を採用

- Status: Accepted
- Date: 2026-07-04
- Phase: 0 (調査)

## Context

バリデータ・レンダラ・表生成 CLI の実装言語を Python / Node.js から選定する。

## Decision

**Python 3.11+ を採用する**(開発環境は 3.13 で検証)。

| 観点 | Python | Node.js |
|---|---|---|
| スキーマ検証 | **pydantic v2**: 型定義=スキーマ=バリデーションが一体。JSON Schema をモデルから自動生成できる | zod / ajv。同等のことは可能 |
| NW 系エコシステム | netmiko / napalm / nornir / ntc-templates 等、将来の実機連携(AWX 経由の逆生成)で使う資産が Python に集中 | 乏しい |
| ユーザー環境 | 既存の業務スクリプト資産が Python。Python 3.13 導入済み | Node 18 (EOL 済み) のみ |
| YAML | PyYAML / ruamel.yaml で安定 | 同等 |
| CLI 配布 | pip インストール一発。uv も利用可能 | npm |

決め手は (1) pydantic による「モデル定義から JSON Schema・ドキュメントを導出できる」単一ソース性、(2) 将来の実機連携ライブラリが Python に集中していること、(3) ユーザーの既存環境。

## 依存ライブラリ方針

- **pydantic v2**: スキーマ定義・検証の中核
- **PyYAML**: YAML ロード(safe_load のみ使用)
- **pytest**: テスト
- 描画は外部プロセス(D2 バイナリ)に委譲し、Python 側に描画ライブラリは持たない

## Consequences

- JSON Schema は pydantic モデルから自動生成し、エディタ補完(YAML Language Server)に提供できる
- D2 バイナリは別途導入が必要(単一バイナリなので導入は軽い)。D2 がない環境でも Mermaid 出力と表生成は動作する
