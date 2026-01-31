/**
 * カスタム辞書管理クラス
 * 外部から単語と読み方の対応を読み込み、テキスト前処理に使用
 * V2.0形式と優先度による競合解決をサポート
 */
export class CustomDictionary {
    constructor() {
        this.entries = new Map();  // key: word, value: {pronunciation, priority}
        this.caseSensitiveEntries = new Map();  // 大文字小文字を区別するエントリ
        this.initialized = false;
        this.compiledRegexCache = new Map();
        this.version = "2.0";
    }

    /**
     * JSONファイルから辞書を読み込む
     * @param {string|string[]} urls - 辞書ファイルのURL（単一または配列）
     */
    async loadFromJSON(urls) {
        try {
            // 配列でない場合は配列に変換
            const urlArray = Array.isArray(urls) ? urls : [urls];
            
            for (const url of urlArray) {
                await this.loadSingleDictionary(url);
            }
            
            // 正規表現を事前コンパイル
            this.compileRegexPatterns();
            
            this.initialized = true;
            console.log(`Loaded custom dictionaries with ${this.entries.size + this.caseSensitiveEntries.size} total entries`);
            
            return true;
        } catch (error) {
            console.error('Failed to load custom dictionaries:', error);
            if (error.name !== 'NetworkError') {
                this.initialized = false;
            }
            return false;
        }
    }

    /**
     * 単一の辞書ファイルを読み込む
     * @param {string} url - 辞書ファイルのURL
     */
    async loadSingleDictionary(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to load dictionary: ${response.status}`);
        }
        
        const data = await response.json();
        
        // データ検証
        if (!data.entries || typeof data.entries !== 'object') {
            throw new Error('Invalid dictionary format: missing entries object');
        }
        
        const version = data.version || "1.0";
        
        // エントリーを処理
        for (const [word, entry] of Object.entries(data.entries)) {
            // コメント行をスキップ
            if (word.startsWith("//")) continue;
            
            if (version === "2.0" && typeof entry === 'object') {
                // V2形式
                this.addEntryWithPriority(word, entry.pronunciation, entry.priority || 5);
            } else {
                // V1形式または単純な文字列
                const pronunciation = typeof entry === 'string' ? entry : entry.pronunciation;
                this.addEntryWithPriority(word, pronunciation, 5);
            }
        }
    }

    /**
     * 辞書にエントリーを追加
     * @param {string} word - 英単語
     * @param {string} reading - カタカナ読み
     */
    addEntry(word, reading) {
        this.addEntryWithPriority(word, reading, 5);
    }

    /**
     * 優先度付きでエントリーを追加
     * @param {string} word - 英単語
     * @param {string} pronunciation - カタカナ読み
     * @param {number} priority - 優先度（0-10）
     */
    addEntryWithPriority(word, pronunciation, priority = 5) {
        const entry = { pronunciation, priority };
        
        // 大文字小文字が混在している場合は区別する
        if (this.isMixedCase(word)) {
            // 既存エントリとの優先度比較
            const existing = this.caseSensitiveEntries.get(word);
            if (!existing || priority > existing.priority) {
                this.caseSensitiveEntries.set(word, entry);
            }
        } else {
            // 全て大文字または小文字の場合は正規化
            const normalizedWord = word.toLowerCase();
            const existing = this.entries.get(normalizedWord);
            if (!existing || priority > existing.priority) {
                this.entries.set(normalizedWord, entry);
            }
        }
    }

    /**
     * 大文字小文字が混在しているかチェック
     * @param {string} word - チェックする単語
     * @returns {boolean} 混在している場合true
     */
    isMixedCase(word) {
        const hasUpper = /[A-Z]/.test(word);
        const hasLower = /[a-z]/.test(word);
        return hasUpper && hasLower;
    }

    /**
     * 辞書からエントリーを削除
     * @param {string} word - 削除する単語
     */
    removeEntry(word) {
        this.entries.delete(word);
        this.entries.delete(word.toLowerCase());
        this.entries.delete(word.toUpperCase());
    }

    /**
     * 正規表現パターンを事前コンパイル
     */
    compileRegexPatterns() {
        this.compiledRegexCache.clear();
        
        // Word boundary: ASCII word chars use \b, but we also need to match
        // when adjacent to Japanese characters (hiragana, katakana, kanji, punctuation).
        // Use a broad approach: match the word anywhere (longer words first prevents partial matches).

        // 大文字小文字を区別するエントリ
        const caseSensitiveSorted = Array.from(this.caseSensitiveEntries.entries())
            .sort((a, b) => b[0].length - a[0].length);

        for (const [word, entry] of caseSensitiveSorted) {
            const regex = new RegExp(this.escapeRegExp(word), 'g');
            this.compiledRegexCache.set(word + '_cs', { regex, reading: entry.pronunciation });
        }

        // 大文字小文字を区別しないエントリ
        const normalSorted = Array.from(this.entries.entries())
            .sort((a, b) => b[0].length - a[0].length);

        for (const [word, entry] of normalSorted) {
            const regex = new RegExp(this.escapeRegExp(word), 'gi');
            this.compiledRegexCache.set(word, { regex, reading: entry.pronunciation });
        }
    }

    /**
     * テキストを辞書に基づいて変換
     * @param {string} text - 変換するテキスト
     * @returns {string} 変換後のテキスト
     */
    processText(text) {
        if (!this.initialized || this.entries.size === 0) {
            return text;
        }

        let processedText = text;
        
        // 事前コンパイルされた正規表現を使用
        for (const { regex, reading } of this.compiledRegexCache.values()) {
            processedText = processedText.replace(regex, reading);
        }
        
        return processedText;
    }

    /**
     * 正規表現の特殊文字をエスケープ
     * @param {string} string - エスケープする文字列
     * @returns {string} エスケープ後の文字列
     */
    escapeRegExp(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    /**
     * 現在の辞書をJSON形式でエクスポート
     * @returns {object} 辞書データ
     */
    exportToJSON() {
        const entries = {};
        for (const [word, reading] of this.entries) {
            entries[word] = reading;
        }
        
        return {
            version: "1.0",
            description: "カスタム辞書 - 英単語とカタカナ読みの対応",
            entries: entries
        };
    }

    /**
     * 辞書の内容をクリア
     */
    clear() {
        this.entries.clear();
        this.initialized = false;
    }

    /**
     * 辞書のエントリー数を取得
     * @returns {number} エントリー数
     */
    get size() {
        return this.entries.size;
    }

    /**
     * 特定の単語が辞書に存在するか確認
     * @param {string} word - 確認する単語
     * @returns {boolean} 存在する場合true
     */
    hasWord(word) {
        return this.entries.has(word);
    }

    /**
     * 特定の単語の読みを取得
     * @param {string} word - 単語
     * @returns {string|null} 読み（存在しない場合null）
     */
    getReading(word) {
        // 大文字小文字を区別してチェック
        const caseSensitive = this.caseSensitiveEntries.get(word);
        if (caseSensitive) {
            return caseSensitive.pronunciation;
        }
        
        // 正規化してチェック
        const normalized = this.entries.get(word.toLowerCase());
        if (normalized) {
            return normalized.pronunciation;
        }
        
        return null;
    }
}