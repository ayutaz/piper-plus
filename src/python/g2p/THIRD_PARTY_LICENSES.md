# Third-Party Licenses — piper-g2p (Python)

piper-g2p is licensed under MIT. Below are the licenses of its
dependencies, grouped by optionality.

## Core (no external dependencies)

piper-g2p core has zero required runtime dependencies. Languages ES, FR,
PT, SV, and KO are fully rule-based and need no external packages.

## Optional: Japanese (`pip install piper-g2p[ja]`)

| Package | License | Purpose |
|---------|---------|---------|
| pyopenjtalk-plus | MIT | OpenJTalk bindings for Japanese G2P |
| numpy | BSD-3-Clause | Numerical arrays (pyopenjtalk dep) |

## Optional: English (`pip install piper-g2p[en]`)

| Package | License | Purpose |
|---------|---------|---------|
| g2p-en | Apache-2.0 | CMU Pronouncing Dictionary + neural G2P |
| numpy | BSD-3-Clause | Neural network inference |

## Optional: Chinese (`pip install piper-g2p[zh]`)

| Package | License | Purpose |
|---------|---------|---------|
| pypinyin | MIT | Hanzi to Pinyin conversion |

## Optional: Korean (`pip install piper-g2p[ko]`)

| Package | License | Purpose |
|---------|---------|---------|
| g2pk2 | Apache-2.0 | Korean G2P with neural disambiguation |

> **Note:** g2pk2 may pull in heavy transitive dependencies (torch or
> tensorflow). Consider whether Korean support is needed before installing.

## Development

| Package | License | Purpose |
|---------|---------|---------|
| pytest | MIT | Test framework |
| ruff | MIT | Linter/formatter |
| mypy | MIT | Type checker |

## No copyleft licenses

All runtime dependencies are MIT, Apache-2.0, or BSD-3-Clause.
No GPL, LGPL, or AGPL licenses are present.
