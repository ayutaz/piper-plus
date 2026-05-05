# PUA Regression Test Matrix

**Purpose:** Comprehensive test coverage to prevent the multi-codepoint regression class
that broke C++ inference for Windows users in v1.12.0 (issue: `ɔɪ`/`œ̃`/`ɐ̃` left as
multi-codepoint keys in the distributed `tsukuyomi` config).

**Contract source:** [`docs/spec/pua-contract.toml`](pua-contract.toml)

**CI workflows:**
- [`.github/workflows/pua-consistency.yml`](../../.github/workflows/pua-consistency.yml)
  — runs on every PR touching PUA-related files
- [`.github/workflows/g2p-cross-platform-ci.yml`](../../.github/workflows/g2p-cross-platform-ci.yml)
  — runs on every G2P PR, includes the consistency check

---

## Test layers

### L1 — Static cross-runtime consistency

The 6 runtime PUA tables (Python runtime, Python G2P, Rust, Go, JS, C#) must all
match the canonical `pua.json` byte-for-byte.

| ID | Test | Where | Status |
|----|------|-------|--------|
| L1.1 | pua.json ↔ Python `token_mapper.FIXED_PUA_MAPPING` entry-by-entry | `scripts/check_pua_consistency.py` | ✅ |
| L1.2 | pua.json ↔ Python G2P `pua.py` (loads pua.json dynamically) | `scripts/check_pua_consistency.py` | ✅ |
| L1.3 | pua.json ↔ Rust `FIXED_PUA_MAP` entry-by-entry | `scripts/check_pua_consistency.py` | ✅ |
| L1.4 | pua.json ↔ Go `fixedPUA` entry-by-entry | `scripts/check_pua_consistency.py` | ✅ |
| L1.5 | pua.json ↔ JS `PUA_MAP` entry-by-entry | `scripts/check_pua_consistency.py` | ✅ |
| L1.6 | pua.json ↔ C# `TokenToChar` entry-by-entry | `scripts/check_pua_consistency.py` | ✅ |
| L1.7 | All `PUA_COMPAT_VERSION` constants match pua.json `version` | `scripts/check_pua_consistency.py --check-version` | ✅ |
| L1.8 | C++ `phoneme_parser.cpp:japanesePhonemePUA` covers JA range subset | future (M5+) | ⚠ deferred |

### L2 — pua.json schema invariants

| ID | Test | Where | Status |
|----|------|-------|--------|
| L2.1 | No duplicate `token` values | `tests/test_pua_invariants.py::TestPuaJsonSchema::test_no_duplicate_tokens` | ✅ |
| L2.2 | No duplicate `codepoint` values | `tests/test_pua_invariants.py::TestPuaJsonSchema::test_no_duplicate_codepoints` | ✅ |
| L2.3 | All codepoints in BMP PUA range (U+E000–U+F8FF) | `tests/test_pua_invariants.py::TestPuaJsonSchema::test_codepoints_in_pua_range` | ✅ |
| L2.4 | No single-codepoint tokens (no PUA mapping needed) | `tests/test_pua_invariants.py::TestPuaJsonSchema::test_all_tokens_are_multi_codepoint_or_special` | ✅ |
| L2.5 | `version` field equals `PUA_COMPAT_VERSION` constant | `tests/test_pua_invariants.py::TestPuaJsonSchema::test_version_matches_pua_compat_version` | ✅ |

### L3 — Inventory coverage

Every multi-codepoint token that appears in any inventory list (`id_maps.py`)
must have a PUA entry. **This is the test that would have caught the v1.12.0 regression.**

| ID | Test | Where | Status |
|----|------|-------|--------|
| L3.1 | `_SPECIAL_TOKENS` multi-codepoint tokens are mapped | `test_pua_invariants.py::TestInventoryCoverage` (param) | ✅ |
| L3.2 | `_JAPANESE_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.3 | `_ENGLISH_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.4 | `_CHINESE_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.5 | `_SPANISH_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.6 | `_FRENCH_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.7 | `_PORTUGUESE_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.8 | `_KOREAN_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |
| L3.9 | `_SWEDISH_PHONEMES` multi-codepoint tokens are mapped | same (param) | ✅ |

### L4 — Fail-fast guards (defence-in-depth)

Even if L1–L3 are bypassed (e.g. someone manually edits a generated config),
these guards refuse to ship a config with multi-codepoint keys.

| ID | Test | Where | Status |
|----|------|-------|--------|
| L4.1 | `map_token(unknown_multi)` raises `UnmappedMultiCodepointTokenError` in strict mode | `test_pua_invariants.py::TestMapTokenFailFast::test_unmapped_multi_codepoint_raises_in_strict_mode` | ✅ |
| L4.2 | `map_token(unknown_multi, strict=False)` warns (legacy) | `test_pua_invariants.py::TestMapTokenFailFast::test_unmapped_multi_codepoint_warns_in_non_strict_mode` | ✅ |
| L4.3 | `_build_japanese_id_map()` asserts all keys are single-codepoint | `test_pua_invariants.py::TestGeneratedMapInvariants::test_all_keys_are_single_codepoint[ja]` | ✅ |
| L4.4 | `_build_multilingual_id_map()` asserts all keys are single-codepoint | `test_pua_invariants.py::TestGeneratedMapInvariants::test_all_keys_are_single_codepoint[multilingual]` | ✅ |
| L4.5 | `update_phoneme_id_map(strict=True)` raises `UnmappedMultiCodepointKeyError` | `test_update_model_config.py::TestUpdatePhonemeIdMap::test_unmapped_multi_codepoint_raises_in_strict_mode` | ✅ |
| L4.6 | `update_phoneme_id_map(strict=False)` warns to stdout | `test_update_model_config.py::TestUpdatePhonemeIdMap::test_unmapped_multi_codepoint_warns_in_non_strict` | ✅ |
| L4.7 | `--validate-only` exits 1 on bad config | `test_update_model_config.py::TestValidateOnlyEntryPoint::test_bad_config_exits_nonzero` | ✅ |
| L4.8 | `--validate-only` exits 0 on clean config | `test_update_model_config.py::TestValidateOnlyEntryPoint::test_clean_config_exits_zero` | ✅ |

### L5 — Generated artifact validation

| ID | Test | Where | Status |
|----|------|-------|--------|
| L5.1 | `get_phoneme_id_map(language)` returns single-codepoint keys for all languages | `test_pua_invariants.py::TestGeneratedMapInvariants` (param) | ✅ |
| L5.2 | PUA v2 additions (ɔɪ, œ̃, ɐ̃) are in multilingual map as PUA chars | `test_pua_invariants.py::TestGeneratedMapInvariants::test_multilingual_contains_pua_v2_additions` | ✅ |
| L5.3 | Pre-flight: any test/fixture `config.json` has only single-codepoint keys | CI workflow `pua-consistency.yml::config-key-validator` | ✅ |

### L6 — End-to-end runtime smoke tests (deferred)

| ID | Test | Where | Status |
|----|------|-------|--------|
| L6.1 | C++ binary loads `tsukuyomi` config without errors | Manual / nightly | ⚠ deferred |
| L6.2 | All 7 runtimes produce identical phoneme IDs for the same input text | `g2p-cross-platform-ci.yml` (existing) | ✅ partial |
| L6.3 | All 7 runtimes synthesize a short sample WAV (golden test) | future | ⚠ deferred |

### L7 — Release pipeline gates

| ID | Test | Where | Status |
|----|------|-------|--------|
| L7.1 | HuggingFace push pre-flight: `update_model_config --validate-only` on every config | release workflow (recommended) | ⚠ deferred |
| L7.2 | Release tag triggers full L1+L2+L3+L4+L5 suite | `pua-consistency.yml` runs on push to dev/main | ✅ |

---

## How to add a new multi-codepoint phoneme

If you need to add a new phoneme with multiple Unicode codepoints (e.g. a new
language's nasal vowel), follow this checklist to keep all gates green:

1. **Update `pua.json`** with the new entry (next free codepoint, e.g. U+E065).
2. **Bump `version`** in pua.json (and `PUA_COMPAT_VERSION` constants in
   `pua.py`, `token_map.rs`, `pua-map.js`).
3. **Sync all 6 runtime tables** with the same `(token, codepoint)`:
   - `src/python_run/piper/phonemize/token_mapper.py`
   - `src/rust/piper-plus-g2p/src/token_map.rs`
   - `src/go/phonemize/pua.go`
   - `src/wasm/g2p/src/pua-map.js`
   - `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs`
   - (`src/python/g2p/piper_plus_g2p/encode/pua.py` reads pua.json — no change needed)
4. **Add to inventory** in `src/python/g2p/piper_plus_g2p/encode/id_maps.py`
   if the new phoneme is part of a language inventory.
5. **Update test counts:**
   - `src/wasm/g2p/test/test-pua-map.js` (search for `96`)
   - `src/go/phonemize/pua_test.go` (`allFixedPUA` table + `want` constants)
   - `src/rust/piper-plus-g2p/src/token_map.rs::test_fixed_pua_count`
6. **Run the gate locally:**
   ```bash
   python scripts/check_pua_consistency.py --verbose --check-version
   uv run pytest src/python/g2p/tests/test_pua_invariants.py -v
   ```
7. **CI must be green** on `pua-consistency.yml` before merging.

If any of these steps is skipped, the CI gate refuses the PR.
