# sample-corp 構成表

サンプル株式会社 全社ネットワーク

## 拠点一覧

| 拠点ID | 拠点名 | 所在地 | 機器数 | 備考 |
|---|---|---|---|---|
| hq | 本社 | 東京都千代田区 | 6 | - |
| osk | 大阪支店 | 大阪府大阪市 | 2 | - |
| ngy | 名古屋営業所 | 愛知県名古屋市 | 2 | - |

## 機器一覧

| 機器ID | 拠点 | 役割 | 機種 | 冗長グループ | 管理IP | 備考 |
|---|---|---|---|---|---|---|
| hq-rt01 | 本社 | ルーター | Cisco ISR4331 | hq-wan-rt (active) | - | - |
| hq-rt02 | 本社 | ルーター | Cisco ISR4331 | hq-wan-rt (standby) | - | - |
| hq-sw01 | 本社 | L3スイッチ | Cisco Catalyst 9300 | - | - | - |
| hq-srv01 | 本社 | サーバー | PowerEdge R760 | - | - | - |
| hq-srv02 | 本社 | サーバー | PowerEdge R760 | - | - | - |
| hq-srv03 | 本社 | サーバー | PowerEdge R760 | - | - | - |
| osk-rt01 | 大阪支店 | ルーター | Cisco ISR1100 | - | - | - |
| osk-sw01 | 大阪支店 | L2スイッチ | Cisco Catalyst 1000 | - | - | - |
| ngy-rt01 | 名古屋営業所 | ルーター | Cisco ISR1100 | - | - | - |
| ngy-sw01 | 名古屋営業所 | L2スイッチ | Cisco Catalyst 1000 | - | - | - |

## 冗長グループ一覧

| グループID | 種別 | プロトコル | グループ番号 | VIP | メンバー | 備考 |
|---|---|---|---|---|---|---|
| hq-wan-rt | FHRP | HSRP | 1 | 10.1.0.1 | hq-rt01 (active) / hq-rt02 (standby) | - |

## インターフェース一覧

| 機器 | インターフェース | IPv4 | セグメント | 接続先 | 説明 |
|---|---|---|---|---|---|
| hq-rt01 | Gi0/0/0 | 172.16.255.1/30 | - | NTT Com IP-VPN網 | IP-VPNアクセス回線 |
| hq-rt01 | Gi0/0/1 | 10.1.0.2/24 | - | hq-sw01 Gi1/0/1 | コアSWへ |
| hq-rt02 | Gi0/0/0 | 203.0.113.10/29 | - | インターネット | インターネット回線 (IPsec用) |
| hq-rt02 | Gi0/0/1 | 10.1.0.3/24 | - | hq-sw01 Gi1/0/2 | コアSWへ |
| hq-rt02 | Tunnel0 | 172.31.0.1/30 | - | - | 大阪向けIPsecトンネル |
| hq-sw01 | Gi1/0/1 | - | - | hq-rt01 Gi0/0/1 | hq-rt01へ |
| hq-sw01 | Gi1/0/2 | - | - | hq-rt02 Gi0/0/1 | hq-rt02へ |
| hq-sw01 | Vlan10 | 10.1.10.1/24 | hq-server | - | サーバセグメントGW |
| hq-sw01 | Vlan20 | 10.1.20.1/24 | hq-client | - | クライアントセグメントGW |
| hq-sw01 | Gi1/0/3 | - | - | hq-srv01 eno1 | hq-srv01へ |
| hq-sw01 | Gi1/0/4 | - | - | hq-srv02 eno1 | hq-srv02へ |
| hq-sw01 | Gi1/0/5 | - | - | hq-srv03 eno1 | hq-srv03へ |
| hq-srv01 | eno1 | 10.1.10.5/24 | hq-server | hq-sw01 Gi1/0/3 | サーバセグメントへ |
| hq-srv02 | eno1 | 10.1.10.6/24 | hq-server | hq-sw01 Gi1/0/4 | サーバセグメントへ |
| hq-srv03 | eno1 | 10.1.10.7/24 | hq-server | hq-sw01 Gi1/0/5 | サーバセグメントへ |
| osk-rt01 | Gi0/0/0 | 172.16.255.5/30 | - | NTT Com IP-VPN網 | IP-VPNアクセス回線 |
| osk-rt01 | Gi0/0/1 | 198.51.100.10/30 | - | インターネット | インターネット回線 (IPsec用) |
| osk-rt01 | Gi0/1/0 | 10.2.10.1/24 | osk-lan | osk-sw01 Gi1/0/1 | フロアSWへ (LAN GW) |
| osk-rt01 | Tunnel0 | 172.31.0.2/30 | - | - | 本社向けIPsecトンネル |
| osk-sw01 | Gi1/0/1 | - | - | osk-rt01 Gi0/1/0 | osk-rt01へ |
| ngy-rt01 | Gi0/0/0 | 172.16.255.9/30 | - | NTT Com IP-VPN網 | IP-VPNアクセス回線 |
| ngy-rt01 | Gi0/1/0 | 10.3.10.1/24 | ngy-lan | ngy-sw01 Gi1/0/1 | フロアSWへ (LAN GW) |
| ngy-sw01 | Gi1/0/1 | - | - | ngy-rt01 Gi0/1/0 | ngy-rt01へ |

