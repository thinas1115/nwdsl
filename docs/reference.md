# リファレンス

nwdsl `0.1` の全フィールドの意味・制約・例。構文の機械可読な定義は `nwdsl schema` で生成する JSON Schema、意味的制約はバリデーション規則(後半)を参照。

- 未定義のフィールドを書くとスキーマ違反になる(タイポ検出のため `extra: forbid`)
- ID はファイル内での参照キー。命名は自由だが、機器は `拠点-役割連番` (例: `hq-rt01`) を推奨

## トップレベル

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `nwdsl` | string | ✓ | スキーマバージョン。現在は `"0.1"` のみ |
| `network` | object | ✓ | メタ情報 (`name` 必須、`description` 任意) |
| `sites` | list | - | 拠点 |
| `devices` | list | - | 機器 |
| `clouds` | list | - | 事業者網・外部網 |
| `circuits` | list | - | キャリア回線契約 |
| `links` | list | - | 接続 |
| `segments` | list | - | L3セグメント |
| `paths` | list | - | 通信経路 (正常時/障害時) |
| `views` | list | - | 図の描き分け定義 |

## sites (拠点)

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | 拠点ID (一意) |
| `name` | string | ✓ | 拠点名 (図のコンテナ名・表に表示) |
| `location` | string | - | 所在地 |
| `description` | string | - | 補足 |

## devices (機器)

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | 機器ID (clouds と合わせて一意) |
| `site` | string | ✓ | 設置拠点ID (sites を参照) |
| `role` | enum | - | `router` / `l3switch` / `l2switch` / `firewall` / `loadbalancer` / `wlc` / `ap` / `server` / `other` (default)。図の配色と表の分類に使う |
| `platform` | string | - | 機種・型番 (図のノードの2行目に表示) |
| `mgmt_ipv4` | string | - | 管理IP (CIDR形式) |
| `redundancy_group` | string | - | 冗長グループ名。HSRP/VRRPペア・スタックは同名を指定 |
| `interfaces` | list | - | インターフェース定義 (下記) |
| `description` | string | - | 補足 |

### devices[].interfaces

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | string | ✓ | IF名 (機器内で一意。例: `Gi0/0/1`, `eth0`, `Tunnel0`, `Vlan10`) |
| `ipv4` | string | - | IPv4アドレス (CIDR形式。例: `10.1.0.1/24`) |
| `segment` | string | - | 所属セグメントID (segments を参照) |
| `description` | string | - | 用途 (表の「説明」列に表示) |

links の端点に書く IF は必ずここで宣言する。SVI (`Vlan10`) やトンネルIF (`Tunnel0`) も IF として書ける。

## clouds (事業者網・外部網)

IP-VPN網・広域Ethernet網・インターネットなど、内部構造を持たない「雲」。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | 網ID (devices と合わせて一意) |
| `name` | string | ✓ | 表示名 (例: `NTT Com IP-VPN網`) |
| `kind` | enum | - | `wan` (default) / `internet` / `other` |
| `description` | string | - | 補足 |

## circuits (回線契約)

キャリアから購入する回線の**契約情報**。どこに結線されるかは wan-circuit link 側に書く(契約と結線の分離)。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | 回線ID (一意) |
| `provider` | string | ✓ | 事業者 |
| `service` | string | ✓ | サービス名 (例: `IP-VPN`, `フレッツ光ネクスト + OCN`) |
| `circuit_id` | string | - | 事業者発行の回線番号 |
| `bandwidth` | string | - | 契約帯域 (例: `100M`, `1G`) |
| `status` | enum | - | `planned` / `active` (default) / `decommissioned`。新旧回線の移行期を1ファイルで表せる |
| `description` | string | - | 補足 |

## links (接続)

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | - | 接続ID (指定時は一意) |
| `type` | enum | ✓ | 線の意味 (下表) |
| `endpoints` | list[2] | ✓ | 両端点 (記法は下記) |
| `circuit` | string | - | 経由する回線契約ID (**wan-circuit では必須、他typeでは指定不可**) |
| `domain` | string | - | 所属ルーティングドメインID (domains を参照)。色分け+凡例で表現される |
| `via` | string | - | 経由する網ID (clouds を参照、logical/tunnel のみ)。論理図で「網の雲を通るピアリング」として2分割描画される |
| `description` | string | - | 補足 (logical/tunnel では図の線ラベルになる) |

