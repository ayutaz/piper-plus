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
