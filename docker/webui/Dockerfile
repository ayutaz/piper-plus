# WebUI Docker image for piper-plus
FROM python:3.13.13-slim-trixie

# Install system dependencies.
#
# `apt-get upgrade` を併せて実行する。 base image (python:3.13.13-slim-trixie)
# は Debian trixie のパッケージを固定時点のまま含むため、 これが無いと
# util-linux / openssl / glibc 等の **fix が公開済みの** CVE をそのまま
# 出荷することになる。 trivy-container-scan.yml は `ignore-unfixed: true` を
# 指定しており、 報告される CVE は「upstream に fix があるのに当たっていない」
# ものだけである (2026-08 時点で 3 イメージ合計 341 件)。
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade setuptools / wheel to clear Trivy supply-chain CVEs that
# ride on the python:3.13.13-slim-trixie default toolchain.
# pip 自身はここで upgrade しない (#748)。 `--ignore-installed` は base image
# の pip を消さずに別版を同じ site-packages に重ねるため、 base の pip と版が
# 違うと dist-info が 2 つ残り、 後段の `pip uninstall` が片方しか消せない
# (base pip が 26.0.1 の python:3.13.13、 26.2.1 の 3.13.15 で実測)。 pip は最後に削除する
# ので、 build 中に使う base の pip で足りる。
RUN pip install --no-cache-dir --break-system-packages --ignore-installed --upgrade setuptools wheel

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy source for piper_train installation
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python /app/src/python
COPY src/python_run/requirements_webui.txt /app/requirements_webui.txt
COPY src/python_run/overrides_webui.txt /app/overrides_webui.txt

# Install piper_train with inference extras + gradio + multilingual
RUN uv pip install --system "/app/src/python[inference]" && \
    uv pip install --system -r /app/requirements_webui.txt --override /app/overrides_webui.txt

# Download NLTK data required by g2p-en (English phonemizer)
# Use a shared path so data is accessible after USER switch to non-root
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# pip をイメージから外す (#748)。 pip 26.x は自分が同梱 (vendor) している
# ライブラリの一覧を CycloneDX SBOM として `pip/_vendor/bom.cdx.json` に持つ。
# Trivy はこの SBOM を読み、 msgpack 1.1.2 / setuptools 70.3.0 (pip 同梱の
# pkg_resources) / urllib3 2.7.0 などを「インストール済みのパッケージ」として
# 報告する (SBOM 由来なので FilePath も license も空になる)。 これは pip の中に
# 実在する古いコードで、 実行時には pip を使わない (依存の導入はすべて
# `uv pip`) ため、 最後の install の後で pip ごと削除する。 setuptools / wheel
# は pkg_resources を import するライブラリのために残す。
# 削除後に pip を import できないこと、 `pip/_vendor` がどこにも残っていない
# ことをビルド時に確認する (tests/scripts/test_runtime_images_ship_no_pip.py
# がこの RUN の位置を検査する)。
RUN python -m pip uninstall -y pip \
    && if python -c "import pip" 2>/dev/null; then echo "pip is still importable" >&2; exit 1; fi \
    && leftover="$(find / -xdev -path '*/pip/_vendor' -prune -print 2>/dev/null || true)" \
    && if [ -n "$leftover" ]; then echo "pip/_vendor is still present: $leftover" >&2; exit 1; fi

# Copy WebUI application and entrypoint
COPY docker/webui/app.py /app/app.py
COPY docker/webui/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create models directory
RUN mkdir -p /models /output

# Expose Gradio default port
EXPOSE 7860

# Set environment variables
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Run as non-root user for security
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /models /output /app
USER piper

ENTRYPOINT ["/app/entrypoint.sh"]
