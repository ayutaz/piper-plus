/**
 * Piper ONNX Runtime Integration
 * 
 * Main entry point for ONNX-based voice synthesis
 */

export { PiperONNXRuntime } from './PiperONNXRuntime';
export { ModelLoader } from './ModelLoader';
export { VoiceSynthesizer } from './VoiceSynthesizer';
export { AudioPlayer } from './AudioPlayer';
export * from './types';

// Default export for UMD builds
import { PiperONNXRuntime } from './PiperONNXRuntime';
export default PiperONNXRuntime;