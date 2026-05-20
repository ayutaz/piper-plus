# T-016: `cpp-dev` distroless 化

**チケット ID**: `T-016`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#1-5` (Distroless / Chainguard 移行 — `cpp-dev` image)
**Tier**: Tier 3 (blast radius 小、 学習用 spike)
**Status**: 除外確定 (M3 distroless scope-out 2026-05-20)
**PR**: PR #524 (wolfi-base trial 実施 → scope 矛盾実証 → cpp-dev は除外確定)
**担当 (予定)**: ―
**着手前提**: ―

> **Note (2026-05-20 scope-out 確定)**
>
> 本 ticket は M3 distroless 移行 scope から **除外確定**。 大目的「production image の CVE 80%+ 削減 / size 50%+ 削減」 に対する寄与が限定的、 かつ ticket §1 の本来目的 (「学習用 spike」) は PR #524 で webui + cpp-inference の trial bundle により達成済。
>
> 除外根拠 (2 点):
>
> 1. **spike 目的が達成済**: ticket §1 で取得目的とされた multi-stage build pattern (Python C 拡張 / shared lib path / ABI 整合 / entrypoint 移植) は、 PR #524 の webui (Python + soundfile + NLTK + Gradio) と cpp-inference (C++ + ldconfig + glibc ABI 整合) で全て実証済。 cpp-dev で同等の spike を再実施する追加価値なし
> 2. **dev image は distroless 哲学と本質的に不整合**: cmake / clang / gdb / valgrind を final stage に同居させないと dev experience が成立せず、 builder = final が事実上強制される。 PR #524 wolfi-base 試行で apk packaging 不足 (OpenJTalk / mecab / HTS Engine / iconv chain) も判明、 minimal 化の利益が消える構造。 加えて cpp-dev は GHCR で公開されているが **production 推論経路ではない dev image** (推論 user の attack surface ではない) ため、 supply chain 大目的への寄与も薄い
>
> 採用しない選択肢 (履歴記録):
>
> - **A. debian:12-slim 切替**: 「distroless 化」 ではないため M3 §1 FR-1.2 (cgr.dev/chainguard or gcr.io/distroless 二択) と不整合。 size 局所最適化として価値はあるが、 別 ticket (`docs/tickets/proposals/cpp-dev-base-optimization.md` 等) として再立案するのが integrity 上 clean
> - **C. wolfi 継続**: 下記旧 Note の apk infinite chain により目的達成不能、 試行 cost 不明
>
> 大目的 (supply chain 防御) は残 4 image (T-012 python-inference / T-013 webui / T-014 wyoming / T-015 cpp-inference) で完結する。 M3 milestone は **distroless × 4 image** に scope 縮小。

---

