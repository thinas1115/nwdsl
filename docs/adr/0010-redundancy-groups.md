# ADR-0010: redundancy_groups エンティティ化 (FHRP/スタックの構造化)

- Status: Accepted
- Date: 2026-07-10
- Phase: 機能拡張

## Context

冗長構成の表現は、これまで `Device.redundancy_group`(同名文字列をペアに付けるだけ)
だった。ADR-0004 では「表・図での利用実績を見てから専用エンティティ化を判断する
(YAGNI)」としていたが、構成図ギャップの棚卸しで以下が判明し、拡張条件を満たしたと
判断した:

1. **文字列版は図に一切反映されていない**(機器一覧の表に出るだけ)。図を見ても
   どの2台が冗長ペアか分からない
2. **VIP(仮想IP)が構造化できない**。IF `description` への自由記述で代用しており、
   論理図のGW表示にもIP設計表にも載らず、タイポも検出できない
3. **active/standby が静的に表せない**。paths の注記でしか書けず、経路図を
   作らない限り図に出ない
4. **スタック(StackWise/VSS等)を論理図で1筐体に畳めない**。「物理図=2筐体・
   論理図=1筐体」は物理図/論理図の最も典型的な描き分けだが、手段がなかった
5. **クロススタックLAG**(2筐体にまたがるLAGが対向からは1論理リンク)も同根

## Decision

### スキーマ: トップレベル `redundancy_groups` を新設し、文字列版は廃止する

```yaml
redundancy_groups:
  - id: hq-wan-rt
    kind: fhrp                 # fhrp (default) | stack
    protocol: hsrp             # kind: fhrp のみ。hsrp | vrrp | glbp | other
    group: 1                   # FHRPグループ番号 (任意)
    vip: 10.1.0.1              # 仮想IP (任意。CIDRなしの単一アドレス)
    members:
      - {device: hq-rt01, role: active}
      - {device: hq-rt02, role: standby}
  - id: hq-core-stack
    kind: stack                # 論理ビューで1ノードに畳む対象
    name: hq-core              # 畳んだときの表示名 (省略時は id)
    members:
      - {device: hq-core01}
      - {device: hq-core02}
```

`Device.redundancy_group`(文字列)は**削除**した。利用者が少ない今のうちに移行する
方が、「文字列版=枠のみ/エンティティ版=フル機能」の2段階仕様を恒久的に抱えるより
安い。既存ファイルは `extra: forbid` によりスキーマ違反として検出され、フィールド名
入りのエラーで移行を促す。スキーマバージョンは `0.2` に上げた(`0.1` も引き続き受理。
バージョン文字列でなくフィールドの有無で互換性を判定する)。

`priority` 数値・preempt・トラッキング等のコンフィグ詳細は引き続きスコープ外
(v0.1からの「Config全文は入れない」方針を維持)。役割は `active` / `standby` の
2語彙に限定する。

### 図: 冗長枠・Act/Sbyバッジ・スタック畳み

- **冗長枠 (全エンジン)**: 同一拠点内に2台以上のメンバーが描かれるグループを
  点線枠で囲み、枠ラベルにプロトコル/グループ番号/VIPを表示する
  (例: `HSRP grp1 VIP 10.1.0.1`)。D2/Mermaidは拠点コンテナ内の入れ子コンテナ、
  内蔵SVGはメンバー配置矩形の外接枠として描く
- **Act/Sbyバッジ**: `role` を持つFHRPメンバーは、ノードラベル1行目に
  `(Act)` / `(Sby)` を付す
- **スタック畳み**: `kind: stack` のグループは、ビュー解決時にメンバーを1ノード
  (ラベルは `name` または id)に集約できる。メンバー間リンク(スタックリンク)は
  自己ループとなり消える。集約後の同一ペア間並列リンクは既存のLAG束ね(×N)が
  そのまま効くため、**クロススタックLAGは追加実装なしで「対向から1論理リンク×N」
  になる**
- **畳みの制御**: `View.merge_stacks: bool` で明示制御。省略時は純粋なL3ビュー
  (show_l3 の自動判定と同じ条件)で自動有効。物理図では畳まない(2筐体+枠表示)

### 表: 冗長グループ一覧の新設とVIPの反映

- 新セクション `redundancy`(冗長グループ一覧): 種別・プロトコル・グループ番号・
  VIP・メンバー(役割付き)
- 機器一覧の「冗長グループ」列はエンティティからの逆引きに変更
- セグメント一覧のゲートウェイ列に、そのセグメントのCIDRに含まれるVIPを
  `VIP x.x.x.x (グループID)` として先頭表示(VIP所属セグメントはCIDR包含で導出する。
  DSLに所属を書かせない)

### バリデーション

| コード | レベル | 内容 |
|---|---|---|
| `dup.id` | error | redundancy_groups の id 重複 |
| `ref.redundancy-member` | error | member の device が devices に存在しない |
| `redundancy.member-duplicate` | error | 同一グループ内で同じ機器を2回参照 |
| `redundancy.multi-stack` | error | 1機器が複数の stack グループに所属 (FHRPの複数所属は正当なので許可) |
| `redundancy.fhrp-only` | error | kind: stack に protocol / group / vip を指定 |
| `redundancy.cross-site` | warning | メンバーが複数拠点にまたがる |
| `redundancy.vip-segment` | warning | vip がメンバーIFのどのネットワーク (IF自身/所属セグメントのCIDR) にも含まれない |

paths の `protocol: HSRP` 注記と静的な `role` の食い違いは検査**しない**(仕様)。
paths は障害時の standby 昇格を書くために静的定義と食い違ってよい。

## 検討した代替案

1. **文字列版を残して枠描画だけ実装** — VIP・Act/Sby・スタック畳みが結局書けず、
   ギャップの過半が残る。却下
2. **Interface に vip フィールドを追加** — ペア2台に重複記述が必要になり、
   食い違いの検証が別途要る。グループという実体に1回書く方が正規形。却下
3. **スタック畳みを常時自動 (フィールドなし)** — 「論理図でも筐体を見せたい」
   ケースに対応できない。明示フィールド+論理ビューでの既定有効を採用

## Consequences

- examples 全件 (sample-corp / complex-lan / branch-20 / scale-50 / hq-dc-cloud) を
  エンティティ形式へ移行。VIPの自由記述 description は構造化フィールドに置換
- スタックの実演として `examples/stack-core` を追加(物理図=2筐体+枠 /
  論理図=1筐体、クロススタックLAGの×2束ね)
- 内蔵SVGの冗長枠は「メンバーの外接矩形」であるため、レイアウト上メンバーの間に
  無関係ノードが挟まった場合は枠が他ノードを含んで見える可能性がある
  (svg_layout はグループ隣接を保証しない)。実測上、冗長ペアは接続パターンが
  対称でレイアウトが隣接させるため実害は確認されていない。問題が出たら
  svg_layout の順序制約に手を入れる
- D2のセグメント内包 (ADR-0009) との関係: 内包対象は `role: server` の末端機器で
  あり、冗長グループのメンバー(ルーター/コアSW)とは通常重ならない。両方に該当
  した場合は冗長枠を優先し、セグメント内包から除外する
