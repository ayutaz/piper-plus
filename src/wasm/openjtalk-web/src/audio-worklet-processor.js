/**
 * PushAudioWorkletProcessor
 *
 * A "push" model AudioWorklet processor for TTS audio playback.
 * Audio data is pushed from the main thread via MessagePort and
 * the processor outputs it in real-time.
 *
 * Usage (main thread):
 *   await audioContext.audioWorklet.addModule('audio-worklet-processor.js');
 *   const node = new AudioWorkletNode(audioContext, 'push-audio-worklet-processor');
 *   node.port.postMessage({ type: 'audio', samples: float32Array });
 *   node.port.postMessage({ type: 'stop' });
 *
 * This file runs in the AudioWorklet scope — no ES module imports,
 * no window/document access.
 */

class PushAudioWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];  // queue of Float32Array chunks
    this._offset = 0;   // current read position in first chunk
    this.port.onmessage = (e) => {
      if (e.data.type === 'audio') {
        this._buffer.push(e.data.samples); // Float32Array
      } else if (e.data.type === 'stop') {
        this._buffer = [];
        this._offset = 0;
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0][0]; // mono channel
    let written = 0;

    while (written < output.length && this._buffer.length > 0) {
      const chunk = this._buffer[0];
      const remaining = chunk.length - this._offset;
      const toWrite = Math.min(remaining, output.length - written);

      for (let i = 0; i < toWrite; i++) {
        output[written + i] = chunk[this._offset + i];
      }

      written += toWrite;
      this._offset += toWrite;

      if (this._offset >= chunk.length) {
        this._buffer.shift();
        this._offset = 0;
      }
    }

    // Fill remaining with silence
    for (let i = written; i < output.length; i++) {
      output[i] = 0;
    }

    return true; // keep processor alive
  }
}

registerProcessor('push-audio-worklet-processor', PushAudioWorkletProcessor);
