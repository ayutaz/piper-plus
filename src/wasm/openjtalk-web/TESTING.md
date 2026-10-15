# Testing the browser runtime

This directory contains the npm package, the multilingual demo, unit tests,
and the Playwright browser probe. The current browser path uses the Rust WASM
phonemizer and `onnxruntime-web`; the old Emscripten/OpenJTalk pages are not
part of the active test path.

## Install

Use Node.js 24 or newer, matching `package.json`:

```bash
cd src/wasm/openjtalk-web
npm ci --ignore-scripts --no-audit --no-fund
```

## Automated checks

The package scripts are the source of truth for test coverage:

```bash
npm test                         # focused package and npm-distribution tests
npm run test:npm-package:all     # complete JS package suite
npm run check:types              # generated type constants are current
npm run test:browser-runtime     # README/demo ORT URL matches package.json
npm run test:importmap           # demo import maps resolve
npm run test:wasm-g2p            # Rust WASM adapter tests
```

The real browser probe downloads the pinned CSS10 and Tsukuyomi fixtures,
starts the local test server, and checks synthesis, decoded WAV data, and
playback:

```bash
npm run test:browser
```

This command requires Playwright Chromium. The fixtures are downloaded by
`test/browser/prepare-models.mjs` and verified against the SHA-256 values in
`test/browser/models.json`. The live deployment probe uses the same test with
`PIPER_PLUS_DEMO_URL` set by the deployment workflow.

## Manual demo

The supplied server adds the CORS and cross-origin-isolation headers needed by
the browser runtime. Run it from this directory:

```bash
python3 test-server.py
```

Open the files that actually live under the test demo directory:

- <http://localhost:8080/test/multilingual-demo/index.html>
- <http://localhost:8080/test/multilingual-demo/simple-multilingual.html>
- <http://localhost:8080/test/multilingual-demo/multilingual.html>

The demo model is selected by the page (`css10`) and is fetched from the
Hugging Face registry. A successful page load is a UI smoke check; use the
Playwright probe for the pinned model, inference, and playback assertions.

## What the browser probe checks

- The CSS10 demo synthesizes Japanese, English, Chinese, Spanish, French, and
  Portuguese text and decodes non-zero WAV output.
- The README import-map and basic-usage pages initialize Tsukuyomi and start
  real audio playback.
- Browser errors are collected and fail the test.
- ORT URLs are pinned to the exact `onnxruntime-web` version in
  `package.json` (currently `1.30.0`).

Keep historical migration and changelog examples unchanged; this file
documents only the current commands and active test paths.
