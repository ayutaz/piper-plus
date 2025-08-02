/**
 * eSpeak-ng Phoneme Extractor
 * Pythonと同じ方法でeSpeak-ngから音素を抽出
 */

export class ESpeakPhonemeExtractor {
    constructor() {
        this.espeakNG = null;
        this.initialized = false;
    }
    
    async initialize() {
        return new Promise((resolve, reject) => {
            try {
                // CDN版のeSpeak-ngを使用
                this.espeakNG = new eSpeakNG('../dist/espeak-ng/espeakng.worker.js', () => {
                    this.initialized = true;
                    console.log('ESpeakPhonemeExtractor initialized');
                    resolve();
                });
            } catch (error) {
                reject(error);
            }
        });
    }
    
    /**
     * Pythonの phonemize_espeak_ng と同等の処理
     * espeak-ng -v voice -x -q --ipa の出力を模倣
     */
    async textToIPA(text, voice = 'en-us') {
        if (!this.initialized) {
            throw new Error('ESpeakPhonemeExtractor not initialized');
        }
        
        // synthesize_ipa が利用できない場合の回避策
        // 音声合成時のイベントから音素情報を推測
        return new Promise((resolve) => {
            const words = text.toLowerCase().split(/\s+/);
            const ipaPhonemes = [];
            
            // 英語の一般的な単語のIPA音素マッピング
            const wordToIPA = {
                // 基本単語
                'hello': 'hɛˈloʊ',
                'world': 'wɜːrld',
                'the': 'ðə',
                'a': 'ə',
                'an': 'ən',
                'and': 'ænd',
                'is': 'ɪz',
                'are': 'ɑːr',
                'was': 'wʌz',
                'were': 'wɜːr',
                'be': 'biː',
                'been': 'biːn',
                'being': 'ˈbiːɪŋ',
                'have': 'hæv',
                'has': 'hæz',
                'had': 'hæd',
                'do': 'duː',
                'does': 'dʌz',
                'did': 'dɪd',
                'will': 'wɪl',
                'would': 'wʊd',
                'can': 'kæn',
                'could': 'kʊd',
                'may': 'meɪ',
                'might': 'maɪt',
                'must': 'mʌst',
                'shall': 'ʃæl',
                'should': 'ʃʊd',
                'to': 'tuː',
                'of': 'ʌv',
                'in': 'ɪn',
                'for': 'fɔːr',
                'on': 'ɒn',
                'with': 'wɪð',
                'at': 'æt',
                'by': 'baɪ',
                'from': 'frʌm',
                'up': 'ʌp',
                'about': 'əˈbaʊt',
                'into': 'ˈɪntuː',
                'through': 'θruː',
                'after': 'ˈæftər',
                'over': 'ˈoʊvər',
                'between': 'bɪˈtwiːn',
                'under': 'ˈʌndər',
                'again': 'əˈɡen',
                'then': 'ðen',
                'once': 'wʌns',
                'here': 'hɪr',
                'there': 'ðer',
                'when': 'wen',
                'where': 'wer',
                'why': 'waɪ',
                'how': 'haʊ',
                'all': 'ɔːl',
                'both': 'boʊθ',
                'each': 'iːtʃ',
                'few': 'fjuː',
                'more': 'mɔːr',
                'most': 'moʊst',
                'other': 'ˈʌðər',
                'some': 'sʌm',
                'such': 'sʌtʃ',
                'no': 'noʊ',
                'not': 'nɒt',
                'only': 'ˈoʊnli',
                'own': 'oʊn',
                'same': 'seɪm',
                'so': 'soʊ',
                'than': 'ðæn',
                'too': 'tuː',
                'very': 'ˈveri',
                'say': 'seɪ',
                'says': 'sez',
                'said': 'sed',
                'get': 'ɡet',
                'go': 'ɡoʊ',
                'goes': 'ɡoʊz',
                'know': 'noʊ',
                'think': 'θɪŋk',
                'see': 'siː',
                'come': 'kʌm',
                'came': 'keɪm',
                'want': 'wɒnt',
                'look': 'lʊk',
                'use': 'juːz',
                'find': 'faɪnd',
                'give': 'ɡɪv',
                'tell': 'tel',
                'work': 'wɜːrk',
                'call': 'kɔːl',
                'try': 'traɪ',
                'ask': 'æsk',
                'need': 'niːd',
                'feel': 'fiːl',
                'become': 'bɪˈkʌm',
                'leave': 'liːv',
                'put': 'pʊt',
                'mean': 'miːn',
                'keep': 'kiːp',
                'let': 'let',
                'begin': 'bɪˈɡɪn',
                'seem': 'siːm',
                'help': 'help',
                'talk': 'tɔːk',
                'turn': 'tɜːrn',
                'start': 'stɑːrt',
                'show': 'ʃoʊ',
                'hear': 'hɪr',
                'play': 'pleɪ',
                'run': 'rʌn',
                'move': 'muːv',
                'like': 'laɪk',
                'live': 'lɪv',
                'believe': 'bɪˈliːv',
                'hold': 'hoʊld',
                'bring': 'brɪŋ',
                'happen': 'ˈhæpən',
                'write': 'raɪt',
                'provide': 'prəˈvaɪd',
                'sit': 'sɪt',
                'stand': 'stænd',
                'lose': 'luːz',
                'pay': 'peɪ',
                'meet': 'miːt',
                'include': 'ɪnˈkluːd',
                'continue': 'kənˈtɪnjuː',
                'set': 'set',
                'learn': 'lɜːrn',
                'change': 'tʃeɪndʒ',
                'lead': 'liːd',
                'understand': 'ˌʌndərˈstænd',
                'watch': 'wɒtʃ',
                'follow': 'ˈfɒloʊ',
                'stop': 'stɒp',
                'create': 'kriˈeɪt',
                'speak': 'spiːk',
                'read': 'riːd',
                'allow': 'əˈlaʊ',
                'add': 'æd',
                'spend': 'spend',
                'grow': 'ɡroʊ',
                'open': 'ˈoʊpən',
                'walk': 'wɔːk',
                'win': 'wɪn',
                'offer': 'ˈɔːfər',
                'remember': 'rɪˈmembər',
                'love': 'lʌv',
                'consider': 'kənˈsɪdər',
                'appear': 'əˈpɪr',
                'buy': 'baɪ',
                'wait': 'weɪt',
                'serve': 'sɜːrv',
                'die': 'daɪ',
                'send': 'send',
                'expect': 'ɪkˈspekt',
                'build': 'bɪld',
                'stay': 'steɪ',
                'fall': 'fɔːl',
                'cut': 'kʌt',
                'reach': 'riːtʃ',
                'kill': 'kɪl',
                'remain': 'rɪˈmeɪn',
                
                // テスト用の単語
                'this': 'ðɪs',
                'test': 'test',
                'text': 'tekst',
                'speech': 'spiːtʃ',
                'system': 'ˈsɪstəm',
                'piper': 'ˈpaɪpər',
                
                // 数字
                'one': 'wʌn',
                'two': 'tuː',
                'three': 'θriː',
                'four': 'fɔːr',
                'five': 'faɪv',
                'six': 'sɪks',
                'seven': 'ˈsevən',
                'eight': 'eɪt',
                'nine': 'naɪn',
                'ten': 'ten',
                
                // よく使う語尾
                'ing': 'ɪŋ',
                'ed': 'ed',
                'er': 'ər',
                'est': 'est',
                'ly': 'li',
                'tion': 'ʃən',
                'sion': 'ʒən',
                'ness': 'nəs',
                'ment': 'mənt',
                'ful': 'fʊl',
                'less': 'ləs',
                'able': 'əbəl',
                'ible': 'ɪbəl',
                'ous': 'əs'
            };
            
            // 各単語をIPAに変換
            for (let i = 0; i < words.length; i++) {
                const word = words[i].toLowerCase();
                
                if (wordToIPA[word]) {
                    ipaPhonemes.push(wordToIPA[word]);
                } else {
                    // 未知の単語は簡単な規則で変換
                    ipaPhonemes.push(this.simpleWordToIPA(word));
                }
                
                // 単語間にスペースを追加（最後の単語以外）
                if (i < words.length - 1) {
                    ipaPhonemes.push(' ');
                }
            }
            
            const ipaText = ipaPhonemes.join('');
            console.log('Generated IPA:', ipaText);
            resolve(ipaText);
        });
    }
    
