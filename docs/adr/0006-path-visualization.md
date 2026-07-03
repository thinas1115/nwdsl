# ADR-0006: 通信経路の可視化 (明示 paths + ハイライトオーバーレイ)

- Status: Accepted
- Date: 2026-07-04
- Phase: 経路可視化 (Phase B)

## Context

設計書には「正常時にトラフィックがどの経路を通るか」「障害時にどう迂回するか」を、経路を決めるプロトコル(HSRP/BGP/OSPF/IPsec フェイルオーバー等)まで含めて示す必要がある。初版の nwdsl には経路の概念がなかった。

## Decision

### 1. 経路は作成者が明示する (`paths`)

```yaml
paths:
  - id: hq-osk-backup
    title: 本社→大阪 (IP-VPN障害時)
    failure: [ipvpn]           # 障害コンポーネント (device/cloud/circuit)
    fallback_of: hq-osk-normal # 無効化された正常経路を灰破線で併記
    hops:
      - node: hq-sw01
      - node: hq-rt02
        protocol: HSRP
        note: standbyがactive昇格
      - node: osk-rt01
        protocol: BGP
        note: IPsecトンネルへ経路切替
      - node: osk-sw01
```

- ホップは devices / clouds の ID の順序列。`protocol` / `note` で「なぜその経路になるか」を注記し、図の線ラベルに表示する
- **ルーティング計算による経路の自動導出は採用しない**(却下理由: メトリック・冗長プロトコルの状態管理を持ち込むとミニシミュレータになり、本 DSL の目的「設計意図の構造化」から外れる。設計書に書くべきは意図された経路であり、明示が正)。将来 AWX/実機連携で as-built 経路を逆生成する拡張余地は残す

### 2. バリデーションで経路の実在性を保証する

- ホップの参照先が devices/clouds に存在すること
- **隣接ホップ間に実在の link(全 type 対象)があること**(`path.hop-not-adjacent`)。トポロジと矛盾した経路は書けない
- failure / fallback_of の参照整合性、view type=path と path 指定の対応

### 3. 描画はトポロジ図へのオーバーレイ (`views.type: path`)

経路専用の図を別に組み立てるのではなく、既存のトポロジ描画(ADR-0005 のレイアウト)をベースに強調・淡色化を重ねる。経路と構成図の見た目が一致し、読者が図の間で迷子にならない。

| 対象 | 表現 |
|---|---|
| 経路上のエッジ | 赤太線 + 進行方向の矢印 + ①②…ホップ番号 + protocol/note ラベル + `style.animated`(SVGで流れる) |
| 経路上のノード | 通常表示 |
| fallback_of の経路 | 灰破線(端点ノードは淡色化しない) |
| failure のノード | 赤枠・赤地 + 「✕障害」ラベル |
| failure の回線・障害ノード接続エッジ | 赤破線 |
| それ以外 | 淡色化 (opacity) |

- 描画対象は経路・障害に関係する拠点のみに自動絞り込み(無関係拠点のノイズを避ける)
- D2 の `style.animated: true` は静的 PNG では破線に見えるが、色(赤 vs 灰)で disabled と区別できることを実描画で確認済み

## Consequences

- 経路の追加は YAML 数行で済み、構成変更(機器リネーム等)で経路が壊れるとバリデータが検出する
- 1障害シナリオ=1 path=1 view。シナリオが多い構成ではビュー数が増えるが、設計書の「障害パターン別経路図」の構成と一致する
- Mermaid 出力も同じ emphasis を反映する(品質は D2 優先)
