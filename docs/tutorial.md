# チュートリアル

最小構成から始めて、WAN・描き分け・表生成まで段階的に nwdsl を学ぶ。所要 30 分程度。
(このチュートリアルの全ステップは実際にコマンドを実行して検証済み)

## 0. 準備

**[uv](https://docs.astral.sh/uv/) の場合**

```powershell
git clone <this-repo> ; cd nw-config-dsl
uv sync
uv run nwdsl --help
```

**pip の場合**

```powershell
git clone <this-repo> ; cd nw-config-dsl
python -m venv .venv
.\.venv\Scripts\pip install -e .
.\.venv\Scripts\Activate.ps1   # nwdsl コマンドを直接使えるようにする (pip install -e . だけではPATHが通らない)
nwdsl --help    # 実行ポリシーでActivate.ps1が弾かれる場合は .\.venv\Scripts\nwdsl.exe --help と読み替える
```

以降のコマンド例は uv 側の表記(`uv run nwdsl ...`)で統一する。pip環境の場合は先頭の `uv run` を省いて読み替える。

図をSVG化する場合は [D2](https://github.com/terrastruct/d2/releases) のバイナリを入れておく(無くても内蔵SVGエンジンでこのチュートリアルは進められる)。
Windowsは `.\scripts\install_d2.ps1` を実行するとリポジトリの `.tools\` に取得され自動検出される(`.tools\` は`.gitignore`対象なのでclone直後は各自実行が必要)。

> **いちばん簡単な試し方**: `nwdsl serve` を実行するとブラウザで playground が開く。
> YAML を編集すると自動で検証+描画され、このチュートリアルも画面内で読める。
> 以降の手順は CLI ベースで説明するが、playground 上で同じ YAML を貼っても動く。

## 1. 最小構成: 1拠点・2機器・1本のケーブル

`network.yaml` を作る:

```yaml
nwdsl: "0.2"

network:
  name: my-first-network

sites:
  - id: hq
    name: 本社

devices:
  - id: hq-rt01
    site: hq
    role: router
    platform: Cisco ISR1100
    interfaces:
      - name: Gi0/1/0
  - id: hq-sw01
    site: hq
    role: l2switch
    platform: Cisco Catalyst 1000
    interfaces:
      - name: Gi1/0/1

links:
  - type: lan-cable
    endpoints: ["hq-rt01:Gi0/1/0", "hq-sw01:Gi1/0/1"]

views:
  - id: physical
    title: 物理構成図
    layers: [lan-cable]
```

ポイント:

- **link の端点は `"機器ID:インターフェース名"`**。そのIFは `devices` 側で宣言されていないとエラーになる(タイポ防止)
- **`type: lan-cable`** は「構内の物理結線」。線の意味は必ず type で宣言する

検査して描画する:

```powershell
uv run nwdsl validate network.yaml
# OK: エラー 0件 / 警告 0件

uv run nwdsl render network.yaml -o diagrams
.\.tools\d2-v0.7.1\bin\d2.exe --layout=elk diagrams\physical.d2 diagrams\physical.svg
# D2をPATHに別途インストール済みなら: d2 --layout=elk diagrams\physical.d2 diagrams\physical.svg
```

## 2. 拠点を増やして WAN でつなぐ

支店と IP-VPN を追加する。**キャリアから買う回線は `circuits`(契約)と link(結線)に分けて書く**のが nwdsl の流儀。IP-VPN のようなマルチポイント網は `clouds` に定義して端点に指定する。

```yaml
# sites に追加
  - id: br1
    name: 支店

# devices に追加
  - id: br1-rt01
    site: br1
    role: router
    platform: Cisco ISR1100
    interfaces:
      - name: Gi0/0/0
        description: IP-VPNアクセス回線

# hq-rt01 の interfaces にも WAN 側を追加
      - name: Gi0/0/0
        description: IP-VPNアクセス回線

clouds:
  - id: ipvpn
    name: IP-VPN網
    kind: wan

circuits:
  - id: cct-ipvpn-hq
    provider: NTTコミュニケーションズ
    service: IP-VPN
    circuit_id: N-000001   # 事業者発行の回線番号
    bandwidth: 100M
  - id: cct-ipvpn-br1
    provider: NTTコミュニケーションズ
    service: IP-VPN
    circuit_id: N-000002
    bandwidth: 50M

# links に追加: アクセス回線 = 機器IF と cloud を wan-circuit で結ぶ
  - type: wan-circuit
    endpoints: ["hq-rt01:Gi0/0/0", "ipvpn"]
    circuit: cct-ipvpn-hq
  - type: wan-circuit
    endpoints: ["br1-rt01:Gi0/0/0", "ipvpn"]
    circuit: cct-ipvpn-br1

# views の physical も layers を広げる
    layers: [lan-cable, wan-circuit]
```

`nwdsl validate` → `nwdsl render` すると、物理図に IP-VPN の雲と青い太線のアクセス回線(回線事業者・帯域・IF名付き)が現れる。

- 専用線のような point-to-point 回線は cloud を使わず `endpoints: ["機器A:IF", "機器B:IF"]` を直接 wan-circuit で結ぶ
- `circuit:` を書き忘れると `link.circuit-required` エラーになる

## 3. 論理構成と「描き分け」

L3 の隣接関係(`logical`)、IP・セグメント、そして views の描き分けを足す:

```yaml
# links に追加: 網の上のBGPピアリング (物理とは別レイヤ)
  - type: logical
    endpoints: ["hq-rt01", "br1-rt01"]   # logical は IF 省略可
    description: BGP (IP-VPN網内)

segments:
  - id: hq-lan
    site: hq
    vlan: 1
    ipv4: 10.1.1.0/24
    name: 本社LAN

# hq-rt01 の LAN 側 IF に IP とセグメントを付ける
      - name: Gi0/1/0
        description: LAN側 (GW)
        ipv4: 10.1.1.1/24
        segment: hq-lan

views:
  - id: physical
    title: 物理構成図
    layers: [lan-cable, wan-circuit]
  - id: logical
    title: 論理構成図
    layers: [logical]
  - id: overview
    title: 全社概要図
    layers: [wan-circuit]
    collapse_sites: true      # 拠点を1ノードに畳む
  - id: hq-only
    title: 本社詳細図
    layers: [lan-cable, wan-circuit]
    include_sites: [hq]       # 範囲を本社に絞る
```

`nwdsl render` で4つの図ソースが生成される。**同じトポロジ定義から、レイヤ・範囲・抽象度の宣言だけで4種類の図が導出される**のが nwdsl の中心機能。

- VPNトンネル(IPsec等)は `type: tunnel` で書く(端点は Tunnel IF でも機器でも可)
- HSRP/VRRP ペアやスタックは `redundancy_groups` にグループを宣言する (書き方は [patterns.md §1](patterns.md)):

```yaml
redundancy_groups:
  - id: hq-wan
    protocol: hsrp
    vip: 10.1.1.254
    members:
      - {device: hq-rt01, role: active}
      - {device: hq-rt02, role: standby}
```

  図では2台が点線枠で囲まれて `(Act)`/`(Sby)` が付き、VIP はIP設計表にも載る

## 4. 通信経路を描く(正常時/障害時)

構成図とは別に「トラフィックがどこを通るか」を示す経路図を出せる。経路はホップ列で明示し、切替を決めるプロトコルを注記する:

```yaml
paths:
  - id: hq-br1-normal
    title: 本社→支店 (正常時)
    hops:
      - node: hq-sw01
      - node: hq-rt01
        protocol: HSRP
        note: active側GW
      - node: ipvpn
      - node: br1-rt01

views:
  - id: path-normal
    title: 通信経路 本社→支店 (正常時)
    type: path
    path: hq-br1-normal
```

- 隣接ホップ間に実在の link が無いと `path.hop-not-adjacent` エラーになる(構成と矛盾した経路は書けない)
- 障害時経路は `failure: [ipvpn]`(障害コンポーネントに赤✕)と `fallback_of: <正常経路id>`(死んだ経路を灰破線で併記)を付ける。完成例は [examples/sample-corp/](../examples/sample-corp/) の `hq-osk-backup` を参照
- 描画すると経路が赤太線+①②…のホップ番号+プロトコル注記で強調され、経路外は淡色化される。SVG では経路の線が流れるアニメーションになる

## 5. 設計書向けの表を出す

```powershell
uv run nwdsl tables network.yaml -o tables.md
uv run nwdsl tables network.yaml --section circuits --section interfaces  # 部分出力
```

拠点一覧・機器一覧・冗長グループ一覧・インターフェース一覧・回線一覧・接続一覧・セグメント一覧・ルーティング一覧が Markdown 表で出力される (冗長・ルーティングは定義がある場合のみ)。インターフェース一覧の「接続先」や回線一覧の「収容先」は links から自動導出されるため、**図と表が食い違うことは構造的にない**。

## 6. バリデーションを味方にする

わざと壊してみる(スイッチ側のIF名をタイポ):

```powershell
uv run nwdsl validate network.yaml
# [ERROR] ref.interface: link links[0] (hq-rt01:Gi0/1/0 -- hq-sw01:Gi1/0/99):
#         device 'hq-sw01' に interface 'Gi1/0/99' が宣言されていません
# NG: エラー 1件 / 警告 0件   (exit code 1)
```

CI に `nwdsl validate --strict`(警告もエラー扱い)を入れておくと、レビュー前に不整合を検出できる。
エディタ補完が欲しい場合は JSON Schema を生成して YAML Language Server に食わせる:

```powershell
uv run nwdsl schema -o nwdsl.schema.json
```

```yaml
# yaml-language-server: $schema=./nwdsl.schema.json
nwdsl: "0.2"
...
```

## 次に読むもの

- 完全なサンプル(3拠点 + 冗長 + バックアップVPN): [examples/sample-corp/](../examples/sample-corp/)
- 全フィールドの意味と制約: [reference.md](reference.md)
- OpenSpec と組み合わせる: [openspec-integration.md](openspec-integration.md)
