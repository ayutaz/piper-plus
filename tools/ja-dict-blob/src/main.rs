//! Generate the external Japanese dictionary blob for WASM builds.
//!
//! `WasmPhonemizer::setJapaneseDictionary` (piper-wasm) accepts a
//! bincode-serialised `jpreprocess::Dictionary`. Nothing in this repository
//! produced one, so the `ja-external` / `multilingual-external` variants had
//! no way to phonemise Japanese: they fall back to `PassthroughPhonemizer`,
//! which emits character-level tokens without any error.
//!
//! The blob is a raw bincode dump — no magic bytes, no version field, no
//! length check. A blob built against a different `jpreprocess` or
//! `lindera-core` version therefore fails with an opaque error at best. This
//! tool writes a `.json` sidecar recording the exact provenance so the
//! consumer side can pin it.
//!
//! ```sh
//! cargo run --release -- naist-jdic.bin
//! ```

use std::path::PathBuf;

use sha2::{Digest, Sha256};

/// Version of `jpreprocess` this blob is compatible with.
///
/// `jpreprocess` documents that a dictionary must be loaded by the same
/// version that built it, and the blob carries no version marker of its own.
const JPREPROCESS_VERSION: &str = "0.9.1";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out: PathBuf = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "naist-jdic.bin".into())
        .into();

    eprintln!("Loading bundled NAIST-JDIC ...");
    let dictionary = jpreprocess::SystemDictionaryConfig::Bundled(
        jpreprocess::kind::JPreprocessDictionaryKind::NaistJdic,
    )
    .load()?;

    eprintln!("Serialising with bincode ...");
    let bytes = bincode::serialize(&dictionary)?;

    // Round-trip before writing. A blob that cannot be read back is worse
    // than no blob: the consumer degrades to passthrough Japanese silently.
    eprintln!("Verifying round-trip ...");
    let restored: jpreprocess::Dictionary = bincode::deserialize(&bytes)?;
    let _ = jpreprocess::JPreprocess::with_dictionaries(restored, None);

    let digest = format!("{:x}", Sha256::digest(&bytes));

    std::fs::write(&out, &bytes)?;

    let sidecar = out.with_extension("json");
    let meta = format!(
        concat!(
            "{{\n",
            "  \"format\": \"bincode/jpreprocess-dictionary\",\n",
            "  \"jpreprocess_version\": \"{}\",\n",
            "  \"bytes\": {},\n",
            "  \"sha256\": \"{}\"\n",
            "}}\n"
        ),
        JPREPROCESS_VERSION,
        bytes.len(),
        digest
    );
    std::fs::write(&sidecar, meta)?;

    println!("wrote {} ({} bytes)", out.display(), bytes.len());
    println!("wrote {}", sidecar.display());
    println!("sha256 {digest}");
    println!();
    println!("Serialisation is deterministic: the graph reachable from");
    println!("`Dictionary` contains no HashMap/HashSet, so the same inputs");
    println!("produce a byte-identical blob. Pin the sha256 above wherever");
    println!("the blob is fetched -- the upstream naist-jdic tarball is");
    println!("downloaded without checksum verification, so reproducibility");
    println!("holds only for a fixed jpreprocess version and upstream tag.");
    Ok(())
}
