/**
 * Simple audio resampler using linear interpolation.
 *
 * Designed for TTS output conversion (typically 22050Hz → 48000Hz).
 * Uses linear interpolation which preserves DC signals and maintains
 * output within [-1, 1] range. No anti-aliasing filter is applied,
 * which is acceptable for upsampling but may cause aliasing artifacts
 * for extreme downsampling ratios (>4x).
 *
 * Limitations:
 * - Linear interpolation only (no sinc/polyphase filtering)
 * - Edge samples use nearest-neighbor clamping when the interpolation
 *   window extends beyond the input buffer
 * - For high-quality downsampling, consider a polyphase resampler with
 *   a low-pass anti-aliasing filter instead
 */
export class SimpleResampler {
  /**
   * @param {number} inputRate  - Input sample rate (e.g. 22050)
   * @param {number} outputRate - Output sample rate (e.g. 48000)
   */
  constructor(inputRate, outputRate) {
    this.inputRate = inputRate;
    this.outputRate = outputRate;
  }

  /**
   * Resample using linear interpolation.
   * @param {Float32Array} input
   * @returns {Float32Array}
   */
  resample(input) {
    const inputLen = input.length;
    if (inputLen === 0) {
      return new Float32Array(0);
    }

    const outputLen = Math.round(inputLen * this.outputRate / this.inputRate);
    if (outputLen === 0) {
      return new Float32Array(0);
    }

    // Identity rate: return a copy
    if (this.inputRate === this.outputRate) {
      return new Float32Array(input);
    }

    const output = new Float32Array(outputLen);
    const ratio = this.inputRate / this.outputRate;

    for (let i = 0; i < outputLen; i++) {
      const srcPos = i * ratio;
      const srcIndex = Math.floor(srcPos);
      const frac = srcPos - srcIndex;

      if (srcIndex + 1 < inputLen) {
        output[i] = input[srcIndex] * (1 - frac) + input[srcIndex + 1] * frac;
      } else {
        output[i] = input[Math.min(srcIndex, inputLen - 1)];
      }
    }

    return output;
  }
}
