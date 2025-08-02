/**
 * Phonemizer - Text to phoneme conversion wrapper
 */

export class Phonemizer {
    constructor(openjtalk) {
        this.openjtalk = openjtalk;
    }
    
    /**
     * Convert text to phonemes
     * @param {string} text - Input text
     * @param {string} lang - Language code ('ja' or 'en')
     * @returns {Promise<Object>} Phoneme data
     */
    async textToPhonemes(text, lang = 'ja') {
        if (lang === 'ja') {
            // Use OpenJTalk for Japanese
            return await this.openjtalk.textToPhonemes(text);
        } else {
            // For English, return a simple structure
            // This will be handled by ESpeakPhonemeExtractor in the main script
            return {
                phonemes: text,
                lang: lang
            };
        }
    }
    
    /**
     * Extract phoneme array from phoneme data
     * @param {Object} phonemeData - Phoneme data from textToPhonemes
     * @param {string} lang - Language code
     * @returns {Array<string>} Array of phonemes
     */
    extractPhonemes(phonemeData, lang = 'ja') {
        if (lang === 'ja') {
            // Extract Japanese phonemes from OpenJTalk data
            if (!phonemeData) {
                return [];
            }
            
            // If phonemeData is a string (labels), parse it
            let labels;
            if (typeof phonemeData === 'string') {
                labels = phonemeData.split('\n').filter(line => line.trim());
            } else if (phonemeData.labels) {
                labels = phonemeData.labels;
            } else {
                return [];
            }
            
            const phonemes = [];
            
            // Multi-character phoneme to Unicode mapping (matching the model)
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
            
            phonemes.push('^'); // Start marker
            
            for (const label of labels) {
                // Extract phoneme from label
                const match = label.match(/\-([^+]+)\+/);
                if (match && match[1] !== 'sil') {
                    let phoneme = match[1];
                    
                    // Replace multi-character phonemes with Unicode
                    if (multiCharPhonemes[phoneme]) {
                        phoneme = multiCharPhonemes[phoneme];
                    }
                    
                    // Skip 'pau' (pause) - it should not be included in phonemes
                    if (phoneme !== 'pau') {
                        phonemes.push(phoneme);
                    }
                }
            }
            
            phonemes.push('$'); // End marker
            return phonemes;
        } else {
            // For English, return simple character array
            // This is a fallback - actual English phonemization is handled by ESpeakPhonemeExtractor
            return ['^', ...phonemeData.phonemes.split(''), '$'];
        }
    }
}