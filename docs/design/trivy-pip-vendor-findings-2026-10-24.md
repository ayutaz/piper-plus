# Trivy が報告する msgpack 1.1.2 / setuptools 70.3.0 は pip 同梱の SBOM から来ていた (Issue #748)

## 経緯

`trivy-container-scan.yml` のイメージスキャンで、 `python-inference`、 `python-inference-cpu-distroless`、 `webui-distroless` の 3 イメージが次の 3 件を報告していた。

| ID | パッケージ | 重大度 |
|----|-----------|--------|
| CVE-2025-47273 | setuptools 70.3.0 | HIGH |
| CVE-2026-59890 | setuptools 70.3.0 | MEDIUM |
| GHSA-6v7p-g79w-8964 | msgpack 1.1.2 (修正版 1.2.1) | HIGH |

Trivy の JSON 出力で見ると、 この 2 パッケージは `FilePath` と `Licenses` が空だった。 実際に入っている setuptools 84.x は `dist-info/METADATA` のパスと license を持つ。 イメージ内の `METADATA` を全部調べても setuptools 70.3.0 と msgpack は見つからなかったため、 「イメージ内に実体が無い報告」と判断し、 `.trivyignore.yaml` で版付きの PURL を指定して抑止していた。

この判断は誤りだった。 実体はイメージ内にある。

## 原因

pip 26.x は、 自分が同梱 (vendor) しているライブラリの一覧を CycloneDX 形式の SBOM として `pip/_vendor/bom.cdx.json` に入れている。 pip 26.2.2 の中身は次のとおり (抜粋)。

```
msgpack 1.1.2       pkg:pypi/msgpack@1.1.2
setuptools 70.3.0   pkg:pypi/setuptools@70.3.0   (pip が同梱する pkg_resources)
urllib3 2.7.0       pkg:pypi/urllib3@2.7.0
requests 2.34.2 / certifi 2026.10.19 / idna 3.18 / packaging 26.2 / rich 14.2.0 ほか
```

Trivy はイメージ内の SBOM ファイルも読み、 そこに載っているパッケージをインストール済みとして扱う。 SBOM から来た項目には `METADATA` のパスが無いので、 `FilePath` と license が空になる。 Trivy の JSON では `Identifier.BOMRef` が付いていることでも見分けられる。 構成の違う複数のイメージが同じ `PkgIdentifier.UID` を返したのも、 どれも同じ pip 26.2.2 を持っていたからである。

msgpack のコードは pip の中 (`pip/_vendor/msgpack/`) に実在する。 「実体のない報告」ではなく、 pip が抱えている古いライブラリの報告だった。

同じ SBOM から urllib3 2.7.0 の 3 件 (CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689) と setuptools 70.3.0 の GHSA-xmj3-9gf7-h52w (LOW) も報告されていた。 前者は抑止していなかったので、 これまで HIGH / MEDIUM としてそのまま SARIF に載っていた。

### 確かめた方法

`python:3.13-slim-trixie` (pip 26.2.2 入り) から 3 つのイメージを作り、 Trivy 0.67.2 と 0.76.1 の両方で走らせた。

| イメージ | msgpack 1.1.2 / setuptools 70.3.0 / urllib3 2.7.0 |
|---------|-----------------------------------------------|
| そのまま | 報告される (言語パッケージの脆弱性 7 件) |
| `pip/_vendor/vendor.txt` を削除 | 報告される (7 件のまま) |
| `pip/_vendor/bom.cdx.json` を削除 | 報告されない (0 件) |

`vendor.txt` (requirements 形式の同梱一覧) は原因ではない。 Ubuntu の apt 版 pip 24.0 (`/usr/lib/python3/dist-packages/pip/_vendor/vendor.txt`、 dpkg 管理) も報告に出てこなかった。

## 変更

### pip を runtime イメージから削除する

これらのイメージは依存の導入をすべて `uv pip install` で行い、 実行時に pip を使わない。 そこで最後の install が済んだ後に pip を削除した。 setuptools と wheel は残す (実行時に `pkg_resources` などを import するライブラリのため)。 `uv` も残るので、 派生イメージで追加の依存が要るときは `uv pip install --system` を使う。

