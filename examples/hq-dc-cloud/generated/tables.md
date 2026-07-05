# hq-dc-cloud 構成表

本社/DC/AWSのハイブリッド構成

## 拠点一覧

| 拠点ID | 拠点名 | 所在地 | 機器数 | 備考 |
|---|---|---|---|---|
| hq | 本社 | 東京都港区 | 3 | - |
| dc | DCコロケーション | 千葉県印西市 | 6 | - |
| aws | AWS ap-northeast-1 | クラウド (東京リージョン) | 1 | - |

## 機器一覧

| 機器ID | 拠点 | 役割 | 機種 | 冗長グループ | 管理IP | 備考 |
|---|---|---|---|---|---|---|
| hq-rt01 | 本社 | ルーター | Cisco C8300 | hq-wan | - | - |
| hq-rt02 | 本社 | ルーター | Cisco C8300 | hq-wan | - | - |
| hq-sw01 | 本社 | L3スイッチ | Catalyst 9300 | - | - | - |
| dc-rt01 | DCコロケーション | ルーター | Cisco C8500 | - | - | - |
| dc-fw01 | DCコロケーション | ファイアウォール | FortiGate 600F | - | - | - |
| dc-core01 | DCコロケーション | L3スイッチ | Nexus 93180 | - | - | - |
| dc-srvsw01 | DCコロケーション | L2スイッチ | Catalyst 9200 | - | - | - |
| dc-srv01 | DCコロケーション | サーバー | PowerEdge R760 (基幹AP) | - | - | - |
| dc-srv02 | DCコロケーション | サーバー | PowerEdge R760 (DB) | - | - | - |
| aws-vgw01 | AWS ap-northeast-1 | ルーター | AWS VGW/TGW | - | - | - |

## インターフェース一覧

| 機器 | インターフェース | IPv4 | セグメント | 接続先 | 説明 |
|---|---|---|---|---|---|
| hq-rt01 | Gi0/0/0 | 10.255.0.1/29 | - | 広域Ethernet網 | 広域Etherアクセス |
| hq-rt01 | Gi0/0/1 | 10.10.0.2/24 | - | hq-sw01 Gi1/0/1 | コアSWへ |
| hq-rt02 | Gi0/0/0 | 10.255.0.2/29 | - | 広域Ethernet網 | 広域Etherアクセス |
| hq-rt02 | Gi0/0/1 | 10.10.0.3/24 | - | hq-sw01 Gi1/0/2 | コアSWへ |
| hq-sw01 | Gi1/0/1 | - | - | hq-rt01 Gi0/0/1 | rt01へ |
| hq-sw01 | Gi1/0/2 | - | - | hq-rt02 Gi0/0/1 | rt02へ |
| hq-sw01 | Vlan100 | 10.10.100.1/24 | hq-users | - | 社内セグメントGW |
| dc-rt01 | Te0/0/0 | 10.255.0.3/29 | - | 広域Ethernet網 | 広域Etherアクセス |
| dc-rt01 | Te0/0/1 | - | - | dc-core01 Eth1/1 | コアへ |
| dc-rt01 | Te0/0/3 | 169.254.100.1/30 | - | aws-vgw01 dx1 | Direct Connect専用線 |
| dc-fw01 | wan1 | 198.51.100.20/29 | - | インターネット | インターネット (VPNバックアップ用) |
| dc-fw01 | internal1 | - | - | dc-core01 Eth1/2 | コアへ |
| dc-fw01 | tunnel.aws | 169.254.200.1/30 | - | - | AWS向けIPsec (バックアップ) |
| dc-core01 | Eth1/1 | - | - | dc-rt01 Te0/0/1 | rt01へ |
| dc-core01 | Eth1/2 | - | - | dc-fw01 internal1 | fw01へ |
| dc-core01 | Eth1/3 | - | - | dc-srvsw01 Gi1/0/1 | サーバSWへ |
| dc-srvsw01 | Gi1/0/1 | - | - | dc-core01 Eth1/3 | コアへ |
| dc-srvsw01 | Gi1/0/11 | - | - | dc-srv01 eno1 | srv01へ |
| dc-srvsw01 | Gi1/0/12 | - | - | dc-srv02 eno1 | srv02へ |
| dc-srv01 | eno1 | 10.20.10.11/24 | dc-servers | dc-srvsw01 Gi1/0/11 | - |
| dc-srv02 | eno1 | 10.20.10.12/24 | dc-servers | dc-srvsw01 Gi1/0/12 | - |
| aws-vgw01 | dx1 | 169.254.100.2/30 | - | dc-rt01 Te0/0/3 | Direct Connect終端 |
| aws-vgw01 | vpn1 | 169.254.200.2/30 | - | - | Site-to-Site VPN終端 (バックアップ) |
| aws-vgw01 | vpc1 | 10.100.0.1/16 | aws-vpc-app | - | VPCアタッチメント |

