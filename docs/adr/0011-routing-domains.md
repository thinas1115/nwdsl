# ADR-0011: ルーティング表現の構造化 (Domain拡張と再配布)

- Status: Accepted
- Date: 2026-07-10
- Phase: 機能拡張

## Context

ルーティングの表現は `logical` link + `domain`(id と表示名だけのエンティティ)+
自由記述ラベルのみで、構成図ギャップの棚卸しで次の不足が判明した:

1. **プロトコルが構造化されていない**。OSPF/BGP の種別・エリア番号・AS番号が
   全部 `name` の自由記述で、凡例の表記が書き手依存になる
2. **ルート再配布が表現できない**。実務の論理構成図では、ドメイン境界の機器
   (ASBR等)に「⇄ 再配布」を注記する定番パターンがあるが、書く場所がない

一方で v0.1 のスコープ宣言(BGPネイバーパラメータ・Config詳細は入れない)は
維持する。「図と表に出る情報」だけを構造化する。

## Decision

### Domain にプロトコル種別と識別子を追加

```yaml
domains:
  - {id: area0, protocol: ospf, area: "0"}          # 表示名 "OSPF Area 0" を自動生成
  - {id: as65000, protocol: bgp, asn: 65000}        # 表示名 "BGP AS65000" を自動生成
  - {id: vrf-guest, name: VRF guest}                # 従来通り name だけでもよい
```

- `protocol`: `ospf | bgp | eigrp | rip | static | other`(任意)
- `area`: OSPFエリア識別子(文字列。`"0"` / `"0.0.0.0"` 両形式を許す)。
  **protocol: ospf のときのみ指定可**
- `asn`: BGP AS番号(整数)。**protocol: bgp のときのみ指定可**
- `name` は任意化し、省略時は protocol/area/asn から表示名を自動生成する
  (`OSPF Area 0`, `BGP AS65000`)。name 指定時はそれを優先(表記を変えたい場合)
- `name` と `protocol` の両方が無いドメインはエラー(凡例に id しか出せないため)

タイマー・認証・ネイバーパラメータ等は引き続き**スコープ外**(reference.md の
スコープ表に明記)。エリアタイプ (stub/NSSA) は `name` の自由記述で表す
(例: `name: OSPF Area 1 (NSSA)`)。

### トップレベル `redistributions` を新設

```yaml
redistributions:
  - from: area0            # domain id
    to: as65000            # domain id
    devices: [hq-rt01, hq-rt02]  # 実施する機器 (複数可 = 冗長ASBR)
    mutual: true           # 相互再配布 (default: false = from→to の一方向)
    description: 支社経路をBGPへ広報
```

図では `devices` の機器ノードのラベルに `再配布: OSPF Area 0 ⇄ BGP AS65000`
(一方向なら `→`)のバッジ行を追加する。バッジは from/to いずれかのドメインが
そのビューに現れる場合のみ表示し、物理図を汚さない。collapse_sites の概要図では
表示しない(機器ノードが存在しないため)。

表では新セクション `routing`(ルーティング一覧)として、ドメイン一覧
(ID・表示名・プロトコル・識別子・所属接続数)と再配布一覧を出力する。

### バリデーション

| コード | レベル | 内容 |
|---|---|---|
| `domain.name-required` | error | name と protocol の両方が未指定 |
| `domain.attr-mismatch` | error | area を ospf 以外に指定 / asn を bgp 以外に指定 |
| `ref.redistribution-domain` | error | from/to が domains に存在しない |
| `redistribution.same-domain` | error | from と to が同一 |
| `ref.redistribution-device` | error | devices の機器が存在しない |
| `redistribution.device-not-in-domain` | warning | devices の機器が from/to 両ドメインの link 端点になっていない |

`device-not-in-domain` を warning に留めるのは、スタティック(protocol: static)の
ようにドメイン所属 link を張らない流儀があり得るため。

## 検討した代替案

1. **汎用 `label` フィールド1本 (area/asn を区別しない)** — タイポ・型ミス
   (AS番号に文字列等)を検出できず、表示名の自動生成もできない。専用フィールドを採用
2. **redistributions を domain 配下にネスト** — 再配布は2つのドメインの間の関係
   であり、どちらか片方の子にすると非対称になる。トップレベルの関係エンティティ
   として独立させた(links と同じ設計)
3. **機器の domain 直接所属フィールド** — link 経由の帰属と二重管理になる。
   見送り(スタブ機器も GW への logical link を書く運用で足りる。patterns.md に記載)

## Consequences

- 既存ファイルは無変更で動く(追加フィールドはすべて任意。name 必須→
  「name または protocol 必須」への変更は緩和方向)
- 凡例・面塗りラベル・表のドメイン列は表示名生成関数 (`domain_display_name`) を
  共通利用し、3エンジンと表で表記が揃う
- 同一プロトコル・同一エリアの連結性チェック(エリア分断検出)は今回入れない。
  グラフ解析が必要で誤検知リスクがあるため、需要が出てから別ADRで判断
