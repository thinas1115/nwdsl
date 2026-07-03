# OpenSpec 統合ガイド

nwdsl を [OpenSpec](https://github.com/Fission-AI/OpenSpec) の仕様駆動ワークフローに組み込み、ネットワーク設計書をAI生成するための構成ガイド。

## 基本方針: spec は「要件」、nwdsl は「構成の事実」

役割を分ける:

- **OpenSpec の specs/**: 要件とシナリオ(「拠点間はキャリア回線を冗長化すること」)
- **nwdsl (network.yaml)**: 構成の事実の単一ソース(どの機器がどの回線でどう繋がるか)
- **生成物 (図・表)**: network.yaml から `nwdsl render` / `nwdsl tables` で導出。手で編集しない

AI には「spec の要件を満たすように network.yaml を編集させ、図や表は生成コマンドに任せる」。AIに図を直接描かせないことで、図・表・定義の不整合を排除する。

## 推奨リポジトリ構成

```
repo/
├── openspec/
│   ├── project.md            # 規約 (下記) を宣言
│   ├── specs/
│   │   └── wan-design/spec.md
│   └── changes/
│       └── add-nagoya-branch/   # 変更提案ごとのフォルダ
├── network/
│   ├── network.yaml          # nwdsl ソース (真実の源)
│   └── nwdsl.schema.json     # `nwdsl schema -o` で生成 (エディタ/AI補完用)
└── docs/
    ├── diagrams/             # `nwdsl render` の出力 (+ d2 で SVG 化)
    └── tables.md             # `nwdsl tables` の出力
```

## project.md に書く規約(例)

```markdown
## ネットワーク構成の記述規約
- ネットワーク構成の事実は `network/network.yaml` (nwdsl 0.1) が単一ソース
- 構成に触れる変更は必ず network.yaml の編集を含めること。図・表を直接編集しない
- 編集後は以下を実行し、エラー0で完了とする:
    nwdsl validate network/network.yaml --strict
    nwdsl render network/network.yaml -o docs/diagrams
    nwdsl tables network/network.yaml -o docs/tables.md
- エンティティIDは安定識別子として扱い、spec から `hq-rt01` のように参照する
- フィールドの意味は docs/reference.md (nwdsl リポジトリ) を参照
```

## spec からの参照パターン

Requirements/Scenarios で nwdsl のエンティティIDと検証コマンドを使うと、要件が機械検証可能になる:

```markdown
## Requirement: 本社WAN回線の冗長化
本社 (site: hq) は WAN 接続を2系統持たなければならない (MUST)。

### Scenario: IP-VPN 障害時のバックアップ
- GIVEN network.yaml の site `hq` に `type: wan-circuit` の link が2本以上ある
- AND 2本が異なる provider の circuit を参照している
- WHEN `nwdsl validate network/network.yaml --strict` を実行する
- THEN エラー0件で終了する
```

変更提案 (changes/) の tasks.md には生成コマンドの再実行をチェックリストとして入れる:

```markdown
- [ ] network.yaml に名古屋営業所 (site: ngy) と回線契約を追加
- [ ] nwdsl validate --strict がエラー0件
- [ ] docs/diagrams と docs/tables.md を再生成しコミット
- [ ] 全社概要図 (wan-overview) に名古屋が現れることを確認
```

## AI に network.yaml を書かせるときの入力

AI エージェントに渡すコンテキスト:

1. `nwdsl.schema.json`(構文。`nwdsl schema` で生成)
2. `docs/reference.md`(フィールドの意味と制約)
3. 現行の `network.yaml`
4. 変更要件(OpenSpec の proposal)

AI の編集後に `nwdsl validate --strict` を必ず実行させ、エラーが出たら修正ループに入れる。バリデータのエラーメッセージは修正指示として機能するよう自然文で書かれている(例: 「構内配線は lan-cable を使用してください」)。

## CI での不整合防止

生成物のコミット漏れは「図と定義の不整合」そのものなので、CI で検出する:

```yaml
# 例 (GitHub Actions)
- run: pip install -e .
- run: nwdsl validate network/network.yaml --strict
- run: nwdsl render network/network.yaml -o docs/diagrams
- run: nwdsl tables network/network.yaml -o docs/tables.md
- run: git diff --exit-code docs/   # 再生成して差分が出たら未更新
```

## 将来の拡張(本プロジェクトのスコープ外)

- `nwdsl` → Containerlab topology 生成(検証環境 clab-lab1-r1/r2/r3 での実機確認)
- AWX 経由で取得した実機情報 → network.yaml の逆生成(as-built と設計の突合)
