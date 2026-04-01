/**
 * Encoder — converts IPA token sequences into Piper phoneme ID arrays.
 *
 * Handles BOS/EOS/PAD insertion and optional prosody feature alignment.
 * The phoneme_id_map comes from the model's config.json.
 *
 * @module encode
 */

import { PUA_MAP } from './pua-map.js';

/**
 * Encoder for converting phoneme tokens to integer ID sequences
 * compatible with Piper TTS ONNX models.
 */
export class Encoder {
    /**
     * @param {Record<string, number[]>} phonemeIdMap
     * @param {{ strict?: boolean }} [options]
     */
    constructor(phonemeIdMap, options = {}) {
        if (!phonemeIdMap || typeof phonemeIdMap !== 'object') {
            throw new Error('phonemeIdMap is required and must be an object');
        }
        this._map = phonemeIdMap;
        this._strict = options.strict === true;

        // Build unified lookup Map: original keys + PUA reverse entries.
        // For each PUA_MAP entry (e.g. "ch" -> "\uE00E"), if the PUA char
        // exists in phonemeIdMap, register the multi-char source token too.
        // This eliminates the per-call mapToken() fallback in _lookupToken().
        this._lookupMap = new Map();
        for (const [key, ids] of Object.entries(phonemeIdMap)) {
            this._lookupMap.set(key, ids);
        }
        for (const [srcToken, puaChar] of Object.entries(PUA_MAP)) {
            if (!this._lookupMap.has(srcToken)) {
                const ids = phonemeIdMap[puaChar];
                if (ids) {
                    this._lookupMap.set(srcToken, ids);
                }
            }
        }

        this._bos = this._resolveId('^', 'BOS');
        this._eos = this._resolveId('$', 'EOS');
        this._pad = this._resolveId('_', 'PAD');
    }

    /**
     * Resolve a special token to its first ID value.
     * @private
     */
    _resolveId(token, label) {
        const ids = this._lookupMap.get(token);
        if (!ids || ids.length === 0) {
            throw new Error(
                `phonemeIdMap is missing required '${token}' (${label}) entry`
            );
        }
        return ids[0];
    }

    /**
     * Look up a token in the unified lookup map.
     * PUA reverse mappings are pre-indexed at construction time,
     * so no per-call mapToken() overhead.
     * @private
     * @param {string} token
     * @returns {number[]|null} Array of IDs, or null if not found
     */
    _lookupToken(token) {
        return this._lookupMap.get(token) ?? null;
    }

    /**
     * Encode a token sequence into phoneme IDs.
     *
     * The output format is:
     *   BOS + token0_ids + PAD + token1_ids + PAD + ... + tokenN_ids + PAD + EOS
     *
     * @param {string[]} tokens - Array of IPA phoneme tokens (no BOS/EOS)
     * @returns {{ phonemeIds: number[] }}
     */
    encode(tokens) {
        const ids = [this._bos];

        for (let i = 0; i < tokens.length; i++) {
            const tokenIds = this._lookupToken(tokens[i]);
            if (tokenIds) {
                ids.push(...tokenIds);
            } else if (this._strict) {
                throw new Error(
                    `Unknown phoneme symbol "${tokens[i]}" not in phonemeIdMap`
                );
            }
            // Insert PAD between tokens and after the last token
            ids.push(this._pad);
        }

        ids.push(this._eos);

        return { phonemeIds: ids };
    }

    /**
     * Encode a token sequence into phoneme IDs with aligned prosody features.
     *
     * Each phoneme ID is assigned prosody values [a1, a2, a3].
     * The returned prosodyFlat is a flat array: [a1,a2,a3, a1,a2,a3, ...]
     * with length = phonemeIds.length * 3.
     *
     * - BOS/EOS/PAD positions get [0, 0, 0].
     * - Each token's IDs all get the same prosody from the corresponding
     *   entry in the prosody array.
     *
     * @param {string[]} tokens - Array of IPA phoneme tokens (no BOS/EOS)
     * @param {Array<{a1: number, a2: number, a3: number}|null>|null} prosody
     *   Per-token prosody info. Must have same length as tokens, or be null.
     *   Null entries or a null array result in [0,0,0] for all positions.
     * @returns {{ phonemeIds: number[], prosodyFlat: number[]|null }}
     */
    encodeWithProsody(tokens, prosody) {
        if (!prosody) {
            const result = this.encode(tokens);
            return { phonemeIds: result.phonemeIds, prosodyFlat: null };
        }

        if (prosody.length !== tokens.length) {
            throw new Error(
                `prosody length (${prosody.length}) must match tokens length (${tokens.length})`
            );
        }

        const ids = [];
        const flat = [];

        // BOS
        ids.push(this._bos);
        flat.push(0, 0, 0);

        for (let i = 0; i < tokens.length; i++) {
            const p = prosody[i];
            const a1 = p ? p.a1 : 0;
            const a2 = p ? p.a2 : 0;
            const a3 = p ? p.a3 : 0;

            const tokenIds = this._lookupToken(tokens[i]);
            if (tokenIds) {
                for (const id of tokenIds) {
                    ids.push(id);
                    flat.push(a1, a2, a3);
                }
            } else if (this._strict) {
                throw new Error(
                    `Unknown phoneme symbol "${tokens[i]}" not in phonemeIdMap`
                );
            }

            // PAD after each token
            ids.push(this._pad);
            flat.push(0, 0, 0);
        }

        // EOS
        ids.push(this._eos);
        flat.push(0, 0, 0);

        return { phonemeIds: ids, prosodyFlat: flat };
    }
}
