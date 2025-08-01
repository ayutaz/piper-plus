/**
 * OpenJTalk-Piper Integration for Browser TTS
 * Combines OpenJTalk WebAssembly for phonemization with Piper ONNX for synthesis
 */

class OpenJTalkPiperTTS {
    constructor() {
        this.openjtalkModule = null;
        this.onnxSession = null;
        this.phonemeIdMap = null;
        this.modelConfig = null;
        this.initialized = false;
    }

    /**
     * Initialize both OpenJTalk and ONNX Runtime
     * @param {Object} config - Configuration object
     */
    async initialize(config) {
        try {
            console.log('Initializing OpenJTalk-Piper TTS...');
            
            // Initialize OpenJTalk
            await this.initializeOpenJTalk(config.openjtalk);
            
            // Initialize ONNX Runtime
            await this.initializeONNX(config.onnx);
            
            this.initialized = true;
            console.log('OpenJTalk-Piper TTS initialized successfully');
        } catch (error) {
            console.error('Initialization failed:', error);
            throw error;
        }
    }

    /**
     * Initialize OpenJTalk WebAssembly module
     */
    async initializeOpenJTalk(config) {
        console.log('Loading OpenJTalk WebAssembly...');
        
        // Import OpenJTalk module
        // Handle both local development and GitHub Pages deployment
        let jsPath = config.jsPath;
        
        // If we're on GitHub Pages and the path doesn't start with relative indicator
        if (window.location.hostname.includes('github.io')) {
            // Convert paths for GitHub Pages deployment
            if (jsPath === 'dist/openjtalk.js' || jsPath === './dist/openjtalk.js') {
                jsPath = '../../dist/openjtalk.js';
            }
        }
        
        // Ensure proper relative path for dynamic imports
        if (!jsPath.startsWith('./') && !jsPath.startsWith('../') && !jsPath.startsWith('/')) {
            jsPath = `./${jsPath}`;
        }
        
        const OpenJTalkModule = (await import(jsPath)).default;
        
        // Adjust wasmPath for GitHub Pages
        let wasmPath = config.wasmPath;
        if (window.location.hostname.includes('github.io')) {
            if (wasmPath === 'dist/openjtalk.wasm' || wasmPath === './dist/openjtalk.wasm') {
                wasmPath = '../../dist/openjtalk.wasm';
            }
        }
        
        this.openjtalkModule = await OpenJTalkModule({
            locateFile: (path) => {
                if (path.endsWith('.wasm')) {
                    return wasmPath;
                }
                return path;
            }
        });
        
        // Create directories
        this.openjtalkModule.FS.mkdir('/dict');
        this.openjtalkModule.FS.mkdir('/voice');
        
        // Adjust paths for GitHub Pages
        let dictPath = config.dictPath;
        let voicePath = config.voicePath;
        if (window.location.hostname.includes('github.io')) {
            if (dictPath === 'dict' || dictPath === './dict') {
                dictPath = '../../dict';
            }
            if (voicePath.startsWith('assets/') || voicePath.startsWith('./assets/')) {
                voicePath = '../../' + voicePath.replace(/^\.?\//, '');
            }
        }
        
        // Load dictionary files
        const dictFiles = [
            'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
            'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
        ];
        
        for (const file of dictFiles) {
            const response = await fetch(`${dictPath}/${file}`);
            const data = await response.arrayBuffer();
            this.openjtalkModule.FS.writeFile(`/dict/${file}`, new Uint8Array(data));
        }
        
        // Load voice file (needed for OpenJTalk initialization)
        const voiceResponse = await fetch(voicePath);
        const voiceData = await voiceResponse.arrayBuffer();
        this.openjtalkModule.FS.writeFile('/voice/voice.htsvoice', new Uint8Array(voiceData));
        
        // Initialize OpenJTalk
        const dictPtr = this.openjtalkModule.allocateUTF8('/dict');
        const voicePtr = this.openjtalkModule.allocateUTF8('/voice/voice.htsvoice');
        const result = this.openjtalkModule._openjtalk_initialize(dictPtr, voicePtr);
        this.openjtalkModule._free(dictPtr);
        this.openjtalkModule._free(voicePtr);
        
        if (result !== 0) {
            throw new Error(`OpenJTalk initialization failed with code: ${result}`);
        }
        
        console.log('OpenJTalk initialized');
    }

    /**
     * Initialize ONNX Runtime and load model
     */
    async initializeONNX(config) {
        console.log('Loading ONNX Runtime...');
        
        // Adjust paths for GitHub Pages
        let modelPath = config.modelPath;
        let modelConfigPath = config.modelConfigPath;
        if (window.location.hostname.includes('github.io')) {
            if (modelPath.startsWith('models/') || modelPath.startsWith('./models/')) {
                modelPath = '../../' + modelPath.replace(/^\.?\//, '');
            }
            if (modelConfigPath.startsWith('models/') || modelConfigPath.startsWith('./models/')) {
                modelConfigPath = '../../' + modelConfigPath.replace(/^\.?\//, '');
            }
        }
        
        // Load model configuration
        const configResponse = await fetch(modelConfigPath);
        this.modelConfig = await configResponse.json();
        this.phonemeIdMap = this.modelConfig.phoneme_id_map;
        
        // Create ONNX session
        this.onnxSession = await ort.InferenceSession.create(modelPath, {
            executionProviders: ['wasm'],
            graphOptimizationLevel: 'all'
        });
        
        console.log('ONNX model loaded:', this.onnxSession.inputNames, this.onnxSession.outputNames);
    }

    /**
     * Convert text to speech
     * @param {string} text - Input text in Japanese
     * @returns {Float32Array} Audio data
     */
    async textToSpeech(text, speakerId = null) {
        if (!this.initialized) {
            throw new Error('TTS not initialized');
        }
        
        console.log('Converting text to speech:', text);
        
        // Step 1: Text to phoneme labels
        const labels = await this.textToLabels(text);
        
        // Step 2: Extract phonemes from labels
        const phonemes = this.extractPhonemes(labels);
        console.log('Phonemes:', phonemes);
        
        // Step 3: Convert phonemes to IDs
        const phonemeIds = this.phonemesToIds(phonemes);
        console.log('Phoneme IDs:', phonemeIds);
        
        // Step 4: Synthesize audio
        const audio = await this.synthesizeAudio(phonemeIds, speakerId);
        
        return audio;
    }

    /**
     * Convert text to phoneme labels using OpenJTalk
     */
    async textToLabels(text) {
        const textPtr = this.openjtalkModule.allocateUTF8(text);
        const labelsPtr = this.openjtalkModule._openjtalk_synthesis_labels(textPtr);
        const labels = this.openjtalkModule.UTF8ToString(labelsPtr);
        
        this.openjtalkModule._openjtalk_free_string(labelsPtr);
        this.openjtalkModule._free(textPtr);
        
        if (labels.startsWith('ERROR:')) {
            throw new Error(labels);
        }
        
        return labels;
    }

    /**
     * Extract phonemes from OpenJTalk labels
     */
    extractPhonemes(labels) {
        const lines = labels.split('\n').filter(line => line.trim());
        const phonemes = [];
        
        // Add start token
        phonemes.push('^');
        
        for (const line of lines) {
            // Extract phoneme from label format: xx^xx-k+o=N/...
            const match = line.match(/\-([^+]+)\+/);
            if (match && match[1] !== 'sil') {
                phonemes.push(match[1]);
            }
        }
        
        // Add end token
        phonemes.push('$');
        
        return phonemes;
    }

    /**
     * Convert phonemes to phoneme IDs
     */
    phonemesToIds(phonemes) {
        const ids = [];
        
        // Multi-character phoneme mappings for OpenJTalk
        const multiCharPhonemeMap = {
            // Long vowels
            'a:': '\ue000',  // 長音あ
            'i:': '\ue001',  // 長音い
            'u:': '\ue002',  // 長音う
            'e:': '\ue003',  // 長音え
            'o:': '\ue004',  // 長音お
            // Special consonants
            'N:': '\ue005',  // 長音ん（モデル側ではclのマッピング）
            // Palatalized consonants
            'ky': '\ue006',  // きゃ行
            'kw': '\ue007',  // くゎ
            'gy': '\ue008',  // ぎゃ行
            'gw': '\ue009',  // ぐゎ
            'ty': '\ue00a',  // ちゃ行
            'dy': '\ue00b',  // ぢゃ行
            'py': '\ue00c',  // ぴゃ行
            'by': '\ue00d',  // びゃ行
            'ts': '\ue00e',  // つ
            'ch': '\ue00f',  // ち
            'sy': '\ue010',  // しゃ行
            'sh': '\ue010',  // しゃ行（別表記）
            'zy': '\ue011',  // じゃ行
            'hy': '\ue012',  // ひゃ行
            'ny': '\ue013',  // にゃ行
            'my': '\ue014',  // みゃ行
            'ry': '\ue015',  // りゃ行
            // Special mappings
            'cl': '\ue005',  // 促音（っ）- Python側のマッピングに合わせる
            'pau': '#',      // ポーズ
            'sp': '#',       // 短いポーズ
            'sil': '_'       // 無音
        };
        
        for (const phoneme of phonemes) {
            // Check multi-character mappings first
            const mapped = multiCharPhonemeMap[phoneme];
            if (mapped) {
                if (this.phonemeIdMap[mapped]) {
                    ids.push(...this.phonemeIdMap[mapped]);
                } else {
                    console.warn(`Mapped phoneme not found in ID map: ${phoneme} -> ${mapped}`);
                    ids.push(0);
                }
            } else if (this.phonemeIdMap[phoneme]) {
                ids.push(...this.phonemeIdMap[phoneme]);
            } else {
                console.warn(`Unknown phoneme: ${phoneme}`);
                // Use padding token
                ids.push(0);
            }
        }
        
        return ids;
    }

    /**
     * Synthesize audio using ONNX model
     */
    async synthesizeAudio(phonemeIds, speakerId = null) {
        // Prepare input tensors
        const inputTensor = new ort.Tensor('int64', 
            new BigInt64Array(phonemeIds.map(id => BigInt(id))), 
            [1, phonemeIds.length]
        );
        
        const lengthTensor = new ort.Tensor('int64', 
            new BigInt64Array([BigInt(phonemeIds.length)]), 
            [1]
        );
        
        const scalesTensor = new ort.Tensor('float32', 
            new Float32Array([
                this.modelConfig.inference.noise_scale || 0.667,
                this.modelConfig.inference.length_scale || 1.0,
                this.modelConfig.inference.noise_w || 0.8
            ]), 
            [3]
        );
        
        // Prepare inputs
        const feeds = {
            'input': inputTensor,
            'input_lengths': lengthTensor,
            'scales': scalesTensor
        };
        
        // Add speaker ID if multi-speaker model
        if (speakerId !== null && this.modelConfig.num_speakers > 1) {
            feeds['sid'] = new ort.Tensor('int64', 
                new BigInt64Array([BigInt(speakerId)]), 
                [1]
            );
        }
        
        // Run inference
        console.log('Running ONNX inference...');
        const startTime = performance.now();
        const results = await this.onnxSession.run(feeds);
        const inferenceTime = performance.now() - startTime;
        console.log(`Inference completed in ${inferenceTime.toFixed(2)}ms`);
        
        // Extract audio from output tensor
        const audioTensor = results['output'] || results[Object.keys(results)[0]];
        const audioData = new Float32Array(audioTensor.data);
        
        // Remove batch and channel dimensions if present
        let audio = audioData;
        if (audioTensor.dims.length > 1) {
            const audioLength = audioTensor.dims[audioTensor.dims.length - 1];
            audio = audioData.slice(0, audioLength);
        }
        
        return audio;
    }

    /**
     * Convert float audio to 16-bit PCM
     */
    floatTo16BitPCM(float32Array) {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            const val = Math.max(-1, Math.min(1, float32Array[i]));
            int16Array[i] = val < 0 ? val * 0x8000 : val * 0x7FFF;
        }
        return int16Array;
    }

    /**
     * Create WAV file from audio data
     */
    createWAV(audioData, sampleRate) {
        const length = audioData.length;
        const arrayBuffer = new ArrayBuffer(44 + length * 2);
        const view = new DataView(arrayBuffer);
        
        // WAV header
        const writeString = (offset, string) => {
            for (let i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        };
        
        writeString(0, 'RIFF');
        view.setUint32(4, 36 + length * 2, true);
        writeString(8, 'WAVE');
        writeString(12, 'fmt ');
        view.setUint32(16, 16, true); // fmt chunk size
        view.setUint16(20, 1, true); // PCM
        view.setUint16(22, 1, true); // Mono
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate * 2, true); // byte rate
        view.setUint16(32, 2, true); // block align
        view.setUint16(34, 16, true); // bits per sample
        writeString(36, 'data');
        view.setUint32(40, length * 2, true);
        
        // Convert to 16-bit PCM
        const pcmData = this.floatTo16BitPCM(audioData);
        const offset = 44;
        for (let i = 0; i < length; i++) {
            view.setInt16(offset + i * 2, pcmData[i], true);
        }
        
        return new Blob([arrayBuffer], { type: 'audio/wav' });
    }

    /**
     * Clean up resources
     */
    dispose() {
        if (this.openjtalkModule && this.openjtalkModule._openjtalk_clear) {
            this.openjtalkModule._openjtalk_clear();
        }
        if (this.onnxSession) {
            this.onnxSession.release();
        }
        this.initialized = false;
    }
}

// Export for use in other modules
export default OpenJTalkPiperTTS;