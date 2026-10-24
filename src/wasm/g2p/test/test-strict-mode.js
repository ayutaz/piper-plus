import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { Encoder } from '../src/encode.js';

const MINIMAL_MAP = {
    '_': [0], '^': [1], '$': [2],
    'a': [3], 'k': [4],
};

describe('Encoder strict mode', () => {
    it('throws on unknown token in strict mode', () => {
        const encoder = new Encoder(MINIMAL_MAP, { strict: true });
        assert.throws(
            () => encoder.encode(['a', 'UNKNOWN', 'k']),
            { message: /Unknown phoneme symbol "UNKNOWN"/ }
        );
    });

    it('skips unknown token in non-strict mode', () => {
        const encoder = new Encoder(MINIMAL_MAP, { strict: false });
        const result = encoder.encode(['a', 'UNKNOWN', 'k']);
        assert.ok(result.phonemeIds.includes(3));
        assert.ok(result.phonemeIds.includes(4));
    });

    it('defaults to non-strict', () => {
        const encoder = new Encoder(MINIMAL_MAP);
        const result = encoder.encode(['a', 'UNKNOWN', 'k']);
        assert.ok(result.phonemeIds.length > 0);
    });

    it('strict works with valid tokens', () => {
        const encoder = new Encoder(MINIMAL_MAP, { strict: true });
        const result = encoder.encode(['a', 'k']);
        assert.ok(result.phonemeIds.includes(3));
        assert.ok(result.phonemeIds.includes(4));
    });

    it('strict throws in encodeWithProsody', () => {
        const encoder = new Encoder(MINIMAL_MAP, { strict: true });
        assert.throws(
            () => encoder.encodeWithProsody(['a', 'UNKNOWN'], [null, null]),
            { message: /Unknown phoneme symbol/ }
        );
    });
});

describe('Encoder droppedSymbols', () => {
    it('lists tokens missing from the map once, in first-seen order', () => {
        const encoder = new Encoder(MINIMAL_MAP);
        const result = encoder.encode(['a', 'Z', ' ', 'k', 'Z']);
        assert.deepEqual(result.droppedSymbols, ['Z', ' ']);
        assert.deepEqual(result.phonemeIds, [1, 3, 0, 0, 0, 4, 0, 0, 2]);
    });

    it('is empty when every token is mapped', () => {
        const encoder = new Encoder(MINIMAL_MAP);
        assert.deepEqual(encoder.encode(['a', 'k']).droppedSymbols, []);
    });

    it('is reported by encodeWithProsody with and without prosody', () => {
        const encoder = new Encoder(MINIMAL_MAP);
        const withProsody = encoder.encodeWithProsody(['a', 'Z'], [null, null]);
        assert.deepEqual(withProsody.droppedSymbols, ['Z']);
        const withoutProsody = encoder.encodeWithProsody(['Z', 'a'], null);
        assert.deepEqual(withoutProsody.droppedSymbols, ['Z']);
    });
});
