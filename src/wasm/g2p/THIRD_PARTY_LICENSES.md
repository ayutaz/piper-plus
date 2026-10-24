# Third-Party Licenses — @piper-plus/g2p (JavaScript)

@piper-plus/g2p is licensed under MIT.

## Runtime Dependencies

**None.** All rule-based G2P engines (EN, ZH, ES, FR, PT, SV) are
implemented in pure JavaScript with zero npm dependencies.

## Bundled Assets

| Asset | License | Purpose | Size |
|-------|---------|---------|------|
| openjtalk.wasm | MIT (OpenJTalk) | Japanese morphological analysis + G2P | ~10 MB |
| openjtalk.js | MIT | WASM loader/glue code | ~50 KB |
| data/cmudict_data.json | BSD-style (CMU) | English word → ARPAbet lookup ([CMU Pronouncing Dictionary v0.7b](http://www.speech.cs.cmu.edu/cgi-bin/cmudict)) | ~3.7 MB |

The OpenJTalk WASM binary is compiled from
[OpenJTalk](http://open-jtalk.sourceforge.net/) source code with
Emscripten. The NAIST-JDIC dictionary data bundled within is licensed
under BSD-3-Clause.

`data/cmudict_data.json` is a byte copy of
`src/rust/piper-plus-g2p/data/cmudict_data.json` (CMU Pronouncing Dictionary
0.7b in JSON form), the dictionary the Rust, C++, Go and Swift runtimes use.

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
>    <sphinx@cs.cmu.edu>.
> 4. Products derived from this software may not be called "Carnegie
>    Mellon Pronouncing Dictionary" nor may "Carnegie Mellon" appear
>    in their names without prior written permission of Carnegie
>    Mellon University.
> 5. Redistributions of any form whatsoever must retain the following
>    acknowledgment: "This product includes data from the Carnegie
>    Mellon Pronouncing Dictionary, which is freely available at
>    <http://www.speech.cs.cmu.edu/cgi-bin/cmudict>."
>
> THIS SOFTWARE IS PROVIDED BY CARNEGIE MELLON UNIVERSITY "AS IS" AND
> ANY EXPRESSED OR IMPLIED WARRANTIES ARE DISCLAIMED.

## Zero npm dependencies = Zero supply chain risk

@piper-plus/g2p has no runtime npm dependencies, eliminating the most
common vector for supply chain attacks in the JavaScript ecosystem.
