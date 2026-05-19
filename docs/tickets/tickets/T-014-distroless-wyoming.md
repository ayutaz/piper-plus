# T-014: `wyoming` distroless 化

**チケット ID**: `T-014`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#1-3` (Distroless / Chainguard 移行 — `wyoming` image)
**Tier**: Tier 3 (Home Assistant addon deploy 対象、 **影響大**)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: T-012 完了必須 (CPU Python distroless + HF Space deploy 検証の知見を確立後に着手)

> **M3 内推奨実装順**: T-016 → T-015 → T-013 → T-012 → **T-014 (本チケット)**。
> 本 image は Home Assistant addon (`addon-piper-plus` 等) として deploy される。 HA supervisor との互換性 (s6-overlay / init system / addon manifest) を維持する必要があり、 5 image 中で最後に着手。 distroless 移行前に **s6-overlay が現状の Dockerfile に含まれているかを spike 確認** する必要あり。

---

## 1. タスク目的とゴール

### 目的

`docker/wyoming/Dockerfile` は Wyoming Protocol TTS adapter for Home Assistant。 現状 `python:3.13.13-slim-trixie` ベースの multi-stage build。 builder で wheel build (workspace editable 回避)、 runtime に `libsndfile1` のみ apt install。 `ENTRYPOINT ["python", "-m", "piper_wyoming"]`。

Home Assistant addon としての deploy 対象であり、 HA supervisor の init system / addon manifest との互換性が必要。 現状の Dockerfile は s6-overlay を **含んでいない** (HA 公式 addon template との差異)。 distroless 化に際して s6-overlay の必要性を判定する spike が前提。

### ゴール (Done definition)

- [ ] base image を `cgr.dev/chainguard/python:3.13` または `gcr.io/distroless/python3-debian12` に置換 (FR-1.2)
- [ ] multi-stage 化を維持 (builder で wheel build、 final で distroless)
- [ ] `docker compose up wyoming` で起動成功、 TCP 10200 で Wyoming protocol を accept (AC-1.1a)
- [ ] image size 50%+ 削減 (AC-1.1b、 現状推定 ~1.0 GB → 500 MB 以下)
- [ ] `trivy image --severity HIGH,CRITICAL` で CVE 数 80%+ 削減 (AC-1.1c)
- [ ] HA addon deploy 後の動作確認手順を Test Plan に user 手動 step として記載 (AC-1.2)
- [ ] s6-overlay の必要性を **spike 結果として明示判定** (採用 / 不採用)
- [ ] image tag 戦略を user が決定し PR 本文に明記 (FR-1.5)
- [ ] PR コメントに `docker/wyoming/distroless-report.md` 自動投稿 (FR-1.4)

### user 判断待ち項目 (着手前確認)

1. **image tag 戦略 (FR-1.5)**:
   - (a) 既存 tag (`wyoming-piper-plus:latest`) を置換
   - (b) `wyoming-piper-plus:<ver>-distroless` を別 tag で並行配信
   - 推奨は (b)。 HA addon 利用者の cold start 互換性を 1-2 週間並行配信で確認後に置換。
2. **s6-overlay 採用判断**:
   - 現状 Dockerfile に s6-overlay は **含まれていない** (確認済み)
   - HA addon template (`ha-addon-base`) は s6-overlay 同梱が default
   - 選択肢:
     - (a) s6-overlay 不採用継続 (現状維持) — distroless と整合性高
     - (b) HA addon 標準準拠で s6-overlay 採用 — distroless との両立は技術的に困難
   - 推奨は (a)。 現行 entrypoint (`python -m piper_wyoming`) で HA addon として動作実績あり (HA 2026.x 互換性は wyoming>=1.7,<2 で確保)。
3. **HA addon manifest との整合性**:
   - `config.yaml` (HA addon manifest) で image: の参照を変更する必要があるか確認
   - addon repository (別 repo: `ayousanz/hassio-addons` 等) の更新が必要か確認

---

## 2. 実装内容の詳細

### 2.1 既存 Dockerfile の base image

