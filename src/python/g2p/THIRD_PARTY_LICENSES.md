# Third-Party Licenses — piper-plus-g2p (Python)

piper-plus-g2p is licensed under MIT. Below are the licenses of its
dependencies, grouped by optionality.

## Core (no external dependencies)

piper-plus-g2p core has zero required runtime dependencies. Languages ES, FR,
PT, SV, and KO are fully rule-based and need no external packages.

## Optional: Japanese (`pip install piper-plus-g2p[ja]`)

| Package | License | Purpose |
|---------|---------|---------|
| pyopenjtalk-plus | MIT | OpenJTalk bindings for Japanese G2P |
| numpy | BSD-3-Clause | Numerical arrays (pyopenjtalk dep) |

## Optional: English (`pip install piper-plus-g2p[en]`)

| Package | License | Purpose |
|---------|---------|---------|
| Bundled g2p-en 2.1.0 | Apache-2.0 | Neural G2P weights/code and homograph table; private `_vendor/g2p_en` namespace |
| Bundled Tacotron normalizer | MIT | Number expansion in `expand.py`; original Keith Ito grant in `TACOTRON-LICENSE.txt` |
| numpy | BSD-3-Clause | Neural network inference |
| nltk | Apache-2.0 | POS tagging and CMU dictionary access; downloaded data has its own notices |
| joblib | BSD-3-Clause | NLTK support |
| inflect | MIT | Number expansion |

The upstream `g2p-en` PyPI distribution declares unused GPL `Distance`.
This source bundles only the reviewed inference files, with original
Apache-2.0 and MIT notices, and does not install either distribution.
The original wheel hash, per-file hashes and the raw-regex-literal patch are
recorded in `_vendor/g2p_en/provenance.json` / `NOTICE.txt` and verified by
`scripts/check_bundled_english.py` in the repository. NLTK `cmudict` and tagger
data are downloaded separately; neither is in the bundled checkpoint.

## Optional: Chinese (`pip install piper-plus-g2p[zh]`)

| Package | License | Purpose |
|---------|---------|---------|
| pypinyin | MIT | Hanzi to Pinyin conversion |

## Optional: Korean (`pip install piper-plus-g2p[ko]`)

| Package | License | Purpose |
|---------|---------|---------|
| g2pk2 | Apache-2.0 | Korean G2P with neural disambiguation |

`g2pk2==0.0.3` declares jamo (Apache-2.0), NLTK and anyascii (ISC).
The optional Korean wrapper can use the repository's rule-based fallback
when the backend is unavailable.

## Development

| Package | License | Purpose |
|---------|---------|---------|
| pytest | MIT | Test framework |
| ruff | MIT | Linter/formatter |
| mypy | MIT | Type checker |

## Scope of the dependency check

The source wheel consumer CI checks installed runtime / English / all-language
dependency closures for declared GPL, LGPL and AGPL licenses and rejects any
installed `Distance` or external `g2p-en` distribution. It also fails on missing
dependencies or absent license metadata. It does not replace a review of each
archive or licenses attached to separately downloaded data.

Already published `piper-plus-g2p==0.3.0` wheels retain their original dependency
metadata, including `g2p-en → Distance` for the `en` / `all` extras. See the
[migration guide](../../../docs/migration/python-g2p-license.md) and the
[source/archive audit](../../../docs/design/python-g2p-license-2026-10-16.md).