### endpoints の記法

| 記法 | 意味 | 使える type |
|---|---|---|
| `"機器ID:IF名"` | 機器の特定IF | すべて (lan-cable / wan-circuit はこれのみ) |
| `"機器ID"` | 機器そのもの | logical / tunnel |
| `"cloudID"` | 網 | wan-circuit のみ |

### type の意味と制約

| type | 意味 | 図での線 | 制約 |
|---|---|---|---|
| `lan-cable` | 構内の物理結線 | 黒細線 + IF名 | 同一拠点の機器IF同士。circuit不可 |
| `wan-circuit` | キャリア回線を通る接続 | 青太線 + 回線情報 | circuit必須。機器IF↔機器IF(異拠点) or 機器IF↔cloud |
| `logical` | L3論理隣接 (ルーティングピア等) | 緑破線 | circuit不可。cloud端点不可 |
| `tunnel` | オーバーレイ (IPsec/GRE等) | 紫破線 | circuit不可。cloud端点不可 |

## segments (L3セグメント)

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | セグメントID (一意) |
| `site` | string | ✓ | 所属拠点ID |
| `name` | string | - | セグメント名 |
| `vlan` | int | - | VLAN ID (1〜4094) |
| `ipv4` | string | - | ネットワークアドレス (例: `10.1.10.0/24`。ホストビットが立っていると構文エラー) |
| `description` | string | - | 補足 |

## domains (ルーティングドメイン)

OSPFエリア・BGP AS・VRFなどの所属を表す。**エリア名を線1本ずつにラベルせず、色分け+凡例で表す**実務の描き方に対応する(色はレンダラが自動割当。DSLに色は書けない)。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | ドメインID (一意) |
| `name` | string | ✓ | 表示名 (例: `OSPF Area 0`)。凡例・面塗りラベルに使用 |
| `description` | string | - | 補足 |

link 側は `domain: <id>` で参照する。指定したエッジは:

- **全エンジン**: ドメイン色で描画され、図に凡例が自動追加される。`description` が無ければエッジ個別ラベルは出ない
- **内蔵SVGのみ**: 所属機器を囲む**半透明の面塗り(凸包)**も描かれ、複数エリアに属するABRは領域の重なり部分に立つ

## paths (通信経路)

正常時/障害時のトラフィックの通り道。作成者が明示し、隣接ホップ間に実在の link があることをバリデータが保証する(設計根拠は [ADR-0006](adr/0006-path-visualization.md))。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | 経路ID (一意) |
| `title` | string | - | 経路の表示名 |
| `hops` | list | ✓ | 始点→終点の順序付きホップ列 (2件以上) |
| `failure` | list | - | この経路が前提とする障害コンポーネント (device/cloud/circuit のID)。図で赤✕表示 |
| `fallback_of` | string | - | 正常時経路のID。指定すると当該経路が灰破線で併記される |
| `description` | string | - | 補足 |

### paths[].hops

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `node` | string | ✓ | ホップのノードID (device または cloud) |
| `protocol` | string | - | このホップへの到達を決めるプロトコル (例: HSRP, BGP)。線ラベルに表示 |
| `note` | string | - | 経路選択の理由 (例: standbyがactive昇格)。線ラベルに表示 |

## views (描き分け定義)

ビューは「事実」ではなく「見せ方」の宣言。座標・色は書けない(描画スタイルは role / type から機械的に決まる)。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | ビューID (= 出力ファイル名) |
| `title` | string | ✓ | 図のタイトル |
| `type` | enum | - | `topology` (default) / `path` (経路ハイライト図) |
| `path` | string | - | `type: path` のとき対象の経路ID (必須)。経路・障害に関係する拠点だけが描かれ、経路が赤太線+ホップ番号+プロトコル注記で強調される |
| `layers` | list | - | 含める接続種別 (省略時は全種別) |
| `include_sites` | list | - | この拠点だけ描く。範囲外の対向機器は「機器ID (拠点名)」の破線ノードで境界表示 |
| `exclude_sites` | list | - | 除外する拠点 |
| `collapse_sites` | bool | - | true で拠点を1ノードに畳む。拠点内で閉じる接続は消え、拠点間接続だけが残る (全社概要図向け) |
| `show_l3` | bool / enum | - | L3表示 (IF IPv4一覧+セグメントノード)。`view`=このビューに現れる接続のIFのみ (`true` と同義・既定挙動) / `used`=いずれかのlinkで使用中のIF / `all`=IPv4を持つ全IF / `false`=非表示。**省略時は純粋なL3ビュー (logical を含む、または物理レイヤ抜きの tunnel のみ) で view モードが自動有効**。セグメントGWのIFは常に表示対象 |
| `description` | string | - | 補足 |

