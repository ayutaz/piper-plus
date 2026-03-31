/**
 * Simple Unified Phonemizer API
 * Uses OpenJTalk for Japanese, a simple phonemizer for English,
 * and character-based fallbacks for zh/es/fr/pt/sv.
 */

import { SimpleEnglishPhonemizer, createEnglishPhonemeMap } from './simple_english_phonemizer.js';
import { extractPhonemesFromLabels as extractJaPhonemes } from './japanese_phoneme_extract.js';

// Swedish-specific characters not used by EN/ES/PT/FR.
// ä (U+00E4), ö (U+00F6), å (U+00E5) and uppercase variants.
const SWEDISH_CHARS = new Set([
    '\u00E4', '\u00F6', '\u00C4', '\u00D6', '\u00E5', '\u00C5',
]);

// Swedish function words for word-level disambiguation.
// These are highly distinctive and do not appear in EN/ES/PT/FR.
const SWEDISH_FUNCTION_WORDS = new Set([
    'och', 'att', 'jag', 'det', 'den', 'inte', 'som', 'han', 'hon',
    'var', 'har', 'kan', 'ska', 'med', 'för', 'sig', 'sin', 'min',
    'din', 'vill', 'från', 'när', 'här', 'där', 'också', 'alla',
    'denna', 'efter', 'eller', 'under', 'utan', 'mycket', 'mellan',
    'genom', 'bara', 'sedan', 'redan', 'aldrig', 'alltid', 'igen',
    'något', 'några', 'varje', 'vilken', 'vilket',
]);

