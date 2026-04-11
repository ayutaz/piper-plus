/**
 * JapaneseG2P — Japanese Grapheme-to-Phoneme using OpenJTalk WASM.
 *
 * Provides phoneme extraction with optional prosody (A1/A2/A3) features.
 * OpenJTalk WASM module and dictionary are injected via DI pattern,
 * so this module has no dependency on onnxruntime-web.
 *
 * Usage:
 *   import { JapaneseG2P } from '@piper-plus/g2p/ja';
 *
 *   const ja = new JapaneseG2P({ openjtalkModule, jaDict: { dictFiles } });
 *   await ja.initialize();
 *
 *   const { tokens, prosody } = ja.phonemizeWithProsody('こんにちは');
 *   // tokens:  ['^', 'k', 'o', ...]
 *   // prosody: [null, { a1: -3, a2: 1, a3: 5 }, ...]
 */

import { extractPhonemesFromLabels } from './phoneme-extract.js';

/**
 * Dictionary file names required for OpenJTalk.
 * @type {string[]}
 */
const DICT_FILE_NAMES = [
    'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
    'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'
];

export { extractPhonemesFromLabels } from './phoneme-extract.js';

export class JapaneseG2P {
    /**
     * @param {Object} [options]
     * @param {Object} [options.openjtalkModule] - Pre-loaded OpenJTalk WASM module instance.
     *   If provided, initialize() will skip module loading.
     * @param {Object} [options.jaDict] - Dictionary data object.
     *   Must contain { dictFiles: { [filename]: ArrayBuffer } }
     */
    constructor(options = {}) {
        /** @private */
        this._openjtalkModule = options.openjtalkModule || null;
        /** @private */
        this._jaDict = options.jaDict || null;
        /** @private */
        this._initialized = false;
    }

    /**
     * Whether the OpenJTalk module is initialized and ready.
     * @returns {boolean}
     */
    get initialized() {
        return this._initialized;
    }

    /**
     * Initialize OpenJTalk WASM with dictionary data.
     *
     * The module and dictionary can be provided here or via the constructor.
     * Constructor values take precedence if both are provided.
     *
     * @param {Object} [options]
     * @param {Object} [options.openjtalkModule] - OpenJTalk WASM module instance
     * @param {Object} [options.jaDict] - { dictFiles: { [filename]: ArrayBuffer } }
     * @throws {Error} If openjtalkModule is not provided
     * @throws {Error} If required dictionary files are missing
     * @throws {Error} If OpenJTalk initialization fails
     */
    async initialize(options = {}) {
        const mod = this._openjtalkModule || options.openjtalkModule;
        const dict = this._jaDict || options.jaDict;

        if (!mod) {
            throw new Error(
                'openjtalkModule is required. ' +
                'Pass it via new JapaneseG2P({ openjtalkModule }) or initialize({ openjtalkModule }).'
            );
        }

        this._openjtalkModule = mod;

        // Load dictionary into the WASM filesystem
        if (dict) {
            this._loadDict(dict);
        }

        // Initialize OpenJTalk C API
        const dictPtr = mod.allocateUTF8('/dict');
        const result = mod._openjtalk_initialize(dictPtr);
        mod._free(dictPtr);

        if (result !== 0) {
            throw new Error(`OpenJTalk initialization failed with code: ${result}`);
        }

        this._initialized = true;
    }

    /**
     * Convert text to phoneme tokens (without prosody info).
     *
     * @param {string} text - Japanese text
     * @returns {{ tokens: string[], prosody: null[] }}
     *   tokens: PUA-mapped phoneme tokens
     *   prosody: array of null (same length as tokens, for API consistency)
     * @throws {Error} If not initialized
     * @throws {Error} If OpenJTalk returns an error
     */
    phonemize(text) {
        const { tokens } = this._synthesizeLabelsAndExtract(text);
        return { tokens, prosody: tokens.map(() => null) };
    }

    /**
     * Convert text to phoneme tokens with A1/A2/A3 prosody features.
     *
     * @param {string} text - Japanese text
     * @returns {{ tokens: string[], prosody: (ProsodyInfo | null)[] }}
     *   tokens: PUA-mapped phoneme tokens
     *   prosody: parallel array; ProsodyInfo { a1, a2, a3 } for phonemes,
     *            null for BOS/EOS/pause/markers
     * @throws {Error} If not initialized
     * @throws {Error} If OpenJTalk returns an error
     */
    phonemizeWithProsody(text) {
        return this._synthesizeLabelsAndExtract(text);
    }

    /**
     * Dispose resources and clear OpenJTalk state.
     */
    dispose() {
        if (this._openjtalkModule && this._openjtalkModule._openjtalk_clear) {
            this._openjtalkModule._openjtalk_clear();
        }
        this._initialized = false;
    }

    // ---- Private helpers ----

    /**
     * Call OpenJTalk to get full-context labels and extract phonemes + prosody.
     * @private
     * @param {string} text
     * @returns {{ tokens: string[], prosody: (ProsodyInfo | null)[] }}
     */
    _synthesizeLabelsAndExtract(text) {
        if (!this._initialized) {
            throw new Error('JapaneseG2P is not initialized. Call initialize() first.');
        }

        const mod = this._openjtalkModule;
        const textPtr = mod.allocateUTF8(text);
        const labelsPtr = mod._openjtalk_synthesis_labels(textPtr);
        const labels = mod.UTF8ToString(labelsPtr);

        mod._openjtalk_free_string(labelsPtr);
        mod._free(textPtr);

        if (labels.startsWith('ERROR:')) {
            throw new Error(`OpenJTalk synthesis failed: ${labels}`);
        }

        return extractPhonemesFromLabels(labels);
    }

    /**
     * Write dictionary files into the WASM filesystem.
     * @private
     * @param {Object} dict - { dictFiles: { [filename]: ArrayBuffer } }
     */
    _loadDict(dict) {
        const mod = this._openjtalkModule;
        const dictFiles = dict.dictFiles || dict.dictData;

        if (!dictFiles) {
            throw new Error(
                'jaDict must have { dictFiles: { [filename]: ArrayBuffer } }.'
            );
        }

        // Validate all required dict files
        const missing = DICT_FILE_NAMES.filter(f => !(dictFiles[f] instanceof ArrayBuffer));
        if (missing.length > 0) {
            throw new Error(
                `Missing required dictionary files: ${missing.join(', ')}. ` +
                'All 8 OpenJTalk dictionary files must be provided.'
            );
        }

        // Create directories (ignore if already exist)
        try { mod.FS.mkdir('/dict'); } catch (_) { /* exists */ }

        for (const file of DICT_FILE_NAMES) {
            mod.FS.writeFile(`/dict/${file}`, new Uint8Array(dictFiles[file]));
        }
    }
}
