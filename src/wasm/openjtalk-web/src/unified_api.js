/**
 * Unified Phonemizer API
 * Supports both Japanese (OpenJTalk) and English/Other languages (eSpeak-ng)
 */

import { extractPhonemesFromLabels as extractJaPhonemes } from './japanese_phoneme_extract.js';

export class UnifiedPhonemizer {
    constructor() {
        this.module = null;
        this.initialized = false;
        this.openjtalkReady = false;
        this.espeakReady = false;
    }

    /**
     * Initialize the unified phonemizer
     */
    async initialize(config) {
        try {
            console.log('Initializing Unified Phonemizer...');
            
            // Load the WebAssembly module
            const UnifiedPhonemizerModule = (await import(config.jsUrl)).default;
            
            // Adjust paths for GitHub Pages if needed
            let wasmPath = config.wasmUrl;
            if (window.location.hostname.includes('github.io')) {
                wasmPath = this.adjustPathForGitHubPages(wasmPath);
            }
            
            // Initialize the module
            this.module = await UnifiedPhonemizerModule({
                locateFile: (path) => {
                    if (path.endsWith('.wasm')) {
                        return wasmPath;
                    } else if (path.endsWith('.data')) {
                        return wasmPath.replace('.wasm', '.data');
                    }
                    return path;
                }
            });
            
            // Initialize OpenJTalk if config provided
            if (config.openjtalk) {
                await this.initializeOpenJTalk(config.openjtalk);
            }
            
            // Initialize eSpeak-ng
            await this.initializeESpeak(config.espeak);
            
            this.initialized = true;
            console.log('Unified Phonemizer initialized successfully');
            
        } catch (error) {
            console.error('Failed to initialize Unified Phonemizer:', error);
            throw error;
        }
    }

    /**
     * Initialize OpenJTalk
     */
    async initializeOpenJTalk(config) {
        console.log('Initializing OpenJTalk...');
        
        // Create directories
        this.module.FS.mkdir('/dict');
        this.module.FS.mkdir('/voice');
        
        // Load dictionary and voice files
        await this.loadOpenJTalkData(config);
        
        // Initialize OpenJTalk
        const dictPtr = this.module.allocateUTF8('/dict');
        const voicePtr = this.module.allocateUTF8('/voice/voice.htsvoice');
        
        const result = this.module._phonemizer_initialize_openjtalk(dictPtr, voicePtr);
        
        this.module._free(dictPtr);
        this.module._free(voicePtr);
        
        if (result !== 0) {
            throw new Error(`OpenJTalk initialization failed with code: ${result}`);
        }
        
        this.openjtalkReady = true;
        console.log('OpenJTalk initialized');
    }

    /**
     * Initialize eSpeak-ng
     */
    async initializeESpeak(config) {
        console.log('Initializing eSpeak-ng...');
        
        // eSpeak data is embedded in the .data file
        const result = this.module._phonemizer_initialize_espeak(null);
        
        if (result < 0) {
            throw new Error(`eSpeak-ng initialization failed with code: ${result}`);
        }
        
        this.espeakReady = true;
        console.log('eSpeak-ng initialized');
    }

    /**
     * Load OpenJTalk dictionary and voice data
     */
    async loadOpenJTalkData(config) {
        // Adjust paths for GitHub Pages
        let dictPath = config.dictPath;
        let voicePath = config.voicePath;
        
        if (window.location.hostname.includes('github.io')) {
            dictPath = this.adjustPathForGitHubPages(dictPath);
            voicePath = this.adjustPathForGitHubPages(voicePath);
        }
        
        // Load dictionary files
        const dictFiles = [
            'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
            'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
        ];
        
        const dictPromises = dictFiles.map(file => 
            fetch(`${dictPath}/${file}`).then(r => r.arrayBuffer())
        );
        const dictData = await Promise.all(dictPromises);
        
        // Write dictionary files to virtual filesystem
        dictFiles.forEach((file, i) => {
            this.module.FS.writeFile(`/dict/${file}`, new Uint8Array(dictData[i]));
        });
        
        // Load voice file
        const voiceResponse = await fetch(voicePath);
        const voiceData = await voiceResponse.arrayBuffer();
        this.module.FS.writeFile('/voice/voice.htsvoice', new Uint8Array(voiceData));
    }

    /**
     * Convert text to phonemes
     */
    async textToPhonemes(text, language = null) {
        if (!this.initialized) {
            throw new Error('Phonemizer not initialized');
        }
        
        const textPtr = this.module.allocateUTF8(text);
        const langPtr = language ? this.module.allocateUTF8(language) : 0;
        
        const resultPtr = this.module._phonemizer_text_to_phonemes(textPtr, langPtr);
        const result = this.module.UTF8ToString(resultPtr);
        
        this.module._phonemizer_free_string(resultPtr);
        this.module._free(textPtr);
        if (langPtr) this.module._free(langPtr);
        
        if (result.startsWith('ERROR:')) {
            throw new Error(result);
        }
        
        return result;
    }

    /**
     * Set the language/voice for eSpeak-ng
     */
    setLanguage(language) {
        if (!this.espeakReady) {
            console.warn('eSpeak-ng not ready');
            return;
        }
        
        const langPtr = this.module.allocateUTF8(language);
        this.module._phonemizer_set_language(langPtr);
        this.module._free(langPtr);
    }

    /**
     * Extract phonemes from OpenJTalk labels
     * Uses shared japanese_phoneme_extract module (matches Python phonemize_japanese)
     */
    extractPhonemesFromLabels(labels) {
        return extractJaPhonemes(labels);
    }

    /**
     * Extract phonemes from eSpeak IPA output
     */
    extractPhonemesFromIPA(ipaText) {
        // Simple IPA to phoneme conversion
        // This is a simplified version - real implementation would need proper IPA parsing
        const phonemes = [];
        
        // Remove stress marks and other IPA symbols
        const cleaned = ipaText.replace(/[ˈˌː]/g, '');
        
        // Split into words
        const words = cleaned.split(/\s+/);
        
        for (const word of words) {
            if (word) {
                // For now, just split into characters
                // Real implementation would parse IPA properly
                phonemes.push(...word.split(''));
            }
        }
        
        return phonemes;
    }

    /**
     * Adjust path for GitHub Pages
     */
    adjustPathForGitHubPages(path) {
        // Add logic to adjust paths for GitHub Pages deployment
        if (path.startsWith('./') || path.startsWith('../')) {
            return '../../' + path.replace(/^\.\.?\//, '');
        }
        return path;
    }

    /**
     * Cleanup
     */
    dispose() {
        if (this.module && this.module._phonemizer_terminate) {
            this.module._phonemizer_terminate();
        }
        this.initialized = false;
        this.openjtalkReady = false;
        this.espeakReady = false;
    }
}