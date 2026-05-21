# Security Policy

Piper-Plus takes the security of its code, models, and downstream integrations
seriously. This document describes which versions receive security fixes, how
to report a vulnerability, and what users can do to harden their own
deployments.

## Supported Versions

| Version | Status | Notes |
|---------|--------|-------|
| 1.12.x  | Supported (current) | Receives security patches and bug fixes. |
| 1.11.x  | End of Life (EOL) | No longer receiving security patches. Please upgrade. |
| <= 1.10 | Unsupported | Pre-EOL releases; will not receive any fixes. |

If you are pinned to an unsupported release, please consult
[`docs/migration/v1.11-to-v1.12.md`](docs/migration/v1.11-to-v1.12.md) for
upgrade guidance (HiFi-GAN -> MB-iSTFT decoder, Flask -> FastAPI server, .NET
TFM bumped to `net10.0`, etc.).

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security reports.** Public
disclosure before a fix is published puts other users at risk.

Use one of the following private channels instead:

1. **Preferred — GitHub Private Security Advisory:**
   <https://github.com/ayutaz/piper-plus/security/advisories/new>
2. **Email:** `rabbitcats77@gmail.com`

When reporting, please include (where applicable):

- Affected version(s) / commit hash / package (PyPI / NuGet / crates.io / npm /
  Maven Central / SPM).
- Affected runtime (Python / C# / Rust / Go / WASM / C++ / Swift / Kotlin).
- Reproduction steps, proof-of-concept, or a minimal failing input.
- Impact assessment (RCE, DoS, data exposure, model integrity, etc.).

### Response SLA

| Stage | Target |
|-------|--------|
| Initial acknowledgement | within **72 hours** of the report |
| Triage and severity assessment | within **30 days** |
| Coordinated disclosure timeline | agreed with the reporter; typically aligned with the next patch release |

These targets are best-effort for a community-maintained project; we will keep
reporters informed if a particular issue requires more time.

## Scope

### In scope

- The `piper-plus` core repository, including:
  - Python package (`piper-plus` on PyPI), training code (`src/python/`) and
    runtime (`src/python_run/`).
  - C# packages (`PiperPlus.Core`, `PiperPlus.Cli`).
  - Rust crates (`piper-plus`, `piper-plus-cli`, `piper-plus-g2p`).
  - Go module (`github.com/ayutaz/piper-plus/src/go`).
  - JS/WASM npm packages (`piper-plus`, `@piper-plus/g2p`).
  - C API (`libpiper_plus`) and the iOS xcframework / Swift Package
    (`PiperPlus`, `PiperPlusG2P`).
  - Kotlin/Android G2P AAR
    (`io.github.ayutaz:piper-plus-g2p-android` on Maven Central).
- Official Docker images shipped from this repository
  (`docker/python-inference/`, `docker/webui/`, `docker/wyoming/`).
- Pre-trained model weights and configs published from this repository or its
  associated Hugging Face accounts.

### Out of scope

- **Training data itself.** Datasets such as MOE-Speech, LibriTTS-R, AISHELL-3,
  CML-TTS, etc. are uploaded by their respective authors / data owners; report
  data-related issues to the upstream dataset publishers.
- **`ayutaz/uPiper`** (Unity UPM package) — this lives in a separate repository
  with its own security policy.
- Third-party forks, mirrors, or repackaged distributions of piper-plus.
- Vulnerabilities that require physical access to the user's machine or that
  rely solely on already-compromised host environments.

### Docker Image Scope

The repository ships several Docker images. Trivy container scanning runs on
a weekly schedule and on changes to `docker/**/Dockerfile*` (and the workflow
file). Monitoring scope is decided **per image**: production / distributed
images and contributor-baseline development helpers are monitored, while
purely-individual local development environments (such as the 4-GPU training
stack) are excluded because their CVE alerts do not represent an external
attack surface in their intended deployment. Existing alerts on excluded
images are dismissed as `won't fix`.

| Image | Distribution | Trivy monitored? | Notes |
|-------|-------------|-----------------:|-------|
| `python-inference` (CUDA) | Production (GHCR / DockerHub) | ✅ | OpenAI-compatible TTS API server for GPU clusters |
| `python-inference-cpu-distroless` | Production | ✅ | Multi-arch CPU inference image |
| `webui` / `webui-distroless` | Production | ✅ | Gradio demo / WebUI |
| `wyoming` | Production | ✅ | Home Assistant Wyoming Protocol TTS |
| `cpp-inference` / `cpp-inference-distroless` | Production | ✅ | Native C++ inference binary |
| `cpp-dev` | Local development helper | ✅ | Build / debug environment (kept under monitoring as a hygiene baseline) |
| `python-train` | **Local development only** (4-GPU training stack) | ❌ | Not deployed to clusters; executed on individual researcher machines. CVE alerts on the ML/training apt layer (CUDA + cuDNN + ML toolchain) do not represent an exposed network attack surface for piper-plus |

If you identify a vulnerability in a development-only image that nonetheless
has a credible attack path (for example, a researcher loading a malicious
checkpoint in a shared training environment), please still report it via the
private channels above — the scope policy is about scanner monitoring, not
about whether we will fix exploitable defects.

## Security Best Practices for Users

Even within supported versions there are operational pitfalls users should be
aware of.

### Do not load untrusted `.ckpt` files

PyTorch checkpoints (`.ckpt`) are deserialized with `weights_only=False` in
several training and conversion code paths, which permits arbitrary code
execution on load. Only load checkpoints from sources you trust (your own
training runs, the official Hugging Face repos, etc.). Prefer ONNX (`.onnx`)
artifacts for inference: ONNX models do not execute arbitrary Python on load.

### Do not expose the HTTP server on `0.0.0.0` without authentication

The bundled FastAPI server (`src/python_run/piper/http_server.py`) and the
OpenAI-compatible TTS API (`docker/python-inference/inference.py`) are intended
for trusted local use. They do not ship with built-in authentication. If you
must expose them beyond `localhost`, place them behind a reverse proxy
(nginx / Caddy / Cloudflare Access / etc.) that enforces TLS and authentication
or an mTLS-terminating gateway.

### Verify SLSA provenance / build attestation on releases

Recent release workflows (5 GitHub Actions workflows) attach SLSA build
attestations to published artifacts. When consuming binaries, prefer
attestation-verified releases and verify the provenance with
`gh attestation verify` (or your supply-chain tooling of choice) before
deployment.

### Pin dependency versions

Each runtime ships a lockfile (`uv.lock`, `Cargo.lock`, `package-lock.json`,
NuGet `packages.lock.json`, etc.). Pin to the lockfile in production builds and
keep an eye on Dependabot alerts.

## Credit

We are happy to credit reporters in the GitHub Security Advisory and in
release notes once a fix has shipped. If you would prefer to remain anonymous,
let us know in the report.
