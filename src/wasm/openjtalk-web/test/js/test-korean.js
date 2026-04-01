/**
 * Korean language support tests for SimpleUnifiedPhonemizer.
 *
 * Verifies Hangul detection, Jamo decomposition, and Korean phonemization,
 * consistent with the Python/Rust/C#/C++ implementations.
 *
 * Run with: node --test test/js/test-korean.js
 */

import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { SimpleUnifiedPhonemizer } from '../../src/simple_unified_api.js';

/** Helper: create a phonemizer instance (no OpenJTalk init needed for detection). */
function createPhonemizer() {
    const p = new SimpleUnifiedPhonemizer();
    return p;
}

/**
 * Helper: create a mock phoneme_id_map that maps Hangul Compatibility Jamo
 * and common characters to sequential IDs.
 */
function createKoreanPhonemeIdMap() {
    const map = {};
    // Map Compatibility Jamo (U+3131..U+3163) to sequential IDs starting at 10
    for (let code = 0x3131; code <= 0x3163; code++) {
        map[String.fromCharCode(code)] = [code - 0x3131 + 10];
    }
    // Space
    map[' '] = [3];
    // Common punctuation
    map[','] = [4];
    map['.'] = [5];
    map['!'] = [6];
    map['?'] = [7];
    // Some Latin characters for mixed-text tests
    map['a'] = [100];
    map['b'] = [101];
    map['c'] = [102];
    return map;
}

// ---------------------------------------------------------------------------
// 1. Hangul Syllable character detection
// ---------------------------------------------------------------------------

describe('Korean: Hangul Syllable detection', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should detect single Hangul syllable (U+AC00, 가)', () => {
        assert.strictEqual(p.detectLanguage('\uAC00'), 'ko');
    });

    it('should detect "한글"', () => {
        assert.strictEqual(p.detectLanguage('한글'), 'ko');
    });

    it('should detect "안녕하세요"', () => {
        assert.strictEqual(p.detectLanguage('안녕하세요'), 'ko');
    });

    it('should detect last Hangul syllable (U+D7A3)', () => {
        assert.strictEqual(p.detectLanguage('\uD7A3'), 'ko');
    });

    it('should detect "서울"', () => {
        assert.strictEqual(p.detectLanguage('서울'), 'ko');
    });

    it('should detect "대한민국"', () => {
        assert.strictEqual(p.detectLanguage('대한민국'), 'ko');
    });
});

// ---------------------------------------------------------------------------
// 2. Hangul Compatibility Jamo detection
// ---------------------------------------------------------------------------

describe('Korean: Hangul Compatibility Jamo detection', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should detect Jamo ㄱ (U+3131)', () => {
        assert.strictEqual(p.detectLanguage('\u3131'), 'ko');
    });

    it('should detect Jamo ㅎ (U+314E)', () => {
        assert.strictEqual(p.detectLanguage('\u314E'), 'ko');
    });

    it('should detect Jamo ㅏ (U+314F)', () => {
        assert.strictEqual(p.detectLanguage('\u314F'), 'ko');
    });

    it('should detect Jamo ㅣ (U+3163)', () => {
        assert.strictEqual(p.detectLanguage('\u3163'), 'ko');
    });
});

// ---------------------------------------------------------------------------
// 3. Korean + English mixed text segmentation
// ---------------------------------------------------------------------------

describe('Korean: Mixed text segmentation', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should segment Korean and English separately', () => {
        const segments = p._segmentText('안녕 hello');
        assert.ok(segments.length >= 2, `expected >= 2 segments, got ${segments.length}`);
        assert.strictEqual(segments[0].lang, 'ko');
    });

    it('should return ko as first significant language for KO-first text', () => {
        assert.strictEqual(p.detectLanguage('안녕하세요 hello'), 'ko');
    });

    it('should return en when English comes first', () => {
        assert.strictEqual(p.detectLanguage('hello 안녕하세요'), 'en');
    });

    it('should segment Korean and Japanese separately', () => {
        const segments = p._segmentText('안녕 こんにちは');
        assert.ok(segments.length >= 2);
        assert.strictEqual(segments[0].lang, 'ko');
        const jaSeg = segments.find(s => s.lang === 'ja');
        assert.ok(jaSeg, 'should have a ja segment');
    });

    it('should segment Korean and Chinese separately', () => {
        // No kana present, so CJK -> zh
        const segments = p._segmentText('안녕 你好');
        assert.ok(segments.length >= 2);
        assert.strictEqual(segments[0].lang, 'ko');
        const zhSeg = segments.find(s => s.lang === 'zh');
        assert.ok(zhSeg, 'should have a zh segment');
    });
});

// ---------------------------------------------------------------------------
// 4. phonemizeKorean() basic operation
// ---------------------------------------------------------------------------

