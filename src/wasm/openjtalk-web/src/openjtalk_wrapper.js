/**
 * OpenJTalk WebAssembly Wrapper
 */

export class OpenJTalkWrapper {
    constructor() {
        this.module = null;
        this.initialized = false;
    }
    
    /**
     * Initialize OpenJTalk WebAssembly module
     * @param {string} modulePath - Path to openjtalk.js
     */
    async initialize(modulePath = '../dist/openjtalk.js') {
        try {
            const OpenJTalkModule = (await import(modulePath)).default;
            
            this.module = await OpenJTalkModule({
                onRuntimeInitialized: () => {
                    console.log('OpenJTalk runtime initialized');
                }
            });
            
            // Wait for module to be fully initialized
            if (!this.module._openjtalk_initialize) {
                throw new Error('OpenJTalk functions not found in module');
            }
            
            // Initialize OpenJTalk
            const result = this.module._openjtalk_initialize();
            if (result !== 0) {
                throw new Error(`OpenJTalk initialization failed with code: ${result}`);
            }
            
            this.initialized = true;
            console.log('OpenJTalkWrapper initialized successfully');
            
        } catch (error) {
            console.error('Failed to initialize OpenJTalk:', error);
            throw error;
        }
    }
    
    /**
     * Convert text to phonemes
     * @param {string} text - Japanese text
     * @returns {Promise<Object>} Phoneme data with labels and durations
     */
    async textToPhonemes(text) {
        if (!this.initialized) {
            throw new Error('OpenJTalk not initialized');
        }
        
        try {
            // Allocate memory for input text
            const encoder = new TextEncoder();
            const textData = encoder.encode(text);
            const textPtr = this.module._malloc(textData.length + 1);
            this.module.HEAPU8.set(textData, textPtr);
            this.module.HEAPU8[textPtr + textData.length] = 0;
            
            // Call text_to_phonemes
            const resultPtr = this.module._text_to_phonemes(textPtr);
            
            // Free input memory
            this.module._free(textPtr);
            
            if (!resultPtr) {
                throw new Error('Failed to convert text to phonemes');
            }
            
            // Parse result
            const resultStr = this.module.UTF8ToString(resultPtr);
            const result = JSON.parse(resultStr);
            
            // Free result memory
            this.module._free_result(resultPtr);
            
            return result;
            
        } catch (error) {
            console.error('Error in textToPhonemes:', error);
            throw error;
        }
    }
    
    /**
     * Synthesize speech from text
     * @param {string} text - Japanese text
     * @param {string} voiceFile - Voice file name (optional)
     * @returns {Promise<Float32Array>} Audio data
     */
    async synthesize(text, voiceFile = 'mei_normal.htsvoice') {
        if (!this.initialized) {
            throw new Error('OpenJTalk not initialized');
        }
        
        try {
            // Allocate memory for input text
            const encoder = new TextEncoder();
            const textData = encoder.encode(text);
            const textPtr = this.module._malloc(textData.length + 1);
            this.module.HEAPU8.set(textData, textPtr);
            this.module.HEAPU8[textPtr + textData.length] = 0;
            
            // Allocate memory for voice file name
            const voiceData = encoder.encode(voiceFile);
            const voicePtr = this.module._malloc(voiceData.length + 1);
            this.module.HEAPU8.set(voiceData, voicePtr);
            this.module.HEAPU8[voicePtr + voiceData.length] = 0;
            
            // Synthesize
            const audioLengthPtr = this.module._malloc(4);
            const audioPtr = this.module._synthesize(textPtr, voicePtr, audioLengthPtr);
            
            // Free input memory
            this.module._free(textPtr);
            this.module._free(voicePtr);
            
            if (!audioPtr) {
                this.module._free(audioLengthPtr);
                throw new Error('Failed to synthesize audio');
            }
            
            // Get audio length and data
            const audioLength = this.module.HEAP32[audioLengthPtr >> 2];
            const audioData = new Float32Array(audioLength);
            
            for (let i = 0; i < audioLength; i++) {
                audioData[i] = this.module.HEAPF32[(audioPtr >> 2) + i];
            }
            
            // Free memory
            this.module._free(audioPtr);
            this.module._free(audioLengthPtr);
            
            return audioData;
            
        } catch (error) {
            console.error('Error in synthesize:', error);
            throw error;
        }
    }
}