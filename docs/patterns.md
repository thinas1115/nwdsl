# 記述パターン集

実務でよく出る構成の nwdsl での書き方。すべて validate 済みの断片で、そのまま組み合わせて使える。完全なサンプルは `examples/` を参照。

## 1. WANルーター冗長 (HSRP/VRRP ペア)

```yaml
devices:
  - id: hq-rt01
    site: hq
    role: router
    redundancy_group: hq-wan   # ペアに同じグループ名を付けるだけ
  - id: hq-rt02
    site: hq
    role: router
    redundancy_group: hq-wan
```

- 仮想IPは代表して active 側 IF の `description` に書く(例: `HSRP VIP 10.1.0.1`)
- どちらが active かは経路 (`paths`) の `protocol: HSRP` 注記で表現する

## 2. マルチポイント網への接続 (IP-VPN / 広域Ethernet)

網は `clouds` に1つ定義し、各拠点のアクセス回線を `wan-circuit` で網につなぐ。

```yaml
clouds:
  - {id: ipvpn, name: NTT Com IP-VPN網, kind: wan}
circuits:
  - {id: cct-hq,  provider: NTT Com, service: IP-VPN, bandwidth: 100M}
  - {id: cct-osk, provider: NTT Com, service: IP-VPN, bandwidth: 50M}
links:
  - {type: wan-circuit, endpoints: ["hq-rt01:Gi0/0/0", "ipvpn"],  circuit: cct-hq}
  - {type: wan-circuit, endpoints: ["osk-rt01:Gi0/0/0", "ipvpn"], circuit: cct-osk}
  # 網内のルーティング隣接は logical で表す
  - {type: logical, endpoints: ["hq-rt01", "osk-rt01"], description: BGP (IP-VPN網内)}
```

## 3. 拠点間の専用線 (point-to-point)

網を介さない回線は機器IF同士を直接 `wan-circuit` で結ぶ。

```yaml
circuits:
  - {id: cct-leased, provider: キャリアA, service: 広域Ether専用線, bandwidth: 1G}
links:
  - type: wan-circuit
    endpoints: ["hq-rt01:Gi0/0/1", "dc-rt01:Gi0/0/1"]
    circuit: cct-leased
```

- 8拠点程度の**メトロリング**もこのパターンの連鎖 (`examples/stress/ring.yaml`)。内蔵SVGエンジンが円環として描画する

## 4. インターネットVPNバックアップ (フレッツ + IPsec)

「アクセス回線 = wan-circuit」「拠点間 = tunnel」に分けるのがポイント。

```yaml
clouds:
  - {id: internet, name: インターネット, kind: internet}
circuits:
  - {id: cct-inet-hq,  provider: NTT東, service: フレッツ光 + OCN, bandwidth: 1G}
  - {id: cct-inet-osk, provider: NTT西, service: フレッツ光 + OCN, bandwidth: 1G}
links:
  - {type: wan-circuit, endpoints: ["hq-rt02:Gi0/0/0", "internet"],  circuit: cct-inet-hq}
  - {type: wan-circuit, endpoints: ["osk-rt01:Gi0/0/1", "internet"], circuit: cct-inet-osk}
  - type: tunnel
    endpoints: ["hq-rt02:Tunnel0", "osk-rt01:Tunnel0"]   # Tunnel IFはdevices側で宣言する
    description: IPsec バックアップVPN
```

## 5. DMZ

```yaml
devices:
  - id: hq-fw01
    site: hq
    role: firewall
    interfaces:
      - {name: eth1/1, description: WAN側}
      - {name: eth1/2, description: 内部LAN側}
      - {name: eth1/3, description: DMZ側}
links:
  - {type: lan-cable, endpoints: ["hq-fw01:eth1/3", "hq-dmz-sw01:Gi1/0/1"]}
```

- FW の役割 (`role: firewall`) で図が赤系に塗られ、境界が一目で分かる

## 6. LAG / スタック間リンク (並列リンク)

同じ機器ペア間に複数の `lan-cable` を書くだけ。図では自動で1本に束ねられ `×N` 表示になる (メンバーIFの対応は接続一覧の表に残る)。

```yaml
links:
  - {type: lan-cable, endpoints: ["core01:Te1/0/49", "core02:Te1/0/49"]}
  - {type: lan-cable, endpoints: ["core01:Te1/0/50", "core02:Te1/0/50"]}
```

## 7. 中継拠点 (拠点—網A—拠点—網B—拠点)

中央拠点は網ごとに別ルーターを置き、間をL2でつなぐ。

