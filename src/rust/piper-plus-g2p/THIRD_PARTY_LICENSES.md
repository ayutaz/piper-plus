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

| Asset | License | Source | Purpose |
|-------|---------|--------|---------|
| NAIST-JDIC | BSD-3-Clause | [NAIST-JDIC project (osdn.net)](https://osdn.net/projects/naist-jdic/) | MeCab dictionary for Japanese morphological analysis |

> **Distribution note:** Bundled inside the `jpreprocess` crate at
> compile time when `naist-jdic` is enabled. Adds approximately 20 MB
> to the binary. The license requires the BSD copyright notice and
> the disclaimer to be retained in redistributed binary form — see
> the BSD-3-Clause license text below.

#### NAIST-JDIC License (BSD-3-Clause)

> Copyright (c) 2009, Nara Institute of Science and Technology, Japan.
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions
> are met:
>
> 1. Redistributions of source code must retain the above copyright
>    notice, this list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright
>    notice, this list of conditions and the following disclaimer in
>    the documentation and/or other materials provided with the
>    distribution.
> 3. Neither the name of the Nara Institute of Science and Technology
>    (NAIST) nor the names of its contributors may be used to endorse
>    or promote products derived from this software without specific
>    prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
> "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
> LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
> FOR A PARTICULAR PURPOSE ARE DISCLAIMED.

> **Note:** The `naist-jdic` feature bundles the dictionary (~20 MB)
> into the binary. For size-constrained targets (WASM, App Clip), prefer
> runtime dictionary loading. For iOS (App Sandbox), use the bundled
> form — runtime dictionary loading from external paths is impractical.

## Bundled Data Files (`--features bundled-dicts`)

The `bundled-dicts` feature embeds the following data files into the
binary via `include_str!` / `include_bytes!`. This is required for iOS
(App Sandbox) and other environments that cannot load external files.

| Asset | License | Source | Purpose |
|-------|---------|--------|---------|
| `data/cmudict_data.json` | BSD-style (CMU) | [CMU Pronouncing Dictionary v0.7b](http://www.speech.cs.cmu.edu/cgi-bin/cmudict) | English word → ARPABET phoneme lookup |
| `data/pinyin_single.json` | MIT | [pypinyin](https://github.com/mozillazg/python-pinyin) (derived from Unicode CLDR + Han database) | Chinese single-char → pinyin |
| `data/pinyin_phrases.json` | MIT | [pypinyin](https://github.com/mozillazg/python-pinyin) | Chinese phrase → pinyin |

### CMU Pronouncing Dictionary License

> The Carnegie Mellon University Pronouncing Dictionary [cmudict.0.7b]
> [...]
> Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions
> are met:
>
> 1. Redistributions of source code must retain the above copyright
>    notice, this list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright
>    notice, this list of conditions and the following disclaimer in
>    the documentation and/or other materials provided with the
>    distribution.
> 3. The name "Carnegie Mellon University" must not be used to endorse
>    or promote products derived from this software without prior
>    written permission. For permission, please contact
>    sphinx@cs.cmu.edu.
> 4. Products derived from this software may not be called "Carnegie
>    Mellon Pronouncing Dictionary" nor may "Carnegie Mellon" appear
>    in their names without prior written permission of Carnegie
>    Mellon University.
> 5. Redistributions of any form whatsoever must retain the following
>    acknowledgment: "This product includes data from the Carnegie
>    Mellon Pronouncing Dictionary, which is freely available at
>    http://www.speech.cs.cmu.edu/cgi-bin/cmudict."
>
> THIS SOFTWARE IS PROVIDED BY CARNEGIE MELLON UNIVERSITY "AS IS" AND
> ANY EXPRESSED OR IMPLIED WARRANTIES ARE DISCLAIMED.

### pypinyin License (MIT)

> Copyright (c) 2016 mozillazg, 闲耘 ([hotoo.cn@gmail.com](mailto:hotoo.cn@gmail.com))
>
> Permission is hereby granted, free of charge, to any person obtaining
> a copy of this software and associated documentation files (the
> "Software"), to deal in the Software without restriction, including
> without limitation the rights to use, copy, modify, merge, publish,
> distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to
> the following conditions:
>
> The above copyright notice and this permission notice shall be
> included in all copies or substantial portions of the Software.

> **Note:** `bundled-dicts` adds approximately 6.3 MB to the binary
> (cmudict 3.7 MB + pinyin_single 705 KB + pinyin_phrases 1.9 MB).
> For Rust-only consumers that can ship JSON files alongside the
> binary, prefer `EnglishPhonemizer::new_with_dict(&path)` /
> `ChinesePhonemizer::new(single_path, phrases_path)` over the
> `new_bundled()` constructors so the binary itself stays small.

## No copyleft licenses

All dependencies and bundled data are MIT, Apache-2.0, BSD-3-Clause,
or BSD-style permissive licenses. No GPL, LGPL, or AGPL licenses are
present in the dependency tree.
