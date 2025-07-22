/**
 * MeCab Core WebAssembly Wrapper
 * Production version with full MeCab functionality
 */

import MeCabCoreModule from '../build/mecab_core_wasm.js';

export default class MeCabCore {
    constructor() {
        this.module = null;
        this.mecab = null;
        this.initialized = false;
    }

    /**
     * Initialize MeCab with dictionary
     * @param {string} wasmPath - Path to WASM file
     * @param {string} dictPath - Path to dictionary (optional for now)
     * @returns {Promise<boolean>}
     */
    async initialize(wasmPath = '../build/mecab_core_wasm.wasm', dictPath = '/dict') {
        try {
            // Load WebAssembly module
            this.module = await MeCabCoreModule({
                locateFile: (filename) => {
                    if (filename.endsWith('.wasm')) {
                        return wasmPath;
                    }
                    return filename;
                }
            });

            // Create MeCab instance using Embind
            this.mecab = new this.module.MeCab();
            
            // Enable debug mode
            if (this.module.setDebugMode) {
                this.module.setDebugMode(true);
            }
            
            // Initialize with dictionary path
            const success = this.mecab.initialize(dictPath);
            
            if (success) {
                this.initialized = true;
                console.log('MeCab Core initialized successfully');
                
                // Log dictionary info
                const dictInfo = this.getDictionaryInfo();
                console.log('Dictionary info:', dictInfo);
            } else {
                const lastError = this.module.getLastError ? this.module.getLastError() : 'Unknown error';
                throw new Error('MeCab initialization failed: ' + lastError);
            }
            
            return success;
        } catch (error) {
            console.error('Failed to initialize MeCab Core:', error);
            throw error;
        }
    }

    /**
     * Parse text and return detailed morphological analysis
     * @param {string} text - Input text
     * @returns {string} - Parsed result
     */
    parse(text) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        return this.mecab.parse(text);
    }

    /**
     * Tokenize text (wakati-gaki)
     * @param {string} text - Input text
     * @returns {string} - Space-separated tokens
     */
    wakati(text) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        return this.mecab.wakati(text);
    }

    /**
     * Get reading (pronunciation) of text
     * @param {string} text - Input text
     * @returns {string} - Reading in katakana
     */
    getReading(text) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        return this.mecab.getReading(text);
    }

    /**
     * Parse text and return array of token objects
     * @param {string} text - Input text
     * @returns {Array} - Array of Feature objects
     */
    parseToTokens(text) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        
        const vectorResult = this.mecab.parseToTokens(text);
        const tokens = [];
        
        // Convert Emscripten vector to JavaScript array
        for (let i = 0; i < vectorResult.size(); i++) {
            const feature = vectorResult.get(i);
            
            // Get features array
            const featuresVector = feature.getFeatures();
            const features = [];
            for (let j = 0; j < featuresVector.size(); j++) {
                features.push(featuresVector.get(j));
            }
            featuresVector.delete();
            
            tokens.push({
                surface: feature.surface,
                reading: feature.reading,
                pronunciation: feature.pronunciation,
                features: features,
                toString: () => feature.toString()
            });
        }
        
        // Clean up the vector
        vectorResult.delete();
        
        return tokens;
    }

    /**
     * Set N-best output
     * @param {number} n - Number of best results to return
     */
    setNBest(n) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        this.mecab.setNBest(n);
    }

    /**
     * Set whether to output all morphs
     * @param {boolean} all - True to output all morphs
     */
    setAllMorphs(all) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        this.mecab.setAllMorphs(all);
    }

    /**
     * Set unknown word feature
     * @param {string} feature - Feature string for unknown words
     */
    setUnkFeature(feature) {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        this.mecab.setUnkFeature(feature);
    }

    /**
     * Clean up resources
     */
    dispose() {
        if (this.mecab) {
            // Embind objects need to be explicitly deleted
            this.mecab.delete();
            this.mecab = null;
        }
        this.module = null;
        this.initialized = false;
    }

    /**
     * Get version information
     * @returns {object} Version info
     */
    getVersion() {
        if (this.module && this.module.getVersion) {
            return this.module.getVersion();
        }
        return {
            mecab: '0.996',
            wrapper: '1.0.0',
            wasm: true,
            production: true
        };
    }
    
    /**
     * Get dictionary information
     * @returns {object} Dictionary info
     */
    getDictionaryInfo() {
        if (!this.initialized) {
            throw new Error('MeCab not initialized');
        }
        return {
            entries: this.mecab.getDictionarySize(),
            hasConnectionMatrix: true,
            initialized: this.mecab.isInitialized()
        };
    }
    
    /**
     * Get memory usage information
     * @returns {object} Memory usage info
     */
    getMemoryUsage() {
        if (this.module && this.module.getMemoryUsage) {
            return this.module.getMemoryUsage();
        }
        return {
            heap8_length: 0,
            heap8_bytes: 0
        };
    }
}

// For backward compatibility with existing code
export class MeCabWrapper extends MeCabCore {
    constructor() {
        super();
        console.warn('MeCabWrapper is deprecated. Use MeCabCore instead.');
    }
}