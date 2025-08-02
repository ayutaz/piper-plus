/**
 * Simple Unified Phonemizer API
 * Uses OpenJTalk for Japanese and a simple phonemizer for English
 */

import { SimpleEnglishPhonemizer, createEnglishPhonemeMap } from './simple_english_phonemizer.js';

export class SimpleUnifiedPhonemizer {
    constructor() {
        this.openjtalkModule = null;
        this.englishPhonemizer = new SimpleEnglishPhonemizer();
        this.englishPhonemeMap = createEnglishPhonemeMap();
        this.initialized = false;
    }

    /**
     * Initialize the phonemizer
     */
    async initialize(config) {
        try {
            console.log('Initializing Simple Unified Phonemizer...');
            
            // Initialize OpenJTalk for Japanese
            if (config.openjtalk) {
                await this.initializeOpenJTalk(config.openjtalk);
            }
            
            this.initialized = true;
            console.log('Simple Unified Phonemizer initialized');
            
        } catch (error) {
            console.error('Failed to initialize:', error);
            throw error;
        }
    }

    /**
     * Initialize OpenJTalk
     */
    async initializeOpenJTalk(config) {
        console.log('Loading OpenJTalk WebAssembly...');
        
        // Import OpenJTalk module
        let jsPath = config.jsPath;
        if (window.location.hostname.includes('github.io')) {
            jsPath = this.adjustPathForGitHubPages(jsPath);
        }
        
        const OpenJTalkModule = (await import(jsPath)).default;
        
        // Adjust wasmPath for GitHub Pages
        let wasmPath = config.wasmPath;
        if (window.location.hostname.includes('github.io')) {
            wasmPath = this.adjustPathForGitHubPages(wasmPath);
        }
        
        // Fetch the WASM binary for GitHub Pages
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
        
        // Load dictionary and voice files
        await this.loadOpenJTalkData(config);
        
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
     * Load OpenJTalk data files
     */
    async loadOpenJTalkData(config) {
        // Adjust paths for GitHub Pages
        let dictPath = config.dictPath;
        let voicePath = config.voicePath;
        
        if (window.location.hostname.includes('github.io')) {
            dictPath = this.adjustPathForGitHubPages(dictPath);
            voicePath = this.adjustPathForGitHubPages(voicePath);
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
    }

    /**
     * Convert text to phonemes
     */
    async textToPhonemes(text, language = null) {
        if (!this.initialized) {
            throw new Error('Phonemizer not initialized');
        }
        
        // Auto-detect language if not specified
        if (!language) {
            language = this.detectLanguage(text);
        }
        
        if (language === 'ja') {
            // Use OpenJTalk for Japanese
            return this.textToPhonemesJapanese(text);
        } else {
            // Use simple phonemizer for English
            return this.textToPhonemesEnglish(text);
        }
    }

    /**
     * Japanese text to phonemes using OpenJTalk
     */
    async textToPhonemesJapanese(text) {
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
     * English text to phonemes using simple phonemizer
     */
    async textToPhonemesEnglish(text) {
        const phonemes = this.englishPhonemizer.textToPhonemes(text);
        const ipaString = this.englishPhonemizer.phonemesToIPA(phonemes);
        return ipaString;
    }

    /**
     * Extract phonemes from OpenJTalk labels
     */
    extractPhonemes(labels, language = 'ja') {
        if (language === 'ja') {
            return this.extractPhonemesFromLabels(labels);
        } else {
            return this.extractPhonemesFromIPA(labels);
        }
    }

    /**
     * Extract phonemes from OpenJTalk labels
     */
    extractPhonemesFromLabels(labels) {
        const lines = labels.split('\n').filter(line => line.trim());
        const phonemes = [];
        
        // Multi-character phoneme to Unicode mapping
        const multiCharPhonemes = {
            'br': '\ue000',
            'ch': '\ue001',
            'cl': '\ue002',
            'dy': '\ue003',
            'gy': '\ue004',
            'hy': '\ue005',
            'ky': '\ue006',
            'my': '\ue007',
            'ny': '\ue008',
            'py': '\ue009',
            'ry': '\ue00a',
            'sh': '\ue00b',
            'ts': '\ue00c',
            'ty': '\ue00d'
        };
        
        phonemes.push('^');
        
        for (const line of lines) {
            const match = line.match(/\-([^+]+)\+/);
            if (match && match[1] !== 'sil') {
                let phoneme = match[1];
                
                // Debug log for multi-character phonemes
                if (multiCharPhonemes[phoneme]) {
                    console.log(`Converting multi-char phoneme: ${phoneme} → U+${multiCharPhonemes[phoneme].charCodeAt(0).toString(16)}`);
                    phoneme = multiCharPhonemes[phoneme];
                }
                
                // Skip 'pau' (pause) - it should not be included in phonemes
                if (phoneme !== 'pau') {
                    phonemes.push(phoneme);
                } else {
                    console.log('Skipping pau');
                }
            }
        }
        
        phonemes.push('$');
        
        console.log('Extracted phonemes:', phonemes.map(p => {
            const code = p.charCodeAt(0);
            if (code >= 0xe000 && code <= 0xe00d) {
                return `${p}(U+${code.toString(16)})`;
            }
            return p;
        }).join(' '));
        
        return phonemes;
    }

    /**
     * Extract phonemes from IPA text
     */
    extractPhonemesFromIPA(ipaData) {
        const phonemes = [];
        
        // Add BOS marker
        phonemes.push('^');
        
        // Handle both array and string input
        if (Array.isArray(ipaData)) {
            // Already an array of phonemes
            phonemes.push(...ipaData);
        } else if (typeof ipaData === 'string') {
            // Split IPA text into individual phonemes
            let i = 0;
            while (i < ipaData.length) {
                const char = ipaData[i];
                
                // Check for two-character phonemes
                if (i + 1 < ipaData.length) {
                    const twoChar = ipaData.substr(i, 2);
                    if (this.englishPhonemeMap[twoChar]) {
                        phonemes.push(twoChar);
                        i += 2;
                        continue;
                    }
                }
                
                // Single character or space
                if (char === ' ') {
                    phonemes.push(' ');
                } else if (this.englishPhonemeMap[char]) {
                    phonemes.push(char);
                }
                i++;
            }
        }
        
        // Add EOS marker
        phonemes.push('$');
        
        return phonemes;
    }

    /**
     * Get phoneme ID map for the specified language
     */
    getPhonemeIdMap(language) {
        if (language === 'en') {
            return this.englishPhonemeMap;
        }
        // For Japanese, the map should come from the model config
        return null;
    }

    /**
     * Detect language from text
     */
    detectLanguage(text) {
        // Simple detection based on character ranges
        for (const char of text) {
            const code = char.charCodeAt(0);
            // Check for Japanese characters
            if ((code >= 0x3040 && code <= 0x309F) || // Hiragana
                (code >= 0x30A0 && code <= 0x30FF) || // Katakana
                (code >= 0x4E00 && code <= 0x9FAF)) { // Kanji
                return 'ja';
            }
        }
        return 'en';
    }

    /**
     * Adjust path for GitHub Pages
     */
    adjustPathForGitHubPages(path) {
        if (path.startsWith('./') || path.startsWith('../')) {
            // Navigate up two levels for GitHub Pages structure
            return '../../' + path.replace(/^\.\.?\//, '');
        }
        return path;
    }

    /**
     * Cleanup
     */
    dispose() {
        if (this.openjtalkModule && this.openjtalkModule._openjtalk_clear) {
            this.openjtalkModule._openjtalk_clear();
        }
        this.initialized = false;
    }
}