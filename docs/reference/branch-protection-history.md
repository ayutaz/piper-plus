# Branch protection history

Single source of truth for changes to `dev` (and later `main`) branch
protection rules on `ayutaz/piper-plus`. Each entry records the change
intent, the `gh api` snapshot before / after, and the verification command
a reviewer can use to confirm the change landed.

The motivating context is M1.1 (cancelled / skipped baseline alarm). GitHub
branch protection treats `cancelled` and `skipped` workflow runs as a pass
(fail-open), and PR #419 showed that this lets a baseline collapse merge
silently. The hub-and-spoke gateway (`required_status_check_gate.yml`) closes
the gap by translating `cancelled` / `skipped` into an explicit `failure`
check, but it must also be wired into branch protection — that's the change
this document tracks.

## Why this file exists, not a `gh api` script

Branch protection edits are one of the few changes that can lock the
repository out of legitimate work. We deliberately do **not** automate
`PATCH /repos/.../branches/dev/protection` in CI; instead, every change is
performed by a maintainer, captured here as a before/after JSON snapshot,
and reviewed in a PR. Future M1 / M2 / M3 tickets that add a required
check append to this file rather than starting a new doc.

## Snapshot conventions

- Use `gh api repos/ayutaz/piper-plus/branches/dev/protection > /tmp/before.json`
  for the **before** snapshot. Redact noisy fields (`url`, timestamps) so the
  diff stays meaningful.
- Capture `gh api ... > /tmp/after.json` immediately after applying the PATCH.
- Commit only the **diff-relevant fields** (`required_status_checks.contexts`,
  `required_pull_request_reviews`, `enforce_admins`, `restrictions`). Full
  payloads contain user-id arrays that change too often to be useful.
- Always state who applied the change, when, and with which gh CLI invocation.

## Changes

### 2026-05-XX — Add `Required Status Check Gate` to `dev` required checks (M1.1)

Status: pending (awaiting M1.1 ticket merge + 1 week green run on dev)

**Why**: PR #419 caused a baseline collapse because three required checks
finished `cancelled` and GitHub treated that as a pass. The new
`required_status_check_gate.yml` workflow converts `cancelled` / `skipped` /
`failure` of monitored spokes into an explicit failure; making the gate a
required check is what actually blocks merges.

**Before** (`required_status_checks.contexts`, abridged):

```json
{
  "strict": false,
  "contexts": [
    "Multi-Runtime RTF Benchmark / rtf",
    "Memory regression (per-language) / regression",
    "CodeQL / analyze (python)",
    "CodeQL / analyze (cpp)",
    "Parity Hub / parity",
    "PUA Consistency Gate / check"
  ]
}
```

**After** (additive — no existing entries removed):

```json
{
  "strict": false,
  "contexts": [
    "Multi-Runtime RTF Benchmark / rtf",
    "Memory regression (per-language) / regression",
    "CodeQL / analyze (python)",
    "CodeQL / analyze (cpp)",
    "Parity Hub / parity",
    "PUA Consistency Gate / check",
    "Required Status Check Gate / gate"
  ]
}
```

**Apply command** (run by maintainer after 1 week green on dev):

```bash
gh api repos/ayutaz/piper-plus/branches/dev/protection > /tmp/before.json
jq '.required_status_checks.contexts += ["Required Status Check Gate / gate"]
    | {required_status_checks, required_pull_request_reviews, enforce_admins, restrictions}' \
  /tmp/before.json > /tmp/patch.json
gh api -X PATCH repos/ayutaz/piper-plus/branches/dev/protection \
  --input /tmp/patch.json
gh api repos/ayutaz/piper-plus/branches/dev/protection > /tmp/after.json
```

**Verify**:

```bash
gh api repos/ayutaz/piper-plus/branches/dev/protection \
  | jq -r '.required_status_checks.contexts[]' \
  | grep "Required Status Check Gate"
```

**Rollback** (if the gate produces sustained false-positive failures):

```bash
gh api repos/ayutaz/piper-plus/branches/dev/protection > /tmp/now.json
jq '.required_status_checks.contexts |= map(select(. != "Required Status Check Gate / gate"))
    | {required_status_checks, required_pull_request_reviews, enforce_admins, restrictions}' \
  /tmp/now.json > /tmp/revert.json
gh api -X PATCH repos/ayutaz/piper-plus/branches/dev/protection \
  --input /tmp/revert.json
```

**Operator**: pending — to be filled in when the change is applied.

---

Future entries (M1.3 first-PR fast lane, M2 audio-tier blockers, M3 ABI
gate, …) append below this section without renaming earlier headings.
