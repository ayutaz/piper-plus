FROM debian:bullseye as build
ARG TARGETARCH
ARG TARGETVARIANT

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        build-essential cmake ca-certificates curl pkg-config git

WORKDIR /build

COPY ./ ./
RUN cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install
RUN cmake --build build --config Release
RUN cmake --install build

# Do a test run
RUN ./build/piper_phonemize --help

# Build .tar.gz to keep symlinks
WORKDIR /dist
RUN mkdir -p piper_phonemize && \
    cp -dR /build/install/* ./piper_phonemize/ && \
    tar -czf "piper-phonemize_${TARGETARCH}${TARGETVARIANT}.tar.gz" piper_phonemize/

# -----------------------------------------------------------------------------

FROM scratch

COPY --from=build /dist/piper-phonemize_*.tar.gz ./
