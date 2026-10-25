# Wyoming Protocol TTS adapter for piper-plus
# CPU-only, multi-stage build for Home Assistant integration
#
# Build (from project root):
#   docker build -t wyoming-piper-plus -f docker/wyoming/Dockerfile .
#
# Run:
#   docker run -p 10200:10200 wyoming-piper-plus

# ============================================================
# Stage 1: Builder -- compile C extensions (pyopenjtalk, etc.)
# ============================================================
FROM python:3.13.16-slim-trixie AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies for pyopenjtalk (cmake, g++) and audio libs.
# `apt-get upgrade` については runtime stage 側のコメント参照 (同じ理由)。
# trivy-container-scan.yml の heavy scan は本 builder stage を対象にする。
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    g++ \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade setuptools / wheel to clear Trivy supply-chain CVEs. The
# builder stage's `/usr/local` is copied verbatim into the runtime stage
# (see the `COPY --from=builder /usr/local /usr/local` instruction below),
# so upgrading here propagates into the published image.
# pip 自身はここで upgrade しない (#748)。 `--ignore-installed` は base image
# の pip を消さずに別版を同じ site-packages に重ねるため、 base の pip と版が
# 違うと dist-info が 2 つ残り、 後段の `pip uninstall` が片方しか消せない
# (base pip が 26.0.1 の python:3.13.13、 26.2.1 の 3.13.15 で実測)。 pip は最後に削除する
# ので、 build 中に使う base の pip で足りる。
RUN pip install --no-cache-dir --break-system-packages --ignore-installed --upgrade setuptools wheel

# Pin uv to a known-good major version (workspace editable handling is uv version-sensitive)
RUN pip install --no-cache-dir "uv>=0.9,<1"

WORKDIR /build

# Copy source tree
COPY VERSION /build/VERSION
COPY pyproject.toml /build/pyproject.toml
COPY src/python/ /build/src/python/

# Build wheels first to guarantee non-editable installs.
# `uv pip install /path[extras]` can resolve to .pth-style editable links when uv
# detects the workspace pyproject.toml (root pyproject.toml has
# `[tool.uv.sources] piper-plus-g2p = { workspace = true, editable = true }`).
# Editable installs would leave `/build/...` references in site-packages, which
# break in stage-2 because `/build/` is not copied to the runtime image.
# Building wheels first sidesteps this entirely (archive_info instead of dir_info
# in dist-info/direct_url.json).
RUN uv build /build/src/python/g2p --wheel --out-dir /tmp/wheels/ \
    && uv build /build/src/python      --wheel --out-dir /tmp/wheels/

# Install piper_plus_g2p (standalone G2P -- all languages)
RUN uv pip install --system "$(ls /tmp/wheels/piper_plus_g2p-*.whl)[all]"

# Install piper_train with inference extras (onnxruntime CPU, soundfile, etc.)
RUN uv pip install --system "$(ls /tmp/wheels/piper_train-*.whl)[inference]"

# Install wyoming protocol library.
# >=1.5.1 added Artifact.version field; 1.5.0 raises TypeError on
# `TtsVoice(version=...)`.  We follow the rhasspy/wyoming-piper upstream pin
# (`wyoming>=1.7,<2`) for HA 2026.x compatibility.
RUN uv pip install --system "wyoming>=1.7,<2"

# Install huggingface-hub for model auto-download
RUN uv pip install --system "huggingface-hub>=0.22"

# Pre-download NLTK data for g2p-en (English phonemizer)
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "\
import nltk; \
nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); \
nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); \
nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# pip をイメージから外す (#748)。 pip 26.x は自分が同梱 (vendor) している
# ライブラリの一覧を CycloneDX SBOM として `pip/_vendor/bom.cdx.json` に持つ。
# Trivy はこの SBOM を読み、 msgpack 1.1.2 / setuptools 70.3.0 (pip 同梱の
# pkg_resources) / urllib3 2.7.0 などを「インストール済みのパッケージ」として
# 報告する (SBOM 由来なので FilePath も license も空になる)。 これは pip の中に
# 実在する古いコードで、 実行時には pip を使わない (依存の導入はすべて
# `uv pip`) ため、 最後の install の後で pip ごと削除する。 setuptools / wheel
# は pkg_resources を import するライブラリのために残す。
# trivy-container-scan.yml の heavy scan は本 builder stage を対象にするので
# ここでも消す。 runtime stage は base image 自身の pip を持つため、 そちらは
# runtime stage 側で別に消す。
# 削除後に pip を import できないこと、 `pip/_vendor` がどこにも残っていない
# ことをビルド時に確認する (tests/scripts/test_runtime_images_ship_no_pip.py
# がこの RUN の位置を検査する)。
RUN python -m pip uninstall -y pip \
    && if python -c "import pip" 2>/dev/null; then echo "pip is still importable" >&2; exit 1; fi \
    && leftover="$(find / -xdev -path '*/pip/_vendor' -prune -print 2>/dev/null || true)" \
    && if [ -n "$leftover" ]; then echo "pip/_vendor is still present: $leftover" >&2; exit 1; fi


