/**
 * WebGPUSessionManager
 * Phase 2b: WebGPU backend with automatic fallback
 *
 * Fallback order: webgpu -> wasm (no webgl)
 */

export class WebGPUSessionManager {
  /**
   * @param {Object} options
   * @param {Object} options.ort - ONNX Runtime module
   * @param {Object|undefined} options.gpu - navigator.gpu object
   */
  constructor({ ort, gpu }) {
    this._ort = ort;
    this._gpu = gpu;
    this.currentProvider = null;
  }

  /**
   * Create an InferenceSession, trying providers in fallback order.
   * @param {string} modelPath
   * @returns {Promise<Object>} InferenceSession
   */
  async createSession(modelPath) {
    const providers = this._gpu
      ? ['webgpu', 'wasm']
      : ['wasm'];

    const errors = [];
    for (const provider of providers) {
      try {
        const options = {
          executionProviders: [provider],
          graphOptimizationLevel: 'extended',
          enableMemPattern: true,
        };
        const session = await this._ort.InferenceSession.create(modelPath, options);
        this.currentProvider = provider;
        return session;
      } catch (e) {
        errors.push(`${typeof provider === 'string' ? provider : provider.name}: ${e?.message ?? String(e)}`);
      }
    }

    throw new Error(`All execution providers failed: ${errors.join('; ')}`);
  }

  /**
   * Check if the GPU can handle a model of the given size.
   * @param {number} modelSizeBytes
   * @returns {Promise<boolean>}
   */
  async checkGPUCapacity(modelSizeBytes) {
    if (!this._gpu) {
      return false;
    }

    const adapter = await this._gpu.requestAdapter();
    if (!adapter) return false;
    const device = await adapter.requestDevice();
    try {
      return device.limits.maxBufferSize >= modelSizeBytes
          && device.limits.maxStorageBufferBindingSize >= modelSizeBytes;
    } finally {
      device.destroy();
    }
  }
}
