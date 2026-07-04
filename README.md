# nwdsl — ネットワーク構成記述 DSL

ネットワーク構成(拠点・機器・回線・接続)を **1つの YAML ソース**で記述し、そこから

- **複数種類の構成図**(物理 / 論理 / 全社概要 / 拠点詳細)を D2・Mermaid で生成
- **設計書向けの表**(拠点・機器・IF・回線・接続・セグメント一覧)を Markdown で生成

するためのスキーマと CLI。図と表が同一ソースから導出されるため、設計ドキュメント間の不整合が構造的に発生しない。AI がパースしやすい形式なので、OpenSpec 等による仕様駆動のドキュメント生成の土台になる。

## 何が解決されるか

| 課題 | nwdsl の回答 |
|---|---|
| 構成図は用途別に描き分けが必要(全社概要/拠点詳細/物理/論理)だが、既存ダイアグラムDSLは意味情報を持てない | トポロジ定義(事実)と `views`(見せ方の宣言)を分離。レイヤ選択・拠点フィルタ・拠点畳み込みで1ソースから複数の図を導出 |
| 機器間の「線」には複数の意味がある | `links[].type` で4種を区別: `lan-cable`(構内配線)/ `wan-circuit`(キャリア回線)/ `logical`(論理隣接)/ `tunnel`(オーバーレイ) |
| 回線契約の管理情報が図に埋もれる | NetBox の思想に倣い `circuits`(契約: 事業者・回線番号・帯域・状態)を結線から分離 |
| 図と表の不整合 | 表の「接続先」「回線収容先」も links から導出。手書き二重管理が発生しない |
| 図の配置が意味と一致しない | クラウド起点BFSでエッジを向き付けし「WANが上・LANが下」を構造的に保証([ADR-0005](docs/adr/0005-layout-bfs-orientation.md))。複雑な多段LANでもスケール |
| 正常時/障害時の通信経路を示せない | `paths` にホップ列+プロトコル注記を明示し、経路図(赤太線+ホップ番号、障害✕、迂回表示)を生成([ADR-0006](docs/adr/0006-path-visualization.md)) |

## サンプル出力

`examples/sample-corp/network.yaml`(3拠点 + IP-VPN + インターネットVPNバックアップ + HSRP冗長)からの生成例:

| 全社物理構成図 | 全社WAN概要図 (`collapse_sites`) |
|---|---|
| ![物理構成図](examples/sample-corp/generated/physical-all.svg) | ![WAN概要図](examples/sample-corp/generated/wan-overview.svg) |

| 全社論理構成図 | 本社詳細図 (`include_sites`) |
|---|---|
| ![論理構成図](examples/sample-corp/generated/logical-all.svg) | ![本社詳細図](examples/sample-corp/generated/hq-physical.svg) |

| 通信経路図 正常時 (`type: path`) | 通信経路図 IP-VPN障害時 (`failure` + `fallback_of`) |
|---|---|
| ![正常時経路](examples/sample-corp/generated/path-normal.svg) | ![障害時経路](examples/sample-corp/generated/path-ipvpn-fail.svg) |

生成された表: [examples/sample-corp/generated/tables.md](examples/sample-corp/generated/tables.md)

> **描画エンジンは2系統**: D2(ELK)は木構造系の構成で最も美しいが、leaf-spineファブリック・メトロリング・10拠点超のWAN概要では破綻する([ADR-0007](docs/adr/0007-renderer-strategy.md)、[examples/stress/](examples/stress/) で再現可能)。このため**「どのパターンでも破綻しない」ことを不変条件(ノード/ラベル重なりゼロ・線のノード貫通ゼロ)として保証する内蔵SVGエンジン**を実装している(`--format svg`、[ADR-0008](docs/adr/0008-invariant-renderer.md))。内蔵エンジンはリングを円環に、ファブリックを2段扇状に自動配置し、全サンプル×全ビューの不変条件をテストで機械検証している。

## クイックスタート

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .

