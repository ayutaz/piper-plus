# Mutation Testing

> Python / Rust / C# の決まった対象に小さな変異 (`+` → `-`、`==` → `!=`、
> `True` → `False` など) を入れ、テストがそれを失敗として検出するかを測る。
> 1 対象で数十分から 2 時間かかるため、**毎週と手動実行だけ**で動かす。
> 対象・使うテスト・`break` score の正本は
> [`docs/spec/mutation-testing.toml`](../spec/mutation-testing.toml)。

## なぜ測るか

line / branch coverage は「実行されたか」しか見ないので、assert のない
テストでも 100% になる。mutation testing は、コードを壊したときにテストが
落ちるかを直接測る。対象は分岐が多く入出力が決まっている G2P / SSML /
text splitter / timing に絞っている。ONNX 推論や I/O は対象外。

## score の数え方

`scripts/check_mutation_score.py score` が 3 ツール共通で次の式を使う。

```text
score = detected / (detected + undetected)
  detected    killed、timeout (テストが無限ループに気づいた)
  undetected  survived、suspicious (mutmut: テストは通り、遅くなっただけ)、
              no coverage (Stryker: どのテストも通らない行)
  数えない    compile できない mutant (unviable / CompileError)、
              `# pragma: no mutate` の行
```

ジョブは次のどれかで失敗する。

- score が `break` 未満
- mutant が 1 つも生成されない、または全部はテストされていない
  (2026-10 まで、どのジョブもこの状態のまま緑だった)
- ツール自体の異常終了

## `break` の決め方

`break` は 2026-10-25 の実測値を 5 の倍数に切り下げた値で、実測より少し下に
置く。score が動くのは対象のコードかテストが変わったときだけなので、`break`
を割ったら「テストのない新しいコード」か「弱くなったテスト」を意味する。
テストを足したら `break` を上げる。下げるときは、他のテスト閾値を緩める
ときと同じく理由を書いてレビューを通す。
`tests/scripts/test_check_mutation_score.py` が「`break` は `measured` 以下で、
5 ポイント以内」を検査している。

| runtime | 対象 | 実測 (2026-10-25) | break |
|---|---|---|---:|
| Python | `piper_plus/text_splitter.py` | 95/107 = 88.8% | 85 |
| Python | `piper_plus/timing.py` | 85/102 = 83.3% | 80 |
| Python | `piper_plus_g2p/ssml.py` | 92/132 = 69.7% | 65 |
| Python | `piper_plus_g2p/base.py` | 2/18 = 11.1% | 10 |
| Python | `piper_plus_g2p/multilingual.py` | 129/306 = 42.2% | 40 |
| Rust | `piper-plus-g2p/src/ssml.rs` | 63/71 = 88.7% | 85 |
| Rust | `piper-core/src/text_splitter.rs` | 140/197 = 71.1% | 70 |
| C# | Phonemize 4 ファイル + `Ssml/SsmlParser.cs` | 434/481 = 90.2% | 90 |

`base.py` と `multilingual.py` は score が低い。テストが各ファイル自身の
処理をほとんど確かめていないためで、テストを足す候補になっている。

## 対象ごとにテストを絞る理由

mutant ごとにテスト全体を流すと終わらない (cargo-mutants で text_splitter.rs
を全テストで回すと 1 mutant 85 秒 × 198 個)。toml の `tests` /
`cargo_test_args` に、その対象を実際に使うテストだけを書く。対象を使う
テストを新しく書いたら、ここにも足す。

## ツール別の手順

CI と同じ版・同じ引数で手元でも実行できる。

### Python (mutmut 2.5.1)

3.x は CLI と結果の形式が違うので 2.5.1 に固定している。
mutmut 2.x は `setup.cfg` / `[tool.mutmut]` しか読まないため、設定は
コマンドラインで渡す (以前あった `.mutmut.toml` は一度も読まれていなかった)。

```bash
uv venv --python 3.13 .mut-venv
VIRTUAL_ENV=.mut-venv uv pip install -e "src/python/g2p[all]" -e "src/python_run[test,cpu,http]" 'mutmut==2.5.1'
TARGET=src/python_run/piper_plus/text_splitter.py
TESTS="src/python_run/tests/test_text_splitter.py src/python_run/tests/test_text_splitter_contract.py"
.mut-venv/bin/mutmut run --paths-to-mutate "$TARGET" \
  --runner "python -m pytest $TESTS -x -q -p no:cacheprovider --override-ini=addopts= -p no:randomly"
python scripts/check_mutation_score.py score python text_splitter .mutmut-cache
.mut-venv/bin/mutmut results          # 生き残った mutant の一覧
.mut-venv/bin/mutmut show "$MUTANT_ID"  # 個別の diff (id は results の一覧にある番号)
```

### Rust (cargo-mutants 27.1.0)

`src/rust` で実行する。`--in-place` を付けるのは、コピー先の木では
`include_str!` で読むデータ (`piper-plus-g2p/data/`) が見つからないため。
実行中は対象ファイルが書き換わるので、終わるまで同じ作業ツリーで
commit しない。

```bash
cargo install --locked cargo-mutants@27.1.0
cd src/rust
cargo mutants -p piper-plus --file piper-core/src/text_splitter.rs \
  --no-shuffle --in-place --timeout 60 \
  -- --lib --test test_text_splitter --test test_text_splitter_contract
python ../../scripts/check_mutation_score.py score rust text_splitter mutants.out/outcomes.json
```

`--file` は `src/rust` からの相対パス。以前の `--file src/ssml.rs` は
どのファイルにも一致せず、0 個の mutant で成功していた。

### C# (Stryker.NET 5.0.0)

```bash
dotnet tool install --global dotnet-stryker --version 5.0.0
cd src/csharp
dotnet stryker --config-file stryker-config.json
# → StrykerOutput/<timestamp>/reports/mutation-report.{html,json}
```

- `stryker-config.json` の `"test-runner": "mtp"` は必須。test project は
  xunit v3 (実行ファイル形式) で、既定の vstest ランナーでは mutant が
  有効にならず、score が 4.2% (Killed 1 / Survived 461) と出ていた。
  mtp では同じ対象が 90.2% になる。
- `thresholds.break` は toml の `break` と同じ値にする (テストで検査)。
  Stryker 自身もこの値を割ると非 0 で終わる。
- Stryker 5 は知らないキーを拒否するので、config に `_comment` を書かない。
  `-c` は 5.x では `--concurrency` の意味になったので、設定ファイルは
  `--config-file` で渡す。

## CI

`.github/workflows/mutation-testing.yml`

- trigger: `schedule` (毎週日曜 00:00 UTC) と `workflow_dispatch`
  (`runtime` で python / rust / csharp / all を選ぶ)
- `plan` job が toml から 3 つの matrix を作る。対象を足すときは toml に
  entry を足すだけでよい
- report は 30 日間 artifact に残る
  (Python `html/` + `.mutmut-cache`、Rust `mutants.out/`、
  C# `StrykerOutput/**/reports/`)

## 関連ファイル

- `docs/spec/mutation-testing.toml` — 対象・テスト・timeout・実測・`break`
- `scripts/check_mutation_score.py` — matrix の生成と score の判定
- `tests/scripts/test_check_mutation_score.py` — 上記と workflow / config の整合
- `src/csharp/stryker-config.json` — Stryker の設定
- `.github/workflows/mutation-testing.yml` — 毎週 / 手動の CI