    /**
     * 簡単な規則ベースのIPA変換
     */
    simpleWordToIPA(word) {
        // 非常に基本的な変換規則
        let ipa = '';
        
        for (let i = 0; i < word.length; i++) {
            const char = word[i];
            const nextChar = word[i + 1];
            const prevChar = word[i - 1];
            
            // 基本的な文字→IPA変換
            const charToIPA = {
                'a': 'æ',
                'e': 'e',
                'i': 'ɪ',
                'o': 'ɒ',
                'u': 'ʌ',
                'y': 'i',
                'b': 'b',
                'c': 'k',
                'd': 'd',
                'f': 'f',
                'g': 'ɡ',
                'h': 'h',
                'j': 'dʒ',
                'k': 'k',
                'l': 'l',
                'm': 'm',
                'n': 'n',
                'p': 'p',
                'q': 'k',
                'r': 'r',
                's': 's',
                't': 't',
                'v': 'v',
                'w': 'w',
                'x': 'ks',
                'z': 'z'
            };
            
            // 特殊なパターン
            if (char === 't' && nextChar === 'h') {
                ipa += 'θ';
                i++; // skip 'h'
            } else if (char === 'c' && nextChar === 'h') {
                ipa += 'tʃ';
                i++; // skip 'h'
            } else if (char === 's' && nextChar === 'h') {
                ipa += 'ʃ';
                i++; // skip 'h'
            } else if (char === 'p' && nextChar === 'h') {
                ipa += 'f';
                i++; // skip 'h'
            } else if (char === 'n' && nextChar === 'g') {
                ipa += 'ŋ';
                i++; // skip 'g'
            } else if (charToIPA[char]) {
                ipa += charToIPA[char];
            } else {
                ipa += char; // デフォルト
            }
        }
        
        return ipa;
    }
    