nwdsl serve                                              # ブラウザで試す (playground)
nwdsl validate examples\sample-corp\network.yaml         # 整合性検査
nwdsl render   examples\sample-corp\network.yaml -o out  # 図ソース生成 (.d2 / .mmd)
nwdsl tables   examples\sample-corp\network.yaml -o out\tables.md
nwdsl schema   -o nwdsl.schema.json                      # エディタ補完用 JSON Schema
```

`nwdsl serve` は http://127.0.0.1:8321/ にローカルの playground を起動する。左ペインで YAML を編集すると自動で検証+描画され、サンプル(最小構成〜50台規模)の読み込み、ビュー切替、表/D2/Mermaid の確認、チュートリアル・リファレンス・ADR の閲覧が画面内でできる。初見の人はまずこれ。

SVG 化には [D2](https://github.com/terrastruct/d2/releases)(単一バイナリ)を使う:

```powershell
d2 --layout=elk out\physical-all.d2 out\physical-all.svg
```

Mermaid 出力(.mmd)は GitHub / Obsidian にそのまま貼れる。詳細図は D2、概要図・埋め込みは Mermaid の使い分けを推奨。

## 記述例(抜粋)

```yaml
nwdsl: "0.1"
network: {name: sample-corp}

sites:
  - {id: hq, name: 本社}
  - {id: osk, name: 大阪支店}

devices:
  - id: hq-rt01
    site: hq
    role: router
    platform: Cisco ISR4331
    interfaces:
      - {name: Gi0/0/0, description: IP-VPNアクセス回線}

clouds:
  - {id: ipvpn, name: NTT Com IP-VPN網, kind: wan}

circuits:
  - {id: cct-ipvpn-hq, provider: NTTコミュニケーションズ, service: IP-VPN, bandwidth: 100M}

links:
  - type: wan-circuit                       # 線の意味を必ず宣言する
    endpoints: ["hq-rt01:Gi0/0/0", "ipvpn"] # 契約(circuits)と結線(links)は分離
    circuit: cct-ipvpn-hq

views:
  - id: wan-overview
    title: 全社WAN概要図
    layers: [wan-circuit, tunnel]
    collapse_sites: true                    # 拠点を1ノードに畳む
```

## サンプル一覧 (playgroundのサンプル選択にも表示される)

| サンプル | 規模 | 見どころ |
|---|---|---|
| [two-site-ipsec](examples/two-site-ipsec/) | 2拠点4台 | 最小実務構成 (フレッツ+IPsecのみ、ヤマハ機、静的経路) |
| [sample-corp](examples/sample-corp/) | 3拠点7台 | 標準サンプル (IP-VPN+VPNバックアップ+HSRP+正常/障害経路) |
| [hq-dc-cloud](examples/hq-dc-cloud/) | 3拠点13台 | ハイブリッド構成 (広域Ether+AWS Direct Connect+VPNバックアップ、DX障害経路) |
| [complex-lan](examples/complex-lan/) | 2拠点19台 | 多段LAN (FW/コア冗長→ディストリ→アクセス、DMZ) |
| [branch-20](examples/branch-20/) | 20拠点44台 | 多拠点ハブ&スポーク (東西DRハブ+モバイル閉域網バックアップ)。概要図は内蔵SVG推奨 |
| [scale-50](examples/scale-50/) | 3拠点50台 | 規模検証 (本社29台の多段構成) |
| [stress/](examples/stress/) | 合成4種 | 描画エンジンの限界検証 (leaf-spine/リング/多拠点/LAG) |

## ドキュメント

- [チュートリアル](docs/tutorial.md) — 最小構成から30分で(全ステップ実機検証済み)
- [リファレンス](docs/reference.md) — 全フィールド・バリデーション規則・CLI
- [OpenSpec 統合ガイド](docs/openspec-integration.md) — 仕様駆動ドキュメント生成への組み込み
- [設計判断記録 (ADR)](docs/adr/) — 先行事例調査、新DSL策定の判断、スキーマ設計の根拠
- [調査ログ](docs/notes/phase0-survey-log.md) — 検討過程の記録

## リポジトリ構成

```
src/nwdsl/          # model(スキーマ) / validate / graph(ビュー解決) / render_d2 / render_mermaid / tables / cli
tests/              # pytest (サンプル正常系 + 異常系)
examples/sample-corp/   # サンプル構成と生成物一式
schema/nwdsl.schema.json
docs/
```

## 動作環境

- Python 3.11+ (pydantic v2, PyYAML)
- 図のSVG化: D2 v0.7+ (dagre/ELK同梱の単一バイナリ)
