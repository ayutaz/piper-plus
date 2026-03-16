/**
 * OpenJTalk-Piper Integration with Lazy Loading
 * ONNXモデルを必要になるまで読み込まない実装
 */

class OpenJTalkPiperTTSLazy {
    constructor() {
        this.openjtalkModule = null;
        this.onnxSession = null;
        this.phonemeIdMap = null;
        this.modelConfig = null;
        this.initialized = false;
        this.openjtalkReady = false;
        this.onnxReady = false;
        this.onnxLoadPromise = null;
    }

    /**
     * Initialize only OpenJTalk (fast initialization)
     */
    async initialize(config) {
        try {
            console.log('Initializing OpenJTalk-piper-plus (Lazy Loading)...');
            
            // Store config for later use
            this.config = config;
            
            // Initialize only OpenJTalk first
            await this.initializeOpenJTalk(config.openjtalk);
            
            // Load only model config (small file)
            await this.loadModelConfig(config.onnx);
            
            this.initialized = true;
            console.log('OpenJTalk initialized. ONNX model will be loaded on first use.');
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
        let jsPath = config.jsPath;
        if (window.location.hostname.includes('github.io')) {
            if (jsPath === 'dist/openjtalk.js' || 
                jsPath === './dist/openjtalk.js' || 
                jsPath === '../dist/openjtalk.js' ||
                jsPath.endsWith('/dist/openjtalk.js')) {
                jsPath = '../../dist/openjtalk.js';
            }
        }
        
        const OpenJTalkModule = (await import(jsPath)).default;
        
        // Adjust wasmPath for GitHub Pages
        let wasmPath = config.wasmPath;
        if (window.location.hostname.includes('github.io')) {
            if (wasmPath === 'dist/openjtalk.wasm' || 
                wasmPath === './dist/openjtalk.wasm' || 
                wasmPath === '../dist/openjtalk.wasm' ||
                wasmPath.endsWith('/dist/openjtalk.wasm')) {
                wasmPath = '../../dist/openjtalk.wasm';
            }
        }
        
        // Fetch the WASM binary directly for GitHub Pages
        let wasmBinary = null;
        if (window.location.hostname.includes('github.io')) {
            const absoluteWasmPath = new URL(wasmPath, import.meta.url).href;
            const wasmResponse = await fetch(absoluteWasmPath);
            wasmBinary = await wasmResponse.arrayBuffer();
        }
        
        this.openjtalkModule = await OpenJTalkModule({
            locateFile: (path) => {
                if (path.endsWith('.wasm')) {
                    return wasmPath;
                }
                return path;
            },
            wasmBinary: wasmBinary
        });
        
        // Create directories
        this.openjtalkModule.FS.mkdir('/dict');
        this.openjtalkModule.FS.mkdir('/voice');
        
        // Adjust paths for GitHub Pages
        let dictPath = config.dictPath;
        let voicePath = config.voicePath;
        if (window.location.hostname.includes('github.io')) {
            if (dictPath === 'assets/dict' || 
                dictPath === './assets/dict' || 
                dictPath === '../assets/dict' ||
                dictPath.endsWith('/assets/dict')) {
                dictPath = '../../assets/dict';
            }
            if (voicePath === 'assets/voice/mei_normal.htsvoice' || 
                voicePath === './assets/voice/mei_normal.htsvoice' || 
                voicePath === '../assets/voice/mei_normal.htsvoice' ||
                voicePath.endsWith('/assets/voice/mei_normal.htsvoice')) {
                voicePath = '../../assets/voice/mei_normal.htsvoice';
            }
        }
        
        // Convert to absolute URLs
        const absoluteDictPath = new URL(dictPath, import.meta.url).href;
        const absoluteVoicePath = new URL(voicePath, import.meta.url).href;
        
        // Load dictionary files
        const dictFiles = [
            'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
            'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
        ];
        
        const dictPromises = dictFiles.map(file => 
            fetch(`${absoluteDictPath}/${file}`).then(r => r.arrayBuffer())
        );
        const dictData = await Promise.all(dictPromises);
        
        dictFiles.forEach((file, i) => {
            this.openjtalkModule.FS.writeFile(`/dict/${file}`, new Uint8Array(dictData[i]));
        });
        
        // Load voice file
        const voiceResponse = await fetch(absoluteVoicePath);
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
        
        this.openjtalkReady = true;
        console.log('OpenJTalk initialized');
    }

    /**
     * Load only model configuration (small file)
     */
    async loadModelConfig(config) {
        let modelConfigPath = config.modelConfigPath;
        if (window.location.hostname.includes('github.io')) {
            if (modelConfigPath === 'models/ja_JP-test-medium.onnx.json' || 
                modelConfigPath === './models/ja_JP-test-medium.onnx.json' || 
                modelConfigPath === '../models/ja_JP-test-medium.onnx.json' ||
                modelConfigPath.endsWith('/models/ja_JP-test-medium.onnx.json')) {
                modelConfigPath = '../../models/ja_JP-test-medium.onnx.json';
            }
        }
        
        const absoluteModelConfigPath = new URL(modelConfigPath, import.meta.url).href;
        const configResponse = await fetch(absoluteModelConfigPath);
        this.modelConfig = await configResponse.json();
        this.phonemeIdMap = this.modelConfig.phoneme_id_map;
        console.log('Model config loaded (ONNX model will be loaded on demand)');
    }

    /**
     * Lazy load ONNX model when needed
     */
    async ensureONNXLoaded() {
        if (this.onnxReady) {
            return;
        }
        
        if (!this.onnxLoadPromise) {
            console.log('First synthesis request - loading ONNX model...');
            this.onnxLoadPromise = this.loadONNXModel();
        }
        
        await this.onnxLoadPromise;
    }

    /**
     * Load ONNX model
     */
    async loadONNXModel() {
        const startTime = performance.now();
        
        let modelPath = this.config.onnx.modelPath;
        if (window.location.hostname.includes('github.io')) {
            if (modelPath === 'models/ja_JP-test-medium.onnx' || 
                modelPath === './models/ja_JP-test-medium.onnx' || 
                modelPath === '../models/ja_JP-test-medium.onnx' ||
                modelPath.endsWith('/models/ja_JP-test-medium.onnx')) {
                modelPath = '../../models/ja_JP-test-medium.onnx';
            }
        }
        
        const absoluteModelPath = new URL(modelPath, import.meta.url).href;
        console.log('Loading ONNX model from:', absoluteModelPath);
        
        // Create ONNX session
        this.onnxSession = await ort.InferenceSession.create(absoluteModelPath, {
            executionProviders: ['wasm'],
            graphOptimizationLevel: 'extended',
            enableMemPattern: true
        });
        
        const loadTime = performance.now() - startTime;
        console.log(`ONNX model loaded in ${loadTime.toFixed(2)}ms`);
        
        // Warm up with minimal inference
        await this.warmUpModel();
        
        this.onnxReady = true;
    }

    /**
     * Warm up the model
     */
    async warmUpModel() {
        const warmUpPhonemes = [1, 7, 2]; // "^a$"
        await this.synthesizeAudio(warmUpPhonemes);
        console.log('Model warmed up');
    }

    /**
     * Convert text to speech
     */
    async textToSpeech(text, speakerId = null) {
        if (!this.initialized) {
            throw new Error('TTS not initialized');
        }
        
        console.log('Converting text to speech:', text);
        
        // Ensure ONNX is loaded before synthesis
        await this.ensureONNXLoaded();
        
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

    // ... (rest of the methods same as original)
    
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
     * Extract phonemes from OpenJTalk labels.
     * Matches Python phonemize_japanese() with Kurihara markers, N variants, PUA mapping.
     */
    extractPhonemes(labels) {
        const RE_PHONEME = /-([^+]+)\+/;
        const RE_A1 = /\/A:([\d-]+)\+/;
        const RE_A2 = /\+([0-9]+)\+/;
        const RE_A3 = /\+([0-9]+)\//;
        const SKIP_TOKENS = new Set(['_', '#', '[', ']', '^', '$', '?', '?!', '?.', '?~']);
        const PUA_MAP = {
            'a:': '\ue000', 'i:': '\ue001', 'u:': '\ue002', 'e:': '\ue003', 'o:': '\ue004',
            'cl': '\ue005',
            'ky': '\ue006', 'kw': '\ue007', 'gy': '\ue008', 'gw': '\ue009',
            'ty': '\ue00a', 'dy': '\ue00b', 'py': '\ue00c', 'by': '\ue00d',
            'ch': '\ue00e', 'ts': '\ue00f', 'sh': '\ue010', 'zy': '\ue011', 'hy': '\ue012',
            'ny': '\ue013', 'my': '\ue014', 'ry': '\ue015',
            'N_m': '\ue019', 'N_n': '\ue01a', 'N_ng': '\ue01b', 'N_uvular': '\ue01c'
        };

        const lines = labels.split('\n').filter(line => line.trim());
        const tokens = [];

        for (let idx = 0; idx < lines.length; idx++) {
            const line = lines[idx];
            const mPh = line.match(RE_PHONEME);
            if (!mPh) continue;
            const phoneme = mPh[1];

            if (phoneme === 'sil') {
                if (idx === 0) tokens.push('^');
                else if (idx === lines.length - 1) tokens.push('$');
                continue;
            }
            if (phoneme === 'pau') { tokens.push('_'); continue; }

            tokens.push(phoneme);

            const mA1 = line.match(RE_A1);
            const mA2 = line.match(RE_A2);
            const mA3 = line.match(RE_A3);
            if (!(mA1 && mA2 && mA3)) continue;

            const a1 = parseInt(mA1[1], 10);
            const a2 = parseInt(mA2[1], 10);
            const a3 = parseInt(mA3[1], 10);

            let a2Next = -1;
            if (idx < lines.length - 1) {
                const m = lines[idx + 1].match(RE_A2);
                if (m) a2Next = parseInt(m[1], 10);
            }

            if (a1 === 0 && a2Next === a2 + 1) tokens.push(']');
            if (a2 === a3 && a2Next === 1) tokens.push('#');
            if (a2 === 1 && a2Next === 2) tokens.push('[');
        }

        // Apply N phoneme rules
        const result = [];
        for (let i = 0; i < tokens.length; i++) {
            if (tokens[i] !== 'N') { result.push(tokens[i]); continue; }
            let next = null;
            for (let j = i + 1; j < tokens.length; j++) {
                if (!SKIP_TOKENS.has(tokens[j])) { next = tokens[j]; break; }
            }
            if (next === null) result.push('N_uvular');
            else if (['m', 'my', 'b', 'by', 'p', 'py'].includes(next)) result.push('N_m');
            else if (['n', 'ny', 't', 'ty', 'd', 'dy', 'ts', 'ch'].includes(next)) result.push('N_n');
            else if (['k', 'ky', 'kw', 'g', 'gy', 'gw'].includes(next)) result.push('N_ng');
            else result.push('N_uvular');
        }

        // Map to PUA
        return result.map(t => PUA_MAP[t] || t);
    }

    phonemesToIds(phonemes) {
        const ids = [];

        for (const phoneme of phonemes) {
            if (this.phonemeIdMap[phoneme]) {
                ids.push(...this.phonemeIdMap[phoneme]);
            } else {
                console.warn(`Unknown phoneme: ${phoneme}`);
                ids.push(0);
            }
        }

        return ids;
    }

    async synthesizeAudio(phonemeIds, speakerId = null) {
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
        
        const feeds = {
            'input': inputTensor,
            'input_lengths': lengthTensor,
            'scales': scalesTensor
        };
        
        if (speakerId !== null && this.modelConfig.num_speakers > 1) {
            feeds['sid'] = new ort.Tensor('int64', 
                new BigInt64Array([BigInt(speakerId)]), 
                [1]
            );
        }
        
        const startTime = performance.now();
        const results = await this.onnxSession.run(feeds);
        const inferenceTime = performance.now() - startTime;
        console.log(`Inference completed in ${inferenceTime.toFixed(2)}ms`);
        
        const audioTensor = results['output'] || results[Object.keys(results)[0]];
        const audioData = new Float32Array(audioTensor.data);
        
        let audio = audioData;
        if (audioTensor.dims.length > 1) {
            const audioLength = audioTensor.dims[audioTensor.dims.length - 1];
            audio = audioData.slice(0, audioLength);
        }
        
        return audio;
    }

    floatTo16BitPCM(float32Array) {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            const val = Math.max(-1, Math.min(1, float32Array[i]));
            int16Array[i] = val < 0 ? val * 0x8000 : val * 0x7FFF;
        }
        return int16Array;
    }

    createWAV(audioData, sampleRate) {
        const length = audioData.length;
        const arrayBuffer = new ArrayBuffer(44 + length * 2);
        const view = new DataView(arrayBuffer);
        
        const writeString = (offset, string) => {
            for (let i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        };
        
        writeString(0, 'RIFF');
        view.setUint32(4, 36 + length * 2, true);
        writeString(8, 'WAVE');
        writeString(12, 'fmt ');
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        writeString(36, 'data');
        view.setUint32(40, length * 2, true);
        
        const pcmData = this.floatTo16BitPCM(audioData);
        const offset = 44;
        for (let i = 0; i < length; i++) {
            view.setInt16(offset + i * 2, pcmData[i], true);
        }
        
        return new Blob([arrayBuffer], { type: 'audio/wav' });
    }

    dispose() {
        if (this.openjtalkModule && this.openjtalkModule._openjtalk_clear) {
            this.openjtalkModule._openjtalk_clear();
        }
        if (this.onnxSession) {
            this.onnxSession.release();
        }
        this.initialized = false;
        this.openjtalkReady = false;
        this.onnxReady = false;
    }
}

export default OpenJTalkPiperTTSLazy;