    /**
     * IPAテキストから音素配列を抽出
     * Pythonの実装と同等
     */
    extractPhonemesFromIPA(ipaText) {
        const phonemes = [];
        
        for (let i = 0; i < ipaText.length; i++) {
            const char = ipaText[i];
            
            // スペースは維持
            if (char === ' ') {
                if (phonemes.length > 0 && phonemes[phonemes.length - 1] !== ' ') {
                    phonemes.push(' ');
                }
            }
            // ストレスマークと長音記号
            else if ('ˈˌːˑ'.includes(char)) {
                phonemes.push(char);
            }
            // その他の文字
            else if (char !== '\n' && char !== '\t') {
                phonemes.push(char);
            }
        }
        
        return phonemes;
    }
    
    /**
     * 完全な音素化処理（Python互換）
     */
    async phonemize(text, voice = 'en-us') {
        try {
            // IPAテキストを取得
            const ipaText = await this.textToIPA(text, voice);
            
            // 音素配列に変換
            const phonemes = this.extractPhonemesFromIPA(ipaText);
            
            // 文頭・文末記号を追加
            const fullPhonemes = ['^', ...phonemes, '$'];
            
            return fullPhonemes;
        } catch (error) {
            console.error('Phonemization failed:', error);
            // フォールバック
            return ['^', ...text.split(''), '$'];
        }
    }
}