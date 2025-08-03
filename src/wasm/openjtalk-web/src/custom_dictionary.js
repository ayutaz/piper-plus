/**
 * カスタム辞書管理クラス
 * 外部から単語と読み方の対応を読み込み、テキスト前処理に使用
 */
export class CustomDictionary {
    constructor() {
        this.entries = new Map();
        this.initialized = false;
        this.compiledRegexCache = new Map();
    }

    /**
     * JSONファイルから辞書を読み込む
     * @param {string} url - 辞書ファイルのURL
     */
    async loadFromJSON(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to load dictionary: ${response.status}`);
            }
            
            const data = await response.json();
            
            // データ検証
            if (!data.entries || typeof data.entries !== 'object') {
                throw new Error('Invalid dictionary format: missing entries object');
            }
            
            // エントリーをMapに変換
            this.entries.clear();
            this.compiledRegexCache.clear();
            for (const [word, reading] of Object.entries(data.entries)) {
                this.entries.set(word, reading);
            }
            
            // 正規表現を事前コンパイル
            this.compileRegexPatterns();
            
            this.initialized = true;
            console.log(`Loaded custom dictionary with ${this.entries.size} entries`);
            
            return true;
        } catch (error) {
            console.error('Failed to load custom dictionary:', error);
            // ネットワークエラーの場合は初期化フラグを維持
            if (error.name !== 'NetworkError') {
                this.initialized = false;
            }
            return false;
        }
    }

    /**
     * 辞書にエントリーを追加
     * @param {string} word - 英単語
     * @param {string} reading - カタカナ読み
     */
    addEntry(word, reading) {
        this.entries.set(word, reading);
        
        // 大文字・小文字のバリエーションも自動追加
        if (word !== word.toLowerCase()) {
            this.entries.set(word.toLowerCase(), reading);
        }
        if (word !== word.toUpperCase()) {
            this.entries.set(word.toUpperCase(), reading);
        }
        
        // 正規表現を再コンパイル
        this.compileRegexPatterns();
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
        // 長い単語から優先的に処理するためにソート
        const sortedEntries = Array.from(this.entries.entries())
            .sort((a, b) => b[0].length - a[0].length);
        
        for (const [word, reading] of sortedEntries) {
            // 単語境界を考慮した正規表現
            const regex = new RegExp(
                `(?<=[\\s。、！？「」（）\\[\\]【】]|^)${this.escapeRegExp(word)}(?=[\\s。、！？「」（）\\[\\]【】]|$)`,
                'g'
            );
            this.compiledRegexCache.set(word, { regex, reading });
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
        return this.entries.get(word) || null;
    }
}