典型的なビュー: 物理図=`[lan-cable, wan-circuit]` / 論理図=`[logical, tunnel]` / 全社概要図=`[wan-circuit, tunnel]` + `collapse_sites` / 拠点詳細図=`include_sites`。

## スコープ (v0.1) — 何を入れて、何を入れないか

nwdsl は「構成図・経路図・設計書表を生成するための最小NWモデル」に意図的に留めている。views は抽出・畳み込み・強調の宣言までとし、座標・色は今後も追加しない (図ツールのYAML再発明を防ぐため)。

| 入れる | 入れない (v0.1では拒否) |
|---|---|
| 拠点 / 機器 / IF / 回線契約 / 接続 / L3セグメント / 通信経路 / ビュー | Config全文、ACL/NAT/QoSの詳細、BGPネイバーパラメータ、監視設定、ラック・パッチパネル収容、座標指定 |

検討中のバックログ (必要になった時点でADRを起こして判断):

- `status` ライフサイクルの devices/links/segments への拡張 (現在は circuits のみ。NW更改・拠点撤去の移行期表現に有用)
- 大規模環境向けのファイル分割 (`include` / ディレクトリ構成)。現状は1ファイル=1ネットワーク
- NetBox/CMDB との import/export 方向の明確化 (network.yaml を「第二のマスタ」にしないため)

## バリデーション規則

`nwdsl validate` が検査する規則。error が1件でもあると exit code 1 (render / tables も中止される)。

| コード | レベル | 内容 |
|---|---|---|
| `dup.id` | error | ID重複 (devices と clouds は名前空間を共有) |
| `dup.interface` | error | 同一機器内のIF名重複 |
| `ref.site` / `ref.segment` / `ref.circuit` / `ref.endpoint` / `ref.interface` / `ref.view-site` | error | 参照先が存在しない |
| `endpoint.cloud-interface` | error | cloud端点にIF指定 |
| `link.lan-endpoint` / `link.lan-cross-site` | error | lan-cable の端点・拠点制約違反 |
| `link.circuit-required` / `link.circuit-forbidden` | error | circuit の必須/禁止違反 |
| `link.wan-endpoint` / `link.wan-same-site` | error | wan-circuit の端点制約違反 |
| `link.overlay-endpoint` | error | logical/tunnel の端点に cloud |
| `link.port-reuse` | error | 同一物理ポートを複数の物理linkが使用 |
| `ref.path-node` / `ref.path-failure` / `ref.path-fallback` | error | 経路の参照先が存在しない |
| `path.hop-not-adjacent` / `path.hop-duplicate` | error | 隣接ホップを結ぶ link が無い / 連続ホップが同一 |
| `view.path-required` / `view.path-forbidden` / `ref.view-path` | error | view の type と path 指定の不整合 |
| `circuit.multi-use` | error | 1つの回線契約を複数linkが参照 (1契約=1結線) |
| `circuit.unused` | warning | active な回線がどのlinkからも未参照 |
| `circuit.decommissioned` | warning | 廃止済み回線を参照 |

## CLI

コピペで動く実行例(リポジトリ直下、`pip install -e .` 済みの前提。自分のファイルに使うときはパスを差し替える):

```powershell
nwdsl validate examples\sample-corp\network.yaml            # 整合性検査
nwdsl validate examples\sample-corp\network.yaml --strict   # 警告もエラー扱い
nwdsl render   examples\sample-corp\network.yaml -o diagrams                # 全ビュー出力
nwdsl render   examples\sample-corp\network.yaml -o diagrams --view wan-overview --format d2
nwdsl render   examples\stress\ring.yaml -o diagrams --format svg   # 内蔵SVGエンジン (D2不要, ADR-0008)
nwdsl tables   examples\sample-corp\network.yaml -o diagrams\tables.md      # 6表すべて
nwdsl tables   examples\sample-corp\network.yaml --section circuits         # 回線一覧のみ標準出力
nwdsl schema   -o nwdsl.schema.json
nwdsl serve                          # playground (http://127.0.0.1:8321/) を起動
nwdsl serve --port 9000 --no-browser # ポート指定 / ブラウザ自動起動なし
```

