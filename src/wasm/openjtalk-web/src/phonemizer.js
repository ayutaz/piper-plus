/**
 * Phonemizer - Text to phoneme conversion wrapper
 */

import { extractPhonemesFromLabels as extractJaPhonemes } from './japanese_phoneme_extract.js';

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
            // Extract Japanese phonemes from OpenJTalk labels
            if (!phonemeData) {
                return [];
            }

            let labelsStr;
            if (typeof phonemeData === 'string') {
                labelsStr = phonemeData;
            } else if (phonemeData.labels) {
                labelsStr = Array.isArray(phonemeData.labels)
                    ? phonemeData.labels.join('\n')
                    : phonemeData.labels;
            } else {
                return [];
            }

            return extractJaPhonemes(labelsStr);
        } else {
            // For English, return simple character array
            // This is a fallback - actual English phonemization is handled by ESpeakPhonemeExtractor
            return ['^', ...phonemeData.phonemes.split(''), '$'];
        }
    }
}