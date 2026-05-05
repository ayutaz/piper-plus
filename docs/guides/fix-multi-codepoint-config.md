# Fix multi-codepoint phoneme regression in distributed configs

**Background:** v1.12.0 distributed `tsukuyomi` config.json had three multi-codepoint
phoneme keys (`ɔɪ`, `œ̃`, `ɐ̃`) that the C++ runtime rejects with
`is not a single codepoint (ids=…)`. The Python runtime tolerated this silently,
so the bug only surfaced for Windows users running the C++ CLI.

This guide describes how to:
1. Verify whether a config.json is affected.
2. Regenerate it with PUA v2 mappings.
3. Push the fixed config to HuggingFace.

## Quick check

```bash
# Validate any local config.json
python -m piper_train.update_model_config path/to/config.json --validate-only
```

Outputs `OK:` or `FAIL:` per file. Non-zero exit on FAIL.

## Regenerate distributed configs

```bash
# Download current config from HF, regenerate, save to tmp/
python scripts/regenerate_tsukuyomi_config.py --repo ayousanz/piper-plus-tsukuyomi-chan

# Or use a local config.json
python scripts/regenerate_tsukuyomi_config.py --source path/to/config.json
```

The script:
- Downloads the original config.json (or loads a local one).
- Runs `update_phoneme_id_map(strict=True)` to PUA-encode all keys.
- Saves both the original (`tmp/config.original.json`) and the fixed
  (`tmp/config.json`) for diff inspection.
- Fails fast if the config contains multi-codepoint keys with no PUA mapping
  (which means `pua.json` itself is incomplete — fix that first).

## Push to HuggingFace

```bash
huggingface-cli login
huggingface-cli upload ayousanz/piper-plus-tsukuyomi-chan tmp/config.json config.json
```

After push, end-users running:
```
piper.exe --download-model tsukuyomi
piper.exe --model tsukuyomi --text "..." --output_file out.wav
```
will receive the corrected config and synthesize successfully on Windows.

## Other affected models

Run the validator across all known piper-plus models:

```bash
for repo in \
    ayousanz/piper-plus-tsukuyomi-chan \
    ayousanz/piper-plus-css10-ja-6lang \
    ayousanz/piper-plus-base; do
  python scripts/regenerate_tsukuyomi_config.py --repo "$repo" --out "tmp/$repo"
done
```

Inspect each `tmp/<repo>/config.json` and push the ones that changed.

## Why this happened

See [`docs/spec/pua-contract.toml`](../spec/pua-contract.toml) and
[`docs/spec/pua-test-matrix.md`](../spec/pua-test-matrix.md) for the full root-cause
analysis. In short:
- `pua.json` had registration gaps for `ɔɪ`, `œ̃`, `ɐ̃`.
- The encode helper `map_token()` fell back to `warnings.warn()` instead of failing.
- The release pipeline never validated that distributed configs had only
  single-codepoint keys.

The fix in this PR ([details](../spec/pua-test-matrix.md)):
- Added the 3 missing entries to `pua.json` and synced all 6 runtime tables.
- Made `update_phoneme_id_map(strict=True)` (default) raise on unmapped keys.
- Added `scripts/check_pua_consistency.py` as a CI gate to prevent drift.
- Added `pua-consistency.yml` workflow exercising L1–L5 of the test matrix.