## 回線一覧

| 回線ID | 事業者 | サービス | 回線番号 | 帯域 | 状態 | 収容先 | 備考 |
|---|---|---|---|---|---|---|---|
| cct-we-hq1 | キャリアA | 広域Ethernet | - | 1G | 利用中 | 本社 hq-rt01 Gi0/0/0 | - |
| cct-we-hq2 | キャリアA | 広域Ethernet | - | 1G | 利用中 | 本社 hq-rt02 Gi0/0/0 | - |
| cct-we-dc | キャリアA | 広域Ethernet | - | 10G | 利用中 | DCコロケーション dc-rt01 Te0/0/0 | - |
| cct-dx | エクイニクス経由 | AWS Direct Connect 専用線 | - | 1G | 利用中 | DCコロケーション dc-rt01 Te0/0/3 / AWS ap-northeast-1 aws-vgw01 dx1 | - |
| cct-inet-dc | キャリアB | DC IXインターネット | - | 1G | 利用中 | DCコロケーション dc-fw01 wan1 | - |

## 接続一覧

| 種別 | 端点1 | 端点2 | 回線 | ドメイン | 備考 |
|---|---|---|---|---|---|
| 構内配線 | hq-rt01:Gi0/0/1 | hq-sw01:Gi1/0/1 | - | - | - |
| 構内配線 | hq-rt02:Gi0/0/1 | hq-sw01:Gi1/0/2 | - | - | - |
| 構内配線 | dc-rt01:Te0/0/1 | dc-core01:Eth1/1 | - | - | - |
| 構内配線 | dc-fw01:internal1 | dc-core01:Eth1/2 | - | - | - |
| 構内配線 | dc-core01:Eth1/3 | dc-srvsw01:Gi1/0/1 | - | - | - |
| 構内配線 | dc-srvsw01:Gi1/0/11 | dc-srv01:eno1 | - | - | - |
| 構内配線 | dc-srvsw01:Gi1/0/12 | dc-srv02:eno1 | - | - | - |
| WAN回線 | hq-rt01:Gi0/0/0 | wide-ether | cct-we-hq1 | - | - |
| WAN回線 | hq-rt02:Gi0/0/0 | wide-ether | cct-we-hq2 | - | - |
| WAN回線 | dc-rt01:Te0/0/0 | wide-ether | cct-we-dc | - | - |
| WAN回線 | dc-rt01:Te0/0/3 | aws-vgw01:dx1 | cct-dx | - | - |
| WAN回線 | dc-fw01:wan1 | internet | cct-inet-dc | - | - |
| トンネル | dc-fw01:tunnel.aws | aws-vgw01:vpn1 | - | - | Site-to-Site VPN (DX障害時のバックアップ) |
| 論理隣接 | hq-rt01 | dc-rt01 | - | - | OSPF |
| 論理隣接 | hq-rt02 | dc-rt01 | - | - | OSPF |
| 論理隣接 | dc-rt01 | aws-vgw01 | - | - | BGP (DX上) |

## セグメント一覧

| セグメントID | 拠点 | VLAN | ネットワーク | 名称 | ゲートウェイ | 備考 |
|---|---|---|---|---|---|---|
| hq-users | 本社 | 100 | 10.10.100.0/24 | 本社ユーザ | hq-sw01 Vlan100 (10.10.100.1/24) | - |
| dc-servers | DCコロケーション | 20 | 10.20.10.0/24 | DCサーバ | dc-srv01 eno1 (10.20.10.11/24) / dc-srv02 eno1 (10.20.10.12/24) | - |
| aws-vpc-app | AWS ap-northeast-1 | - | 10.100.0.0/16 | VPC アプリ用 | aws-vgw01 vpc1 (10.100.0.1/16) | - |
