/**
 * Custom dictionary for G2P text pre-processing.
 *
 * Supports JSON v1.0 and v2.0 formats (compatible with C#/Rust implementations).
 * Entries map surface words to arrays of phoneme tokens, which are substituted
 * into the text before phonemization.
 *
 * @module custom-dictionary
 */

/**
 * Custom dictionary that maps words to phoneme token arrays.
 */
export class CustomDictionary {
    /**
     * @param {Record<string, string[]>} [entries={}]
     *   Initial entries: word -> array of phoneme tokens.
     */
    constructor(entries = {}) {
        /** @type {Map<string, {tokens: string[], priority: number, caseSensitive: boolean}>} */
        this._entries = new Map();

        // Populate from initial entries (all case-insensitive, default priority)
        for (const [word, tokens] of Object.entries(entries)) {
            this._entries.set(word.toLowerCase(), {
                tokens,
                priority: 5,
                caseSensitive: false,
            });
        }

        /** @private */
        this._sortedKeys = null;
    }

    /**
     * Number of entries in the dictionary.
     * @type {number}
     */
    get size() {
        return this._entries.size;
    }

    /**
     * Load a custom dictionary from a JSON file or URL.
     *
     * Supports two formats:
     *
     * **v1.0** (string values):
     * ```json
     * {
     *   "version": "1.0",
     *   "entries": {
     *     "word": ["p", "h", "o", "n", "e", "m", "e", "s"],
     *     "another": ["t", "o", "k", "e", "n", "s"]
     *   }
     * }
     * ```
     *
     * **v2.0** (object values with priority):
     * ```json
     * {
     *   "version": "2.0",
     *   "entries": {
     *     "word": {
     *       "tokens": ["p", "h", "o", "n", "e", "m", "e", "s"],
     *       "priority": 8
     *     }
     *   }
     * }
     * ```
     *
     * @param {string} pathOrUrl - URL or path to a JSON dictionary file
     * @returns {Promise<CustomDictionary>}
     */
    static async fromJSON(pathOrUrl) {
        const response = await fetch(pathOrUrl);
        if (!response.ok) {
            throw new Error(
                `Failed to load dictionary from ${pathOrUrl}: ${response.status} ${response.statusText}`
            );
        }
        const data = await response.json();
        return CustomDictionary._fromParsed(data);
    }

    /**
     * Create a dictionary from an already-parsed JSON object.
     *
     * @param {object} data - Parsed dictionary JSON
     * @returns {CustomDictionary}
     */
    static fromObject(data) {
        return CustomDictionary._fromParsed(data);
    }

    /**
     * Internal: build dictionary from parsed JSON data.
     * @private
     * @param {object} data
     * @returns {CustomDictionary}
     */
    static _fromParsed(data) {
        if (!data.entries || typeof data.entries !== 'object') {
            throw new Error('Invalid dictionary format: missing "entries" object');
        }

        const dict = new CustomDictionary();
        const version = String(data.version || '1.0');

        for (const [word, entry] of Object.entries(data.entries)) {
            // Skip comment keys
            if (word.startsWith('//')) continue;

            if (version === '2.0' && entry !== null && typeof entry === 'object' && !Array.isArray(entry)) {
                // v2.0: { tokens: [...], priority?: number }
                const tokens = entry.tokens;
                if (!Array.isArray(tokens)) {
                    throw new Error(
                        `Invalid v2.0 entry for "${word}": "tokens" must be an array`
                    );
                }
                const priority = typeof entry.priority === 'number' ? entry.priority : 5;
                const caseSensitive = _isMixedCase(word);
                dict._addEntry(word, tokens, priority, caseSensitive);
            } else if (Array.isArray(entry)) {
                // v1.0: word -> [token, ...]
                const caseSensitive = _isMixedCase(word);
                dict._addEntry(word, entry, 5, caseSensitive);
            } else {
                throw new Error(
                    `Invalid entry for "${word}": expected an array (v1.0) or object (v2.0)`
                );
            }
        }

        dict._invalidateCache();
        return dict;
    }

    /**
     * Add or update a single entry.
     *
     * @param {string} word - The surface form to match
     * @param {string[]} tokens - Replacement phoneme tokens
     * @param {number} [priority=5] - Priority (0-10); higher wins on conflict
     */
    addEntry(word, tokens, priority = 5) {
        const caseSensitive = _isMixedCase(word);
        this._addEntry(word, tokens, priority, caseSensitive);
        this._invalidateCache();
    }

    /**
     * Remove an entry by word.
     *
     * @param {string} word
     * @returns {boolean} true if the entry existed and was removed
     */
    removeEntry(word) {
        const deleted =
            this._entries.delete(word) || this._entries.delete(word.toLowerCase());
        if (deleted) this._invalidateCache();
        return deleted;
    }

    /**
     * Check whether a word exists in the dictionary.
     *
     * @param {string} word
     * @returns {boolean}
     */
    has(word) {
        return this._entries.has(word) || this._entries.has(word.toLowerCase());
    }

    /**
     * Get the phoneme tokens for a word, or null.
     *
     * @param {string} word
     * @returns {string[]|null}
     */
    get(word) {
        const entry = this._entries.get(word) || this._entries.get(word.toLowerCase());
        return entry ? entry.tokens : null;
    }

    /**
     * Apply the dictionary to input text.
     *
     * Scans the text for dictionary entries (longest match first) and records
     * which words were matched along with their phoneme tokens.
     *
     * The returned `text` has matched words replaced with a placeholder
     * marker `\x00<index>\x00` so the caller can substitute phoneme tokens
     * at the right positions.  `replacements` is a Map from the matched
     * surface form to its phoneme token array.
     *
     * @param {string} text - Input text
     * @returns {{ text: string, replacements: Map<string, string[]> }}
     */
    apply(text) {
        if (this._entries.size === 0) {
            return { text, replacements: new Map() };
        }

        const keys = this._getSortedKeys();
        const replacements = new Map();
        let result = text;
        let placeholderIndex = 0;

        for (const key of keys) {
            const entry = this._entries.get(key);
            if (!entry) continue;

            const flags = entry.caseSensitive ? 'g' : 'gi';
            const pattern = new RegExp(_escapeRegExp(key), flags);

            result = result.replace(pattern, (match) => {
                replacements.set(match, entry.tokens);
                const placeholder = `\x00${placeholderIndex}\x00`;
                placeholderIndex++;
                return placeholder;
            });
        }

        return { text: result, replacements };
    }

    /**
     * Internal: add an entry to the map, respecting priority.
     * @private
     */
    _addEntry(word, tokens, priority, caseSensitive) {
        const key = caseSensitive ? word : word.toLowerCase();
        const existing = this._entries.get(key);
        if (!existing || priority >= existing.priority) {
            this._entries.set(key, { tokens, priority, caseSensitive });
        }
    }

    /**
     * Internal: invalidate the sorted-keys cache.
     * @private
     */
    _invalidateCache() {
        this._sortedKeys = null;
    }

    /**
     * Internal: get entry keys sorted longest-first (cached).
     * @private
     * @returns {string[]}
     */
    _getSortedKeys() {
        if (!this._sortedKeys) {
            this._sortedKeys = Array.from(this._entries.keys()).sort(
                (a, b) => b.length - a.length
            );
        }
        return this._sortedKeys;
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Check if a word has mixed uppercase and lowercase letters.
 * @param {string} word
 * @returns {boolean}
 */
function _isMixedCase(word) {
    return /[A-Z]/.test(word) && /[a-z]/.test(word);
}

/**
 * Escape special regex characters.
 * @param {string} str
 * @returns {string}
 */
function _escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
