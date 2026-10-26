# Security Policy

Piper-Plus takes the security of its code, models, and downstream integrations
seriously. This document describes which versions receive security fixes, how
to report a vulnerability, and what users can do to harden their own
deployments.

## Supported Versions

| Version | Status | Notes |
|---------|--------|-------|
| 2.0.x | Supported (current Python/native release line) | Use the latest patch release. |
| 1.x | Unsupported | Upgrade to the current release line. |

If you are pinned to an unsupported release, please consult
the [migration index](docs/migration/README.md), including
[v1.12 → v2.0](docs/migration/v1.12-to-v2.0.md), for upgrade guidance.
Rust, npm, NuGet and Kotlin packages have independent version numbers;
their current source versions are listed in
[`docs/spec/release-versions.toml`](docs/spec/release-versions.toml).

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
- Official Docker images shipped from this repository to
  `ghcr.io/ayutaz/piper-plus/*` (`docker/python-inference/`,
  `docker/python-train/`, `docker/webui/`, `docker/cpp-inference/`,
  `docker/cpp-dev/`, `docker/wyoming/`).
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
| `python-inference-cpu-distroless` | Build-only trial (not published) | ✅ | Distroless variant of the multi-arch CPU inference image (the published CPU image is `python-inference` with a `-cpu` tag suffix) |
| `webui` / `webui-distroless` | Production (`-distroless` is a build-only trial, not published) | ✅ | Gradio demo / WebUI |
| `wyoming` | Production | ✅ | Home Assistant Wyoming Protocol TTS |
| `cpp-inference` / `cpp-inference-distroless` | Production (`-distroless` is a build-only trial, not published) | ✅ | Native C++ inference binary |
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

The package HTTP server (`src/python_run/piper_plus/http_server.py`) has no
built-in authentication. The Docker OpenAI-compatible TTS API
(`docker/python-inference/inference.py`) supports Bearer authentication when
`PIPER_PLUS_API_KEYS` is set to a comma-separated list of accepted keys;
authentication is disabled when the variable is unset. The check covers
`/synthesize`, `/v1/audio/speech`, `/v1/models` and
`/v1/audio/speech/languages`. `/health` and `/api/phoneme-timing` do not use
that authentication dependency, so a deployment requiring authentication
for every route must enforce it at the proxy/gateway. See the
[integration guide](docs/guides/integration/open-webui-integration.md).

Bind local services to loopback when possible. For deployment beyond the
trusted host, configure authentication and a TLS-terminating proxy/gateway;
enabling Docker API keys does not add TLS or protect a different server.

### Verify SLSA provenance / build attestation on releases

Release workflows attach build attestations to supported published artifacts.
When consuming binaries, check the release's attestation availability, prefer
attestation-verified releases and verify the provenance with
`gh attestation verify` (or your supply-chain tooling of choice) before
deployment.

### Pin dependency versions

Use the tracked lockfiles provided for each build (`uv.lock`, `Cargo.lock`,
`package-lock.json`, NuGet `packages.lock.json`, etc.) and the runtime's
documented locked restore/install mode. Not every standalone example has a
lockfile. Keep an eye on dependency alerts.

## Credit

We are happy to credit reporters in the GitHub Security Advisory and in
release notes once a fix has shipped. If you would prefer to remain anonymous,
let us know in the report.
