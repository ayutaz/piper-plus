# Future design: Canonical PUA codegen

**Status:** Design proposal — not yet implemented.

**Context:** As of PUA v2, `pua.json` is the canonical source but each of 6 runtime
tables (Python runtime, Rust, Go, JS, C#, partly C++) is **manually synchronized**.
The CI gate `scripts/check_pua_consistency.py` catches drift after the fact, but
new contributors must still manually update 6 places per new phoneme. This document
explores moving to a **codegen-based** model where the 6 tables are auto-generated.

## Why bother?

The v1.12.0 ɔɪ/œ̃/ɐ̃ regression had two layers of failure:
1. **pua.json** itself was missing the entries.
2. Even if pua.json had them, **6 separate manual edits** per language are needed.

Layer 2 means: every time someone forgets one of the 6 tables, the CI gate fires
and the PR has to be revised. The friction is real but bounded; the gate prevents
the bug from reaching users. So codegen is a polish, not a correctness requirement.

## Three codegen strategies

### Strategy A — Full codegen (tables are generated artifacts)

Each runtime ships a **generated** PUA table file (e.g. `token_map_generated.rs`).
A single `scripts/generate_pua_tables.py` reads `pua.json` and emits all 6 files.
A pre-commit hook + CI gate verifies the generated files are up to date.

**Pros:**
- Zero manual sync. Update `pua.json`, run codegen, commit. One step.
- Eliminates entire bug class.

**Cons:**
- Adds a build dependency on Python in Rust/Go/C# pipelines (or vendored generated code).
- Generated code must be checked in (otherwise consumers of the published Rust/Go
  crates / NuGet package would need codegen too).
- New contributors need to learn "don't edit X, edit pua.json and run codegen".
- Rust analyzer and other IDE tooling work fine on checked-in generated code, but
  some teams find generated code in the repo undesirable.

### Strategy B — Runtime JSON loading

Each runtime loads `pua.json` at startup and builds the table in memory.

**Pros:**
- True single source of truth at runtime.
- No checked-in generated code.

**Cons:**
- Adds a runtime file dependency (each runtime must ship `pua.json`).
- Performance: slight startup cost (~1ms parse) acceptable for all uses.
- For C++ shared library (`libpiper_plus`), ship pua.json as resource bundle —
  already a deployment hassle; or embed as `static const char[]` at compile time
  (which is just codegen-lite).
- Rust crate consumers can't easily bundle the JSON (would need build.rs).
- Doesn't help C# (no obvious resource-loading path that works on iOS/Android/desktop).

### Strategy C — Hybrid (current state + better tooling)

Keep manual tables but add:
- `scripts/check_pua_consistency.py` — already done ✅
- `scripts/sync_pua_tables.py --auto-fix` — reads pua.json and patches each
  runtime table to match (semi-automated synchronization).
- pre-commit hook that runs the consistency check before `git commit`.

**Pros:**
- Zero changes to runtime code or build pipelines.
- Backward compatible.
- The CI gate already prevents drift.
- `--auto-fix` script makes additions trivial without forcing codegen-based workflow.

**Cons:**
- Tables remain duplicated in source (just synced reliably).
- New phoneme additions still touch 6 files (but `--auto-fix` does the boilerplate).

## Recommendation

**Strategy C in the short term, Strategy A only if drift becomes a recurring pain.**

Justification:
- The CI gate (`pua-consistency.yml`) already prevents regressions reaching users.
- The cost of Strategy A is real (build pipeline complexity, generated artifacts in
  source control) and the benefit (no manual sync) is marginal given how rarely we
  add new multi-codepoint phonemes (3 entries added in 6 months).
- Strategy B is impractical for C# / iOS distribution.

If a future PR needs to add ≥5 new multi-codepoint phonemes at once, revisit
Strategy A. The migration would be:
1. Write `scripts/generate_pua_tables.py` that emits all 6 files.
2. Add a CI job that runs the generator and fails if `git diff` is non-empty.
3. Convert each `*_pua_*` source file to `// AUTO-GENERATED — do not edit`.
4. Add `pre-commit` hook running the generator.

## Open questions for Strategy A (when revisited)

1. **Where does the generator run for crate/npm/NuGet publishes?** If Rust crates
   ship the generated `token_map_generated.rs`, that file is in source control,
   so consumers don't need codegen. But the file becomes "double-source-of-truth"
   — the `.rs` and the `.json` could drift if codegen is skipped.

2. **What about pre-existing PUA assignments in shipped models?** Codepoints are
   baked into trained models (PUA_COMPAT_VERSION). The generator must enforce
   that assignments are *append-only* — never reorder or repurpose codepoints.

3. **C++ codegen target.** `phoneme_parser.cpp` only has the JA subset today.
   Should codegen produce the full multilingual table for C++ runtime, or stick
   with JA-only since the C++ phoneme_id_map loader uses PUA strings directly?

These can be answered when (and if) the Strategy A migration starts.
