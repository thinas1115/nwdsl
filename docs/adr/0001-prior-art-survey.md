# ADR-0001: 先行事例調査と流用判断

- Status: Accepted
- Date: 2026-07-04
- Phase: 0 (調査)

## Context

ネットワーク構成の構造化記述に適した既存フォーマットがあれば新DSLは作らない、という前提で先行事例を調査した。評価軸は以下の6つ。

- **A. 意味情報**: 線種の区別(構内LANケーブル / キャリア契約回線 / 論理隣接 / VPNトンネル)と業務エンティティ(拠点・回線契約・機器・IF)を表現できるか
- **B. ビュー制御**: 1ソースから範囲・抽象度を変えて複数の図を描き分けられるか
- **C. AIパース性**: スキーマが明確でAIが確実に読み書きできるか
- **D. 表生成適性**: 拠点一覧・回線一覧などの表を導出できるか
- **E. 整合性検査**: 参照整合性・意味的整合性を検査できる構造か
- **F. コスト**: 学習コスト・ツールチェーンの導入しやすさ

## 調査結果と判断

### NetBox データモデル — 判断: **参考(モデル設計を強く流用)**

- 確認元: https://netboxlabs.com/docs/netbox/models/circuits/circuit/
- Site / Device / Interface / Cable / Circuit を独立エンティティとして分離。特に **Cable(構内の物理結線)と Circuit(キャリアから購入する回線契約)を別モデルにし、Circuit は Provider・回線ID・種別・帯域(commit rate)・両端の Termination を持つ**という分離思想は、本プロジェクトの課題2(線の意味の区別)への直接の答えになっている。
- ただし NetBox は DB を持つ Web アプリケーションであり、Git 管理できるファイルベース DSL ではない(A◎ B× C△ D◎ E◎ F×)。運用に DB サーバーが必要になり、「設計書の単一ソースを Git リポジトリに置く」という利用形態に合わない。
- → **エンティティ分割(Site/Device/Interface/Circuit)と Cable/Circuit 分離の思想を DSL のモデル設計に流用**する。NetBox 本体は採用しない。

### netlab (netsim-tools) — 判断: **不採用(グラフ出力の実績のみ参考)**

- 確認元: https://netlab.tools/ , https://blog.ipspace.net/2021/09/netsim-tools-graphs/
- 仮想ラボ構築の自動化ツール。トポロジ YAML は nodes/links 中心で簡潔だが、拠点・キャリア回線契約・図の描き分けの概念がない。ラボ用途に最適化されており、本番構成のドキュメント記述には設計目的が異なる(A× B× C○ D× E△ F○)。
- netlab が Graphviz / D2 形式のグラフを出力する実績は、D2 を NW 図の出力先とする判断の裏付けとして参考にした。

### Containerlab topology YAML — 判断: **不採用(将来の相互変換先として意識)**

- 確認元: https://containerlab.dev/manual/topo-def-file/
- `name` + `topology.nodes` + `topology.links(endpoints: ["node:if", ...])` というシンプルな形式。拠点・WAN 回線の抽象がなく、単一デプロイメント内のコンテナラボ記述に特化(A× B× C○ D× E△ F○)。
- ただし links の `endpoints: ["device:interface", "device:interface"]` という端点表現は簡潔で優れており、**DSL の接続記述の記法として借用**する。将来の「DSL → clab topo 生成」(スコープ外)でも対応が取りやすい。

### Mermaid — 判断: **部分採用(セカンダリ出力先)**

- 確認元: https://mermaid.js.org/syntax/architecture.html
- architecture 図(v11.1+)はグループ化はできるが**エッジラベル非対応**で、回線名・IF名を線に添えられず NW 図には不足。flowchart 記法ならエッジラベル・subgraph が使える。
- レイアウト制御が弱く物理構成図の品質は D2 に劣るが、**GitHub / Obsidian がネイティブ描画する**という配布上の決定的な利点がある(A△ B× C○ D- E- F◎)。
- → DSL の入力形式としては不採用。**レンダラのセカンダリ出力先(flowchart 記法)として採用**。

### D2 — 判断: **採用(プライマリ出力先)**

- 確認元: https://d2lang.com/ , https://github.com/terrastruct/d2/releases
- コンテナ(ネスト可)・エッジラベル・classes によるスタイル一括定義・実線/破線/太さの制御を備え、dagre と ELK レイアウトエンジンを単一バイナリに同梱。Windows へは tar.gz 展開のみで導入できる(管理者権限不要)。
- **本環境で v0.7.1 を実際に導入し、拠点コンテナ2つ+機器5台+3種類の線種(LAN/キャリア回線/トンネル)+日本語ラベルの描画を検証済み**。品質は設計書掲載レベル。
- DSL の入力形式としては不採用(意味情報を持てない、描画専用言語)。**レンダラのプライマリ出力先として採用**。

### IETF RFC 8345 (YANG ネットワークトポロジモデル) — 判断: **参考(レイヤリング思想のみ)**

- ネットワークを network / node / link / termination-point で表し、論理ネットワークが下位ネットワークに `supporting-network` で紐づく階層化思想は「物理の上に論理を重ねる」の標準的な定式化として参考にした。ただし YANG/XML ベースで人間の記述性が低く、拠点・回線契約など業務エンティティもない。

### Graphviz (DOT) — 判断: **不採用**

- レイアウトアルゴリズムは実績があるが、コンテナ表現が cluster 頼みで制御しづらく、Windows への導入にインストーラが必要。D2(ELK 同梱・単一バイナリ)で代替できるため不採用。

### drawthe.net / nwdiag 等の NW 図特化ツール — 判断: **不採用**

- 座標指定ベース(drawthe.net)や開発停滞(nwdiag)であり、「データモデルから図を導出する」方向性と合わない。見た目制御を DSL 側に持ち込みすぎない、という反面教師として参考。

## Decision

**要件(特に A: 線種の意味区別、B: ビュー制御、D: 表生成)をすべて満たす既存フォーマットは存在しない。** NetBox のエンティティモデルを参考にした新規 YAML ベース DSL を策定し、D2(主)/ Mermaid(従)に変換するレンダラを実装する。詳細は [ADR-0002](0002-new-yaml-dsl.md)、[ADR-0003](0003-runtime-python.md) を参照。

## Consequences

- 車輪の再発明になる部分は「スキーマ定義」のみで、レイアウト計算・描画は D2/Mermaid に完全委譲する
- NetBox 利用経験者にはエンティティ名(site/device/interface/circuit)が直感的に対応する
- 将来の Containerlab topo 生成・NetBox からの逆生成の対応関係が明確
