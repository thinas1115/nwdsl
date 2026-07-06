# FAQ / トラブルシューティング

## よく出るバリデーションエラーと対処

| エラーコード | 意味 | 対処 |
|---|---|---|
| `ref.interface` | link端点のIFが機器に宣言されていない | `devices[].interfaces` に該当IFを追加する (タイポ検出のための仕様。自動生成はしない) |
| `ref.endpoint` | 端点のIDが devices/clouds に無い | ID のタイポを確認。cloud を使う場合は `clouds` に定義があるか確認 |
| `link.circuit-required` | wan-circuit に回線契約が無い | `circuits` に契約を定義し `circuit:` で参照する |
| `link.circuit-forbidden` | lan-cable/logical/tunnel に circuit を指定 | 回線はアクセス回線側の wan-circuit link に付ける |
| `link.lan-cross-site` | lan-cable が拠点をまたいでいる | 拠点間は wan-circuit (専用線) か tunnel を使う |
| `link.port-reuse` | 同じ物理ポートを2本の物理linkが使用 | IF を分ける。意図的な並列リンク (LAG) は別IFで書けば自動で×N束ねになる |
| `circuit.multi-use` | 1契約を複数linkが参照 | 1契約=1結線。回線が2本あるなら circuits も2つ定義する |
| `path.hop-not-adjacent` | 経路の隣接ホップを結ぶlinkが無い | 経路は実在の link 上しか通れない。中間ホップ (cloudやSW) の書き漏れが典型 |
| `circuit.unused` (警告) | active な回線が未使用 | 解約済みなら `status: decommissioned` に。移行中ならそのままでよい |

## Q&A

**Q. 図が崩れる/重なるときは?**
まずエンジンを切り替える (playground右上 or CLI `--format`)。木構造系はD2が最も整い、リング・leaf-spine・多拠点概要・確実性優先なら内蔵SVG (重なりゼロを機械検証済み)。Markdownに埋め込むならMermaid。

**Q. D2バイナリはどこから?**
Windowsは `.\scripts\install_d2.ps1` を実行すると [GitHub Releases](https://github.com/terrastruct/d2/releases) から `.tools/` に取得され自動検出される(`.tools/` は`.gitignore`対象なのでclone後に各自実行が必要)。手動で入れる場合はtar.gzを展開してPATHへ、またはリポジトリの `.tools/` に置いても自動検出される。無くても内蔵SVGエンジンで描画できる。

**Q. インターフェースを自動生成してくれないの?**
しない (設計判断)。IF宣言の強制はタイポ検出とIF一覧表の品質保証のため。書くのが手間な場合は playground でエラーを見ながら追記するのが速い。

**Q. 図とYAMLどちらを直すべき?**
内容の問題 (機器がない・線が違う) は常にYAML。見た目の問題はエンジン切替かビュー分割で対処。`.d2`/`.mmd`/`.svg` の手編集は再生成で消えるため禁止。

**Q. 拠点が多くて全社図が読めない**
全社図は `collapse_sites: true` で拠点を畳み、詳細は `include_sites: [拠点]` の拠点別ビューに分ける。「全部入り1枚」はどのツールでも破綻する。

**Q. Mermaidがplaygroundで描画されない**
Mermaid描画はCDN (jsdelivr) から mermaid.js を取得するためオフラインでは不可。「Mermaid」タブのソースをコピーして GitHub/Obsidian に貼れば描画される。

**Q. AIにDSLを書かせたい**
Docsビューア右上の「.md をコピー」でリファレンス等の原文を取得してプロンプトに貼る。加えて `nwdsl schema -o nwdsl.schema.json` のJSON Schemaを渡すと構文ミスが減る。書かせた後は必ず `nwdsl validate --strict` を通すこと (OpenSpec統合ガイド参照)。

**Q. 経路 (paths) は自動計算できないの?**
しない (設計判断、ADR-0006)。設計書に書くべきは「意図した経路」であり、明示+バリデータ検証が正。実機からのas-built取得は将来のAWX連携スコープ。

**Q. 表の「接続先」「収容先」はどこから来る?**
links からの逆引き導出。手入力ではないので図と表が食い違うことは構造的にない。

**Q. バージョン管理の運用は?**
network.yaml をGit管理し、CIで `nwdsl validate --strict` + 生成物の再生成差分チェックを回す (OpenSpec統合ガイドにGitHub Actions例あり)。
