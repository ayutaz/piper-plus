# GitHub Pages deployment

The active deployment is defined by
`.github/workflows/deploy-webassembly-demo.yml`. It publishes the current
multilingual test page and the Rust WASM package; keep this guide aligned with
that workflow rather than copying an older `demo/` layout.

## What is deployed

The workflow builds `src/rust/piper-wasm` with the `multilingual` feature and
copies the output to `deploy/dist/rust-wasm/`. It then copies:

- `src/wasm/openjtalk-web/test/multilingual-demo/index.html` to `deploy/index.html`;
- the remaining files in `test/multilingual-demo/` to
  `deploy/multilingual-demo/`;
- the package `src/wasm/openjtalk-web/src/` and the `@piper-plus/g2p` source/data
  needed by the import map;
- the checked-in `src/wasm/openjtalk-web/models/` directory, including the
  `multilingual-test-medium` ONNX/config fixture.

The page downloads registry models from Hugging Face when it selects a model
such as `css10`; the deployment also carries the test fixture required by the
workflow's asset checks. Browser model caching uses IndexedDB.

## Local build

From the repository root, install the package dependencies and build the same
multilingual WASM variant used by the workflow:

```bash
cd src/wasm/openjtalk-web
npm ci --ignore-scripts --no-audit --no-fund
npm run build:wasm:multilingual
```

The script writes `dist/rust-wasm/`. It requires `wasm-pack`; the CI workflow
installs it with `cargo install wasm-pack --locked`.

To inspect the local pages with the required response headers:

```bash
python3 test-server.py
```

Then open `http://localhost:8080/test/multilingual-demo/index.html`.

## Workflow triggers and gates

Deployment runs for pushes to `dev` that affect the WASM/runtime paths, or
through `workflow_dispatch`. It also republishes after a successful
Multi-Runtime RTF Benchmark workflow.

Before upload, the workflow checks the WASM files, model/config files, favicon
links, relative JSON imports, and import maps. After deployment it probes the
live assets and runs the browser synthesis/playback test with
`PIPER_PLUS_DEMO_URL` set to the Pages URL.

## Runtime URL and model rules

The active demo and npm README use the exact `onnxruntime-web` version pinned
in `package.json` (currently `1.30.0`). Run the URL check after changing either
the manifest or demo:

```bash
npm run test:browser-runtime
```

Use the registry shortcuts implemented by `src/model-manager.js`, such as
`css10` and `tsukuyomi`. For the experimental public `zs-v1` bundle, use the
pinned direct URL and matching `base.onnx.json` documented in
`README.npm.md`; do not substitute the repository's legacy root config.

GitHub Pages serves the static files over HTTPS. The workflow does not add
Cross-Origin-Isolation response headers, so ONNX Runtime Web uses its normal
WASM fallback rather than relying on WASM threads.