## 回線一覧

| 回線ID | 事業者 | サービス | 回線番号 | 帯域 | 状態 | 収容先 | 備考 |
|---|---|---|---|---|---|---|---|
| cct-ipvpn-hq | NTTコミュニケーションズ | IP-VPN | N-100001 | 100M | 利用中 | 本社 hq-rt01 Gi0/0/0 | - |
| cct-ipvpn-osk | NTTコミュニケーションズ | IP-VPN | N-100002 | 50M | 利用中 | 大阪支店 osk-rt01 Gi0/0/0 | - |
| cct-ipvpn-ngy | NTTコミュニケーションズ | IP-VPN | N-100003 | 50M | 利用中 | 名古屋営業所 ngy-rt01 Gi0/0/0 | - |
| cct-inet-hq | NTT東日本 | フレッツ光ネクスト + OCN | CAF-200001 | 1G | 利用中 | 本社 hq-rt02 Gi0/0/0 | - |
| cct-inet-osk | NTT西日本 | フレッツ光ネクスト + OCN | CAF-200002 | 1G | 利用中 | 大阪支店 osk-rt01 Gi0/0/1 | - |

## 接続一覧

| 種別 | 端点1 | 端点2 | 回線 | ドメイン | 備考 |
|---|---|---|---|---|---|
| 構内配線 | hq-rt01:Gi0/0/1 | hq-sw01:Gi1/0/1 | - | - | - |
| 構内配線 | hq-rt02:Gi0/0/1 | hq-sw01:Gi1/0/2 | - | - | - |
| 構内配線 | osk-rt01:Gi0/1/0 | osk-sw01:Gi1/0/1 | - | - | - |
| 構内配線 | ngy-rt01:Gi0/1/0 | ngy-sw01:Gi1/0/1 | - | - | - |
| 構内配線 | hq-sw01:Gi1/0/3 | hq-srv01:eno1 | - | - | - |
| 構内配線 | hq-sw01:Gi1/0/4 | hq-srv02:eno1 | - | - | - |
| 構内配線 | hq-sw01:Gi1/0/5 | hq-srv03:eno1 | - | - | - |
| WAN回線 | hq-rt01:Gi0/0/0 | ipvpn | cct-ipvpn-hq | - | - |
| WAN回線 | osk-rt01:Gi0/0/0 | ipvpn | cct-ipvpn-osk | - | - |
| WAN回線 | ngy-rt01:Gi0/0/0 | ipvpn | cct-ipvpn-ngy | - | - |
| WAN回線 | hq-rt02:Gi0/0/0 | internet | cct-inet-hq | - | - |
| WAN回線 | osk-rt01:Gi0/0/1 | internet | cct-inet-osk | - | - |
| トンネル | hq-rt02:Tunnel0 | osk-rt01:Tunnel0 | - | - | IPsec バックアップVPN |
| 論理隣接 | hq-rt01 | osk-rt01 | - | - | BGP |
| 論理隣接 | hq-rt01 | ngy-rt01 | - | - | BGP |

## セグメント一覧

| セグメントID | 拠点 | VLAN | ネットワーク | 名称 | ゲートウェイ | 備考 |
|---|---|---|---|---|---|---|
| hq-server | 本社 | 10 | 10.1.10.0/24 | 本社サーバ | hq-sw01 Vlan10 (10.1.10.1/24) / hq-srv01 eno1 (10.1.10.5/24) / hq-srv02 eno1 (10.1.10.6/24) / hq-srv03 eno1 (10.1.10.7/24) | - |
| hq-client | 本社 | 20 | 10.1.20.0/24 | 本社クライアント | hq-sw01 Vlan20 (10.1.20.1/24) | - |
| osk-lan | 大阪支店 | 1 | 10.2.10.0/24 | 大阪LAN | osk-rt01 Gi0/1/0 (10.2.10.1/24) | - |
| ngy-lan | 名古屋営業所 | 1 | 10.3.10.0/24 | 名古屋LAN | ngy-rt01 Gi0/1/0 (10.3.10.1/24) | - |