| stage | base | 主要 install |
|-------|------|--------------|
| Stage 1 (builder) | `python:3.13.13-slim-trixie` | apt `build-essential cmake g++ libsndfile1-dev` + uv + wheel build + `wyoming>=1.7,<2` + `huggingface-hub>=0.22` + NLTK data |
| Stage 2 (runtime) | `python:3.13.13-slim-trixie` | apt `libsndfile1` + COPY `/usr/local` + NLTK data + `piper_plus` / `piper_wyoming` source |

### 2.2 s6-overlay 必要性 spike (着手前必須)

着手前に以下を確認:

- [ ] HA addon として deploy された場合、 init system は何か (s6 / runit / direct python)
- [ ] HA supervisor が container 起動時に s6 startup files (`/etc/services.d/*`) を期待するか
- [ ] 現行 image (s6 なし) で HA addon として動作実績はあるか — addon repository の commit log 確認

**結論案** (spike 結果次第):

- 動作実績あり + supervisor 互換性 OK → s6-overlay **不採用** で distroless 化進行
- 動作未確認 → 別 PR で先に s6 互換性検証、 本チケットは pending

### 2.3 移行後 base image 候補比較

| 候補 | 長所 | 短所 |
|------|------|------|
| `cgr.dev/chainguard/python:3.13` | T-012 / T-013 と統一、 Python 3.13 維持 | s6-overlay 同梱不可 |
| `gcr.io/distroless/python3-debian12` | Google maintained | Python 3.11 で version 後退 |
| `cgr.dev/chainguard/wolfi-base` + python | apk で s6-overlay install 可 | size 大、 distroless 哲学から外れる |

**推奨**: `cgr.dev/chainguard/python:3.13` (T-012 / T-013 と統一)。

### 2.4 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `docker/wyoming/Dockerfile` | 変更 | runtime stage の base 置換 |
| `docker/wyoming/distroless-report.md` | 新規 | size + CVE diff の auto-generate 出力 |
| `docker/wyoming/docker-compose.yml` | 変更 | user UID (65532) 調整、 volume mount permission |
| `.github/workflows/docker-build.yml` | 変更 | wyoming matrix に distroless variant 追加 |
| `docs/reference/distroless-migration.md` | 追記 | wyoming 移行の知見追記 |
| (別 repo) HA addon manifest `config.yaml` | 確認 | 必要なら image: 参照を更新 |

### 2.5 multi-stage build 構成

```dockerfile
# Stage 1: Builder (unchanged: pin python:3.13.13-slim-trixie for wheel build environment consistency)
FROM python:3.13.13-slim-trixie AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake g++ libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv>=0.9,<1"

WORKDIR /build

COPY VERSION /build/VERSION
COPY pyproject.toml /build/pyproject.toml
COPY src/python/ /build/src/python/

# wheel build (workspace editable 回避、 既存 wyoming Dockerfile comment 参照)
RUN uv build /build/src/python/g2p --wheel --out-dir /tmp/wheels/ \
    && uv build /build/src/python      --wheel --out-dir /tmp/wheels/

RUN uv pip install --system "$(ls /tmp/wheels/piper_plus_g2p-*.whl)[all]" \
    && uv pip install --system "$(ls /tmp/wheels/piper_train-*.whl)[inference]" \
    && uv pip install --system "wyoming>=1.7,<2" \
    && uv pip install --system "huggingface-hub>=0.22"

# NLTK data
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "\
import nltk; \
nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); \
nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); \
nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# Stage 2: Distroless final
FROM cgr.dev/chainguard/python:3.13

USER root

COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/share/nltk_data /usr/share/nltk_data
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsndfile.so* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libgomp.so* /usr/lib/x86_64-linux-gnu/

# piper_plus / piper_wyoming source (not part of piper_train wheel)
COPY src/python/piper_plus/   /app/piper_plus/
COPY src/python/piper_wyoming/ /app/piper_wyoming/

ENV NLTK_DATA=/usr/share/nltk_data
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PIPER_MODEL=tsukuyomi
ENV PIPER_LANGUAGE=ja
ENV PIPER_SPEAKER_ID=0
ENV PIPER_NOISE_SCALE=0.667
ENV PIPER_LENGTH_SCALE=1.0
ENV PIPER_NOISE_W=0.8
ENV PIPER_DEVICE=cpu
ENV PIPER_PORT=10200

WORKDIR /app

RUN mkdir -p /app/models /home/nonroot/.cache/piper-plus/models \
    && chown -R 65532:65532 /app/models /home/nonroot

USER 65532

EXPOSE 10200

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 10200)); s.close()"]

ENTRYPOINT ["python", "-m", "piper_wyoming"]
CMD ["--model", "tsukuyomi", "--uri", "tcp://0.0.0.0:10200"]
```

