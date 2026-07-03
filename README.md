# nwdsl — ネットワーク構成記述 DSL

ネットワーク構成(拠点・機器・回線・接続)を **1つの YAML ソース**で記述し、そこから

- 物理構成図 / 論理構成図(D2 → SVG/PNG、Mermaid)
- 設計書向けの表(拠点一覧・機器一覧・回線一覧・接続一覧)

を生成するためのスキーマと CLI ツール。図と表が同一ソースから導出されるため、設計ドキュメント間の不整合が構造的に発生しない。

> ステータス: 開発中。設計判断は [docs/adr/](docs/adr/) を参照。

## なぜ作ったか

- 既存ダイアグラム DSL(Mermaid 等)は「全社概要図/拠点詳細図/物理図/論理図」の描き分けに必要な意味情報を持てない
- 機器間の「線」には複数の意味がある(構内 LAN ケーブル / キャリア契約回線 / 論理隣接 / VPN トンネル)が、これを区別できる記述形式がない
- 拠点・回線契約・機器といった業務エンティティを AI が確実にパースできる形式で保持し、OpenSpec による仕様駆動ドキュメント生成の入力にしたい

先行事例(NetBox / netlab / Containerlab / D2 / Mermaid / RFC 8345)の調査と「新 DSL を作る」判断の根拠は [ADR-0001](docs/adr/0001-prior-art-survey.md) / [ADR-0002](docs/adr/0002-new-yaml-dsl.md) を参照。

## ドキュメント

- [docs/tutorial.md](docs/tutorial.md) — チュートリアル(最小構成から段階的に)
- [docs/reference.md](docs/reference.md) — 全フィールドリファレンス
- [docs/adr/](docs/adr/) — 設計判断記録
- [docs/openspec-integration.md](docs/openspec-integration.md) — OpenSpec 統合ガイド
- [examples/](examples/) — サンプル構成
