# ADR-0012: 有向 logical リンク (デフォルトルート矢印)

- Status: Accepted
- Date: 2026-07-10
- Phase: 機能拡張

## Context

「default → FW」のようなスタティック/デフォルトルートの矢印は論理構成図の頻出
要素だが、link は無向であり矢印を描く手段がなかった。paths で代用する案は
「特定フローの経路」と「常設のルーティング設計」の意味が違うため不適。

## Decision

link タイプは増やさず、`logical` link に任意フィールド `direction` を追加する。

```yaml
links:
  - {type: logical, endpoints: [hq-core01, hq-fw01], description: default,
     direction: forward}   # endpoints[0] → endpoints[1] の矢印
```

- `direction`: `forward | both`(default: `both` = 従来通り無向)
- **logical でのみ指定可**(`link.direction-forbidden`)。lan-cable/wan-circuit は
  物理配線に向きがなく、tunnel は常に双方向のため
- 描画: 3エンジンとも矢印付きで描く。レイアウトの WAN→LAN 向き付け (ADR-0005) は
  エッジの src/dst を入れ替えるが、**有向エッジは入れ替え対象から除外**する
  (矢印の意味が反転してしまうため)。数本のデフォルトルート矢印がランク推定から
  外れてもレイアウトへの実害は小さいことを実測で確認した

## Consequences

- Mermaid は `-->`、D2 は `->`、内蔵SVGは marker-end で表現(経路ビューの矢印と
  同じ機構を再利用)
- スタティックルート網羅(宛先プレフィックスの列挙)はスコープ外のまま。
  向きと `description` ラベルで「設計意図として太い1本」を示す用途に限る
