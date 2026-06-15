## Summary

<!-- What does this PR do? Keep it brief (1-3 sentences). -->

## Affected Components

<!-- Check all that apply -->

- [ ] Python (src/python/, pyproject.toml)
- [ ] Rust (src/rust/)
- [ ] C# (src/csharp/)
- [ ] C++ (src/cpp/, CMakeLists.txt)
- [ ] Go (src/go/)
- [ ] WASM/npm (src/wasm/)
- [ ] Docker (docker/)
- [ ] CI/CD (.github/workflows/)
- [ ] Documentation (docs/, README*)

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactoring
- [ ] Documentation
- [ ] CI/CD
- [ ] Dependencies

## Risk Level

<!-- pick exactly one — affects review intensity and release scheduling -->

- [ ] **patch** — bug fix / internal refactor / docs only
- [ ] **minor** — new feature / additive API / no breaking change
- [ ] **major** — breaking change (API removal, schema migration, behavior reversal)

## Decoder Regression Guard (AI-15)

<!--
AI-15 regression-guard reviewer checklist for A-1 / A-2 / FLY-TTS
decoder variants. Tick each box once you have confirmed the invariant
locally. Enforced by scripts/check_pr222_pr537_isolation_checklist.py.

NOTE: Lives in its own section so the `validate-pr-body` gate that counts
`- [x]` inside Risk Level is not contaminated by this checklist.
-->

- [ ] default decoder_type 不変 (no change to the default config field)
- [ ] [mb_istft_1d] audio parity 不変 (baseline lock untouched or
      `audio-parity-baseline-bump:` trailer present)
- [ ] ONNX I/O 不変 (input_names / output_names / dynamic_axes match
      `scripts/onnx_io_spec.lock.json`; PR #222 deferred to AI-17)
- [ ] PR #537 TF32/bf16-mixed impact deferred to AI-16 (no mixed-precision
      re-baseline in this PR)
- [ ] freeze-dp 互換 (`--resume-from-multispeaker-checkpoint` still
      auto-enables `--freeze-dp` in `piper_train/__main__.py`)

## Contract Impact

<!--
For changes that touch cross-runtime behavior, mark the relevant
docs/spec/*.toml. Helps reviewers focus on parity drift.
-->

- [ ] None (Python/runtime-internal change only)
- [ ] `docs/spec/ort-session-contract.toml` (ORT init / providers)
- [ ] `docs/spec/short-text-contract.toml` (Strategy A/B/C)
- [ ] `docs/spec/text-splitter-contract.toml` (sentence boundary)
- [ ] `docs/spec/phoneme-timing-contract.toml` (timing output)
- [ ] `docs/spec/pua-contract.toml` (PUA codepoint mapping)
- [ ] `docs/spec/japanese-n-variant-contract.toml`
- [ ] `docs/spec/chinese-tone-contract.toml`
- [ ] `docs/spec/pt-dialect-contract.toml` (BR/EU)
- [ ] `docs/spec/loanword-mirrors.toml` (ZH-EN dispatch)
- [ ] `docs/spec/inference-input-contract.toml`
- [ ] Other: `docs/spec/<...>.toml`

## Test Plan

<!-- How was this tested? What commands did you run? -->

## Checklist

- [ ] Tests pass locally
- [ ] No GPL/LGPL dependencies added ([License Policy](CONTRIBUTING.md#license-policy))
- [ ] Documentation updated (if applicable)

## Related Issues

<!-- Closes #123, Fixes #456 -->