| Dockerfile | 対応 |
|-----------|------|
| `docker/webui/Dockerfile.distroless` | builder stage で削除 (最終段は builder の `/usr/local/lib/python3.13` をそのまま COPY する) |
| `docker/python-inference/Dockerfile.cpu.distroless` | 同上 |
| `docker/python-inference/Dockerfile` (CUDA) | pip 自身で入れた pip 26.x を削除し、 apt の `python3-pip` も `apt-get purge` する。 apt 版を残すと deadsnakes の python3.13 から `import pip` できてしまうため。 `--auto-remove` は付けず、 依存として入った `python3-setuptools` / `python3-wheel` は残す |
| `docker/python-inference/Dockerfile.cpu` | 最後の install と smoke test の後で削除 |
| `docker/webui/Dockerfile` | 同上 |
| `docker/wyoming/Dockerfile` | builder stage と runtime stage の両方で削除。 runtime stage は base image 自身の pip を持ち、 `COPY --from=builder /usr/local /usr/local` は builder に無いファイルを消さないため、 builder で消すだけでは残る。 heavy scan は builder stage を対象にするので builder 側も消す |

公式 `python:` イメージを base にする 5 本では、 既存の `pip install --ignore-installed --upgrade pip setuptools wheel` から `pip` を外した (setuptools / wheel の upgrade は残す)。 `--ignore-installed` は base image の pip を消さずに別の版を同じ site-packages に重ねる。 base の pip と版が違うと dist-info が 2 つ残り、 `pip uninstall` は片方しか消せず、 消えなかったほうのファイルが壊れたまま残る。 実際に `python:3.13.13-slim-trixie` (base の pip 26.0.1) の `webui` と `python:3.13.15-slim-trixie` (26.2.1) の `wyoming` は、 下のビルド時確認で「pip is still importable」となって止まった。 pip は最後に削除するので、 build 中は base の pip で足りる。 CUDA イメージの pip 26.x は apt 版とは別のディレクトリ (/usr/local/lib/python3.13/dist-packages) に入るのでこの問題は起きず、 そのままにした。

各 Dockerfile の削除手順には、 ビルド時の確認を付けた。 pip を import できたら、 あるいは `pip/_vendor` ディレクトリがファイルシステムのどこかに残っていたら、 ビルドを失敗させる。

```dockerfile
RUN python -m pip uninstall -y pip \
    && if python -c "import pip" 2>/dev/null; then echo "pip is still importable" >&2; exit 1; fi \
    && leftover="$(find / -xdev -path '*/pip/_vendor' -prune -print 2>/dev/null || true)" \
    && if [ -n "$leftover" ]; then echo "pip/_vendor is still present: $leftover" >&2; exit 1; fi
```

変えていないもの: `docker/python-train/Dockerfile` (学習用。 研究者がコンテナ内で pip を使う前提で、 Trivy のスキャン対象からも外している) と `docker/cpp-dev/Dockerfile` (C++ 開発用。 pip は apt の `python3-pip` だけで、 Trivy の言語パッケージ解析は dpkg 管理のファイルを読まない)。

### 抑止を外す

`.trivyignore.yaml` から 3 件の抑止を外した。 workflow の `trivyignores:` がこのファイルを読むので、 ファイルは `vulnerabilities: []` として残した (Trivy 0.67.2 が空のリストをエラーなく読むことを確認済み)。 冒頭のコメントは正しい原因に書き直した。

## 確認

### webui-distroless (実ビルド)

`docker build -f docker/webui/Dockerfile.distroless` を修正前 (origin/dev) と修正後で行い、 Trivy 0.67.2 (`image --list-all-pkgs --format json --scanners vuln`) で比べた。

| 項目 | 修正前 | 修正後 |
|------|-------|-------|
| `pip` 26.2.2 (`usr/local/lib/python3.13/site-packages/pip-26.2.2.dist-info/METADATA`) | あり | なし |
| msgpack 1.1.2 (FilePath なし、 BOMRef あり) | あり (GHSA-6v7p-g79w-8964 HIGH) | なし |
| setuptools 70.3.0 (FilePath なし、 BOMRef あり) | あり (CVE-2025-47273 HIGH / CVE-2026-59890 MEDIUM / GHSA-xmj3-9gf7-h52w LOW) | なし |
| urllib3 2.7.0 (イメージに urllib3 は入っていない) | あり (HIGH 2 / MEDIUM 1) | なし |
| setuptools 84.2.1 (実在、 METADATA あり) | あり | あり |
| 言語パッケージの脆弱性 | 91 件 | 84 件 (上の 7 件が消えた) |

修正前後とも、 最終イメージで gradio / soundfile / onnxruntime / piper_train / piper_plus_g2p と `piper_train.model_manager` を import できることを確かめた。 `pkg_resources` は修正前から import できない (setuptools 84 が提供しない) ので、 pip 削除による変化は無い。

### python-inference-cpu-distroless (実ビルド)

