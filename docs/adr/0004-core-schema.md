# ADR-0004: コアスキーマの構造

- Status: Accepted
- Date: 2026-07-04
- Phase: 1 (コア設計)

## Context

[ADR-0002](0002-new-yaml-dsl.md) で決めた「トポロジ定義とビュー定義の2層」を具体的なスキーマに落とす。要件の中心は (1) 線種4種の意味区別、(2) 拠点・回線契約の業務エンティティ、(3) 1ソースから複数の図・表を導出できること。

## Decision

### エンティティ構成(6種+ビュー)

```yaml
nwdsl: "0.1"          # スキーマバージョン(必須)
network: {...}        # メタ情報
sites: [...]          # 拠点
devices: [...]        # 機器(interfaces を子に持つ)
circuits: [...]       # キャリア回線契約
clouds: [...]         # 事業者網・外部網(IP-VPN網、インターネット等)
links: [...]          # 接続(必須の type で意味を区別)
segments: [...]       # L3セグメント(VLAN/サブネット)
views: [...]          # 図の描き分け定義
```

### 判断1: `clouds` を独立エンティティにする

NetBox の Circuit は point-to-point 前提だが、実務の WAN は IP-VPN・広域 Ethernet などの**マルチポイント網**が中心で、物理構成図でも「網の雲」を描くのが慣習。そこで NetBox の ProviderNetwork に相当する `clouds` を設け、link の端点に `"device:interface"` だけでなく cloud の id を書けるようにした。

- アクセス回線: `type: wan-circuit` の link が機器 IF と cloud を結び、`circuit:` で契約を参照
- 専用線などの真の point-to-point 回線: 機器 IF 同士を直接 `wan-circuit` link で結ぶ
- 網内での拠点間の通信関係: `type: logical` の link(ルーティング隣接)で表現

### 判断2: interface は device の子として宣言必須

link の endpoints に現れる IF は、必ず device 側の `interfaces` で宣言されていなければならない(バリデータがエラーにする)。

- 代替案「endpoints に書いた IF を自動生成する」は記述が楽だが、タイポが検出できず「IF 一覧表」の品質が保証できないため却下
- IF 宣言には IP アドレス・所属セグメント・説明を書けるようにし、論理構成図と IP 設計表の情報源にする

### 判断3: link type は4値固定+typeごとの制約

| type | 意味 | 制約(バリデータが検査) |
|---|---|---|
| `lan-cable` | 構内の物理結線 | 端点は同一拠点の機器IF同士。circuit 参照不可 |
| `wan-circuit` | キャリア回線を通る接続 | `circuit:` 参照必須。端点は機器IF↔機器IF(異拠点)または機器IF↔cloud |
| `logical` | L3論理隣接(ルーティングピア等) | 物理制約なし。circuit 参照不可 |
| `tunnel` | オーバーレイ(IPsec/GRE等) | 物理制約なし。circuit 参照不可 |

物理ポートの二重使用(同一 IF が複数の物理 link に登場)はエラーとする。

### 判断4: views はフィルタ+抽象度の宣言のみ

```yaml
views:
  - id: physical-all
    title: 全社物理構成図
    layers: [lan-cable, wan-circuit]   # 含める線種
  - id: wan-overview
    title: 全社WAN概要図
    layers: [wan-circuit, tunnel]
    collapse_sites: true               # 拠点を1ノードに畳む
  - id: hq-physical
    title: 本社 物理構成図
    layers: [lan-cable, wan-circuit]
    include_sites: [hq]                # 範囲フィルタ(境界をまたぐlinkは相手側を境界ノード表示)
```

- 座標・色・形などの見た目情報は views に持たせない(描画スタイルは線種・機器ロールから機械的に決める)。drawthe.net の座標手打ちの反省による
- `collapse_sites: true` のとき、拠点内の機器・LAN 配線は畳まれ、拠点間の link は拠点ノード間のエッジに集約される。全社概要図はこれで表現する

### 判断5: 冗長構成は `redundancy_group` 文字列で軽量に表現

HSRP/VRRP ペアやスタックは device の `redundancy_group` に同じグループ名を書くことで表す。専用エンティティ化(仮想IPやプライオリティの構造化)は、表・図での利用実績を見てから拡張する(YAGNI)。

## Consequences

- ID 参照(link→device/interface/circuit/cloud、device→site、segment→site)が多いため、参照整合性検査がバリデータの中核になる
- `clouds` の導入により、インターネット VPN 構成(フレッツ+IPsec)も「アクセス回線は wan-circuit、拠点間は tunnel」と自然に書ける
- collapse_sites の集約ロジック(多重エッジの縮約と本数表示)はレンダラ実装の主要な複雑性になる