# ============================================================
# Stage 2: Runtime -- minimal image
# ============================================================
FROM python:3.13.16-slim-trixie

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Runtime-only system dependencies.
#
# `apt-get upgrade` を併せて実行する。 base image は Debian trixie の
# パッケージを固定時点のまま含むため、 これが無いと util-linux / openssl /
# glibc 等の **fix が公開済みの** CVE をそのまま出荷することになる。
# trivy-container-scan.yml は `ignore-unfixed: true` を指定しており、
# 報告される CVE は「upstream に fix があるのに当たっていない」ものだけ。
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder.
# Use `/usr/local` as a whole instead of `/usr/local/lib/python3.X/site-packages`
# so the Dockerfile stays valid across future Python minor bumps (e.g. 3.13 → 3.14).
# Same base image in both stages → no /usr/local conflicts.
COPY --from=builder /usr/local /usr/local

# Copy NLTK data
COPY --from=builder /usr/share/nltk_data /usr/share/nltk_data
ENV NLTK_DATA=/usr/share/nltk_data

# Copy piper_plus and piper_wyoming source (not included in piper_train package).
# The high-level PiperPlus API now lives at piper_plus.api (physically merged into
# the runtime package under src/python_run/piper_plus/api/), so copy the whole
# runtime package. `import piper_plus` only pulls numpy + onnxruntime at import time
# (heavy G2P deps are lazy-loaded), so the smoke test below stays green.
COPY src/python_run/piper_plus/ /app/piper_plus/
COPY src/python/piper_wyoming/ /app/piper_wyoming/

# Add /app to PYTHONPATH so piper_plus and piper_wyoming are importable
ENV PYTHONPATH=/app

# Create directories
RUN mkdir -p /app/models /home/piper/.cache/piper-plus/models

# Environment variables for configuration
ENV PIPER_MODEL=tsukuyomi
ENV PIPER_LANGUAGE=ja
ENV PIPER_SPEAKER_ID=0
ENV PIPER_NOISE_SCALE=0.4
ENV PIPER_LENGTH_SCALE=1.0
ENV PIPER_NOISE_W=0.5
ENV PIPER_DEVICE=cpu
ENV PIPER_PORT=10200

# Build-time smoke test
RUN python --version && \
    python -c "import onnxruntime as ort; print(f'ONNX Runtime: {ort.__version__}')" && \
    python -c "import wyoming; print('wyoming installed')" && \
    python -c "import piper_plus; print('piper_plus importable')" && \
    python -c "import piper_wyoming; print('piper_wyoming importable')" && \
    python -c "import piper_plus_g2p; print('piper_plus_g2p importable')" && \
    python -c "from huggingface_hub import hf_hub_download; print('huggingface_hub available')"

# runtime stage の base image 自身が持つ pip も消す (#748、 理由は builder
# stage の同じ手順のコメント参照)。 `COPY --from=builder /usr/local` は
# builder に無いファイルを消さないので、 builder 側で消しただけでは残る。
RUN python -m pip uninstall -y pip \
    && if python -c "import pip" 2>/dev/null; then echo "pip is still importable" >&2; exit 1; fi \
    && leftover="$(find / -xdev -path '*/pip/_vendor' -prune -print 2>/dev/null || true)" \
    && if [ -n "$leftover" ]; then echo "pip/_vendor is still present: $leftover" >&2; exit 1; fi

# Run as non-root user
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /app/models /home/piper
USER piper

# Wyoming standard port
EXPOSE 10200

# Healthcheck: TCP connection to the Wyoming server
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 10200)); s.close()" || exit 1

ENTRYPOINT ["python", "-m", "piper_wyoming"]
CMD ["--model", "tsukuyomi", "--uri", "tcp://0.0.0.0:10200"]