修正後のイメージで msgpack / setuptools 70.3.0 / pip は報告されず、 言語パッケージの脆弱性は webui-distroless と同じ 84 件。 onnxruntime 1.28.0 / piper_train / gradio / fastapi / uvicorn / soundfile を import できる。

### webui / wyoming / python-inference CPU (実ビルド)

`docker/webui/Dockerfile`、 `docker/wyoming/Dockerfile` (最終段と、 heavy scan が見る `--target builder`)、 `docker/python-inference/Dockerfile.cpu` も修正後のものをビルドした。 どれも pip は残らず、 Trivy の報告に msgpack 1.1.2 / setuptools 70.3.0 / urllib3 2.7.0 / pip は出ない。 wyoming は onnxruntime / wyoming / piper_plus / piper_wyoming / piper_plus_g2p / huggingface_hub、 webui は gradio / piper_train / soundfile、 CPU 版は onnxruntime / gradio / piper_train / fastapi / uvicorn を import でき、 CPU 版では `uv` と `inference.py --help` も動く。

### python-inference (CUDA、 代替ビルド)

CUDA の base image は大きいため、 `FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04` を同じ Ubuntu 24.04 の `ubuntu:24.04` に置き換えたものを修正前後でビルドした。 apt / deadsnakes / pip / uv の手順は CUDA ライブラリに依存しないので、 pip まわりの挙動は同じになる。

- 修正前: `/usr/local/lib/python3.13/dist-packages/pip/_vendor/bom.cdx.json` があり、 msgpack 1.1.2 / setuptools 70.3.0 / urllib3 2.7.0 の 7 件が報告された。 apt 版 pip 24.0 の `vendor.txt` も残っていたが、 そこからの報告は無かった。
- 修正後: `pip uninstall` が pip 26.2.2 を削除し、 `apt-get purge -y python3-pip` が apt 版を削除した (`py3clean` は python3.13 で DeprecationWarning を出すだけで成功する)。 `import pip` は失敗し、 `pip/_vendor` は残らない。 Trivy の報告から 7 件が消え、 setuptools 84.2.1、 uv、 onnxruntime / gradio / piper_train の import は残る。

CUDA の base image そのものでのビルドは行っていない。 CI の `docker-build.yml` と `trivy-container-scan.yml` が実際のビルドを行う。

## 再発防止

- `tests/scripts/test_runtime_images_ship_no_pip.py` を追加した。 `docker/` 以下のすべての Dockerfile と、 `trivy-container-scan.yml` の matrix にある Dockerfile (新しい scan 対象を足すと自動で検査対象に入る) を読み、 次を確かめる。
  - pip を入れる stage と、 公式 `python:` イメージから始まる stage (base image が pip を持つ) は、 最後の `pip install` / `uv pip install` の後に `pip uninstall -y pip` を持つ。
  - apt で `python3-pip` を入れる stage は、 後でそれを purge する。
  - その後にビルド時の確認 (`import pip` と `pip/_vendor` の検索) がある。
  - `python:` イメージから始まる stage で、 `pip install --ignore-installed` に pip 自身を含めない。
  - `.trivyignore.yaml` の各エントリは版付きの PURL、 `statement`、 `expired_at` を持ち、 pip 同梱の版 (msgpack 1.1.2 / setuptools 70.3.0) を再び抑止していない。
  - 例外は `python-train` と `cpp-dev` だけで、 理由をテスト内に書いてある。
- このテストは pre-commit hook `runtime-images-ship-no-pip` (Dockerfile、 `.trivyignore.yaml`、 Trivy workflow、 テスト自身の変更で動く) と、 `trivy-container-scan.yml` の `gate-script-tests` job で動く。 workflow の `paths:` にもテストを追加した。
- 修正前の Dockerfile と `.trivyignore.yaml` では、 このテストは 7 件失敗する (Dockerfile 6 本と抑止 1 件)。

### 見立てを誤った理由

`FilePath` が空のパッケージを「どのファイルにも対応しない」と読んだが、 実際は「`METADATA` ではなく SBOM から来た」という意味だった。 Trivy の JSON で `Identifier.BOMRef` が付いているかどうかを見れば区別できる。 出どころの分からない報告を抑止する前に、 その版を含むファイルをイメージ全体から文字列で探す (`grep -rl 'msgpack@1.1.2' / --exclude-dir=proc --exclude-dir=sys`) と、 SBOM のような METADATA 以外の出どころも見つかる。 `python:3.13-slim-trixie` ではこれだけで `pip/_vendor/bom.cdx.json` が出てくる。
