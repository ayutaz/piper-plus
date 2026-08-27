# ja-dict-blob

Generates the bincode-serialised NAIST-JDIC blob that
`WasmPhonemizer.setJapaneseDictionary()` accepts.

## Why this exists

The `ja-external` and `multilingual-external` WASM variants keep the ~55 MB
Japanese dictionary *out* of the binary and expect it to be supplied at
runtime. That halves nothing for Japanese users — the bytes move rather than
shrink — but it means the five dictionary-free languages (`ko`, `es`, `fr`,
`pt`, `sv`) no longer pay for Japanese: `multilingual` ships a 57 MiB `.wasm`,
`ja-lite` ships 1.56 MiB.

Nothing in the repository could produce that blob, so those variants had no
working Japanese path at all. `create_phonemizer` starts them on
`PassthroughPhonemizer`, which emits character-level tokens **without raising
an error**, so the failure is silent.

## Usage

```sh
cd tools/ja-dict-blob
cargo run --release -- naist-jdic.bin
```

Writes `naist-jdic.bin` plus a `naist-jdic.json` sidecar recording the
`jpreprocess` version, byte count, and SHA-256.

Measured output (jpreprocess 0.9.1):

| | |
|---|---|
| raw | 58,026,142 B (55.3 MiB) |
| gzip -9 | 18,957,365 B (18.1 MiB) |
| sha256 | `bd0e46d9f93d7d9105a31994b98213c650cedc91d29c1206f1c5c8b3322c977f` |

## Version coupling

The blob is a raw bincode dump of `lindera_core::dictionary::Dictionary` with
**no magic bytes, no version field, and no length check** (see
`piper-plus-g2p/src/japanese.rs::new_from_serialized_dict`). jpreprocess
documents that a dictionary must be loaded by the same version that built it.

A blob built against a different `jpreprocess` or `lindera-core` version
therefore produces an opaque bincode error at best. Bumping either dependency
invalidates every published blob — regenerate and re-pin the SHA-256, and give
the artifact a version-qualified name so caches cannot serve a stale one.

## Reproducibility

Serialisation is deterministic: the object graph reachable from `Dictionary`
(`PrefixDict`, `ConnectionCostMatrix`, `CharacterDefinitions`,
`UnknownDictionary`, two `Cow<[u8]>`) contains no `HashMap` or `HashSet`, and
the upstream dictionary builder sorts its inputs. Three independent runs of
this tool produced byte-identical output.

That said, `jpreprocess-naist-jdic`'s build script downloads
`naist-jdic/archive/refs/tags/v0.1.3.tar.gz` **without checksum verification**,
so the build is not hermetic. Treat the SHA-256 as a pin to verify against,
not as something reproducible from first principles.

## Licensing

The dictionary data is NAIST-JDIC, BSD-3-Clause, Copyright (c) 2009 Nara
Institute of Science and Technology. Binary redistribution requires
reproducing the copyright notice, the licence conditions, and the disclaimer
alongside the distribution. `src/wasm/openjtalk-web/THIRD-PARTY-LICENSES.md`
section 4 already carries that text; it must travel with any published blob.