```yaml
devices:  # 中継拠点 ngy
  - {id: ngy-rt01, site: ngy, role: router}   # 網A側
  - {id: ngy-rt02, site: ngy, role: router}   # 網B側
  - {id: ngy-sw01, site: ngy, role: l2switch}
links:
  - {type: wan-circuit, endpoints: ["ngy-rt01:Gi0/0/0", "wan-a"], circuit: cct-a}
  - {type: wan-circuit, endpoints: ["ngy-rt02:Gi0/0/0", "wan-b"], circuit: cct-b}
  - {type: lan-cable, endpoints: ["ngy-rt01:Gi0/1/0", "ngy-sw01:Gi1/0/1"]}
  - {type: lan-cable, endpoints: ["ngy-rt02:Gi0/1/0", "ngy-sw01:Gi1/0/2"]}
```

## 8. 正常時/障害時の通信経路

経路はホップ列で明示し、切替を決めるプロトコルを注記する。障害コンポーネントは `failure` で赤✕表示。

```yaml
paths:
  - id: hq-osk-normal
    title: 本社→大阪 (正常時)
    hops:
      - {node: hq-sw01}
      - {node: hq-rt01, protocol: HSRP, note: active側GW}
      - {node: ipvpn,   protocol: BGP}
      - {node: osk-rt01}
  - id: hq-osk-backup
    title: 本社→大阪 (IP-VPN障害時)
    failure: [ipvpn]
    fallback_of: hq-osk-normal
    hops:
      - {node: hq-sw01}
      - {node: hq-rt02, protocol: HSRP, note: standbyがactive昇格}
      - {node: osk-rt01, protocol: BGP, note: IPsecトンネルへ経路切替}
views:
  - {id: path-fail, title: IP-VPN障害時経路, type: path, path: hq-osk-backup}
```

## 9. OSPFエリアの表し方 (domains)

エリア名を線1本ずつにラベルせず、`domains` への参照で表す。図ではエリア別の色分け+凡例(内蔵SVGでは所属機器を囲む面塗りも)になり、ABRは複数エリアの領域の重なりに立つ。

```yaml
domains:
  - {id: area0, name: OSPF Area 0 (バックボーン)}
  - {id: area1, name: OSPF Area 1 (支店側)}

links:
  - {type: logical, endpoints: ["rt01", "core01"], domain: area0}
  - {type: logical, endpoints: ["core01", "dist01"], domain: area1}  # core01がABR
```

- 色はレンダラが自動割当(DSLに色は書かない)。BGP等ドメイン外の隣接は従来どおり `description` でラベル

## 10. ビューの定番セット

用途別に4種類を定義しておくと設計書の図がほぼ揃う。

```yaml
views:
  - {id: wan-overview,  title: 全社WAN概要図,  layers: [wan-circuit, tunnel], collapse_sites: true}
  - {id: physical-all,  title: 全社物理構成図, layers: [lan-cable, wan-circuit]}
  - {id: logical-all,   title: 全社論理構成図, layers: [logical, tunnel]}
  - {id: hq-physical,   title: 本社 物理構成図, layers: [lan-cable, wan-circuit], include_sites: [hq]}
```

- 拠点数が多い場合、`physical-all` は読みにくくなる。全社は `collapse_sites`、詳細は拠点別ビューに分けるのが定石

## 11. セグメント配下の端末をボックス内に表示 (D2のみ)

```yaml
devices:
  - id: hq-srv01
    site: hq
    role: server
    interfaces:
      - {name: eno1, ipv4: 10.1.10.5/24, segment: hq-server}
```

- `role: server` の機器が、参照セグメントが1つだけの場合、論理図でそのセグメントの箱の中に入れ子で描画される([ADR-0009](adr/0009-segment-nesting.md))
- 複数セグメントに跨る機器やルーター/L3スイッチは対象外(従来通りGW接続の線で描画)
- 内蔵SVGエンジンは今のところ非対応(単一ノードとして描画される)。完成例は [examples/sample-corp/](../examples/sample-corp/) の `hq-srv01`〜`03`

## 12. 複数ビュー間で拠点の左右順序を揃える

```yaml
views:
  - {id: physical-all, title: 全社物理構成図, layers: [lan-cable, wan-circuit], order: declared}
  - {id: logical-all,  title: 全社論理構成図, layers: [logical, tunnel],        order: declared}
```

- `order: declared` を付けたビュー同士は、拠点の左右位置が `sites` の宣言順で揃う
- **内蔵SVGエンジンのみ有効**。D2(ELK)はクロス最小化ヒューリスティック任せで順序を保証できないため、物理図と論理図で拠点の並びを揃えたい場合は内蔵SVGを使う([ADR-0005 補遺3](adr/0005-layout-bfs-orientation.md))
