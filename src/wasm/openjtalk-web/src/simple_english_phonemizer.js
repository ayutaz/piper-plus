/**
 * Simple English Phonemizer
 * A lightweight alternative to eSpeak-ng for demo purposes
 */

export class SimpleEnglishPhonemizer {
    constructor() {
        // Basic pronunciation dictionary for common words
        // Using only phonemes available in the test model
        this.dictionary = {
            // Common words
            'hello': ['h', 'ɛ', 'l', 'o'],
            'world': ['w', 'ɜ', 'r', 'l', 'd'],
            'the': ['ð', 'ə'],
            'a': ['ə'],
            'an': ['æ', 'n'],
            'and': ['æ', 'n', 'd'],
            'is': ['ɪ', 'z'],
            'are': ['ɑ', 'r'],
            'was': ['w', 'ʌ', 'z'],
            'were': ['w', 'ɜ', 'r'],
            'been': ['b', 'ɪ', 'n'],
            'have': ['h', 'æ', 'v'],
            'has': ['h', 'æ', 'z'],
            'had': ['h', 'æ', 'd'],
            'do': ['d', 'u'],
            'does': ['d', 'ʌ', 'z'],
            'did': ['d', 'ɪ', 'd'],
            'will': ['w', 'ɪ', 'l'],
            'would': ['w', 'ʊ', 'd'],
            'can': ['k', 'æ', 'n'],
            'could': ['k', 'ʊ', 'd'],
            'should': ['ʃ', 'ʊ', 'd'],
            'may': ['m', 'e', 'i'],
            'might': ['m', 'a', 'i', 't'],
            'must': ['m', 'ʌ', 's', 't'],
            'to': ['t', 'u'],
            'of': ['ʌ', 'v'],
            'in': ['ɪ', 'n'],
            'on': ['ɒ', 'n'],
            'at': ['æ', 't'],
            'by': ['b', 'a', 'i'],
            'for': ['f', 'ɔ', 'r'],
            'with': ['w', 'ɪ', 'θ'],
            'from': ['f', 'r', 'ʌ', 'm'],
            'up': ['ʌ', 'p'],
            'out': ['a', 'u', 't'],
            'over': ['o', 'v', 'ə', 'r'],
            'under': ['ʌ', 'n', 'd', 'ə', 'r'],
            'not': ['n', 'ɒ', 't'],
            'all': ['ɔ', 'l'],
            'one': ['w', 'ʌ', 'n'],
            'two': ['t', 'u'],
            'three': ['θ', 'r', 'i'],
            'four': ['f', 'ɔ', 'r'],
            'five': ['f', 'a', 'i', 'v'],
            'good': ['ɡ', 'ʊ', 'd'],
            'bad': ['b', 'æ', 'd'],
            'new': ['n', 'j', 'u'],
            'old': ['o', 'l', 'd'],
            'big': ['b', 'ɪ', 'ɡ'],
            'small': ['s', 'm', 'ɔ', 'l'],
            
            // Tech terms
            'text': ['t', 'ɛ', 'k', 's', 't'],
            'speech': ['s', 'p', 'i', 'ʃ'],
            'voice': ['v', 'ɔ', 'i', 's'],
            'audio': ['ɔ', 'd', 'i', 'o'],
            'system': ['s', 'ɪ', 's', 't', 'ə', 'm'],
            'computer': ['k', 'ə', 'm', 'p', 'j', 'u', 't', 'ə', 'r'],
            'artificial': ['ɑ', 'r', 't', 'ɪ', 'f', 'ɪ', 'ʃ', 'ə', 'l'],
            'intelligence': ['ɪ', 'n', 't', 'ɛ', 'l', 'ɪ', 'ʒ', 'ə', 'n', 's'],
            'technology': ['t', 'ɛ', 'k', 'n', 'ɒ', 'l', 'ə', 'ʒ', 'i'],
            'synthesis': ['s', 'ɪ', 'n', 'θ', 'ə', 's', 'ɪ', 's']
        };
        
        // Basic letter-to-phoneme rules for unknown words
        this.letterRules = {
            'a': ['æ'], 'b': ['b'], 'c': ['k'], 'd': ['d'],
            'e': ['ɛ'], 'f': ['f'], 'g': ['g'], 'h': ['h'],
            'i': ['ɪ'], 'j': ['dʒ'], 'k': ['k'], 'l': ['l'],
            'm': ['m'], 'n': ['n'], 'o': ['ɒ'], 'p': ['p'],
            'q': ['k', 'w'], 'r': ['r'], 's': ['s'], 't': ['t'],
            'u': ['ʌ'], 'v': ['v'], 'w': ['w'], 'x': ['k', 's'],
            'y': ['j'], 'z': ['z']
        };
    }
    
    /**
     * Convert text to phonemes
     */
    textToPhonemes(text) {
        const words = text.toLowerCase().split(/\s+/);
        const allPhonemes = [];
        
        for (const word of words) {
            if (!word) continue;
            
            // Remove punctuation
            const cleanWord = word.replace(/[^a-z]/g, '');
            if (!cleanWord) continue;
            
            // Look up in dictionary first
            if (this.dictionary[cleanWord]) {
                allPhonemes.push(...this.dictionary[cleanWord]);
                allPhonemes.push(' '); // Word boundary
            } else {
                // Fall back to letter-by-letter conversion
                for (const letter of cleanWord) {
                    if (this.letterRules[letter]) {
                        allPhonemes.push(...this.letterRules[letter]);
                    }
                }
                allPhonemes.push(' '); // Word boundary
            }
        }
        
        // Remove trailing space
        if (allPhonemes[allPhonemes.length - 1] === ' ') {
            allPhonemes.pop();
        }
        
        return allPhonemes;
    }
    
    /**
     * Convert phonemes to a format similar to eSpeak IPA output
     */
    phonemesToIPA(phonemes) {
        // Keep spaces as separate elements for proper word boundaries
        return phonemes;
    }
}

/**
 * Simple phoneme-to-ID mapping for English
 * This maps IPA phonemes to numeric IDs for the ONNX model
 */
export function createEnglishPhonemeMap() {
    const phonemes = [
        '_', '^', '$', ' ', // Special markers
        'a', 'æ', 'ɑː', 'ə', 'ɜː', 'ɔː', 'ɒ', 'ʌ', // Vowels
        'e', 'ɛ', 'i', 'ɪ', 'iː', 'o', 'oʊ', 'u', 'uː', 'ʊ',
        'aɪ', 'aʊ', 'eɪ', 'ɔɪ', 'əʊ', // Diphthongs
        'b', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm', 'n', // Consonants
        'p', 'r', 's', 't', 'v', 'w', 'z',
        'θ', 'ð', 'ʃ', 'ʒ', 'tʃ', 'dʒ', 'ŋ', // Special consonants
        'ər', 'l̩', 'n̩' // Syllabic consonants
    ];
    
    const phonemeIdMap = {};
    phonemes.forEach((phoneme, index) => {
        phonemeIdMap[phoneme] = [index];
    });
    
    return phonemeIdMap;
}