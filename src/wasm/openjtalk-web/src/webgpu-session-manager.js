/**
 * WebGPUSessionManager
 * Phase 2b: WebGPU backend with automatic fallback
 *
 * Fallback order: webgpu -> wasm (no webgl)
 *
 * NOTE: WebGPU (WGSL) does not support 64-bit integers (i64/u64).
 * ONNX Runtime's WebGPU backend has limited int64 support — operators
 * like GatherND fail at runtime with "Unsupported data type: 7".
 * VITS models use int64 tensors for input/input_lengths/lid/prosody_features,
 * so we skip WebGPU for models that declare int64 inputs and fall back to WASM.
 */

/**
 * ONNX TensorProto data types that are unsupported in WebGPU's WGSL shaders.
 * See: https://onnx.ai/onnx/api/mapping.html
 * INT64 = 7, UINT64 = 13
 */
const WEBGPU_UNSUPPORTED_DTYPES = new Set(['int64', 'uint64']);

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
   *
   * When a session is successfully created with WebGPU, we inspect the model's
   * input tensor types. If any input uses a dtype unsupported by WebGPU (e.g.
   * int64), we proactively fall back to WASM to avoid runtime kernel failures.
   *
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

        // Check for int64 inputs that WebGPU cannot handle
        if (provider === 'webgpu' && this._hasUnsupportedDtypes(session)) {
          console.warn(
            '[piper-plus] Model uses int64 tensors unsupported by WebGPU (WGSL has no i64). '
            + 'Falling back to WASM execution provider.'
          );
          // Release the WebGPU session before retrying
          if (typeof session.release === 'function') {
            await session.release();
          }
          errors.push('webgpu: model uses int64 tensors (unsupported by WGSL)');
          continue;
        }

        this.currentProvider = provider;
        return session;
      } catch (e) {
        errors.push(`${typeof provider === 'string' ? provider : provider.name}: ${e?.message ?? String(e)}`);
      }
    }

    throw new Error(`All execution providers failed: ${errors.join('; ')}`);
  }

  /**
   * Check whether a session's inputs use data types unsupported by WebGPU.
   * @param {Object} session - ONNX InferenceSession
   * @returns {boolean} true if any input uses an unsupported dtype
   * @private
   */
  _hasUnsupportedDtypes(session) {
    try {
      // session.inputNames + session.inputMetadata (ort-web >= 1.17)
      // or iterate session handler's inputTypes
      const names = session.inputNames;
      if (!names) return false;
      for (const name of names) {
        const meta = session.inputMetadata?.[name];
        if (meta && WEBGPU_UNSUPPORTED_DTYPES.has(meta.dataType)) {
          return true;
        }
      }
      // Fallback: check handler (internal API, best-effort)
      const handler = session.handler || session._handler;
      if (handler?.inputTypes) {
        for (const dtype of handler.inputTypes) {
          if (WEBGPU_UNSUPPORTED_DTYPES.has(dtype)) {
            return true;
          }
        }
      }
    } catch {
      // If introspection fails, be conservative and allow the provider
    }
    return false;
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