`serve` は編集→自動描画の playground。SVG プレビューには D2 バイナリが必要 (PATH または リポジトリ `.tools/` から自動検出)。D2 が無い環境では図ソースの表示のみになる。docs/ と examples/ はカレントディレクトリ基準で検出するため、リポジトリ直下での起動を推奨。

`--view` / `--section` は複数回指定できる。`--format` は `d2` / `mermaid` / `all`(既定)。

D2 出力の描画: `d2 --layout=elk <view>.d2 <view>.svg`(ELKレイアウト推奨)。
PNG が必要なら Windows では Edge のヘッドレスで変換できる:

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu `
  --screenshot=out.png --window-size=1600,1000 --default-background-color=FFFFFFFF file:///C:/path/to/in.svg
```

Mermaid 出力 (.mmd) は GitHub / Obsidian に貼るとそのまま描画される。

## 描画エンジンの使い分け

| | D2 (ELK) | Mermaid | 内蔵SVG |
|---|---|---|---|
| 実装 | 外部バイナリ (`.tools/` or PATH) | GitHub/Obsidian/mermaid.js | Python内蔵 (依存なし) |
| 木構造系の見た目 | ◎ 最も洗練 | △ 中規模で乱れる | ○ 直交配線・整列済み |
| リング / leaf-spine / 多拠点概要 | ✕ 破綻 (ADR-0007) | ✕ 同様に破綻 | ◎ 円環/2段/格子で描画 |
| 重なりの保証 | なし (回避策を実装済み) | なし | **あり** (不変条件を機械検証, ADR-0008) |
| 用途 | 設計書の正式図 (木構造系) | Markdown埋め込み・レビュー共有 | 特殊トポロジ / D2なし環境 / 確実性優先 |

## アーキテクチャ (コンポーネントと役割)

```
network.yaml ─▶ loader.py ─▶ model.py(pydantic) ─▶ validate.py ─▶ graph.py ─▶ シリアライザ群
   (唯一のソース)  YAML読込     スキーマ=型=検証      参照/意味検査   ビュー解決    (下記)
```

| コンポーネント | 役割 |
|---|---|
| `model.py` | スキーマの単一ソース。pydanticモデル=型=検証=JSON Schema生成元 |
| `loader.py` | YAML読込と構文レベル検証 (スキーマ違反を日本語で報告) |
| `validate.py` | 意味的整合性 (参照解決・linkタイプ制約・経路の隣接性など約20規則) |
| `graph.py` | View定義を **RenderGraph** (フォーマット非依存の中間グラフ) に解決。BFS向き付け・LAG束ね・経路オーバーレイもここ |
| `render_d2.py` / `render_mermaid.py` / `render_svg.py` | RenderGraph を各記法にシリアライズ。意味論 (色・線種) は3者で共通 |
| `svg_layout.py` | 内蔵SVGのレイアウトエンジン (不変条件保証, ADR-0008) |
| `tables.py` | 設計書向け6表をMarkdown生成 (接続先・収容先はlinksから逆引き) |
| `cli.py` / `webapp.py` | CLI 5コマンド / playground (ローカルWebサーバー) |

## エンティティ関係 (参照の向き)

```
Site ◀── Device ── Interface ──▶ Segment
            ▲          ▲
            │ endpoints │ (device:interface)
           Link ──▶ Circuit        Link ──▶ Cloud (端点として)
            ▲
           Path.hops (node列。隣接性はlinkで検証)
           Path.failure ──▶ Device / Cloud / Circuit
View ──▶ Site (include/exclude) / Path (type: path)
```

- ID参照はすべてバリデータが検査する。逆方向の導出 (IF→接続先、Circuit→収容先) は表生成が行う

## playground

`nwdsl serve` で起動するローカルUI。YAML編集 (ハイライト付き) → 自動検証+描画、エンジン切替 (D2/Mermaid/内蔵SVG)、表/D2/Mermaidソースのタブ、Docsビューア (右上の「.md をコピー」でAIに読み込ませる用のMarkdown原文を取得可)。プレビューはドラッグ移動+ホイール拡大縮小。
