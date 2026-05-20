# T-015: `cpp-inference` distroless 化

**チケット ID**: `T-015`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#1-4` (Distroless / Chainguard 移行 — `cpp-inference` image)
**Tier**: Tier 3 (C++ runtime image、 ship 対象だが HF Space / HA addon は無し)
**Status**: 着手中 (trial 投入済 — PR #524 merged 2026-05-20。 `docker/cpp-inference/Dockerfile.distroless` 新設、 既存 Dockerfile / entrypoint.sh は不変更。 canonical 置換は promotion PR で別途、 観測期間後に着手)
**PR**: #524 (merged 2026-05-20、 T-013 と同 PR で 2 image bundle。 T-016 は wolfi 試行で scope 矛盾発覚し別 PR に分離)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: T-016 完了推奨 (Wolfi multi-stage の知見を流用)

> **M3 内推奨実装順**: T-016 → **T-015 (本チケット)** → T-013 → T-012 → T-014。
> T-016 (cpp-dev) で取得した Chainguard wolfi-base + multi-stage の知見をそのまま流用できる image。 dev image ではなく runtime image なので shared lib 解決と ldconfig 周りに特有の懸念がある。

---

## 1. タスク目的とゴール

### 目的

`docker/cpp-inference/Dockerfile` は C++ CLI ベースの TTS 推論 image (`piper --version` で起動)。 現状 `ubuntu:24.04` builder + `ubuntu:24.04` runtime の multi-stage 構成。 runtime に `libgomp1` のみ apt install。 base image を distroless 系に置換することで CVE 表面積をさらに削減する。

cpp-inference は HF Space / HA addon の deploy 対象ではないが、 **shared lib (ONNX Runtime / OpenJTalk dic) を含む binary 配布の test case** として価値が高い。 ldconfig による shared lib path 解決の挙動を distroless でも維持できるかが論点。

### ゴール (Done definition)

- [ ] runtime stage の base image を `cgr.dev/chainguard/cc-dynamic` または `gcr.io/distroless/cc-debian12` に置換 (FR-1.2)
- [ ] `docker compose up cpp-inference` (該当 service 無ければ `docker build` + `docker run`) で起動成功 (AC-1.1a)
- [ ] image size 50%+ 削減 (AC-1.1b、 現状推定 ~1.2 GB → 600 MB 以下)
- [ ] `trivy image --severity HIGH,CRITICAL` で CVE 数 80%+ 削減 (AC-1.1c)
- [ ] image tag 戦略を user が決定し PR 本文に明記 (FR-1.5)
- [ ] PR コメントに `docker/cpp-inference/distroless-report.md` (size + CVE diff) 自動投稿 (FR-1.4)
- [ ] `piper --version` / `piper --help` / 実 TTS 合成が動作

### user 判断待ち項目 (着手前確認)

1. **image tag 戦略 (FR-1.5)**:
   - (a) 既存 tag (`piper-plus-cpp:latest`) を置換
   - (b) `piper-plus-cpp:<ver>-distroless` を別 tag で並行配信
   - 推奨は (a)。 cpp-inference は内部 CI で test 用途が主体。
2. **OpenJTalk dictionary の配置場所**:
   - 現状: `/usr/local/share/open_jtalk/dic`
   - distroless では `/usr/local/share` が存在しない場合あり → `mkdir -p` + `COPY` で明示配置
3. **base image の dynamic vs static**:
   - (a) `cgr.dev/chainguard/cc-dynamic` (glibc + dynamic loader)
   - (b) `gcr.io/distroless/cc-debian12` (Debian 12 baseline)
   - 推奨は (a)。 ONNX Runtime shared lib (`.so`) を `ldconfig` で解決する前提。

---

## 2. 実装内容の詳細

### 2.1 既存 Dockerfile の base image

| stage | base | 主要 install |
|-------|------|--------------|
| Stage 1 (builder) | `ubuntu:24.04` | `build-essential cmake git wget ninja-build pkg-config ca-certificates autoconf automake libtool` + CMake ExternalProject (fmt / spdlog / piper-phonemize / espeak-ng / OpenJTalk / ONNX Runtime) |
| Stage 2 (runtime) | `ubuntu:24.04` | `libgomp1` + `COPY --from=builder /install/ /usr/local/` |

### 2.2 移行後 base image 候補比較

| 候補 | 長所 | 短所 |
|------|------|------|
| `cgr.dev/chainguard/cc-dynamic` | glibc + dynamic loader 同梱、 `.so` 解決可能、 minimal | shell 不在 (debug 困難)、 Chainguard image registry 認証 (free tier OK) |
| `cgr.dev/chainguard/wolfi-base` | shell + ca-certificates 同梱、 apk で追加 install 可 | size が cc-dynamic より大、 dev image 寄り |
| `gcr.io/distroless/cc-debian12` | Google maintained、 Debian 12 baseline、 free | update cadence が遅い、 CVE patch lag |
| `gcr.io/distroless/base-debian12` | libc 同梱、 minimal | C++ runtime (libstdc++) 不在で別途必要 |

**推奨**: `cgr.dev/chainguard/cc-dynamic`。 T-016 と base registry を統一し M3 retrospective での比較を容易化。 distroless/cc-debian12 を別 spike で 1 件比較し、 update cadence 差を計測 (M3 retrospective に記録)。

### 2.3 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `docker/cpp-inference/Dockerfile` | 変更 | runtime stage base 置換 |
| `docker/cpp-inference/distroless-report.md` | 新規 | size + CVE diff の auto-generate 出力 |
| `.github/workflows/docker-build.yml` | 変更 | cpp-inference matrix に distroless variant 追加 (tag 戦略 b の場合のみ) |
| `docs/reference/distroless-migration.md` | 追記 | cpp-inference 移行の知見を T-016 doc に追記 |

### 2.4 multi-stage build 構成

```dockerfile
# Stage 1: Builder (unchanged from current, possibly migrated to Wolfi for consistency)
FROM cgr.dev/chainguard/wolfi-base AS builder

USER root
RUN apk add --no-cache \
    build-base cmake ninja pkgconf git wget ca-certificates \
    autoconf automake libtool

# (現行と同等の build steps)
COPY CMakeLists.txt VERSION ./
COPY cmake/ cmake/
COPY src/cpp/ src/cpp/
COPY src/rust/piper-plus-g2p/data/ src/rust/piper-plus-g2p/data/

RUN mkdir -p build && cd build && \
    cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/install -DBUILD_TESTS=OFF && \
    ninja -j$(nproc) && ninja install

# OpenJTalk dictionary
RUN if [ ! -d /install/share/open_jtalk/dic ]; then \
      mkdir -p /install/share/open_jtalk && \
      wget -q -O /tmp/open_jtalk_dic.tar.gz \
        "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz" && \
      tar -xzf /tmp/open_jtalk_dic.tar.gz -C /install/share/open_jtalk && \
      mv /install/share/open_jtalk/open_jtalk_dic_utf_8-1.11 /install/share/open_jtalk/dic && \
      rm -f /tmp/open_jtalk_dic.tar.gz; \
    fi

# Stage 2: Distroless runtime
FROM cgr.dev/chainguard/cc-dynamic

COPY --from=builder /install/ /usr/local/

# ldconfig は cc-dynamic に同梱されている dynamic loader が解決するため不要だが、
# /etc/ld.so.cache を生成するためには ldconfig binary が必要
# → wolfi-base 経由で ldconfig を COPY するか、 LD_LIBRARY_PATH で代替
ENV LD_LIBRARY_PATH=/usr/local/lib

# entrypoint / test scripts
COPY docker/cpp-inference/entrypoint.sh /entrypoint.sh
COPY docker/cpp-inference/test.sh /test.sh

WORKDIR /app

USER 1000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["piper", "--version"]
```

### 2.5 shared lib path 解決の懸念

cc-dynamic は `/lib`, `/usr/lib` のみ default loader path として解決。 `/usr/local/lib` は明示 `LD_LIBRARY_PATH` 設定が必須:

```dockerfile
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
```

または、 build 時に `-Wl,-rpath,/usr/local/lib` を ld flag に追加して binary 自身に rpath を埋め込む方法もある (CMakeLists.txt 修正)。 後者は build 側修正が必要なので本チケット scope 外 (将来検討)。

### 2.6 PR コメント自動投稿 (`docker/cpp-inference/distroless-report.md`)

format (FR-1.4): T-016 と同 format。 base image / size / CVE / layers を表示。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | Dockerfile 移行 + multi-stage + LD path 解決 | `docker/cpp-inference/Dockerfile` |
| **Test author** | 1 | smoke test (`piper --version` + 実 TTS 合成) | `docker/cpp-inference/test.sh` 修正 |
| **Spec / Doc author** | 1 | distroless-migration.md 追記 (T-016 doc に cpp-inference の知見を追加) | doc |
| **Reviewer** | 1 | shared lib path / OpenJTalk dict 配置確認 | review |

**並列度**: T-016 完了後に着手。 cpp-dev で得た Wolfi 知見を流用するため、 builder stage は T-016 から copy 可。

**Agent prompt の与え方**: Explore subagent で `docker/cpp-inference/Dockerfile` + `entrypoint.sh` + `test.sh` を dump → general-purpose で cc-dynamic + Wolfi builder の組合せ実装と smoke test 並列。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `docker/cpp-inference/Dockerfile` の runtime stage base 置換 (builder も Wolfi へ移行検討)
- shared lib path 解決 (LD_LIBRARY_PATH 設定)
- OpenJTalk dictionary 配置確認
- size / CVE 計測の PR コメント自動投稿
- distroless-migration.md (T-016 共通 doc) に cpp-inference 知見追記

**Out of scope**:

- CMakeLists.txt の rpath 修正 (将来検討)
- 他の 4 image (別チケット)
- HF Space / HA addon 等の外部 deploy 検証 (cpp-inference は内部利用のみ)
- GPU 対応 (cpp-inference は CPU only)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | Dockerfile build | `docker build -f docker/cpp-inference/Dockerfile .` | exit 0 |
| UT-2 | image size | `docker images --format '{{.Size}}'` | before の 50% 以下 |
| UT-3 | CVE scan | `trivy image --severity HIGH,CRITICAL` | before の 20% 以下 |
| UT-4 | shared lib | `docker run ... ldd $(which piper)` | 全 .so が解決 (not found なし) |
| UT-5 | OpenJTalk dict | `docker run ... ls /usr/local/share/open_jtalk/dic` | exit 0、 ファイル存在 |
| UT-6 | piper smoke | `docker run ... piper --version` | piper version 出力 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full build | `docker build -t cpp-inference:distroless .` → image 生成 |
| E2E-2 | TTS 合成 | `docker run -v $(pwd)/test/models:/app/models cpp-inference:distroless piper --model /app/models/multilingual-test-medium.onnx --text "test"` → wav 生成 |
| E2E-3 | PR コメント | distroless-report.md が PR に自動投稿 |

### 4.4 リグレッション確認

- [ ] 既存 `entrypoint.sh` / `test.sh` の動作 (CI で実行)
- [ ] `docker-build.yml` matrix で cpp-inference が継続 build
- [ ] `hadolint.yml` rule pass (DEP-1.1)
- [ ] `Dockerfile.test` (テスト用 variant) も同様に distroless 化検討 (本チケット scope 外、 後続)
- [ ] silent-zero 防御: `trivy image` 出力件数が 0 件のとき `::warning::`

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | shared lib (`.so`) 解決失敗 (`/usr/local/lib` が default path に無い) | `LD_LIBRARY_PATH` 環境変数で明示設定、 ldconfig は cc-dynamic に含まれない | UT-4 (ldd check) |
| C-2 | OpenJTalk dictionary path が distroless で `/usr/local/share` に存在しない | builder で `COPY --from` で配置済み、 path 維持 | UT-5 |
| C-3 | `userdel -r ubuntu` が Wolfi base で動作しない (default user 違い) | Wolfi 既定の non-root user (`nonroot`、 UID 65532) を使うか、 piper user を adduser で再作成 | E2E-1 |
| C-4 | shell 不在で `entrypoint.sh` が動作しない (#!/bin/bash) | shell script を廃止し ENTRYPOINT を直接 binary 呼び出しに変更、 または busybox/bash を COPY | E2E-2 |
| C-5 | HEALTHCHECK が `piper --version` を呼ぶが distroless で shell wrapping が動作しない | HEALTHCHECK CMD を exec form で書く (`CMD ["piper", "--version"]`) | E2E-1 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] base image が `cgr.dev/chainguard/<base>` または `gcr.io/distroless/<base>` であること (FR-1.2)
- [ ] runtime stage に build tools が漏れていないこと (builder のみに留めること)
- [ ] image tag 戦略が PR 本文 §1 で明示されていること (FR-1.5、 user 判断)
- [ ] `docker/cpp-inference/distroless-report.md` が PR コメントに投稿されること (FR-1.4)
- [ ] image size 50%+ 削減 / CVE 80%+ 削減を満たすこと (AC-1.1)
- [ ] `piper --version` / 実 TTS 合成が動作すること (E2E-2)
- [ ] shared lib 解決が `ldd` で確認できること (UT-4)
- [ ] OpenJTalk dictionary が `/usr/local/share/open_jtalk/dic` に存在すること (UT-5)
- [ ] `entrypoint.sh` の shell 依存を排除または bash COPY すること
- [ ] silent-zero pattern を踏んでいないか
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か
- [ ] markdownlint / hadolint 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか

---

## 6. 一から作り直すとしたら

### 案 A: distroless ではなく Wolfi (apk-based) を runtime にも採用

- **概要**: cc-dynamic ではなく `cgr.dev/chainguard/wolfi-base` を runtime にも使い、 必要最小限の lib を apk で install。 shell + ldconfig が同梱されているため、 entrypoint.sh / HEALTHCHECK が現行のまま動作。
- **長所**: 既存 entrypoint.sh / HEALTHCHECK 維持、 debug 容易、 update cadence 早い (M3 milestone §4 で議論済み spike 候補)
- **短所**: cc-dynamic より size 大 (~50-100 MB 増)、 AC-1.1b の 50% 削減目標達成しにくい場合あり
- **採否**: T-016 spike 結果次第。 cc-dynamic で 50% 削減達成できない場合は Wolfi に fallback。

### 案 B: multi-stage ではなく static binary build

- **概要**: CMake build で `-static-libstdc++ -static-libgcc -Wl,-Bstatic` を指定し、 .so 依存を完全排除。 final stage は `gcr.io/distroless/static-debian12` (libc も不要)。
- **長所**: shared lib path 問題が消滅、 image size 極小 (~50-100 MB)、 attack surface 最小
- **短所**: ONNX Runtime が dynamic linking 前提のため static build できない (NumPy backend 等で symbol resolution が動的に変わる)、 license 上 LGPL 等の static link 制限あり
- **採否**: ONNX Runtime の制約により採用不可。 ただし C++ runtime のうち ONNX 以外を static link する hybrid 案は将来検討余地あり。

### 結論

現時点での選択は **cc-dynamic 採用 + 案 A fallback 余地を残す**。 T-016 retrospective で Wolfi vs distroless の比較を確定。 v2 では rpath 埋め込みで LD_LIBRARY_PATH 不要化 (CMakeLists.txt 修正) を検討。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-013 (webui)、 T-012 (python-inference)、 T-014 (wyoming)
- **連携 milestone**: M3 内で 3 件後続
- **依存解消**: shared lib path 解決 pattern を後続 3 image (Python image でも `pyopenjtalk` C 拡張 .so が同種問題を起こす) に転用

### 7.2 引き継ぎ事項 (Handoff)

- cc-dynamic は `ldconfig` を含まないため `LD_LIBRARY_PATH` での解決が必須
- HEALTHCHECK CMD は exec form (`CMD ["binary", "--flag"]`) で書く必要あり (shell 不在のため shell form 不可)
- Wolfi base への full migration を検討する場合、 T-016 と整合性を取ること
- `Dockerfile.test` の distroless 化は後続別チケットに切り出し (本 PR の scope 拡張回避)
- 1 image / 1 PR cadence を守る (FR-1.3)

### 7.3 未解決の質問

- [ ] image tag 戦略 (FR-1.5、 a vs b) — user 判断待ち
- [ ] cc-dynamic vs Wolfi base どちらを採用するか (T-016 retrospective で決定)
- [ ] CMakeLists.txt の rpath 埋め込みによる LD_LIBRARY_PATH 不要化 (v2 検討)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.1 (`#1` Distroless)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.3
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 実 Dockerfile: [`docker/cpp-inference/Dockerfile`](../../../docker/cpp-inference/Dockerfile)
- 関連: `docker/cpp-inference/entrypoint.sh`, `docker/cpp-inference/test.sh`, `cmake/Install.cmake`
- 先行チケット: [T-016 cpp-dev distroless 化](T-016-distroless-cpp-dev.md)
- 外部: Chainguard cc-dynamic <https://images.chainguard.dev/directory/image/cc-dynamic>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
| 2026-05-20 | trial PR #524 merged。 `docker/cpp-inference/Dockerfile.distroless` 投入 (builder は ubuntu:24.04 → debian:12-slim へ ABI 整合のため変更、 final は gcr.io/distroless/cc-debian12)、 canonical Dockerfile / entrypoint.sh は不変更。 image size 237MB → 232MB (-2.2%)。 `MODEL_PATH → PIPER_MODEL_PATH` 変数 remap は Dockerfile コメント内 migration note のみで未配信、 promotion PR で user 向け docs 整備必須。 promotion (canonical 置換 + 実モデル E2E 検証) は別 PR で観測期間後に実施。 | Claude Code |
