/**
 * OpenJTalk WebAssembly Wrapper
 * Provides Japanese text-to-phoneme conversion
 */

import OpenJTalkModule from './openjtalk_wasm.js';

export class OpenJTalkWrapper {
    constructor() {
        this.module = null;
        this.openjtalk = null;
        this.initialized = false;
    }

    /**
     * Initialize OpenJTalk
     * @param {Object} options - Configuration options
     * @returns {Promise<void>}
     */
    async initialize(options = {}) {
        try {
            // Load WebAssembly module
            this.module = await OpenJTalkModule({
                locateFile: (path) => {
                    if (path.endsWith('.wasm')) {
                        return options.wasmPath || './openjtalk_wasm.wasm';
                    }
                    return path;
                }
            });

            // Create OpenJTalk instance
            this.openjtalk = new this.module.OpenJTalk();
            
            // Initialize
            const success = this.openjtalk.initialize();
            
            if (!success) {
                throw new Error('Failed to initialize OpenJTalk');
            }

            // Set debug mode if requested
            if (options.debug) {
                this.module.setDebugMode(true);
            }

            this.initialized = true;
            console.log('OpenJTalk initialized successfully');
        } catch (error) {
            console.error('OpenJTalk initialization error:', error);
            throw error;
        }
    }

    /**
     * Process MeCab output to phonemes
     * @param {string} mecabOutput - MeCab analysis result
     * @returns {string} Space-separated phoneme sequence
     */
    processText(mecabOutput) {
        if (!this.initialized) {
            throw new Error('OpenJTalk not initialized. Call initialize() first.');
        }

        try {
            return this.openjtalk.processText(mecabOutput);
        } catch (error) {
            console.error('OpenJTalk processText error:', error);
            throw error;
        }
    }

    /**
     * Process to PUA encoded string
     * @param {string} mecabOutput - MeCab analysis result
     * @returns {string} PUA encoded phoneme string
     */
    processToPUA(mecabOutput) {
        if (!this.initialized) {
            throw new Error('OpenJTalk not initialized. Call initialize() first.');
        }

        try {
            return this.openjtalk.processToPUA(mecabOutput);
        } catch (error) {
            console.error('OpenJTalk processToPUA error:', error);
            throw error;
        }
    }

    /**
     * Get NJD nodes for debugging
     * @param {string} mecabOutput - MeCab analysis result
     * @returns {Array} Array of NJD nodes
     */
    getNJDNodes(mecabOutput) {
        if (!this.initialized) {
            throw new Error('OpenJTalk not initialized. Call initialize() first.');
        }

        try {
            const nodes = this.openjtalk.getNJDNodes(mecabOutput);
            // Convert from Emscripten vector to JS array
            const result = [];
            for (let i = 0; i < nodes.size(); i++) {
                const node = nodes.get(i);
                result.push({
                    string: node.string,
                    pos: node.pos,
                    pos_group1: node.pos_group1,
                    pos_group2: node.pos_group2,
                    pos_group3: node.pos_group3,
                    read: node.read,
                    pron: node.pron,
                    acc: node.acc,
                    mora_size: node.mora_size
                });
            }
            return result;
        } catch (error) {
            console.error('OpenJTalk getNJDNodes error:', error);
            throw error;
        }
    }

    /**
     * Check if OpenJTalk is initialized
     * @returns {boolean}
     */
    isInitialized() {
        return this.initialized && this.openjtalk && this.openjtalk.isInitialized();
    }

    /**
     * Enable/disable debug mode
     * @param {boolean} enabled
     */
    setDebugMode(enabled) {
        if (this.module) {
            this.module.setDebugMode(enabled);
        }
    }

    /**
     * Cleanup resources
     */
    dispose() {
        if (this.openjtalk) {
            // C++ object will be garbage collected
            this.openjtalk = null;
        }
        this.module = null;
        this.initialized = false;
    }
}

// Helper class for complete TTS pipeline
export class JapaneseTTSPipeline {
    constructor() {
        this.mecab = null;
        this.openjtalk = null;
    }

    /**
     * Initialize both MeCab and OpenJTalk
     * @param {Object} options
     */
    async initialize(options = {}) {
        // Dynamic import to avoid circular dependencies
        const { MeCabWrapper } = await import('../../mecab/dist/mecab-wrapper.js');
        
        // Initialize MeCab
        this.mecab = new MeCabWrapper();
        await this.mecab.initialize({
            wasmPath: options.mecabWasmPath || '../../mecab/dist/mecab_wasm.wasm',
            dataPath: options.mecabDataPath || '../../mecab/dist/mecab_wasm.data'
        });

        // Initialize OpenJTalk
        this.openjtalk = new OpenJTalkWrapper();
        await this.openjtalk.initialize({
            wasmPath: options.openjtalkWasmPath || './openjtalk_wasm.wasm',
            debug: options.debug
        });
    }

    /**
     * Convert text to phonemes
     * @param {string} text - Japanese text
     * @returns {Object} Result with phonemes and debug info
     */
    async textToPhonemes(text) {
        // Step 1: Morphological analysis with MeCab
        const mecabOutput = this.mecab.parse(text);
        
        // Step 2: Convert to phonemes with OpenJTalk
        const phonemes = this.openjtalk.processText(mecabOutput);
        const puaEncoded = this.openjtalk.processToPUA(mecabOutput);
        const njdNodes = this.openjtalk.getNJDNodes(mecabOutput);

        return {
            text: text,
            mecabOutput: mecabOutput,
            phonemes: phonemes,
            puaEncoded: puaEncoded,
            njdNodes: njdNodes
        };
    }

    /**
     * Simple text to phoneme conversion
     * @param {string} text
     * @returns {string} Space-separated phonemes
     */
    async convertToPhonemes(text) {
        const mecabOutput = this.mecab.parse(text);
        return this.openjtalk.processText(mecabOutput);
    }

    /**
     * Cleanup
     */
    dispose() {
        if (this.mecab) {
            this.mecab.dispose();
        }
        if (this.openjtalk) {
            this.openjtalk.dispose();
        }
    }
}

export default OpenJTalkWrapper;