describe('Korean: phonemizeKorean() basic', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should return BOS and EOS for empty string', () => {
        const ids = p.phonemizeKorean('');
        assert.deepStrictEqual(ids, [1, 2]); // BOS, EOS
    });

    it('should produce phoneme IDs with BOS and EOS', () => {
        const ids = p.phonemizeKorean('가');
        assert.strictEqual(ids[0], 1); // BOS
        assert.strictEqual(ids[ids.length - 1], 2); // EOS
        assert.ok(ids.length > 2, 'should have phoneme IDs between BOS and EOS');
    });

    it('should handle space between words', () => {
        const ids = p.phonemizeKorean('가 나');
        // Should contain space mapping (ID 3)
        assert.ok(ids.includes(3), 'should contain space ID');
    });
});

// ---------------------------------------------------------------------------
// 5. Hangul decomposition accuracy
// ---------------------------------------------------------------------------

describe('Korean: Hangul decomposition accuracy', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should decompose 가 (U+AC00) = ㄱ + ㅏ (no final)', () => {
        // 가: initial=ㄱ(0x3131), medial=ㅏ(0x314F), final=none
        const ids = p.phonemizeKorean('가');
        // BOS=1, ㄱ_id + PAD, ㅏ_id + PAD, EOS=2
        const giyeokId = phonemeIdMap['\u3131'][0]; // ㄱ
        const aId = phonemeIdMap['\u314F'][0]; // ㅏ
        assert.deepStrictEqual(ids, [1, giyeokId, 0, aId, 0, 2]);
    });

    it('should decompose 한 (U+D55C) = ㅎ + ㅏ + ㄴ', () => {
        // 한: initial=ㅎ(0x314E), medial=ㅏ(0x314F), final=ㄴ(0x3134)
        const ids = p.phonemizeKorean('한');
        const hieuhId = phonemeIdMap['\u314E'][0]; // ㅎ
        const aId = phonemeIdMap['\u314F'][0]; // ㅏ
        const nieunId = phonemeIdMap['\u3134'][0]; // ㄴ
        assert.deepStrictEqual(ids, [1, hieuhId, 0, aId, 0, nieunId, 0, 2]);
    });

    it('should decompose 글 = ㄱ + ㅡ + ㄹ', () => {
        // 글 (U+AE00): initial=ㄱ, medial=ㅡ(0x3161), final=ㄹ(0x3139)
        const ids = p.phonemizeKorean('글');
        const giyeokId = phonemeIdMap['\u3131'][0]; // ㄱ
        const euId = phonemeIdMap['\u3161'][0]; // ㅡ
        const rieulId = phonemeIdMap['\u3139'][0]; // ㄹ
        assert.deepStrictEqual(ids, [1, giyeokId, 0, euId, 0, rieulId, 0, 2]);
    });

    it('should decompose syllable without final consonant: 나 = ㄴ + ㅏ', () => {
        // 나 (U+B098): initial=ㄴ(0x3134), medial=ㅏ(0x314F), final=none
        const ids = p.phonemizeKorean('나');
        const nieunId = phonemeIdMap['\u3134'][0]; // ㄴ
        const aId = phonemeIdMap['\u314F'][0]; // ㅏ
        assert.deepStrictEqual(ids, [1, nieunId, 0, aId, 0, 2]);
    });

    it('should decompose 힣 (U+D7A3, last Hangul syllable) = ㅎ + ㅣ + ㅎ', () => {
        // U+D7A3: initial=ㅎ(18), medial=ㅣ(20), final=ㅎ(27)
        const ids = p.phonemizeKorean('\uD7A3');
        const hieuhId = phonemeIdMap['\u314E'][0]; // ㅎ
        const iId = phonemeIdMap['\u3163'][0]; // ㅣ
        assert.deepStrictEqual(ids, [1, hieuhId, 0, iId, 0, hieuhId, 0, 2]);
    });

    it('should handle multi-syllable word: 한글 = ㅎ+ㅏ+ㄴ ㄱ+ㅡ+ㄹ', () => {
        const ids = p.phonemizeKorean('한글');
        // Should have BOS + 6 jamo entries (each with PAD) + EOS
        // 3 jamo for 한 + 3 jamo for 글 = 6 jamo, each with PAD = 12 + BOS + EOS = 14
        assert.strictEqual(ids.length, 14);
        assert.strictEqual(ids[0], 1); // BOS
        assert.strictEqual(ids[ids.length - 1], 2); // EOS
    });
});

// ---------------------------------------------------------------------------
// 6. Space handling
// ---------------------------------------------------------------------------

describe('Korean: Space handling', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should map space character using phoneme_id_map', () => {
        const idsWithSpace = p.phonemizeKorean('가 나');
        const idsNoSpace = p.phonemizeKorean('가나');
        // With space should be longer
        assert.ok(idsWithSpace.length > idsNoSpace.length);
    });

    it('should handle multiple spaces', () => {
        const ids = p.phonemizeKorean('가  나');
        // Two spaces, both mapped
        assert.strictEqual(ids[0], 1); // BOS
        assert.strictEqual(ids[ids.length - 1], 2); // EOS
    });

    it('should handle leading and trailing spaces', () => {
        const ids = p.phonemizeKorean(' 가 ');
        assert.strictEqual(ids[0], 1); // BOS
        assert.strictEqual(ids[ids.length - 1], 2); // EOS
    });
});

