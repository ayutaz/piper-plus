/**
 * Short-text mitigation (Strategy A + B) and the Issue #499 EOS-region trim.
 *
 * Kept free of imports so that `bin/piper-cli.js` (the Node parity / RTF
 * surface, which installs only onnxruntime-node) applies the same
 * post-processing as `PiperPlus.synthesize()`. `index.js` re-exports every
 * name, so the public API is unchanged.
 */

// Short-text mitigation constants (keep in sync with other runtimes —
// docs/spec/short-text-contract.toml).
//
// Issue #356: MIN_PHONEME_IDS was 40, but tsukuyomi 6lang testing showed
// synthesis is stable down to ~8 IDs. 40 caused Strategy A to fire on
// already-stable inputs and leak padding artifacts. 15 keeps Strategy A
// active for genuinely tiny inputs only. MIN_BODY_FOR_STRATEGY_A = 3
// additionally bypasses Strategy A when the body (= phoneme IDs minus
// BOS/EOS) is too small for padding to outweigh content (e.g. 「あ。」).
export const MIN_PHONEME_IDS = 15;
export const MIN_BODY_FOR_STRATEGY_A = 3;
// Number of EOS frames retained by the durations-based Strategy A trim.
// 0 = drop the entire EOS region (issue #356).
export const TRIM_EOS_MAX_FRAMES = 0;
// Default hop length when config.json does not declare audio.hop_size.
export const DEFAULT_HOP_SIZE = 256;
const TRIM_THRESHOLD_RMS = 0.01;
const TRIM_MIN_SAMPLES = 2205; // 22050 Hz * 0.1 s

// ---------------------------------------------------------------------------
// Short-text mitigation helpers (Strategy A + B)
// ---------------------------------------------------------------------------

/**
 * Strategy A: Pad short phoneme ID sequences with silence tokens.
 *
 * Inserts pause tokens (ID = 0) evenly after BOS and before EOS until the
 * sequence reaches MIN_PHONEME_IDS length.  Also pads prosodyFeatures with
 * zero triplets at matching positions when present.
 *
 * Strategy A is skipped when the body (= phoneme IDs minus BOS / EOS) is
 * shorter than MIN_BODY_FOR_STRATEGY_A — see issue #356.
 *
 * The returned object now also carries `frontPad` / `backPad` (the number
 * of pad tokens inserted on each side) so the durations-based post-trim
 * can locate the padding precisely. Existing callers that only consumed
 * `phonemeIds` / `prosodyFeatures` / `wasPadded` continue to work
 * unchanged (object extension, not breaking).
 *
 * @param {number[]} phonemeIds
 * @param {number[][]|null} prosodyFeatures
 * @returns {{ phonemeIds: number[], prosodyFeatures: number[][]|null, wasPadded: boolean, frontPad: number, backPad: number }}
 */
export function padPhonemeIds(phonemeIds, prosodyFeatures) {
  const n = phonemeIds.length;
  const bodyLen = n - 2; // exclude BOS / EOS
  if (bodyLen < MIN_BODY_FOR_STRATEGY_A) {
    return { phonemeIds, prosodyFeatures, wasPadded: false, frontPad: 0, backPad: 0 };
  }
  if (n >= MIN_PHONEME_IDS) {
    return { phonemeIds, prosodyFeatures, wasPadded: false, frontPad: 0, backPad: 0 };
  }

  const padTotal = MIN_PHONEME_IDS - n;
  const padFront = Math.floor(padTotal / 2);
  const padBack = padTotal - padFront;

  // phonemeIds layout: [BOS, ...body..., EOS]
  const bos = phonemeIds.slice(0, 1);
  const body = phonemeIds.slice(1, -1);
  const eos = phonemeIds.slice(-1);

  const padded = [
    ...bos,
    ...new Array(padFront).fill(0),
    ...body,
    ...new Array(padBack).fill(0),
    ...eos,
  ];

  let paddedProsody = null;
  if (prosodyFeatures != null) {
    const pBos = prosodyFeatures.slice(0, 1);
    const pBody = prosodyFeatures.slice(1, -1);
    const pEos = prosodyFeatures.slice(-1);
    paddedProsody = [
      ...pBos,
      ...new Array(padFront).fill(null).map(() => [0, 0, 0]),
      ...pBody,
      ...new Array(padBack).fill(null).map(() => [0, 0, 0]),
      ...pEos,
    ];
  }

  return {
    phonemeIds: padded,
    prosodyFeatures: paddedProsody,
    wasPadded: true,
    frontPad: padFront,
    backPad: padBack,
  };
}

