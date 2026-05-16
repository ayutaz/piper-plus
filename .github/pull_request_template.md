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