export class SimpleUnifiedPhonemizer {
    constructor(options = {}) {
        this.openjtalkModule = null;
        this.englishPhonemizer = new SimpleEnglishPhonemizer();
        this.englishPhonemeMap = createEnglishPhonemeMap();
        this.initialized = false;
        // phoneme_id_map from model config (set via setPhonemeIdMap or initialize)
        this.phonemeIdMap = options.phonemeIdMap || null;
        // GitHub Pages deployment configuration
        this.deploymentConfig = options.deploymentConfig || {
            isGitHubPages: false,
            basePath: ''
        };
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

        // Import OpenJTalk module -- resolve jsPath relative to this package
        let jsPath = config.jsPath;
        if (!jsPath) {
            // Auto-resolve from package: dist/openjtalk.js is a sibling of src/
            jsPath = new URL('../dist/openjtalk.js', import.meta.url).href;
        } else if (this.deploymentConfig.isGitHubPages && this.deploymentConfig.basePath) {
            jsPath = this.adjustPathForDeployment(jsPath);
        }

        const OpenJTalkModule = (await import(jsPath)).default;

        // Resolve wasmPath
        let wasmPath = config.wasmPath;
        if (!wasmPath) {
            wasmPath = new URL('../dist/openjtalk.wasm', import.meta.url).href;
        } else if (typeof window !== 'undefined' && window.location.hostname.includes('github.io')) {
            const pathParts = window.location.pathname.split('/').filter(p => p);
            const repoName = pathParts.length > 0 ? pathParts[0] : '';
            const basePath = repoName ? `/${repoName}` : '';
            if (wasmPath.startsWith('./') || wasmPath.startsWith('../')) {
                wasmPath = basePath + '/dist/openjtalk.wasm';
            }
        }

        // Fetch the WASM binary if needed (GitHub Pages or absolute URL)
        let wasmBinary = null;
        if (typeof window !== 'undefined' && window.location.hostname.includes('github.io')) {
            const absoluteWasmPath = new URL(wasmPath, window.location.origin).href;
            const wasmResponse = await fetch(absoluteWasmPath);
            if (!wasmResponse.ok) {
                throw new Error(`Failed to load WASM: ${wasmResponse.status} ${wasmResponse.statusText}`);
            }
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
     * Load OpenJTalk data files.
     *
     * Accepts either pre-loaded ArrayBuffer data (from DictManager) or
     * URL paths (for standalone demo usage).
     */
    async loadOpenJTalkData(config) {
        const dictFileNames = [
            'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
            'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
        ];

        // ---- Pre-loaded data path (from DictManager.loadDictionary()) ----
        if (config.dictData && config.voiceData) {
            // Validate all required files are present
            const missing = dictFileNames.filter(f => !(config.dictData[f] instanceof ArrayBuffer));
            if (missing.length > 0) {
                throw new Error(
                    `Missing required dictionary files: ${missing.join(', ')}. ` +
                    'All 8 OpenJTalk dictionary files must be provided.'
                );
            }
            if (!(config.voiceData instanceof ArrayBuffer)) {
                throw new Error('voiceData must be an ArrayBuffer.');
            }

            for (const file of dictFileNames) {
                this.openjtalkModule.FS.writeFile(`/dict/${file}`, new Uint8Array(config.dictData[file]));
            }
            this.openjtalkModule.FS.writeFile(
                '/voice/voice.htsvoice',
                new Uint8Array(config.voiceData)
            );
            return;
        }

        // ---- URL-based path (for standalone demos) ----
        let dictPath = config.dictPath;
        let voicePath = config.voicePath;

        if (typeof window !== 'undefined' && window.location.hostname.includes('github.io')) {
            const pathParts = window.location.pathname.split('/').filter(p => p);
            const repoName = pathParts.length > 0 ? pathParts[0] : '';
            const basePath = repoName ? `/${repoName}` : '';

            if (dictPath.startsWith('./') || dictPath.startsWith('../')) {
                dictPath = basePath + '/assets/dict';
            }
            if (voicePath.startsWith('./') || voicePath.startsWith('../')) {
                voicePath = basePath + '/assets/voice/mei_normal.htsvoice';
            }
        }

        const absoluteDictPath = new URL(dictPath, window.location.origin).href;
        const absoluteVoicePath = new URL(voicePath, window.location.origin).href;

        const dictPromises = dictFileNames.map(file =>
            fetch(`${absoluteDictPath}/${file}`).then(r => r.arrayBuffer())
        );
        const dictData = await Promise.all(dictPromises);

        dictFileNames.forEach((file, i) => {
            this.openjtalkModule.FS.writeFile(`/dict/${file}`, new Uint8Array(dictData[i]));
        });

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
        } else if (language === 'en') {
            // Use simple phonemizer for English
            return this.textToPhonemesEnglish(text);
        } else if (language === 'zh') {
            // Chinese: character-based phoneme_id_map fallback
            return this.phonemizeChinese(text);
        } else {
            // es/fr/pt/sv: Latin-script character-based fallback
            return this.phonemizeLatinFallback(text);
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
     * Chinese text to phoneme IDs using character-based phoneme_id_map fallback.
     * Since proper pinyin conversion requires a large dictionary, this maps
     * each character directly through the model's phoneme_id_map.
     * Returns an array of phoneme IDs (integers).
     */
    phonemizeChinese(text) {
        const phonemeIdMap = this.phonemeIdMap;
        if (!phonemeIdMap) {
            throw new Error('phonemeIdMap is required for Chinese phonemization. Call setPhonemeIdMap() first.');
        }
        const phonemeIds = [1]; // BOS
        for (const char of text) {
            if (phonemeIdMap[char]) {
                phonemeIds.push(...phonemeIdMap[char]);
                phonemeIds.push(0); // PAD
            }
        }
        phonemeIds.push(2); // EOS
        return phonemeIds;
    }

    /**
     * Latin-script language (es/fr/pt) text to phoneme IDs using character-based
     * phoneme_id_map fallback. Lowercases the text and maps each character
     * through the model's phoneme_id_map.
     * Returns an array of phoneme IDs (integers).
     */
    phonemizeLatinFallback(text) {
        const phonemeIdMap = this.phonemeIdMap;
        if (!phonemeIdMap) {
            throw new Error('phonemeIdMap is required for Latin fallback phonemization. Call setPhonemeIdMap() first.');
        }
        const phonemeIds = [1]; // BOS
        for (const char of text.toLowerCase()) {
            if (phonemeIdMap[char]) {
                phonemeIds.push(...phonemeIdMap[char]);
                phonemeIds.push(0); // PAD
            } else if (char === ' ') {
                // Use space mapping if available
                if (phonemeIdMap[' ']) {
                    phonemeIds.push(...phonemeIdMap[' ']);
                    phonemeIds.push(0); // PAD
                }
            }
            // Unknown characters are skipped
        }
        phonemeIds.push(2); // EOS
        return phonemeIds;
    }

    /**
     * Set the phoneme_id_map from model config.
     * Required for zh/es/fr/pt/sv fallback phonemization.
     * @param {Object} phonemeIdMap - mapping from character/phoneme string to array of IDs
     */
    setPhonemeIdMap(phonemeIdMap) {
        this.phonemeIdMap = phonemeIdMap;
    }

    /**
     * Extract phonemes from OpenJTalk labels
     */
    extractPhonemes(labels, language = 'ja') {
        if (language === 'ja') {
            return this.extractPhonemesFromLabels(labels);
        } else if (language === 'en') {
            return this.extractPhonemesFromIPA(labels);
        } else {
            // zh/es/fr/pt/sv: textToPhonemes already returns phoneme ID arrays,
            // so pass through directly
            return labels;
        }
    }

    /**
     * Extract phonemes from OpenJTalk labels
     * Uses shared japanese_phoneme_extract module (matches Python phonemize_japanese)
     */
    extractPhonemesFromLabels(labels) {
        return extractJaPhonemes(labels);
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
        if (language === 'zh' || language === 'es' || language === 'fr' || language === 'pt' || language === 'sv') {
            // zh/es/fr/pt/sv use the model's phoneme_id_map directly
            return this.phonemeIdMap;
        }
        // For Japanese, the map should come from the model config
        return null;
    }

    /**
     * Detect language from text.
     * Uses segment-level scoring consistent with Python/Rust/C#/C++ implementations.
     * Priority: JA (Hiragana/Katakana) > ZH (CJK without Kana) > SV (Swedish indicators) > EN (default).
     */
    detectLanguage(text) {
        const segments = this._segmentText(text);
        // Return the language of the first significant segment
        for (const seg of segments) {
            if (seg.lang !== null) {
                return seg.lang;
            }
        }
        return 'en';
    }

    /**
     * Segment text into consecutive runs of the same language.
     * Pre-scans for kana to disambiguate JA vs ZH for CJK characters.
     * Applies Swedish refinement as a post-pass on Latin/'en' segments.
     * @param {string} text
     * @returns {Array<{lang: string, text: string}>}
     */
    _segmentText(text) {
        if (!text || text.trim().length === 0) {
            return [{ lang: 'en', text: text || '' }];
        }

        // Pre-scan: check if any kana exists (for CJK disambiguation)
        let hasKana = false;
        for (const char of text) {
            const code = char.charCodeAt(0);
            if ((code >= 0x3040 && code <= 0x309F) || // Hiragana
                (code >= 0x30A0 && code <= 0x30FF)) { // Katakana
                hasKana = true;
                break;
            }
        }

        // Walk character-by-character, classifying each
        const segments = [];
        let currentLang = null;
        let currentText = '';

        for (const char of text) {
            const lang = this._classifyChar(char, hasKana);

            if (lang === currentLang || lang === null) {
                // Same language or neutral (punctuation/space) -- extend current segment
                currentText += char;
            } else if (currentLang === null) {
                // First language-bearing character in this segment
                currentLang = lang;
                currentText += char;
            } else {
                // Language switch -- flush and start new segment
                if (currentText.length > 0) {
                    segments.push({ lang: currentLang, text: currentText });
                }
                currentLang = lang;
                currentText = char;
            }
        }
        // Flush final segment
        if (currentText.length > 0) {
            segments.push({ lang: currentLang, text: currentText });
        }

        // Fall back to 'en' for segments with no language-specific characters
        for (const seg of segments) {
            if (seg.lang === null) {
                seg.lang = 'en';
            }
        }

        // Post-pass: refine Latin/'en' segments for Swedish
        return this._refineLatinSegmentsForSwedish(segments);
    }

    /**
     * Classify a single character into a language or null (neutral).
     * @param {string} char
     * @param {boolean} hasKana - whether the full text contains kana
     * @returns {string|null} 'ja', 'zh', 'en', or null
     */
    _classifyChar(char, hasKana) {
        const code = char.charCodeAt(0);

        // Hiragana / Katakana → JA
        if ((code >= 0x3040 && code <= 0x309F) ||
            (code >= 0x30A0 && code <= 0x30FF)) {
            return 'ja';
        }

        // CJK Unified Ideographs → JA if kana present, else ZH
        if (code >= 0x4E00 && code <= 0x9FFF) {
            return hasKana ? 'ja' : 'zh';
        }

        // Latin letters (basic + extended, excluding × U+00D7 and ÷ U+00F7)
        // Matches Python's [A-Za-zÀ-ÖØ-öø-ÿ]
        if ((code >= 0x0041 && code <= 0x005A) || // A-Z
            (code >= 0x0061 && code <= 0x007A) || // a-z
            (code >= 0x00C0 && code <= 0x00D6) || // À-Ö
            (code >= 0x00D8 && code <= 0x00F6) || // Ø-ö
            (code >= 0x00F8 && code <= 0x00FF)) { // ø-ÿ
            return 'en';
        }

        // Everything else (spaces, punctuation, digits) → neutral
        return null;
    }

    /**
     * Refine 'en' segments that may actually be Swedish.
     * For each 'en' segment, count Swedish indicators (ä/ö/å characters
     * and Swedish function words). Re-classify as 'sv' if score >= 1.
     * @param {Array<{lang: string, text: string}>} segments
     * @returns {Array<{lang: string, text: string}>}
     */
    _refineLatinSegmentsForSwedish(segments) {
        for (const seg of segments) {
            if (seg.lang !== 'en') {
                continue;
            }

            let score = 0;

            // Per-word scoring matching Python's elif pattern:
            // Each word counts as +1 if it contains a Swedish character
            // OR is a Swedish function word (mutually exclusive per word).
            for (const rawWord of seg.text.split(/\s+/)) {
                const word = rawWord.replace(/^[.,;:!?]+|[.,;:!?]+$/g, '').toLowerCase();
                if (!word) continue;

                if ([...word].some(c => SWEDISH_CHARS.has(c))) {
                    score++;
                } else if (SWEDISH_FUNCTION_WORDS.has(word)) {
                    score++;
                }
            }

            if (score >= 1) {
                seg.lang = 'sv';
            }
        }
        return segments;
    }

    /**
     * Adjust path for deployment
     */
    adjustPathForDeployment(path) {
        if (this.deploymentConfig.basePath) {
            // Remove leading ../ or ./ and add base path with proper slash
            const cleanPath = path.replace(/^\.\.?\//, '');
            return this.deploymentConfig.basePath + '/' + cleanPath;
        }
        return path;
    }
    
    /**
     * Adjust path for GitHub Pages (deprecated - use adjustPathForDeployment)
     */
    adjustPathForGitHubPages(path) {
        // This method is deprecated, but kept for compatibility
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