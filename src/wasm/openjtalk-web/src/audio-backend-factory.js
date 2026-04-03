/**
 * AudioBackendFactory — creates best available audio playback backend
 *
 * Fallback chain: AudioWorklet → ScriptProcessor → HTMLAudioElement
 */

export class AudioBackendFactory {
  /**
   * Create the best available audio backend
   * @param {Object} options
   * @param {string} options.workletUrl - URL to audio-worklet-processor.js
   * @param {number} options.sampleRate - Output sample rate (default: 48000)
   * @returns {Promise<AudioBackend>}
   */
  static async create({ workletUrl = './audio-worklet-processor.js', sampleRate = 48000 } = {}) {
    // Try AudioWorklet first
    let ctx;
    try {
      ctx = new AudioContext({ sampleRate });
      if (ctx.audioWorklet) {
        await ctx.audioWorklet.addModule(workletUrl);
        return new AudioWorkletBackend(ctx);
      }
    } catch (e) {
      console.warn('[piper-plus] AudioWorklet not available, falling back:', e.message);
    }
    // Close unused AudioContext before trying next fallback
    if (ctx && ctx.state !== 'closed') {
      try { await ctx.close(); } catch { /* ignore close errors */ }
    }

    // Try ScriptProcessor (deprecated but widely supported)
    try {
      ctx = new AudioContext({ sampleRate });
      return new ScriptProcessorBackend(ctx);
    } catch (e) {
      console.warn('[piper-plus] ScriptProcessor not available, falling back:', e.message);
      if (ctx && ctx.state !== 'closed') {
        try { await ctx.close(); } catch { /* ignore close errors */ }
      }
    }

    // Fallback: HTMLAudioElement (iOS Safari)
    return new HTMLAudioBackend(sampleRate);
  }
}

/** AudioWorklet-based backend */
class AudioWorkletBackend {
  constructor(ctx) {
    this.ctx = ctx;
    this.node = null;
    this.type = 'audioworklet';
  }

  async play(audioData) {
    // audioData is Float32Array at 48kHz
    if (this.ctx.state === 'suspended') await this.ctx.resume();
    this.stop();
    this.node = new AudioWorkletNode(this.ctx, 'push-audio-worklet-processor');
    this.node.connect(this.ctx.destination);
    this.node.port.postMessage({ type: 'audio', samples: audioData });
  }

  pushChunk(chunk) {
    if (this.node) {
      this.node.port.postMessage({ type: 'audio', samples: chunk });
    }
  }

  stop() {
    if (this.node) {
      this.node.port.postMessage({ type: 'stop' });
      this.node.disconnect();
      this.node = null;
    }
  }

  async dispose() {
    this.stop();
    if (this.ctx.state !== 'closed') await this.ctx.close();
  }
}

/** ScriptProcessor-based backend (deprecated fallback) */
class ScriptProcessorBackend {
  constructor(ctx) {
    this.ctx = ctx;
    this.processor = null;
    this.buffer = [];
    this.offset = 0;
    this.type = 'scriptprocessor';
  }

  async play(audioData) {
    if (this.ctx.state === 'suspended') await this.ctx.resume();
    this.stop();
    this.buffer = [audioData];
    this.offset = 0;
    const bufSize = 4096;
    this.processor = this.ctx.createScriptProcessor(bufSize, 0, 1);
    this.processor.onaudioprocess = (e) => {
      const output = e.outputBuffer.getChannelData(0);
      let written = 0;
      while (written < output.length && this.buffer.length > 0) {
        const chunk = this.buffer[0];
        const remaining = chunk.length - this.offset;
        const toWrite = Math.min(remaining, output.length - written);
        for (let i = 0; i < toWrite; i++) {
          output[written + i] = chunk[this.offset + i];
        }
        written += toWrite;
        this.offset += toWrite;
        if (this.offset >= chunk.length) {
          this.buffer.shift();
          this.offset = 0;
        }
      }
      for (let i = written; i < output.length; i++) {
        output[i] = 0;
      }
    };
    this.processor.connect(this.ctx.destination);
  }

  pushChunk(chunk) {
    this.buffer.push(chunk);
  }

  stop() {
    if (this.processor) {
      this.processor.onaudioprocess = null;
      this.processor.disconnect();
      this.processor = null;
    }
    this.buffer = [];
    this.offset = 0;
  }

  async dispose() {
    this.stop();
    if (this.ctx.state !== 'closed') await this.ctx.close();
  }
}

/** HTMLAudioElement-based backend (iOS Safari fallback) */
class HTMLAudioBackend {
  constructor(sampleRate) {
    this.sampleRate = sampleRate;
    this.audio = null;
    this._blobUrl = null;
    this.type = 'htmlaudio';
  }

  async play(audioData) {
    // Stop any existing playback before starting new one
    this.stop();
    // Encode as WAV and play via <audio> element
    const wav = this._encodeWav(audioData);
    const blob = new Blob([wav], { type: 'audio/wav' });
    this._blobUrl = URL.createObjectURL(blob);
    this.audio = new Audio(this._blobUrl);
    try {
      await this.audio.play();
    } catch (e) {
      this.stop();
      throw e;
    }
  }

  pushChunk(chunk) {
    // HTMLAudio doesn't support streaming — buffer and play at end
    console.warn('[piper-plus] HTMLAudioBackend does not support streaming pushChunk');
  }

  stop() {
    if (this.audio) {
      this.audio.pause();
      this.audio = null;
    }
    if (this._blobUrl) {
      URL.revokeObjectURL(this._blobUrl);
      this._blobUrl = null;
    }
  }

  dispose() {
    this.stop();
  }

  _encodeWav(samples) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeString = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, this.sampleRate, true);
    view.setUint32(28, this.sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
  }
}

export { AudioWorkletBackend, ScriptProcessorBackend, HTMLAudioBackend };
