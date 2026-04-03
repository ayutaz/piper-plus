# Third-Party Licenses — piper-g2p (Rust)

piper-g2p is licensed under MIT. Below are the licenses of its
direct dependencies.

## Required Dependencies

| Crate | License | Purpose |
|-------|---------|---------|
| thiserror | MIT OR Apache-2.0 | Error derive macros |
| serde | MIT OR Apache-2.0 | Serialization framework |
| serde_json | MIT OR Apache-2.0 | JSON parsing |
| regex | MIT OR Apache-2.0 | Regular expressions |
| tracing | MIT | Logging/diagnostics |

## Optional: Japanese (`--features japanese`)

| Crate | License | Purpose |
|-------|---------|---------|
| jpreprocess | MIT | OpenJTalk-compatible Japanese NLP |

### NAIST-JDIC Dictionary (`--features naist-jdic`)

| Asset | License | Purpose |
|-------|---------|---------|
| NAIST-JDIC | BSD-3-Clause | MeCab dictionary for Japanese morphological analysis |

> **Note:** The `naist-jdic` feature bundles the dictionary (~20 MB)
> into the binary. For size-constrained targets (mobile, WASM), prefer
> runtime dictionary loading.

## No copyleft licenses

All dependencies are MIT, Apache-2.0, or BSD-3-Clause.
No GPL, LGPL, or AGPL licenses are present in the dependency tree.