### 2.6 HA addon deploy 検証手順 (AC-1.2、 user 手動 step)

PR Test Plan に以下を必須記載 (Claude Code は実行不可、 user 手動 step):

```markdown
## Test Plan: HA addon deploy validation (manual)

1. Branch checkout: `git checkout <pr-branch>`
2. Build distroless image: `docker build -f docker/wyoming/Dockerfile -t wyoming-piper-plus:distroless .`
3. Smoke test: `docker run -p 10200:10200 -v ~/wyoming-models:/app/models wyoming-piper-plus:distroless`
4. Wyoming protocol check: `python -c "import asyncio; from wyoming.client import AsyncTcpClient; ..."` (基本接続)
5. HA staging instance に手動で image push (HA supervisor 経由 or `docker save` + `docker load` on HA host)
6. HA addon UI から addon を install / start、 ログ確認
7. HA 音声 assist で TTS 動作確認 (HA admin manual step)
8. 24h 連続稼働で memory leak / cold restart 失敗が無いことを確認
9. If staging OK, addon repository (別 repo) の manifest を update
```

### 2.7 PR コメント自動投稿 (`docker/wyoming/distroless-report.md`)

format (FR-1.4): T-012 と同 format に HA addon deploy 結果 (user 手動測定後追記欄) を含む。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | Dockerfile runtime stage の base 置換、 multi-stage 維持 | `docker/wyoming/Dockerfile` |
| **Test author** | 1 | Wyoming protocol smoke test、 docker-compose 修正 | `docker/wyoming/test_integration.py` |
| **Spec / Doc author** | 1 | distroless-migration.md 追記、 HA addon 検証手順 + s6-overlay spike 結果記録 | doc + Test Plan |
| **Deploy verifier** | 1 (user 自身) | HA staging instance deploy + 24h 連続稼働確認 | 手動検証 report |
| **Reviewer** | 1 | Wyoming protocol / HA supervisor 互換性 | review |

**並列度**: T-012 完了後に着手。 s6-overlay spike は Spec / Doc author が先行実施し結論を出してから Implementer が着手。

**Agent prompt の与え方**: Explore subagent で `docker/wyoming/Dockerfile` + `test_integration.py` + `README.md` + HA addon repository (別 repo を確認可能なら) を dump → general-purpose で s6-overlay spike + distroless 化実装と Wyoming protocol smoke test 並列、 最後に user に HA staging deploy を request。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `docker/wyoming/Dockerfile` の runtime stage base 置換
- multi-stage build (builder = python:3.13.13-slim-trixie、 final = chainguard/python:3.13) の維持
- Wyoming protocol TCP 10200 smoke test
- s6-overlay 必要性 spike + 不採用判断の doc 化
- HA addon deploy 検証手順 (user 手動 step) の Test Plan 記載

**Out of scope**:

- HA addon repository (別 repo) の manifest 更新 (user 手動、 別 PR)
- s6-overlay 採用する場合の addon repository 改修 (本チケット scope 外、 別 milestone)
- 他の 4 image (別チケット)
- HA supervisor 側の修正 (HA core への PR、 別 line)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | Dockerfile build | `docker build -f docker/wyoming/Dockerfile .` | exit 0 |
| UT-2 | image size | `docker images` | before の 50% 以下 |
| UT-3 | CVE scan | `trivy image --severity HIGH,CRITICAL` | before の 20% 以下 |
| UT-4 | Python import | `python -c "import piper_wyoming; import wyoming; import piper_plus; import piper_plus_g2p"` | exit 0 |
| UT-5 | NLTK data | `python -c "import nltk; nltk.data.find('taggers/...')"` | exit 0 |
| UT-6 | libsndfile / libgomp | `python -c "import soundfile, onnxruntime"` | exit 0 |
| UT-7 | non-root user | `id` | UID 65532 |
| UT-8 | huggingface_hub | `python -c "from huggingface_hub import hf_hub_download"` | exit 0 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full build | `docker build -t wyoming:distroless .` |
| E2E-2 | Wyoming TCP listen | `docker run -p 10200:10200 ...` + `nc -zv localhost 10200` exit 0 |
| E2E-3 | Wyoming protocol handshake | `wyoming-cli describe localhost:10200` で TtsVoice 情報 取得成功 |
| E2E-4 | TTS 合成 | `wyoming-cli synthesize "test" --output test.wav` → wav 生成成功 |
| E2E-5 | PR コメント | distroless-report.md 自動投稿 |
| E2E-6 (manual) | HA addon | user 手動で HA staging instance に install + 音声 assist で TTS 動作確認 |
| E2E-7 (manual) | 24h 連続稼働 | user 手動で 24h 稼働、 memory leak / restart 確認 |

### 4.4 リグレッション確認

- [ ] 既存 `docker-compose.yml` (wyoming service) が継続動作
- [ ] `test_integration.py` (Wyoming protocol integration test) が継続 pass
- [ ] HA supervisor 互換性 (image label / health check 形式) を維持
- [ ] `hadolint.yml` rule pass (DEP-1.1)
- [ ] silent-zero 防御: `trivy image` 出力件数 0 件で `::warning::`

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | s6-overlay 互換性 (HA addon template との差異) | 着手前 spike で必要性判定、 不採用継続なら現状維持 | spike report |
| C-2 | HA supervisor が container を kill する条件 (health check 失敗 / OOM / etc.) | HEALTHCHECK を exec form + Python socket で書き、 distroless 互換維持 | E2E-6 |
| C-3 | huggingface-hub の model 自動 download が non-root user (UID 65532) で動作しない | `/home/nonroot/.cache/piper-plus/models` を chown 済み、 NLTK data と同様の pattern | E2E-3 |
| C-4 | wyoming protocol の TCP listen が distroless で動作しない (network stack 制約) | python socket binding は OS network stack 経由、 distroless でも問題なし (E2E-2 で確認) | E2E-2 |
| C-5 | `piper_wyoming` source が piper_train wheel に含まれず COPY 必須 | builder ではなく final stage の `COPY src/python/piper_wyoming/` で対応 | UT-4 |
| C-6 | HA addon repository 側 manifest との image tag 整合性 | user 手動 update に依存、 本 PR Test Plan に明示 | manual |
| C-7 | 24h 連続稼働での memory leak / cold restart | user 手動 E2E-7、 24h+ 稼働で確認 | E2E-7 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] base image が `cgr.dev/chainguard/python:3.13` であること (FR-1.2)
- [ ] multi-stage build の wheel pattern が維持されていること (workspace editable 回避)
- [ ] s6-overlay 必要性 spike 結果が doc に記載されていること
- [ ] HA addon deploy 検証手順が Test Plan に **user 手動 step** として記載されていること (AC-1.2 必須)
- [ ] image tag 戦略が PR 本文 §1 で明示されていること (FR-1.5、 user 判断)
- [ ] `docker/wyoming/distroless-report.md` が PR コメントに投稿されること (FR-1.4)
- [ ] image size 50%+ 削減 / CVE 80%+ 削減を満たすこと (AC-1.1)
- [ ] Wyoming TCP 10200 で listen + protocol handshake 動作 (E2E-2, E2E-3)
- [ ] TTS 合成が wyoming-cli 経由で動作 (E2E-4)
- [ ] HEALTHCHECK が exec form + Python socket で書かれていること
- [ ] non-root user (UID 65532) で起動すること
- [ ] silent-zero pattern を踏んでいないか
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か
- [ ] markdownlint / hadolint 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか
- [ ] **HA staging instance で 24h 連続稼働確認を user が完了したか** (AC-1.2、 E2E-7)

---

## 6. 一から作り直すとしたら

### 案 A: HA addon を独自 image でなく公式 `ha-addon-base` ベースで再実装