/**
 * Strategy A precise post-trim using the model's duration output.
 * Mirrors the Python reference (src/python_run/piper_plus/voice.py
 * `_trim_padding_by_durations`) so all runtimes produce byte-equal output
 * for the same inputs (issue #356).
 *
 * Padded layout: `[BOS, pad×frontPad, ...body..., pad×backPad, EOS]`.
 *
 * Trimming policy:
 *   - BOS + front padding: stripped completely
 *   - Back padding: stripped completely
 *   - EOS: keep only `eosMaxFrames` frames (default 0 — drop the entire EOS)
 *
 * All frame→sample conversions use `Math.trunc()` (truncation toward zero),
 * matching `int()` in Python and `as i64` in Rust. `Math.round()` is *not*
 * used because it would diverge from the other runtimes.
 *
 * @param {Float32Array} audio  Audio samples in the range -1.0 to 1.0
 * @param {number[]|Float32Array|null} durations  Per-phoneme frame counts
 * @param {number} frontPad
 * @param {number} backPad
 * @param {number} hopSize  VITS hop length (samples per frame)
 * @param {number} [eosMaxFrames=TRIM_EOS_MAX_FRAMES]
 * @returns {Float32Array} Trimmed audio (or the original if inputs are inconsistent)
 */
export function trimPaddingByDurations(
  audio,
  durations,
  frontPad,
  backPad,
  hopSize,
  eosMaxFrames = TRIM_EOS_MAX_FRAMES
) {
  if (frontPad <= 0 && backPad <= 0) {
    return audio;
  }
  if (durations == null || hopSize <= 0) {
    return audio;
  }
  const expectedLen = 1 + frontPad + backPad + 1; // BOS + pads + EOS
  if (durations.length < expectedLen) {
    return audio;
  }

  // Front: BOS + front padding samples (truncated).
  let frontSum = 0;
  for (let i = 0; i < 1 + frontPad; i++) {
    frontSum += durations[i];
  }
  const frontSamples = Math.trunc(frontSum * hopSize);

  // Back: back padding samples + EOS excess (over eosMaxFrames).
  let backPadSum = 0;
  if (backPad > 0) {
    // Equivalent to durations[-(1+backPad) : -1] in Python.
    const start = durations.length - 1 - backPad;
    for (let i = start; i < durations.length - 1; i++) {
      backPadSum += durations[i];
    }
  }
  const backPadSamples = Math.trunc(backPadSum * hopSize);
  const eosFrames = durations[durations.length - 1];
  const eosExcess = Math.max(0, eosFrames - eosMaxFrames);
  const backSamples = backPadSamples + Math.trunc(eosExcess * hopSize);

  const total = audio.length;
  const start = Math.max(0, frontSamples);
  let end = total - backSamples;
  if (end < start) {
    end = start;
  }
  if (start >= total || end <= 0 || start >= end) {
    return audio;
  }

  // subarray() avoids a copy; subscribers that mutate must already clone.
  return audio.subarray(start, end);
}

/**
 * Tier 1 workaround for Issue #499: trim the EOS region from the tail for
 * **every** inference path (long-text included).
 *
 * `VitsModel.infer()` expands attention with `ceil(w)` but exposes the raw
 * float `w` as the `durations` output. The EOS frame(s) generated under
 * `ceil` carry decoder leakage that sounds like the final syllable was
 * repeated — clearly audible on fine-tuned models such as
 * `piper-plus-tsukuyomi-chan`. {@link trimPaddingByDurations} already drops
 * the EOS region only when Strategy A short-text padding was applied; this
 * helper applies the same drop to every other inference path so long-text
 * outputs do not retain the audible doubled tail.
 *
 * Mirrors `src/python_run/piper_plus/voice.py::_trim_eos_region` so all runtimes
 * produce byte-equal output for the same `(audio, durations[-1], hopSize,
 * eosMaxFrames)` tuple. The sample-count conversion uses `Math.trunc()` to
 * match Python's `int(...)` semantics — cross-runtime contract (Issue #499).
 *
 * @param {Float32Array} audio  Audio samples in the range -1.0 to 1.0
 * @param {number[]|Float32Array|null} durations  Per-phoneme frame counts
 * @param {number} hopSize  VITS hop length (samples per frame)
 * @param {number} [eosMaxFrames=TRIM_EOS_MAX_FRAMES]
 * @returns {Float32Array} Trimmed audio (or the original if inputs are inconsistent)
 */
