/**
 * G2P integration class tests
 *
 * Validates the unified G2P class that coordinates language detection,
 * phonemization, encoding, and resource management.
 *
 * Note: Japanese tests require OpenJTalk WASM + dictionary, so they are
 * skipped when WASM is not available. Non-JA languages work without WASM.
 *
 * Run: node --test src/wasm/g2p/test/test-g2p.js
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { G2P } from '../src/index.js';

// ---------------------------------------------------------------------------
// G2P.create() -- factory
// ---------------------------------------------------------------------------

describe('G2P.create', () => {
    it('should create instance with non-JA languages only', async () => {
        const g2p = await G2P.create({ languages: ['en', 'zh', 'es', 'fr', 'pt'] });
        assert.ok(g2p);
        g2p.dispose();
    });

    it('should create instance with single language', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        assert.ok(g2p);
        g2p.dispose();
    });

    it('should throw for empty languages array', async () => {
        await assert.rejects(
            () => G2P.create({ languages: [] }),
            /no valid languages/
        );
    });

    it('should filter out invalid language codes', async () => {
        const g2p = await G2P.create({ languages: ['en', 'invalid', 'xx'] });
        assert.ok(g2p);
        g2p.dispose();
    });

    it('should throw if all language codes are invalid', async () => {
        await assert.rejects(
            () => G2P.create({ languages: ['invalid', 'xx'] }),
            /no valid languages/
        );
    });

    it('should create instance with Korean only', async () => {
        const g2p = await G2P.create({ languages: ['ko'] });
        assert.ok(g2p);
        const result = g2p.phonemize('\uD55C\uAD6D\uC5B4', { language: 'ko' }); // 한국어
        assert.ok(result.tokens.length > 0, 'should phonemize Korean text');
        assert.equal(result.language, 'ko');
        g2p.dispose();
    });

    it('should create instance with Swedish only', async () => {
        const g2p = await G2P.create({ languages: ['sv'] });
        assert.ok(g2p);
        const result = g2p.phonemize('hej', { language: 'sv' });
        assert.ok(result.tokens.length > 0, 'should phonemize Swedish text');
        assert.equal(result.language, 'sv');
        g2p.dispose();
    });

    it('should create multilingual instance with ko, sv, and en', async () => {
        const g2p = await G2P.create({ languages: ['ko', 'sv', 'en'] });
        assert.ok(g2p);
        // Verify all three languages are functional
        const koResult = g2p.phonemize('\uAC00', { language: 'ko' }); // 가
        assert.ok(koResult.tokens.length > 0);
        const svResult = g2p.phonemize('hej', { language: 'sv' });
        assert.ok(svResult.tokens.length > 0);
        const enResult = g2p.phonemize('hello', { language: 'en' });
        assert.ok(enResult.tokens.length > 0);
        g2p.dispose();
    });
});

// ---------------------------------------------------------------------------
// detectLanguage()
// ---------------------------------------------------------------------------

describe('G2P.detectLanguage', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ['en', 'zh', 'es', 'fr', 'pt'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should detect English text', () => {
        assert.equal(g2p.detectLanguage('Hello world'), 'en');
    });

    it('should detect Chinese text', () => {
        assert.equal(g2p.detectLanguage('你好世界'), 'zh');
    });

    it('should default to en for Latin text', () => {
        assert.equal(g2p.detectLanguage('Bonjour'), 'en');
    });

    it('should handle empty string', () => {
        const result = g2p.detectLanguage('');
        assert.equal(typeof result, 'string');
    });
});

describe('G2P.detectLanguage (ko)', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ['ko', 'en'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should detect Korean for Hangul text', () => {
        assert.equal(g2p.detectLanguage('\uD55C\uAD6D\uC5B4'), 'ko'); // 한국어
    });

    it('should detect Korean for mixed Hangul text', () => {
        assert.equal(g2p.detectLanguage('\uC548\uB155\uD558\uC138\uC694 hello'), 'ko'); // 안녕하세요 hello
    });
});

describe('G2P.detectLanguage (sv)', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ['sv', 'en'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should detect Swedish for text dominated by \u00e5/\u00e4/\u00f6', () => {
        // å ä ö are Swedish-specific chars; when they outnumber plain Latin chars
        // the detector returns 'sv'
        assert.equal(g2p.detectLanguage('\u00e5\u00e4\u00f6'), 'sv'); // åäö
    });

    it('should detect Swedish for short word with \u00e5/\u00e4/\u00f6', () => {
        assert.equal(g2p.detectLanguage('\u00f6l'), 'sv'); // öl
    });
});

// ---------------------------------------------------------------------------
// segmentText()
// ---------------------------------------------------------------------------

describe('G2P.segmentText', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ['en', 'zh'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should return array of segments', () => {
        const segments = g2p.segmentText('Hello你好');
        assert.ok(Array.isArray(segments));
        assert.ok(segments.length >= 2);
    });

    it('should return segments with language and text', () => {
        const segments = g2p.segmentText('Hello你好');
        for (const seg of segments) {
            assert.ok('language' in seg);
            assert.ok('text' in seg);
        }
    });

    it('should return empty array for empty string', () => {
        const segments = g2p.segmentText('');
        assert.deepEqual(segments, []);
    });

    it('should return single segment for uniform text', () => {
        const segments = g2p.segmentText('Hello world');
        assert.equal(segments.length, 1);
        assert.equal(segments[0].language, 'en');
    });
});

// ---------------------------------------------------------------------------
// phonemize() -- non-JA languages
// ---------------------------------------------------------------------------

describe('G2P.phonemize (non-JA)', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ['en', 'zh', 'es', 'fr', 'pt'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should phonemize English text', () => {
        const result = g2p.phonemize('Hello', { language: 'en' });
        assert.ok(Array.isArray(result.tokens));
        assert.ok(result.tokens.length > 0);
        assert.equal(result.language, 'en');
    });

    it('should auto-detect English', () => {
        const result = g2p.phonemize('Hello world');
        assert.equal(result.language, 'en');
    });

    it('should phonemize Chinese text', () => {
        const result = g2p.phonemize('你好', { language: 'zh' });
        assert.ok(result.tokens.length > 0);
        assert.equal(result.language, 'zh');
    });

    it('should auto-detect Chinese', () => {
        const result = g2p.phonemize('你好世界');
        assert.equal(result.language, 'zh');
    });

    it('should phonemize with explicit language override', () => {
        const result = g2p.phonemize('hola', { language: 'es' });
        assert.equal(result.language, 'es');
        assert.ok(result.tokens.length > 0);
    });

    it('should return { tokens, prosody, language } structure', () => {
        const result = g2p.phonemize('test', { language: 'en' });
        assert.ok('tokens' in result);
        assert.ok('prosody' in result);
        assert.ok('language' in result);
    });

    it('should throw for uninitialised language', () => {
        assert.throws(
            () => g2p.phonemize('test', { language: 'ja' }),
            /not initialised/
        );
    });
});

// ---------------------------------------------------------------------------
// phonemizeWithProsody() -- non-JA languages
// ---------------------------------------------------------------------------

describe('G2P.phonemizeWithProsody (non-JA)', () => {
    let g2p;

    before(async () => {
        g2p = await G2P.create({ languages: ['en'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should return { tokens, prosody, language }', () => {
        const result = g2p.phonemizeWithProsody('hello', { language: 'en' });
        assert.ok('tokens' in result);
        assert.ok('prosody' in result);
        assert.ok('language' in result);
    });

    it('should have prosody array matching tokens length', () => {
        const result = g2p.phonemizeWithProsody('hello', { language: 'en' });
        assert.equal(result.tokens.length, result.prosody.length);
    });
});

// ---------------------------------------------------------------------------
// encode() -- non-JA languages
// ---------------------------------------------------------------------------

describe('G2P.encode (non-JA)', () => {
    let g2p;
    const testMap = {
        '^': [1], '$': [2], '_': [0],
        'h': [10], 'e': [11], 'l': [12], 'o': [13],
        '\u02C8': [14],  // primary stress
        '\u028C': [15],  // ʌ
    };

    before(async () => {
        g2p = await G2P.create({ languages: ['en'] });
    });

    after(() => {
        if (g2p) g2p.dispose();
    });

    it('should return { phonemeIds, prosodyFlat }', () => {
        const result = g2p.encode('hello', testMap, { language: 'en' });
        assert.ok('phonemeIds' in result);
        assert.ok('prosodyFlat' in result);
    });

    it('should produce array of integers for phonemeIds', () => {
        const { phonemeIds } = g2p.encode('hello', testMap, { language: 'en' });
        assert.ok(Array.isArray(phonemeIds));
        assert.ok(phonemeIds.length > 0);
        assert.ok(phonemeIds.every(id => typeof id === 'number'));
    });

    it('should start with BOS and end with EOS', () => {
        const { phonemeIds } = g2p.encode('hello', testMap, { language: 'en' });
        assert.equal(phonemeIds[0], 1, 'first ID should be BOS (1)');
        assert.equal(phonemeIds[phonemeIds.length - 1], 2, 'last ID should be EOS (2)');
    });
});

// ---------------------------------------------------------------------------
// dispose()
// ---------------------------------------------------------------------------

describe('G2P.dispose', () => {
    it('should not throw on double dispose', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        g2p.dispose();
        g2p.dispose(); // second call should be safe
    });

    it('should throw on phonemize after dispose', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        g2p.dispose();
        assert.throws(
            () => g2p.phonemize('test'),
            /disposed/
        );
    });

    it('should throw on detectLanguage after dispose', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        g2p.dispose();
        assert.throws(
            () => g2p.detectLanguage('test'),
            /disposed/
        );
    });

    it('should throw on segmentText after dispose', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        g2p.dispose();
        assert.throws(
            () => g2p.segmentText('test'),
            /disposed/
        );
    });

    it('should throw on encode after dispose', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        g2p.dispose();
        assert.throws(
            () => g2p.encode('test', { '^': [1], '$': [2], '_': [0] }),
            /disposed/
        );
    });

    it('should throw on phonemizeWithProsody after dispose', async () => {
        const g2p = await G2P.create({ languages: ['en'] });
        g2p.dispose();
        assert.throws(
            () => g2p.phonemizeWithProsody('test'),
            /disposed/
        );
    });
});

// ---------------------------------------------------------------------------
// JA tests -- skipped unless OpenJTalk WASM is available
// ---------------------------------------------------------------------------

describe('G2P with Japanese (WASM required)', { skip: 'OpenJTalk WASM not available in Node.js test environment' }, () => {
    it('should create instance with ja language', async () => {
        // This would require: jaDict and openjtalkModule
        const g2p = await G2P.create({
            languages: ['ja', 'en'],
            // jaDict: dictData,
            // openjtalkModule: wasmModule,
        });
        assert.ok(g2p);
        g2p.dispose();
    });

    it('should phonemize Japanese text', async () => {
        // Placeholder -- requires WASM
    });
});
