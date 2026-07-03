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

## views (描き分け定義)

ビューは「事実」ではなく「見せ方」の宣言。座標・色は書けない(描画スタイルは role / type から機械的に決まる)。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `id` | string | ✓ | ビューID (= 出力ファイル名) |
| `title` | string | ✓ | 図のタイトル |
| `layers` | list | - | 含める接続種別 (省略時は全種別) |
| `include_sites` | list | - | この拠点だけ描く。範囲外の対向機器は「機器ID (拠点名)」の破線ノードで境界表示 |
| `exclude_sites` | list | - | 除外する拠点 |
| `collapse_sites` | bool | - | true で拠点を1ノードに畳む。拠点内で閉じる接続は消え、拠点間接続だけが残る (全社概要図向け) |
| `description` | string | - | 補足 |

典型的なビュー: 物理図=`[lan-cable, wan-circuit]` / 論理図=`[logical, tunnel]` / 全社概要図=`[wan-circuit, tunnel]` + `collapse_sites` / 拠点詳細図=`include_sites`。

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
nwdsl tables   examples\sample-corp\network.yaml -o diagrams\tables.md      # 6表すべて
nwdsl tables   examples\sample-corp\network.yaml --section circuits         # 回線一覧のみ標準出力
nwdsl schema   -o nwdsl.schema.json
```

`--view` / `--section` は複数回指定できる。`--format` は `d2` / `mermaid` / `all`(既定)。

D2 出力の描画: `d2 --layout=elk <view>.d2 <view>.svg`(ELKレイアウト推奨)。
PNG が必要なら Windows では Edge のヘッドレスで変換できる:

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu `
  --screenshot=out.png --window-size=1600,1000 --default-background-color=FFFFFFFF file:///C:/path/to/in.svg
```

Mermaid 出力 (.mmd) は GitHub / Obsidian に貼るとそのまま描画される。機器数が多い詳細図はレイアウトが乱れやすいため、詳細図は D2、概要図・埋め込みは Mermaid という使い分けを推奨する。
