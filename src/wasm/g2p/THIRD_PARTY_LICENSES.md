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

The OpenJTalk WASM binary is compiled from
[OpenJTalk](http://open-jtalk.sourceforge.net/) source code with
Emscripten. The NAIST-JDIC dictionary data bundled within is licensed
under BSD-3-Clause.

## Zero npm dependencies = Zero supply chain risk

@piper-plus/g2p has no runtime npm dependencies, eliminating the most
common vector for supply chain attacks in the JavaScript ecosystem.