export function trimEosRegion(audio, durations, hopSize, eosMaxFrames = TRIM_EOS_MAX_FRAMES) {
  if (hopSize <= 0 || durations == null || durations.length === 0) {
    return audio;
  }
  const eosFrames = durations[durations.length - 1];
  const eosCeil = Math.ceil(eosFrames);
  const eosExcess = Math.max(0, eosCeil - eosMaxFrames);
  if (eosExcess <= 0) {
    return audio;
  }
  // Math.trunc() makes the frame→sample conversion explicit so the truncation
  // contract holds even when `hopSize` (or any intermediate product) ends up
  // non-integer — matches Python `int(...)` and Rust `as i64`. Without this
  // the implementation would rely on TypedArray.subarray()'s implicit index
  // coercion, which diverges around boundary float values.
  const trimSamples = Math.trunc(eosExcess * hopSize);
  if (trimSamples >= audio.length) {
    return audio;
  }
  // subarray() avoids a copy; subscribers that mutate must already clone.
  return audio.subarray(0, audio.length - trimSamples);
}

/**
 * Strategy A (post-step): Trim leading and trailing silence from Float32Array
 * audio using a sliding RMS window.
 *
 * Keeps at least TRIM_MIN_SAMPLES to avoid producing empty audio.
 *
 * @param {Float32Array} audio - Audio samples in the range -1.0 to 1.0
 * @param {number} [windowSize=256] - RMS window size in samples
 * @returns {Float32Array}
 */
export function trimSilence(audio, windowSize = 256) {
  const n = audio.length;
  if (n <= TRIM_MIN_SAMPLES) {
    return audio;
  }

  const nWindows = Math.floor(n / windowSize);
  if (nWindows === 0) {
    return audio;
  }

  // Compute per-window RMS
  let firstAbove = -1;
  let lastAbove = -1;
  for (let w = 0; w < nWindows; w++) {
    const offset = w * windowSize;
    let sumSq = 0;
    for (let j = 0; j < windowSize; j++) {
      const s = audio[offset + j];
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / windowSize);
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = w;
      }
      lastAbove = w;
    }
  }

  // Check partial window (remainder samples after the last full window)
  const remainder = n % windowSize;
  if (remainder > 0) {
    const offset = nWindows * windowSize;
    let sumSq = 0;
    for (let j = 0; j < remainder; j++) {
      const s = audio[offset + j];
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / remainder);
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) {
        firstAbove = nWindows;
      } // virtual window index for the partial
      lastAbove = nWindows;
    }
  }

  if (firstAbove < 0) {
    // All silence — return minimum-length slice from the start
    return audio.slice(0, TRIM_MIN_SAMPLES);
  }

  let startSample = firstAbove * windowSize;
  let endSample = Math.min((lastAbove + 1) * windowSize, n);

  // Ensure minimum length
  const length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    const center = Math.floor((startSample + endSample) / 2);
    const half = Math.floor(TRIM_MIN_SAMPLES / 2);
    startSample = Math.max(0, center - half);
    endSample = Math.min(n, startSample + TRIM_MIN_SAMPLES);
    startSample = Math.max(0, endSample - TRIM_MIN_SAMPLES);
  }

  return audio.slice(startSample, endSample);
}

/**
 * Strategy B: Adjust noise scales for short inputs.
 *
 * For inputs shorter than MIN_PHONEME_IDS, attenuate noiseScale and noiseW
 * proportionally while keeping lengthScale unchanged.
 *
 * @param {number} phonemeCount - Number of phoneme IDs
 * @param {number} noiseScale
 * @param {number} noiseW
 * @returns {{ noiseScale: number, noiseW: number }}
 */
export function adjustScalesForShortInput(phonemeCount, noiseScale, noiseW) {
  if (phonemeCount >= MIN_PHONEME_IDS) {
    return { noiseScale, noiseW };
  }

  const ratio = Math.min(1.0, phonemeCount / MIN_PHONEME_IDS);
  return {
    noiseScale: noiseScale * Math.max(0.5, ratio),
    noiseW: noiseW * Math.max(0.4, ratio),
  };
}
