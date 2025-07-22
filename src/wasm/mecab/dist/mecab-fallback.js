/**
 * MeCab Fallback Implementation
 * Simple Japanese tokenizer for when MeCab dictionary is not available
 */

export class MeCabFallback {
    constructor() {
        // Basic Japanese character patterns
        this.patterns = {
            hiragana: /[\u3040-\u309F]/,
            katakana: /[\u30A0-\u30FF]/,
            kanji: /[\u4E00-\u9FAF]/,
            punctuation: /[。、！？「」『』（）［］｛｝]/,
            particle: /^(は|が|を|に|で|と|の|へ|から|まで|より|ね|よ|か|な|も|や|だ|です|ます)$/
        };
    }

    /**
     * Simple tokenization based on character types
     */
    tokenize(text) {
        const tokens = [];
        let currentToken = '';
        let currentType = null;

        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            const type = this.getCharType(char);

            if (type !== currentType && currentToken) {
                tokens.push({
                    surface: currentToken,
                    type: currentType
                });
                currentToken = '';
            }

            currentToken += char;
            currentType = type;
        }

        if (currentToken) {
            tokens.push({
                surface: currentToken,
                type: currentType
            });
        }

        return tokens;
    }

    getCharType(char) {
        if (this.patterns.hiragana.test(char)) return 'hiragana';
        if (this.patterns.katakana.test(char)) return 'katakana';
        if (this.patterns.kanji.test(char)) return 'kanji';
        if (this.patterns.punctuation.test(char)) return 'punctuation';
        if (/[a-zA-Z]/.test(char)) return 'alpha';
        if (/[0-9]/.test(char)) return 'numeric';
        if (/\s/.test(char)) return 'space';
        return 'symbol';
    }

    /**
     * Parse text and return in MeCab-like format
     */
    parse(text) {
        const tokens = this.tokenize(text);
        const lines = [];

        for (const token of tokens) {
            if (token.type === 'space') continue;
            
            const feature = this.guessFeature(token);
            lines.push(`${token.surface}\t${feature}`);
        }

        lines.push('EOS');
        return lines.join('\n');
    }

    /**
     * Guess morphological features
     */
    guessFeature(token) {
        const surface = token.surface;
        const reading = this.guessReading(surface);
        
        // Check if it's a known particle
        if (token.type === 'hiragana' && this.patterns.particle.test(surface)) {
            if (surface === 'です' || surface === 'ます') {
                return `助動詞,*,*,*,特殊,基本形,${surface},${reading},${reading}`;
            }
            return `助詞,*,*,*,*,*,${surface},${reading},${reading}`;
        }

        // Guess based on character type
        switch (token.type) {
            case 'kanji':
                return `名詞,一般,*,*,*,*,${surface},${reading},${reading}`;
            case 'katakana':
                return `名詞,一般,*,*,*,*,${surface},${reading},${reading}`;
            case 'hiragana':
                return `名詞,一般,*,*,*,*,${surface},${reading},${reading}`;
            case 'alpha':
                return `名詞,固有名詞,*,*,*,*,${surface},${reading},${reading}`;
            case 'numeric':
                return `名詞,数,*,*,*,*,${surface},${reading},${reading}`;
            case 'punctuation':
                return `記号,*,*,*,*,*,${surface},${reading},${reading}`;
            default:
                return `記号,*,*,*,*,*,${surface},${reading},${reading}`;
        }
    }
    
    /**
     * Guess katakana reading
     */
    guessReading(surface) {
        // Simple reading table for common words
        const readingMap = {
            'こんにちは': 'コンニチハ',
            '世界': 'セカイ',
            '今日': 'キョウ',
            'は': 'ハ',
            '良い': 'ヨイ',
            '良': 'ヨ',
            'い': 'イ',
            '天気': 'テンキ',
            'です': 'デス',
            'ますです': 'マス',
            'ね': 'ネ',
            'の': 'ノ',
            'を': 'ヲ',
            'が': 'ガ',
            'に': 'ニ',
            'で': 'デ',
            'と': 'ト',
            'へ': 'ヘ',
            'から': 'カラ',
            'まで': 'マデ',
            'より': 'ヨリ',
            'か': 'カ',
            'な': 'ナ',
            'も': 'モ',
            'や': 'ヤ',
            'だ': 'ダ'
        };
        
        // Check if we have a known reading
        if (readingMap[surface]) {
            return readingMap[surface];
        }
        
        // Convert hiragana to katakana
        if (this.patterns.hiragana.test(surface)) {
            return this.hiraganaToKatakana(surface);
        }
        
        // Already katakana
        if (this.patterns.katakana.test(surface)) {
            return surface;
        }
        
        // For kanji, return the surface (ideally need a dictionary)
        if (this.patterns.kanji.test(surface)) {
            return surface; // Fallback
        }
        
        // For others, return as-is
        return surface;
    }
    
    /**
     * Convert hiragana to katakana
     */
    hiraganaToKatakana(text) {
        let result = '';
        for (let i = 0; i < text.length; i++) {
            const code = text.charCodeAt(i);
            // Hiragana range: 0x3040-0x309F
            // Katakana range: 0x30A0-0x30FF
            if (code >= 0x3040 && code <= 0x309F) {
                result += String.fromCharCode(code + 0x60);
            } else {
                result += text[i];
            }
        }
        return result;
    }

    /**
     * Simple wakati-gaki (word segmentation)
     */
    wakati(text) {
        const tokens = this.tokenize(text);
        return tokens
            .filter(t => t.type !== 'space' && t.type !== 'punctuation')
            .map(t => t.surface)
            .join(' ');
    }

    /**
     * Return tokens as JSON
     */
    parseToJSON(text) {
        const tokens = this.tokenize(text);
        return tokens
            .filter(t => t.type !== 'space')
            .map(token => ({
                surface: token.surface,
                feature: this.guessFeature(token),
                cost: 0
            }));
    }
}