// ---------------------------------------------------------------------------
// 7. Punctuation handling
// ---------------------------------------------------------------------------

describe('Korean: Punctuation handling', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should include comma in output when in phoneme_id_map', () => {
        const ids = p.phonemizeKorean('가,');
        const commaId = phonemeIdMap[','][0];
        assert.ok(ids.includes(commaId), 'should contain comma ID');
    });

    it('should include period in output', () => {
        const ids = p.phonemizeKorean('가.');
        const periodId = phonemeIdMap['.'][0];
        assert.ok(ids.includes(periodId), 'should contain period ID');
    });

    it('should include exclamation mark in output', () => {
        const ids = p.phonemizeKorean('가!');
        const exclId = phonemeIdMap['!'][0];
        assert.ok(ids.includes(exclId), 'should contain exclamation ID');
    });

    it('should include question mark in output', () => {
        const ids = p.phonemizeKorean('가?');
        const questionId = phonemeIdMap['?'][0];
        assert.ok(ids.includes(questionId), 'should contain question ID');
    });

    it('should skip unknown characters not in phoneme_id_map', () => {
        const idsBase = p.phonemizeKorean('가');
        const idsWithUnknown = p.phonemizeKorean('가@');
        // @ is not in the map, so should be skipped — same length
        assert.deepStrictEqual(idsWithUnknown, idsBase);
    });
});

// ---------------------------------------------------------------------------
// 8. Error handling
// ---------------------------------------------------------------------------

describe('Korean: Error handling', () => {
    let p;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        // No phonemeIdMap set
    });

    it('should throw when phonemeIdMap is not set', () => {
        assert.throws(
            () => p.phonemizeKorean('안녕'),
            /phonemeIdMap is required/
        );
    });
});

// ---------------------------------------------------------------------------
// 9. Non-Hangul passthrough
// ---------------------------------------------------------------------------

describe('Korean: Non-Hangul character passthrough', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should pass Latin characters through phoneme_id_map', () => {
        const ids = p.phonemizeKorean('abc');
        const aId = phonemeIdMap['a'][0];
        const bId = phonemeIdMap['b'][0];
        const cId = phonemeIdMap['c'][0];
        assert.deepStrictEqual(ids, [1, aId, 0, bId, 0, cId, 0, 2]);
    });

    it('should pass Jamo characters directly through phoneme_id_map', () => {
        const ids = p.phonemizeKorean('\u3131'); // ㄱ as standalone
        const giyeokId = phonemeIdMap['\u3131'][0];
        assert.deepStrictEqual(ids, [1, giyeokId, 0, 2]);
    });
});

// ---------------------------------------------------------------------------
// 10. extractPhonemes passthrough
// ---------------------------------------------------------------------------

describe('Korean: extractPhonemes passthrough', () => {
    let p;
    beforeEach(() => { p = createPhonemizer(); });

    it('should pass through phoneme ID array for Korean', () => {
        const ids = [1, 10, 0, 20, 0, 2];
        const result = p.extractPhonemes(ids, 'ko');
        assert.deepStrictEqual(result, ids);
    });
});

// ---------------------------------------------------------------------------
// 11. getPhonemeIdMap returns model map for Korean
// ---------------------------------------------------------------------------

describe('Korean: getPhonemeIdMap', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should return the model phonemeIdMap for Korean', () => {
        assert.strictEqual(p.getPhonemeIdMap('ko'), phonemeIdMap);
    });
});

// ---------------------------------------------------------------------------
// 12. textToPhonemes integration
// ---------------------------------------------------------------------------

describe('Korean: textToPhonemes integration', () => {
    let p;
    let phonemeIdMap;
    beforeEach(() => {
        p = createPhonemizer();
        p.initialized = true;
        phonemeIdMap = createKoreanPhonemeIdMap();
        p.setPhonemeIdMap(phonemeIdMap);
    });

    it('should route to phonemizeKorean when language is ko', async () => {
        const ids = await p.textToPhonemes('가', 'ko');
        assert.ok(Array.isArray(ids));
        assert.strictEqual(ids[0], 1); // BOS
        assert.strictEqual(ids[ids.length - 1], 2); // EOS
    });

    it('should auto-detect Korean and produce phoneme IDs', async () => {
        const ids = await p.textToPhonemes('안녕하세요');
        assert.ok(Array.isArray(ids));
        assert.strictEqual(ids[0], 1); // BOS
        assert.strictEqual(ids[ids.length - 1], 2); // EOS
    });
});
