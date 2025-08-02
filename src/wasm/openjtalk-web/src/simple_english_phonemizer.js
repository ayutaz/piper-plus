/**
 * Simple English Phonemizer
 * A lightweight alternative to eSpeak-ng for demo purposes
 */

export class SimpleEnglishPhonemizer {
    constructor() {
        // Basic pronunciation dictionary for common words
        this.dictionary = {
            // Common words
            'hello': ['h', 'ɛ', 'l', 'oʊ'],
            'world': ['w', 'ɜː', 'l', 'd'],
            'the': ['ð', 'ə'],
            'a': ['ə'],
            'an': ['æ', 'n'],
            'and': ['æ', 'n', 'd'],
            'is': ['ɪ', 'z'],
            'are': ['ɑː', 'r'],
            'was': ['w', 'ʌ', 'z'],
            'were': ['w', 'ɜː', 'r'],
            'been': ['b', 'ɪ', 'n'],
            'have': ['h', 'æ', 'v'],
            'has': ['h', 'æ', 'z'],
            'had': ['h', 'æ', 'd'],
            'do': ['d', 'uː'],
            'does': ['d', 'ʌ', 'z'],
            'did': ['d', 'ɪ', 'd'],
            'will': ['w', 'ɪ', 'l'],
            'would': ['w', 'ʊ', 'd'],
            'can': ['k', 'æ', 'n'],
            'could': ['k', 'ʊ', 'd'],
            'should': ['ʃ', 'ʊ', 'd'],
            'may': ['m', 'eɪ'],
            'might': ['m', 'aɪ', 't'],
            'must': ['m', 'ʌ', 's', 't'],
            'to': ['t', 'uː'],
            'of': ['ʌ', 'v'],
            'in': ['ɪ', 'n'],
            'on': ['ɒ', 'n'],
            'at': ['æ', 't'],
            'by': ['b', 'aɪ'],
            'for': ['f', 'ɔː', 'r'],
            'with': ['w', 'ɪ', 'θ'],
            'from': ['f', 'r', 'ʌ', 'm'],
            'up': ['ʌ', 'p'],
            'out': ['aʊ', 't'],
            'over': ['oʊ', 'v', 'ər'],
            'under': ['ʌ', 'n', 'd', 'ər'],
            'not': ['n', 'ɒ', 't'],
            'all': ['ɔː', 'l'],
            'one': ['w', 'ʌ', 'n'],
            'two': ['t', 'uː'],
            'three': ['θ', 'r', 'iː'],
            'four': ['f', 'ɔː', 'r'],
            'five': ['f', 'aɪ', 'v'],
            'good': ['g', 'ʊ', 'd'],
            'bad': ['b', 'æ', 'd'],
            'new': ['n', 'juː'],
            'old': ['oʊ', 'l', 'd'],
            'big': ['b', 'ɪ', 'g'],
            'small': ['s', 'm', 'ɔː', 'l'],
            
            // Tech terms
            'text': ['t', 'ɛ', 'k', 's', 't'],
            'speech': ['s', 'p', 'iː', 'tʃ'],
            'voice': ['v', 'ɔɪ', 's'],
            'audio': ['ɔː', 'd', 'i', 'oʊ'],
            'system': ['s', 'ɪ', 's', 't', 'ə', 'm'],
            'computer': ['k', 'ə', 'm', 'p', 'juː', 't', 'ər'],
            'artificial': ['ɑː', 'r', 't', 'ɪ', 'f', 'ɪ', 'ʃ', 'əl'],
            'intelligence': ['ɪ', 'n', 't', 'ɛ', 'l', 'ɪ', 'dʒ', 'ə', 'n', 's'],
            'technology': ['t', 'ɛ', 'k', 'n', 'ɒ', 'l', 'ə', 'dʒ', 'i'],
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
        return phonemes.join('');
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