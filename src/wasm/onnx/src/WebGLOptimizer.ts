/**
 * WebGL/WebGPU バックエンド最適化
 */

import { InferenceSession } from 'onnxruntime-web';

export interface OptimizationOptions {
  preferredBackend?: 'cpu' | 'webgl' | 'webgpu' | 'wasm' | 'auto';
  enableProfiling?: boolean;
  powerPreference?: 'low-power' | 'high-performance' | 'default';
}

export interface BackendCapabilities {
  webgl: boolean;
  webgl2: boolean;
  webgpu: boolean;
  simd: boolean;
  threads: boolean;
}

export class WebGLOptimizer {
  private capabilities: BackendCapabilities;

  constructor() {
    this.capabilities = this.detectCapabilities();
  }

  /**
   * 利用可能なバックエンドを検出
   */
  private detectCapabilities(): BackendCapabilities {
    return {
      webgl: this.checkWebGLSupport(1),
      webgl2: this.checkWebGLSupport(2),
      webgpu: this.checkWebGPUSupport(),
      simd: this.checkSIMDSupport(),
      threads: this.checkThreadsSupport()
    };
  }

  /**
   * WebGL サポート確認
   */
  private checkWebGLSupport(version: 1 | 2): boolean {
    try {
      const canvas = document.createElement('canvas');
      const contextName = version === 2 ? 'webgl2' : 'webgl';
      const gl = canvas.getContext(contextName) || canvas.getContext('experimental-' + contextName);
      
      if (!gl) return false;

      // 追加のWebGL機能確認
      if (version === 2) {
        // WebGL 2.0 必須拡張の確認
        const requiredExtensions = [
          'EXT_color_buffer_float',
          'OES_texture_float_linear'
        ];
        
        for (const ext of requiredExtensions) {
          if (!(gl as WebGL2RenderingContext).getExtension(ext)) {
            console.warn(`WebGL2 extension ${ext} not available`);
          }
        }
      }

      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * WebGPU サポート確認
   */
  private checkWebGPUSupport(): boolean {
    return 'gpu' in navigator;
  }

  /**
   * SIMD サポート確認
   */
  private checkSIMDSupport(): boolean {
    try {
      // WebAssembly SIMD feature detection
      const simdTest = new Uint8Array([
        0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b, 0x03,
        0x02, 0x01, 0x00, 0x0a, 0x0a, 0x01, 0x08, 0x00,
        0x41, 0x00, 0xfd, 0x0f, 0x0b
      ]);
      
      const module = new WebAssembly.Module(simdTest);
      return module !== null;
    } catch (e) {
      return false;
    }
  }

  /**
   * WebAssembly Threads サポート確認
   */
  private checkThreadsSupport(): boolean {
    return typeof SharedArrayBuffer !== 'undefined';
  }

  /**
   * 最適な実行プロバイダーを取得
   */
  getOptimalExecutionProviders(options: OptimizationOptions = {}): string[] {
    const providers: string[] = [];
    const { preferredBackend = 'auto' } = options;

    console.log('Backend capabilities:', this.capabilities);

    // 優先バックエンドが指定されている場合
    if (preferredBackend !== 'auto' && preferredBackend !== 'cpu') {
      if (this.isBackendAvailable(preferredBackend)) {
        providers.push(this.getProviderName(preferredBackend));
      }
    }

    // 自動選択またはフォールバック
    if (providers.length === 0) {
      // WebGPU (最高性能、実験的)
      if (this.capabilities.webgpu && preferredBackend !== 'webgl') {
        providers.push('webgpu');
      }

      // WebGL (安定、広くサポート)
      if (this.capabilities.webgl2) {
        providers.push('webgl');
      }

      // WASM with SIMD (CPUフォールバック)
      if (this.capabilities.simd) {
        providers.push('wasm');
      } else {
        providers.push('wasm');
      }
    }

    return providers;
  }

  /**
   * セッションオプションを最適化
   */
  getOptimizedSessionOptions(options: OptimizationOptions = {}): InferenceSession.SessionOptions {
    const executionProviders = this.getOptimalExecutionProviders(options);
    
    const sessionOptions: InferenceSession.SessionOptions = {
      executionProviders: executionProviders as any,
      graphOptimizationLevel: 'all',
      enableCpuMemArena: true,
      enableMemPattern: true,
      executionMode: 'sequential',
      logSeverityLevel: options.enableProfiling ? 1 : 3, // 1: Verbose, 3: Warning
    };

    // WebGL特有の設定
    if (executionProviders.includes('webgl')) {
      sessionOptions.executionProviders = [{
        name: 'webgl',
        // WebGL specific options
        contextId: 'webgl2',  // Use WebGL 2.0 if available
        matmulMaxBatchSize: 16,
        textureCacheMode: 'full',
        powerPreference: options.powerPreference || 'high-performance'
      } as any];
    }

    // WebGPU特有の設定
    if (executionProviders.includes('webgpu')) {
      sessionOptions.executionProviders = [{
        name: 'webgpu',
        powerPreference: options.powerPreference || 'high-performance',
        forceFallback: false
      } as any];
    }

    // WASM特有の設定
    if (executionProviders.includes('wasm')) {
      const wasmProvider: any = {
        name: 'wasm'
      };

      if (this.capabilities.simd) {
        wasmProvider.simd = true;
      }

      if (this.capabilities.threads) {
        wasmProvider.numThreads = Math.min(4, navigator.hardwareConcurrency || 2);
      }

      if (sessionOptions.executionProviders && Array.isArray(sessionOptions.executionProviders)) {
        sessionOptions.executionProviders.push(wasmProvider);
      }
    }

    return sessionOptions;
  }

  /**
   * パフォーマンス統計を取得
   */
  async getPerformanceProfile(session: InferenceSession): Promise<any> {
    try {
      // セッションのプロファイリングデータを取得
      // 注: この機能は ONNX Runtime Web の将来のバージョンで利用可能になる予定
      return {
        backend: (session as any).handler ? 'active' : 'unknown',
        capabilities: this.capabilities
      };
    } catch (error) {
      console.warn('Performance profiling not available:', error);
      return null;
    }
  }

  /**
   * バックエンドが利用可能か確認
   */
  private isBackendAvailable(backend: string): boolean {
    switch (backend) {
      case 'webgl':
        return this.capabilities.webgl2 || this.capabilities.webgl;
      case 'webgpu':
        return this.capabilities.webgpu;
      case 'wasm':
        return true; // WASM は常に利用可能
      default:
        return false;
    }
  }

  /**
   * プロバイダー名を取得
   */
  private getProviderName(backend: string): string {
    switch (backend) {
      case 'webgl':
        return 'webgl';
      case 'webgpu':
        return 'webgpu';
      case 'wasm':
        return 'wasm';
      default:
        return 'wasm';
    }
  }

  /**
   * 推奨設定を取得
   */
  getRecommendations(): string[] {
    const recommendations: string[] = [];

    if (!this.capabilities.webgl2 && !this.capabilities.webgl) {
      recommendations.push('WebGL サポートが検出されませんでした。GPU アクセラレーションは利用できません。');
    }

    if (!this.capabilities.simd) {
      recommendations.push('WebAssembly SIMD がサポートされていません。Chrome 91+ または Firefox 89+ へのアップグレードを推奨します。');
    }

    if (!this.capabilities.threads) {
      recommendations.push('SharedArrayBuffer が利用できません。Cross-Origin-Embedder-Policy と Cross-Origin-Opener-Policy ヘッダーを設定してください。');
    }

    if (this.capabilities.webgpu) {
      recommendations.push('WebGPU が利用可能です（実験的機能）。最高のパフォーマンスが期待できます。');
    }

    return recommendations;
  }
}

// エクスポート
export default WebGLOptimizer;