> **旧 Note (PR #524 wolfi-base trial 結果、 履歴記録)**
>
> PR [#524](https://github.com/ayutaz/piper-plus/pull/524) で本 ticket §2.2 推奨の `cgr.dev/chainguard/wolfi-base` を試行したが、 以下の構造的問題で **wolfi-base + apk add のみで canonical 機能 parity を取れない** ことが判明:
>
> 1. wolfi-base に **prebuilt package がない依存**: OpenJTalk / HTS Engine / mecab / libmecab-dev は Wolfi 公式 apk repository に未提供 (Debian apt 専用)
> 2. **source build に必要な tooling も連鎖的に不足**: `iconv` (OpenJTalk Makefile が使う) / libtool / gettext / autoconf-archive 等が apk add で順次必要、 1 build cycle ごとに次の missing が判明する infinite chain
> 3. **結果として「Wolfi minimal の CVE/size 削減」 という trial の目的が達成困難**: Debian package 群を Wolfi で source build で full reconstruction することになり、 base image 切替の supply-chain benefit が失われる
>
> **ticket 再設計の選択肢** (本 ticket は計画中に差し戻し、 別 PR で着手):
>
> - **A. base を `debian:12-slim` に変更**: ticket §2.2 の wolfi 推奨を撤回、 ubuntu:24.04 から debian:12-slim への切替で apt package を維持しつつ size 削減 (Wolfi ほどではないが Ubuntu からは小さい)。 distroless カテゴリではないが minimal 化の利益はある
> - **B. cpp-dev を distroless 化スコープから除外**: dev image は shell + apt 必須 / production deploy なし / image size の優先度が低いため、 distroless 化のメリットが薄い。 M3 milestone から cpp-dev を外して 4 image (python-inference / webui / cpp-inference / wyoming) に縮小
> - **C. Wolfi で apk add を継続的に拡張**: missing package を順次追加。 試行 cost が予測不能、 推奨しない
>
> 推奨は A または B。 user 判断後に別 PR で実施。

> **M3 内推奨実装順**: **T-016 (本チケット)** → T-015 → T-013 → T-012 → T-014。
> 本チケットは「distroless 移行の社内学習教材」 を兼ねる。 cpp-dev は dev 用 image であり、 ship 先 (HF Space / HA addon) が無いため、 移行失敗時の blast radius が repo 内に限定される。

---

## 1. タスク目的とゴール

### 目的

`docker/cpp-dev/Dockerfile` は C++ 開発者向けの dev image (cmake / clang / gdb / valgrind / cpplint 等を同梱)。 現状 `ubuntu:24.04` ベースで apt install 多数、 image size 大、 CVE 表面積大。

本チケットは distroless 移行 5 image (T-012〜T-016) の **学習用 spike** として cpp-dev を最初に置換し、 以下を取得する:

- `pyopenjtalk` C 拡張 multi-stage build pattern (後続 T-012 / T-013 / T-014 に転用)
- dev tools (cmake / gcc / gdb) を distroless final stage に置くか builder のみに留めるかの判断
- image size 削減率と CVE 削減率の base line 取得 (後続 4 image の見積もり根拠)

### ゴール (Done definition)

- [ ] base image を `cgr.dev/chainguard/<base>` または `gcr.io/distroless/<base>` に置換 (FR-1.2)
- [ ] `docker compose up cpp-dev` (該当 service 無ければ `docker build` + `docker run`) で起動成功 (AC-1.1a)
- [ ] image size 50%+ 削減 (AC-1.1b、 現状推定 ~2.5 GB → 1.2 GB 以下が目安)
- [ ] `trivy image --severity HIGH,CRITICAL` で CVE 数 80%+ 削減 (AC-1.1c)
- [ ] image tag 戦略を user が決定し PR 本文に明記 (FR-1.5)
- [ ] PR コメントに `docker/cpp-dev/distroless-report.md` (size + CVE diff) 自動投稿 (FR-1.4)
- [ ] dev 用途として最低限の subset (cmake / clang / gdb) が final stage で動作 (現行 dev tooling との互換性)
- [ ] `docker/cpp-dev/build.sh` / `test.sh` がそのまま動作

### user 判断待ち項目 (着手前確認)

1. **image tag 戦略 (FR-1.5)**:
   - (a) 既存 tag (`piper-plus-cpp-dev:latest` 等) を置換
   - (b) `piper-plus-cpp-dev:<ver>-distroless` を別 tag で並行配信
   - 推奨は (a)。 dev image は外部に ship されず、 互換性懸念が小さいため。
2. **dev tools の final stage 配置範囲**:
   - (a) cmake / clang / gdb / valgrind 全て final stage に配置 (現行互換、 size 削減効果限定的)
   - (b) build tools は builder のみ、 final は runtime に必要な lib + minimal debug tool のみ (size 最小化、 dev experience に影響)
   - 推奨は (a)。 dev image の目的を維持しつつ apt 経由でなく builder からの `COPY --from=` で配置することで `apt-get` lockfile を排除し CVE 削減を達成する。

---

## 2. 実装内容の詳細

### 2.1 既存 Dockerfile の base image

| stage | base | apt install 主要パッケージ |
|-------|------|---------------------------|
| (single stage) | `ubuntu:24.04` | `build-essential cmake ninja-build pkg-config git wget curl vim gdb valgrind clang clang-format clang-tidy ccache libsndfile1-dev libopenblas-dev libeigen3-dev libfmt-dev libspdlog-dev libgtest-dev libgmock-dev libbenchmark-dev python3.12 python3.12-dev python3-pip libmecab-dev mecab mecab-ipadic-utf8` |

外部 download:

- ONNX Runtime v1.20.0 (tarball)
- HTS Engine API 1.10 (source、 configure + make)
- Open JTalk 1.11 (source、 configure + make)
- uv installer

### 2.2 移行後 base image 候補比較

| 候補 | 長所 | 短所 |
|------|------|------|
| `cgr.dev/chainguard/wolfi-base` | apk-based、 shell / ca-certificates 同梱で dev image に向く、 update cadence 早い | apk packaging に詳しい maintainer 必要、 dev tools の入手は apk add 経由 |
| `cgr.dev/chainguard/gcc-glibc` | C++ build に最適、 glibc 互換 | runtime には別 image が必要 (本チケットは dev image なのでこの組合せは過剰) |
| `gcr.io/distroless/cc-debian12` | C runtime library 同梱、 Debian 12 baseline | dev tools 不在、 builder で全て build する必要あり |
| `gcr.io/distroless/base-debian12` | minimal、 libc 同梱 | shell なし、 dev experience に影響 |

**推奨**: dev image 用途のため `cgr.dev/chainguard/wolfi-base` を採用。 distroless 系は dev tools 不在で dev image に向かない。 ただし「distroless / Chainguard 二択」 (FR-1.2) のうち Chainguard 系を選ぶ形になる。

### 2.3 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `docker/cpp-dev/Dockerfile` | 変更 | base image 置換 + multi-stage 化 |
| `docker/cpp-dev/distroless-report.md` | 新規 | size + CVE diff の auto-generate 出力 |
| `.github/workflows/docker-build.yml` | 変更 | cpp-dev matrix に distroless variant 追加 (tag 戦略 b の場合のみ) |
| `.github/workflows/distroless-report.yml` | 新規 (M3 共通) | PR コメント自動投稿 ロジック (5 image で共有) |
| `docs/reference/distroless-migration.md` | 新規 (M3 共通) | 5 image 移行の学習集約 doc。 本チケットで初版作成 |

### 2.4 multi-stage build 構成

```dockerfile
# Stage 1: Builder (with full apt + sources)
FROM cgr.dev/chainguard/wolfi-base AS builder

USER root
RUN apk add --no-cache \
    build-base cmake ninja pkgconf git wget curl \
    clang clang-extra-tools-extra \
    sndfile-dev openblas-dev eigen-dev fmt-dev spdlog-dev \
    gtest-dev benchmark-dev \
    python-3.12 python-3.12-dev py3.12-pip \
    mecab-dev mecab-ipadic

# ONNX Runtime / HTS Engine / OpenJTalk build (現行と同等)
# ...

# Stage 2: Final (distroless dev image)
FROM cgr.dev/chainguard/wolfi-base

USER root
# Runtime + minimal dev tools
RUN apk add --no-cache \
    build-base cmake ninja clang gdb \
    sndfile openblas fmt spdlog \
    mecab mecab-ipadic \
    bash

COPY --from=builder /usr/local /usr/local
COPY --from=builder /opt/devtools /opt/devtools
ENV VIRTUAL_ENV=/opt/devtools
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN ldconfig

# 非 root user
RUN adduser -D -u 1000 piper
USER piper
WORKDIR /workspace

CMD ["bash"]
```

### 2.5 PR コメント自動投稿 (`docker/cpp-dev/distroless-report.md`)

format (FR-1.4):

```markdown
## Distroless migration report: `cpp-dev`

| metric | before (ubuntu:24.04) | after (wolfi-base) | delta |
|--------|----------------------|-------------------|-------|
| image size | 2.54 GB | 1.18 GB | -54% (AC-1.1b pass) |
| CVE HIGH | 23 | 3 | -87% (AC-1.1c pass) |
| CVE CRITICAL | 5 | 0 | -100% |
| layers | 38 | 12 | -68% |

Trivy command: `trivy image --severity HIGH,CRITICAL piper-plus-cpp-dev:<tag>`
Comparison run at: <ISO-8601 timestamp>
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | Dockerfile 移行 + multi-stage build | `docker/cpp-dev/Dockerfile` |
| **Test author** | 1 | smoke test (build.sh / test.sh 互換) | `docker/cpp-dev/test.sh` |
| **Spec / Doc author** | 1 | distroless-migration.md 初版 + Test Plan の手動 step | `docs/reference/distroless-migration.md` |
| **Reviewer** | 1 | base image / trivy report consistency | review |

**並列度**: 並列実行可能。 Implementer が Dockerfile draft → Test author が container 起動 + dev workflow 確認 → Spec author が doc 化、 を pipeline で進める。

**Agent prompt の与え方**: Explore subagent で既存 `docker/cpp-dev/Dockerfile` + `build.sh` + `test.sh` を dump → general-purpose で Wolfi / distroless base の検証 spike を並列、 最後に main agent で integrate。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `docker/cpp-dev/Dockerfile` の base image 置換と multi-stage 化
- size / CVE 計測の PR コメント自動投稿
- distroless-migration.md (M3 共通 doc) 初版作成
- 後続 4 image (T-012 / T-013 / T-014 / T-015) への学習引き継ぎ

**Out of scope**:

- 他の 4 image (別チケット)
- HF Space / HA addon 等の外部 deploy 検証 (cpp-dev は内部利用のみ)
- `python-train` の distroless 化 (CON-1.1、 GPU CUDA toolkit 依存で対象外)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | Dockerfile build | `docker build -f docker/cpp-dev/Dockerfile .` | exit 0、 final stage まで成功 |
| UT-2 | image size | `docker images --format '{{.Size}}'` | before の 50% 以下 |
| UT-3 | CVE scan | `trivy image --severity HIGH,CRITICAL` | before の 20% 以下 (80% reduction) |
| UT-4 | dev tools 存在 | `docker run ... which cmake clang gdb` | 全て /usr 配下に発見 |
| UT-5 | smoke test | `docker run ... /workspace/test.sh` | exit 0 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full build | `docker build -t cpp-dev:distroless .` → image 生成成功 |
| E2E-2 | dev workflow | `docker run -v $(pwd):/workspace cpp-dev:distroless bash -c 'cd /workspace && ./docker/cpp-dev/build.sh'` |
| E2E-3 | PR コメント | distroless-report.md が PR に自動投稿 |

### 4.4 リグレッション確認

- [ ] 既存 `build.sh` / `test.sh` の動作 (CI で `./docker/cpp-dev/test.sh` を実行)
- [ ] `docker-build.yml` matrix で cpp-dev が継続 build
- [ ] `hadolint.yml` rule pass (DEP-1.1)
- [ ] silent-zero 防御: `trivy image` 出力件数が 0 件のとき `::warning::` を立てる

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | Wolfi の apk packaging 知見不足 | distroless-migration.md に Wolfi cheat sheet を残す | M3 共通 doc |
| C-2 | dev tools (cmake / clang / gdb) が final stage で見つからない | `apk add` で final にも install (size 増だが dev image なので許容) | UT-4 |
| C-3 | OpenJTalk / HTS Engine の source build が distroless で動作しない | builder stage は wolfi-base、 source build は builder で完結 → final に `COPY --from=` | E2E-1 |
| C-4 | uv installer (`https://astral.sh/uv/install.sh`) が distroless で動作しない | builder で uv venv 構築 → final に `COPY --from=` | UT-4 |
| C-5 | non-root user 切替時の permission | `adduser -D -u 1000 piper && chown -R piper /workspace` | E2E-1 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] base image が `cgr.dev/chainguard/<base>` または `gcr.io/distroless/<base>` であること (FR-1.2)
- [ ] multi-stage build で builder の build artifact のみ final に COPY されていること
- [ ] image tag 戦略が PR 本文 §1 で明示されていること (FR-1.5、 user 判断)
- [ ] `docker/cpp-dev/distroless-report.md` が PR コメントに投稿されること (FR-1.4)
- [ ] image size 50%+ 削減 / CVE 80%+ 削減を満たすこと (AC-1.1)
- [ ] `build.sh` / `test.sh` がそのまま動作すること
- [ ] silent-zero pattern を踏んでいないか (`trivy image` 0 件で success にならない)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (sliding `@v<major>` 禁止)
- [ ] `permissions:` が least privilege か (default `contents: read`)
- [ ] markdownlint / hadolint 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか

---

## 6. 一から作り直すとしたら

> 既存実装 / 既存ドキュメントから離れて、 同じ目的を達成する別アプローチを思考実験として記載。 「現実装が劣っているか」 ではなく、 **次世代版 (v2) の設計時に再考すべき選択肢** を残すことを目的とする。

### 案 A: Dockerfile を廃止し、 buildpack / nixpkgs container に置換

- **概要**: `paketo-buildpacks/python` または `nixpkgs/cachix` を container builder として採用。 Dockerfile の手書きを廃止し、 依存宣言だけ管理。
- **長所**: 再現可能 build (nix lock file)、 CVE 自動更新、 multi-stage を意識せずに済む
- **短所**: piper-plus 既存の `cmake` / `ExternalProject` build と統合困難、 maintainer 学習 cost 大、 GPU 拡張不能
- **採否**: v1 では現方針 (Dockerfile + Chainguard wolfi-base) を採用。 v2 で nix flake への移行余地あり。

### 案 B: dev image を 2 つに分割 (dev-build / dev-runtime)

- **概要**: build tools のみ含む `cpp-dev-build` (size 大) と debug + runtime tool のみ含む `cpp-dev-runtime` (size 小) に分割。 daily dev 作業は dev-runtime で実施し、 build 時のみ dev-build に切替。
- **長所**: 通常 dev experience の size 削減、 attack surface が dev-runtime で最小化
- **短所**: docker-compose 構成が複雑化、 学習 cost 増
- **採否**: v1 では単一 cpp-dev image を維持 (現方針の継続)。 v2 で 2 分割を再評価。

### 結論

現時点での選択は **案 A / B いずれも不採用**、 Chainguard wolfi-base への単純置換を採用 (理由: M3 milestone scope 内に収まる、 後続 4 image の学習材料として最小 cost、 既存 dev workflow 互換性維持)。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-015 (cpp-inference)、 T-013 (webui)、 T-012 (python-inference)、 T-014 (wyoming)
- **連携 milestone**: M3 内で 4 件後続
- **依存解消**: 本チケットで取得した「Wolfi / distroless multi-stage の知見」 を後続 4 image に転用

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。 git history では拾えない context を残す。

- Wolfi の apk repo は最新のため CVE patch lag が小さい (distroless より早い)。 ただし固定 release への pin 戦略は別途検討
- `cp -r onnxruntime-linux-x64-1.20.0/lib/* /usr/local/lib/` の trailing slash は重要 (lib/cmake/ サブディレクトリのため `cp -r` 必須、 既存 Dockerfile コメント参照)
- HTS Engine + Open JTalk の source build は builder stage で完結させ、 final stage は `COPY --from=builder /usr/local` で十分
- distroless-report.md は M3 5 image で共通 format。 後続 ticket でも踏襲すること
- 1 image / 1 PR cadence を守る (FR-1.3、 まとめ移行禁止)

### 7.3 未解決の質問

- [ ] image tag 戦略 (FR-1.5、 a vs b) — user 判断待ち
- [ ] dev tools の final stage 配置範囲 (§1 user 判断項目 2) — 推奨案 (a) で進めるが user 確認後着手
- [ ] Wolfi vs distroless どちらを 5 image 共通とするか (T-016 spike 結果で M3 retrospective 判定)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.1 (`#1` Distroless)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.3
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 実 Dockerfile: [`docker/cpp-dev/Dockerfile`](../../../docker/cpp-dev/Dockerfile)
- 関連: `docker/cpp-dev/build.sh`, `docker/cpp-dev/test.sh`
- 外部: Chainguard Wolfi <https://www.chainguard.dev/unchained/introducing-wolfi-the-first-linux-un-distro>, distroless <https://github.com/GoogleContainerTools/distroless>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
| 2026-05-20 | M3 distroless scope から除外確定。 PR #524 で webui + cpp-inference trial が成功し spike 目的 (multi-stage pattern / ABI 整合 / entrypoint 移植) は達成済。 cpp-dev は dev image (production 推論経路なし) で distroless 哲学と構造的不整合のため、 大目的 (supply chain 防御) への寄与が限定的と判断。 ticket は履歴 / 再着手時の参照用として保持、 M3 は 4 image (T-012 / T-013 / T-014 / T-015) に scope 縮小。 | Claude Code |
