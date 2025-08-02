/**
 * Unified API with real eSpeak-ng support
 */

import { SimpleUnifiedPhonemizer } from './simple_unified_api.js';
import { ESpeakNGWrapper } from './espeak_ng_wrapper.js';

export class UnifiedPhonemizerWithESpeakNG extends SimpleUnifiedPhonemizer {
    constructor() {
        super();
        this.espeakNG = null;
    }
    
    async initialize(config) {
        // Initialize OpenJTalk for Japanese
        await super.initialize(config);
        
        // Initialize eSpeak-ng for other languages
        this.espeakNG = new ESpeakNGWrapper();
        await this.espeakNG.initialize();
        
        console.log('Unified phonemizer with eSpeak-ng initialized');
    }
    
    async textToPhonemes(text, language = 'ja') {
        if (language === 'ja') {
            // Use OpenJTalk for Japanese
            return super.textToPhonemes(text, language);
        } else {
            // Use eSpeak-ng for other languages
            const phonemes = await this.espeakNG.textToPhonemes(text, language);
            return phonemes;
        }
    }
}