- **概要**: `ghcr.io/home-assistant/<arch>-base-python:3.13` を base にし、 HA 公式 addon template に準拠。 s6-overlay 同梱、 HA supervisor 互換性が最大化。
- **長所**: HA 公式互換性が保証、 maintainer 負担削減、 HA 上流 update に自動追従
- **短所**: distroless 化と矛盾 (s6-overlay 同梱で size 増)、 AC-1.1b 達成困難、 distroless milestone 目標に反する
- **採否**: v1 では現方針 (distroless) を採用。 HA addon 互換性は spike で確認した範囲で十分。 v2 で HA 公式 addon template への移行検討余地あり。

### 案 B: Wyoming protocol を独立 binary (Rust) で再実装し、 Python 不要化

- **概要**: `piper-plus` Rust ランタイムに Wyoming protocol サーバを追加実装、 Python runtime を不要化。 final image は `cc-dynamic` で C++ 同等の最小構成。
- **長所**: image size 極小 (~100 MB)、 Python 依存排除で attack surface 最小化、 cold start 高速
- **短所**: Rust 側に Wyoming protocol 実装が必要 (~1000-2000 LOC)、 maintainer 学習 cost 大、 HF model download などの Python ecosystem を再実装する必要
- **採否**: v1 では Python wyoming 継続 (現方針)。 v2 で Rust 化検討時に再評価。 piper-plus の multilingual runtime parity 路線とも整合する可能性あり。

### 結論

現時点での選択は **Chainguard Python distroless + 現行 wyoming Python source 維持** (理由: M3 scope 内に収まる、 HA addon 互換性は s6-overlay 不採用継続で動作実績あり、 Rust 移植は M3 範囲外)。 v2 では HA 公式 base or Rust 再実装の二択を再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: なし (M3 distroless 5 件の最終チケット)
- **連携 milestone**: M3 retrospective で Wolfi / distroless / Chainguard 選定の総括、 後続 milestone (M4 docs infra 等) に学習引き継ぎ
- **依存解消**: M3 distroless milestone の Acceptance Criteria 全完了

### 7.2 引き継ぎ事項 (Handoff)

- s6-overlay は **不採用継続** が現方針 (HA addon template と異なるが動作実績あり)
- HA addon repository (別 repo) の manifest 更新は user 手動、 本 PR では scope 外
- HA supervisor 互換性は HEALTHCHECK exec form + Python socket で OK
- 24h 連続稼働確認は user 手動の E2E-7 で実施、 memory leak / restart 失敗を確認
- huggingface-hub の model download cache path は `/home/nonroot/.cache/piper-plus/models` (UID 65532 owner)
- M3 全 5 image の distroless 化完了後、 M3 retrospective を実施 (Wolfi vs distroless vs Chainguard 選定の総括)
- 1 image / 1 PR cadence を守る (FR-1.3、 本チケットも独立 PR)

### 7.3 未解決の質問

- [ ] image tag 戦略 (FR-1.5、 a vs b) — user 判断待ち、 推奨は (b) 並行配信
- [ ] s6-overlay 採用判断 (§1 user 判断項目 2) — 推奨案 (a) 不採用継続で着手するが、 spike 結果次第で再判定
- [ ] HA addon repository (別 repo) の manifest 更新 — user 手動、 本 PR では scope 外
- [ ] HA staging instance の準備状況 (user 側 setup 必要)
- [ ] M3 retrospective 実施タイミング (本チケット merge 後 1-2 週間以内)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.1 (`#1` Distroless), AC-1.2 (HA addon deploy)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.3
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md), M3-R2 リスク (HA addon supervisor 互換性)
- 実 Dockerfile: [`docker/wyoming/Dockerfile`](../../../docker/wyoming/Dockerfile)
- 関連: `docker/wyoming/README.md`, `docker/wyoming/docker-compose.yml`, `docker/wyoming/test_integration.py`, `src/python/piper_wyoming/`
- 先行チケット: [T-016](T-016-distroless-cpp-dev.md), [T-015](T-015-distroless-cpp-inference.md), [T-013](T-013-distroless-webui.md), [T-012](T-012-distroless-python-inference.md)
- 外部: Wyoming protocol <https://github.com/rhasspy/wyoming>, HA addon docs <https://developers.home-assistant.io/docs/add-ons>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
