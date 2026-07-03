# Phase 0 調査ログ(検討過程の記録)

ADR には結論と根拠の要約のみを残しているため、途中の検討内容・実機検証の詳細をここに記録する。

- Date: 2026-07-04
- 関連: [ADR-0001](../adr/0001-prior-art-survey.md), [ADR-0002](../adr/0002-new-yaml-dsl.md), [ADR-0003](../adr/0003-runtime-python.md)

## 1. 環境確認の結果

| ツール | 状態 |
|---|---|
| Python | 3.13.3 ✓ |
| Node.js | v18.18.2 (EOL 済み) |
| git | 2.32.0.windows.1 ✓ |
| d2 / dot (Graphviz) / mmdc (Mermaid CLI) | いずれも未導入 → D2 のみ後から導入 |
| uv / pip | ✓ |

- リポジトリ設置場所は Obsidian Work Vault 内も検討したが、venv / node_modules / .git が Obsidian Sync の同期対象になる懸念から `d:\thinas\documents\programing\nw-config-dsl` に決定(ユーザー確認済み)

## 2. 調査で確認した一次情報の要点

### NetBox Circuit モデル (netboxlabs.com/docs)

- Circuit のフィールド: Provider / Provider Account / Circuit ID(プロバイダ内で一意)/ Circuit Type("Internet access", "MPLS/VPN" 等ユーザー定義)/ Status(Planned→Active→Decommissioned のライフサイクル)/ Commit Rate(kbps)/ Installation・Termination Date
- 「Circuit は拠点間を長距離で結ぶ point-to-point 接続を表す」と明記。**構内配線(Cable)とキャリア購入回線(Circuit)を別エンティティにする**設計が、本 DSL の link type 分離の直接の元ネタ
- Status のライフサイクル管理は本 DSL でも `planned / active / decommissioned` として採り入れる価値あり(新旧回線の移行期を1ファイルで表現できる)

### netlab

- ラボ構築専用。本番ドキュメント用途ではないと公式が明確に位置づけ
- ただし `netlab graph` が Graphviz と **D2** の両形式を出力する(ipSpace blog で確認)。「NW トポロジ→D2」は実績のある変換パスだと確認できたのが収穫

### Containerlab topo

- `endpoints: ["r1:eth1", "r2:eth1"]` の端点記法が簡潔で借用価値あり
- links には brief/extended の2形式があり、extended では MAC/IP/MTU/vars/labels を持てる → 「まず簡潔に書けて、必要なら詳細化できる」二段構えは DSL 設計の参考になる
- 検証環境 clab-lab1-r1/r2/r3 (VyOS) との将来の相互変換を考えると、interface 名を実名(eth0, ge-0/0/0)で持つ設計が無難

### Mermaid

- architecture 図は v11.1+ で stable だが**エッジラベルを付けられない**のが NW 図として致命的
- flowchart なら `A -- "label" --> B` でエッジラベル可、subgraph で拠点グルーピング可、linkStyle で線種制御可 → セカンダリ出力は flowchart 記法を使う
- 兄弟ノードが重なるレイアウト問題が既知(v11.16+ の align 指示で緩和)。品質限界は割り切る

### 掃引調査(見落とし確認)

- 「network topology diagram as code YAML」で検索し、Topolograph(OSPF/IS-IS 実ネットワーク可視化)、Tufin(商用・機器から自動取得)、mingrammer/diagrams(クラウドアーキ図特化)等を確認
- いずれも「設計時に人間/AI が書く、拠点・回線契約セマンティクスを持つファイルベース DSL」ではない → 新規策定の判断を補強

## 3. D2 実機検証の詳細

- v0.7.1 の Windows amd64 tar.gz(約 21MB)を GitHub Releases から取得し `.tools/` に展開。**管理者権限不要、展開のみで動作**
- `d2 layout` で dagre / ELK の2エンジン同梱を確認(TALA は別売りのため対象外)
- テスト内容: 拠点コンテナ2つ(本社/大阪支店)+ ルーター3台 + スイッチ2台、線種3種類を classes で定義
  - `lan-cable`: 細実線 + IF 名ラベル(Gi0/0/1 - Gi1/0/1)
  - `wan-circuit`: 青太線 + 回線名ラベル(NTT東 IP-VPN 100Mbps)
  - `tunnel`: グレー破線 + ラベル(フレッツ + IPsec バックアップ)
- 結果: **ELK レイアウトで全要素が意図通り描画**。日本語ラベル・コンテナタイトル・エッジラベルすべて正常。品質は設計書掲載レベルと判断
- SVG → PNG 変換: mmdc も d2 の PNG 出力もヘッドレス Chrome が必要なため、**Windows 標準の Edge のヘッドレスモード** (`msedge --headless --screenshot=... file:///...svg`) を使う方式を検証し成功。追加インストール不要
- 注意点: `--default-background-color=FFFFFFFF` を付けないと透過背景になる

## 4. ボツにした案とその理由

- **独自テキスト文法(D2 風)**: `hq.rt01 -- br1.rt01: ...` のような専用文法は記述量では有利だが、パーサ・エディタ支援・AI の学習済み知識の面で YAML に劣ると判断。AI パース性が要件の中心にあるため、構造が自明な YAML を選択
- **NetBox をそのまま使い YAML export を DSL 扱いする案**: DB サーバー運用が前提になり、Git ベースの仕様駆動(OpenSpec)ワークフローと合わない。エクスポート形式も安定した公開スキーマではない
- **JSON Schema を手書きして言語非依存にする案**: pydantic モデルから JSON Schema を生成する方が単一ソースになり、手書き二重管理を避けられる
- **Graphviz を出力先に含める案**: D2(ELK 同梱)で品質・導入性ともに上回るため見送り。将来ニーズが出たらレンダラのシリアライザ追加で対応可能な構造にしておく

## 5. Phase 1 への引き継ぎ論点

1. **ビュー定義の表現力**をどこまで持たせるか: レイヤ選択(physical/logical)、拠点フィルタ、拠点の畳み込み(全社概要図で拠点=1ノード)の3つは必須。VLAN/セグメント表示は Phase 1 で要否判断
2. interface を device の子として書くか、link 側に書き捨てるか → 表生成(IF 一覧)と将来の実機連携を考えると device 子要素として明示定義が本命
3. 冗長構成(HSRP/VRRP ペア、スタック)の表現 → まず `redundancy_group` 的な軽量表現で開始
4. IP アドレス・VLAN をどこまでスキーマに含めるか(論理構成図と IP 設計表に必要な範囲まで)
