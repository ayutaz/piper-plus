/**
 * Korean G2P tests
 *
 * Validates Hangul decomposition + IPA mapping (ported from Rust korean.rs).
 * Tests: Hangul decomposition, single syllables, tense/aspirated consonants,
 * unreleased finals, liaison rules, diphthongs, mixed text, prosody structure.
 *
 * Run: node --test src/wasm/g2p/test/test-korean.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { KoreanG2P } from '../src/ko/index.js';

// ---------------------------------------------------------------------------
// PUA codepoints -- must match pua-map.js / Rust token_map.rs
// ---------------------------------------------------------------------------

// Aspirated consonants (shared with Chinese)
const PUA_PH  = '\uE020'; // pʰ
const PUA_TH  = '\uE021'; // tʰ
const PUA_KH  = '\uE022'; // kʰ

// Affricates (shared with Chinese)
const PUA_TC  = '\uE023'; // tɕ
const PUA_TCH = '\uE024'; // tɕʰ

// Tense consonants (Korean-only)
const PUA_PP   = '\uE04B'; // p͈
const PUA_TT   = '\uE04C'; // t͈
const PUA_KK   = '\uE04D'; // k͈
const PUA_SS   = '\uE04E'; // s͈
const PUA_TTCH = '\uE04F'; // t͈ɕ

// Unreleased finals (Korean-only)
const PUA_K_UNREL = '\uE050'; // k̚
const PUA_T_UNREL = '\uE051'; // t̚
const PUA_P_UNREL = '\uE052'; // p̚

// Single IPA codepoints
const IPA_FLAP          = '\u027E'; // ɾ  alveolar flap (ㄹ initial)
const IPA_ENG           = '\u014B'; // ŋ  velar nasal (ㅇ coda)
const IPA_OPEN_E        = '\u025B'; // ɛ  open-mid front unrounded (ㅐ)
const IPA_OPEN_MID_BACK = '\u028C'; // ʌ  open-mid back unrounded (ㅓ)
const IPA_CLOSE_BACK_UNR = '\u026F'; // ɯ  close back unrounded (ㅡ)
const IPA_VELAR_APPROX  = '\u0270'; // ɰ  velar approximant (ㅢ)

// ---------------------------------------------------------------------------
// Helper: check that a token array contains a specific phoneme
// ---------------------------------------------------------------------------

function hasToken(tokens, token) {
    return tokens.includes(token);
}

// ===========================================================================
// Basic API structure
// ===========================================================================

describe('KoreanG2P -- API structure', () => {
    it('should return { tokens, prosody } from phonemize()', () => {
        const ko = new KoreanG2P();
        const result = ko.phonemize('\uAC00'); // 가
        assert.ok(Array.isArray(result.tokens), 'tokens should be an array');
        assert.ok(Array.isArray(result.prosody), 'prosody should be an array');
        assert.equal(result.tokens.length, result.prosody.length,
            'tokens and prosody should have same length');
    });

    it('should return all-null prosody from phonemize()', () => {
        const ko = new KoreanG2P();
        const { prosody } = ko.phonemize('\uAC00'); // 가
        assert.ok(prosody.every(p => p === null), 'phonemize prosody should be all null');
    });

    it('should return { tokens, prosody } from phonemizeWithProsody()', () => {
        const ko = new KoreanG2P();
        const result = ko.phonemizeWithProsody('\uAC00'); // 가
        assert.ok(Array.isArray(result.tokens));
        assert.ok(Array.isArray(result.prosody));
        assert.equal(result.tokens.length, result.prosody.length);
    });

    it('should return prosody objects with a1/a2/a3 from phonemizeWithProsody()', () => {
        const ko = new KoreanG2P();
        const { prosody } = ko.phonemizeWithProsody('\uAC00'); // 가
        for (const p of prosody) {
            assert.ok(p !== null, 'prosody entries should not be null');
            assert.ok('a1' in p, 'prosody should have a1');
            assert.ok('a2' in p, 'prosody should have a2');
            assert.ok('a3' in p, 'prosody should have a3');
        }
    });

    it('should handle empty string', () => {
        const ko = new KoreanG2P();
        const r1 = ko.phonemize('');
        assert.deepEqual(r1.tokens, []);
        const r2 = ko.phonemizeWithProsody('');
        assert.deepEqual(r2.tokens, []);
    });

    it('should handle null/undefined input', () => {
        const ko = new KoreanG2P();
        const r1 = ko.phonemize(null);
        assert.deepEqual(r1.tokens, []);
        const r2 = ko.phonemize(undefined);
        assert.deepEqual(r2.tokens, []);
    });

    it('should have languageCode "ko"', () => {
        const ko = new KoreanG2P();
        assert.equal(ko.languageCode, 'ko');
    });
});

// ===========================================================================
// Hangul decomposition -- single syllables
// ===========================================================================

describe('KoreanG2P -- single syllables', () => {
    const ko = new KoreanG2P();

    it('should phonemize 가 (ga) -> k a', () => {
        // 가 = ㄱ(initial=0) + ㅏ(medial=0) + no final
        const { tokens } = ko.phonemize('\uAC00');
        assert.deepEqual(tokens, ['k', 'a']);
    });

    it('should phonemize 한 (han) -> h a n', () => {
        // 한 = ㅎ(initial=18) + ㅏ(medial=0) + ㄴ(final=4)
        const { tokens } = ko.phonemize('\uD55C');
        assert.deepEqual(tokens, ['h', 'a', 'n']);
    });

    it('should phonemize 앙 (ang) -> a + velar nasal', () => {
        // 앙 = ㅇ(silent initial) + ㅏ + ㅇ(final=21, velar nasal)
        const { tokens } = ko.phonemize('\uC559');
        assert.deepEqual(tokens, ['a', IPA_ENG]);
    });

    it('should phonemize 바 (ba) -> p a', () => {
        // 바 = ㅂ(initial=7) + ㅏ
        const { tokens } = ko.phonemize('\uBC14');
        assert.deepEqual(tokens, ['p', 'a']);
    });

    it('should phonemize 다 (da) -> t a', () => {
        // 다 = ㄷ(initial=3) + ㅏ
        const { tokens } = ko.phonemize('\uB2E4');
        assert.deepEqual(tokens, ['t', 'a']);
    });

    it('should phonemize 나 (na) -> n a', () => {
        // 나 = ㄴ(initial=2) + ㅏ
        const { tokens } = ko.phonemize('\uB098');
        assert.deepEqual(tokens, ['n', 'a']);
    });

    it('should phonemize 마 (ma) -> m a', () => {
        // 마 = ㅁ(initial=6) + ㅏ
        const { tokens } = ko.phonemize('\uB9C8');
        assert.deepEqual(tokens, ['m', 'a']);
    });

    it('should phonemize 사 (sa) -> s a', () => {
        // 사 = ㅅ(initial=9) + ㅏ
        const { tokens } = ko.phonemize('\uC0AC');
        assert.deepEqual(tokens, ['s', 'a']);
    });

    it('should phonemize 하 (ha) -> h a', () => {
        // 하 = ㅎ(initial=18) + ㅏ
        const { tokens } = ko.phonemize('\uD558');
        assert.deepEqual(tokens, ['h', 'a']);
    });
});

// ===========================================================================
// Affricate consonants
// ===========================================================================

describe('KoreanG2P -- affricate consonants', () => {
    const ko = new KoreanG2P();

    it('should phonemize 자 (ja) -> PUA_TC + a', () => {
        // 자 = ㅈ(initial=12) + ㅏ -> tɕ + a
        const { tokens } = ko.phonemize('\uC790');
        assert.deepEqual(tokens, [PUA_TC, 'a']);
    });

    it('should phonemize 차 (cha) -> PUA_TCH + a', () => {
        // 차 = ㅊ(initial=14) + ㅏ -> tɕʰ + a
        const { tokens } = ko.phonemize('\uCC28');
        assert.deepEqual(tokens, [PUA_TCH, 'a']);
    });
});

// ===========================================================================
// Tense consonants (경음)
// ===========================================================================

describe('KoreanG2P -- tense consonants', () => {
    const ko = new KoreanG2P();

    it('should phonemize 까 (kka) -> PUA_KK + a', () => {
        // 까 = ㄲ(initial=1) + ㅏ -> k͈ + a
        const { tokens } = ko.phonemize('\uAE4C');
        assert.deepEqual(tokens, [PUA_KK, 'a']);
    });

    it('should phonemize 빠 (ppa) -> PUA_PP + a', () => {
        // 빠 = ㅃ(initial=8) + ㅏ -> p͈ + a
        const { tokens } = ko.phonemize('\uBE60');
        assert.deepEqual(tokens, [PUA_PP, 'a']);
    });

    it('should phonemize 따 (tta) -> PUA_TT + a', () => {
        // 따 = ㄸ(initial=4) + ㅏ -> t͈ + a
        const { tokens } = ko.phonemize('\uB530');
        assert.deepEqual(tokens, [PUA_TT, 'a']);
    });

    it('should phonemize 싸 (ssa) -> PUA_SS + a', () => {
        // 싸 = ㅆ(initial=10) + ㅏ -> s͈ + a
        const { tokens } = ko.phonemize('\uC2F8');
        assert.deepEqual(tokens, [PUA_SS, 'a']);
    });

    it('should phonemize 짜 (jja) -> PUA_TTCH + a', () => {
        // 짜 = ㅉ(initial=13) + ㅏ -> t͈ɕ + a
        const { tokens } = ko.phonemize('\uC9DC');
        assert.deepEqual(tokens, [PUA_TTCH, 'a']);
    });
});

// ===========================================================================
// Aspirated consonants (격음)
// ===========================================================================

describe('KoreanG2P -- aspirated consonants', () => {
    const ko = new KoreanG2P();

    it('should phonemize 카 (ka) -> PUA_KH + a', () => {
        // 카 = ㅋ(initial=15) + ㅏ -> kʰ + a
        const { tokens } = ko.phonemize('\uCE74');
        assert.deepEqual(tokens, [PUA_KH, 'a']);
    });

    it('should phonemize 타 (ta) -> PUA_TH + a', () => {
        // 타 = ㅌ(initial=16) + ㅏ -> tʰ + a
        const { tokens } = ko.phonemize('\uD0C0');
        assert.deepEqual(tokens, [PUA_TH, 'a']);
    });

    it('should phonemize 파 (pa) -> PUA_PH + a', () => {
        // 파 = ㅍ(initial=17) + ㅏ -> pʰ + a
        const { tokens } = ko.phonemize('\uD30C');
        assert.deepEqual(tokens, [PUA_PH, 'a']);
    });
});

// ===========================================================================
// Alveolar flap (ㄹ) initial
// ===========================================================================

describe('KoreanG2P -- alveolar flap', () => {
    const ko = new KoreanG2P();

    it('should phonemize 라 (ra) -> IPA_FLAP + a', () => {
        // 라 = ㄹ(initial=5) + ㅏ -> ɾ + a
        const { tokens } = ko.phonemize('\uB77C');
        assert.deepEqual(tokens, [IPA_FLAP, 'a']);
    });
});

// ===========================================================================
// Unreleased finals (불파음)
// ===========================================================================

describe('KoreanG2P -- unreleased finals', () => {
    const ko = new KoreanG2P();

    it('should phonemize 박 (bak) -> p a + unreleased k', () => {
        // 박 = ㅂ + ㅏ + ㄱ(final=1) -> p a k̚
        const { tokens } = ko.phonemize('\uBC15');
        assert.deepEqual(tokens, ['p', 'a', PUA_K_UNREL]);
    });

    it('should phonemize 맛 (mat) -> m a + unreleased t', () => {
        // 맛 = ㅁ + ㅏ + ㅅ(final=19) -> m a t̚
        const { tokens } = ko.phonemize('\uB9DB');
        assert.deepEqual(tokens, ['m', 'a', PUA_T_UNREL]);
    });

    it('should phonemize 밥 (bap) -> p a + unreleased p', () => {
        // 밥 = ㅂ + ㅏ + ㅂ(final=17) -> p a p̚
        const { tokens } = ko.phonemize('\uBC25');
        assert.deepEqual(tokens, ['p', 'a', PUA_P_UNREL]);
    });

    it('should phonemize 국 (guk) with unreleased k final', () => {
        // 국 = ㄱ + ㅜ + ㄱ(final=1) -> k u k̚
        const { tokens } = ko.phonemize('\uAD6D');
        assert.deepEqual(tokens, ['k', 'u', PUA_K_UNREL]);
    });
});

// ===========================================================================
// Multi-syllable words
// ===========================================================================

describe('KoreanG2P -- multi-syllable words', () => {
    const ko = new KoreanG2P();

    it('should phonemize 한글 (hangul) -> h a n k ɯ l', () => {
        // 한글 = h a n + k ɯ l
        const { tokens } = ko.phonemize('\uD55C\uAE00');
        assert.deepEqual(tokens, ['h', 'a', 'n', 'k', IPA_CLOSE_BACK_UNR, 'l']);
    });
});

// ===========================================================================
// Diphthongs (이중모음)
// ===========================================================================

describe('KoreanG2P -- diphthongs', () => {
    const ko = new KoreanG2P();

    it('should phonemize 와 (wa) -> w a', () => {
        // 와 = ㅇ(silent) + ㅘ(medial=9: w+a) -> w a
        const { tokens } = ko.phonemize('\uC640');
        assert.deepEqual(tokens, ['w', 'a']);
    });

    it('should phonemize 의 (ui) -> velar approximant + i', () => {
        // 의 = ㅇ(silent) + ㅢ(medial=19: ɰ+i) -> ɰ i
        const { tokens } = ko.phonemize('\uC758');
        assert.deepEqual(tokens, [IPA_VELAR_APPROX, 'i']);
    });
});

// ===========================================================================
// Medial vowels
// ===========================================================================

describe('KoreanG2P -- medial vowels', () => {
    const ko = new KoreanG2P();

    it('should phonemize ㅏ (a) in 아 -> a', () => {
        // 아 = ㅇ(silent) + ㅏ(medial=0) -> a
        const { tokens } = ko.phonemize('\uC544');
        assert.deepEqual(tokens, ['a']);
    });

    it('should phonemize ㅐ (ae) in 애 -> open-mid front ɛ', () => {
        // 애 = ㅇ(silent) + ㅐ(medial=1) -> ɛ
        const { tokens } = ko.phonemize('\uC560');
        assert.deepEqual(tokens, [IPA_OPEN_E]);
    });

    it('should phonemize ㅓ (eo) in 어 -> open-mid back ʌ', () => {
        // 어 = ㅇ(silent) + ㅓ(medial=4) -> ʌ
        const { tokens } = ko.phonemize('\uC5B4');
        assert.deepEqual(tokens, [IPA_OPEN_MID_BACK]);
    });

    it('should phonemize ㅔ (e) in 에 -> e', () => {
        // 에 = ㅇ(silent) + ㅔ(medial=5) -> e
        const { tokens } = ko.phonemize('\uC5D0');
        assert.deepEqual(tokens, ['e']);
    });

    it('should phonemize ㅗ (o) in 오 -> o', () => {
        // 오 = ㅇ(silent) + ㅗ(medial=8) -> o
        const { tokens } = ko.phonemize('\uC624');
        assert.deepEqual(tokens, ['o']);
    });

    it('should phonemize ㅜ (u) in 우 -> u', () => {
        // 우 = ㅇ(silent) + ㅜ(medial=13) -> u
        const { tokens } = ko.phonemize('\uC6B0');
        assert.deepEqual(tokens, ['u']);
    });

    it('should phonemize ㅡ (eu) in 으 -> close back unrounded ɯ', () => {
        // 으 = ㅇ(silent) + ㅡ(medial=18) -> ɯ
        const { tokens } = ko.phonemize('\uC73C');
        assert.deepEqual(tokens, [IPA_CLOSE_BACK_UNR]);
    });

    it('should phonemize ㅣ (i) in 이 -> i', () => {
        // 이 = ㅇ(silent) + ㅣ(medial=20) -> i
        const { tokens } = ko.phonemize('\uC774');
        assert.deepEqual(tokens, ['i']);
    });

    it('should phonemize ㅑ (ya) in 야 -> j a', () => {
        // 야 = ㅇ(silent) + ㅑ(medial=2: j+a) -> j a
        const { tokens } = ko.phonemize('\uC57C');
        assert.deepEqual(tokens, ['j', 'a']);
    });

    it('should phonemize ㅕ (yeo) in 여 -> j ʌ', () => {
        // 여 = ㅇ(silent) + ㅕ(medial=6: j+ʌ) -> j ʌ
        const { tokens } = ko.phonemize('\uC5EC');
        assert.deepEqual(tokens, ['j', IPA_OPEN_MID_BACK]);
    });

    it('should phonemize ㅛ (yo) in 요 -> j o', () => {
        // 요 = ㅇ(silent) + ㅛ(medial=12: j+o) -> j o
        const { tokens } = ko.phonemize('\uC694');
        assert.deepEqual(tokens, ['j', 'o']);
    });

    it('should phonemize ㅠ (yu) in 유 -> j u', () => {
        // 유 = ㅇ(silent) + ㅠ(medial=17: j+u) -> j u
        const { tokens } = ko.phonemize('\uC720');
        assert.deepEqual(tokens, ['j', 'u']);
    });
});

// ===========================================================================
// Liaison (연음화)
// ===========================================================================

describe('KoreanG2P -- liaison', () => {
    const ko = new KoreanG2P();

    it('should apply liaison: 국어 -> k u k ʌ', () => {
        // 국어 = ㄱ+ㅜ+ㄱ(final=1) + ㅇ(initial=11)+ㅓ
        // Liaison: final ㄱ (idx 1) has liaison_initial=0 (ㄱ)
        // After: 구 + 거 -> k u + k ʌ
        const { tokens } = ko.phonemize('\uAD6D\uC5B4');
        assert.deepEqual(tokens, ['k', 'u', 'k', IPA_OPEN_MID_BACK]);
    });

    it('should apply liaison with complex final: 읽어 -> i l k ʌ', () => {
        // 읽어 = ㅇ+ㅣ+ㄺ(final=9) + ㅇ(initial=11)+ㅓ
        // ㄺ (final=9): liaison_initial=0 (ㄱ), residual_final=8 (ㄹ)
        // After: 일(residual ㄹ) + 거(ㄱ initial) -> i l + k ʌ
        const { tokens } = ko.phonemize('\uC77D\uC5B4');
        assert.deepEqual(tokens, ['i', 'l', 'k', IPA_OPEN_MID_BACK]);
    });

    it('should NOT apply liaison when next initial is not ㅇ: 국민', () => {
        // 국민 = ㄱ+ㅜ+ㄱ(final=1) + ㅁ(initial=6)+ㅣ+ㄴ(final=4)
        // No liaison: next initial is ㅁ(6), not ㅇ(11)
        // -> k u k̚ + m i n
        const { tokens } = ko.phonemize('\uAD6D\uBBFC');
        assert.deepEqual(tokens, ['k', 'u', PUA_K_UNREL, 'm', 'i', 'n']);
    });

    it('should handle liaison across 3 syllables: 먹어요 -> m ʌ k ʌ j o', () => {
        // 먹어요 = ㅁ+ㅓ+ㄱ(final=1) + ㅇ+ㅓ + ㅇ+ㅛ
        // First liaison: ㄱ -> next syllable initial ㄱ(0)
        // Second: 어(no final) + 요(initial=ㅇ but no final to move)
        // -> m ʌ + k ʌ + j o
        const { tokens } = ko.phonemize('\uBA39\uC5B4\uC694');
        assert.deepEqual(tokens, ['m', IPA_OPEN_MID_BACK, 'k', IPA_OPEN_MID_BACK, 'j', 'o']);
    });
});

// ===========================================================================
// Punctuation passthrough
// ===========================================================================

describe('KoreanG2P -- punctuation', () => {
    const ko = new KoreanG2P();

    it('should pass through period: 가. -> k a .', () => {
        const { tokens } = ko.phonemize('\uAC00.');
        assert.deepEqual(tokens, ['k', 'a', '.']);
    });

    it('should pass through comma', () => {
        const { tokens } = ko.phonemize('\uAC00,');
        assert.ok(hasToken(tokens, ','),
            `expected comma in [${tokens.join(', ')}]`);
    });

    it('should pass through exclamation mark', () => {
        const { tokens } = ko.phonemize('\uAC00!');
        assert.ok(hasToken(tokens, '!'),
            `expected ! in [${tokens.join(', ')}]`);
    });

    it('should pass through question mark', () => {
        const { tokens } = ko.phonemize('\uAC00?');
        assert.ok(hasToken(tokens, '?'),
            `expected ? in [${tokens.join(', ')}]`);
    });

    it('should pass through CJK period', () => {
        const { tokens } = ko.phonemize('\uAC00\u3002'); // 가。
        assert.ok(hasToken(tokens, '\u3002'),
            `expected CJK period in [${tokens.join(', ')}]`);
    });
});

// ===========================================================================
// Latin text passthrough
// ===========================================================================

describe('KoreanG2P -- Latin passthrough', () => {
    const ko = new KoreanG2P();

    it('should pass through Latin characters with spaces: Hello', () => {
        // Each Latin char is processed individually; space inserted between each
        // (matches C++ korean_phonemize.cpp / Rust behavior)
        const { tokens } = ko.phonemize('Hello');
        assert.deepEqual(tokens, ['h', ' ', 'e', ' ', 'l', ' ', 'l', ' ', 'o']);
    });

    it('should lowercase Latin characters', () => {
        const { tokens } = ko.phonemize('A');
        assert.deepEqual(tokens, ['a']);
    });
});

// ===========================================================================
// Mixed Hangul + Latin text
// ===========================================================================

describe('KoreanG2P -- mixed text', () => {
    const ko = new KoreanG2P();

    it('should handle mixed Hangul and Latin: 가 OK', () => {
        // Space between Hangul and Latin runs; each Latin char gets spaces
        const { tokens } = ko.phonemize('\uAC00 OK');
        assert.deepEqual(tokens, ['k', 'a', ' ', 'o', ' ', 'k']);
    });
});

// ===========================================================================
// Word boundary / whitespace
// ===========================================================================

describe('KoreanG2P -- word boundaries', () => {
    const ko = new KoreanG2P();

    it('should insert space between Hangul words: 가 나', () => {
        const { tokens } = ko.phonemize('\uAC00 \uB098');
        assert.deepEqual(tokens, ['k', 'a', ' ', 'n', 'a']);
    });

    it('should not produce leading space for whitespace-prefixed input', () => {
        const { tokens } = ko.phonemize('  \uAC00');
        assert.deepEqual(tokens, ['k', 'a']);
    });
});

// ===========================================================================
// Prosody structure
// ===========================================================================

describe('KoreanG2P -- prosody', () => {
    const ko = new KoreanG2P();

    it('should set a1=0, a2=0, a3=0 for all tokens in phonemizeWithProsody', () => {
        const { tokens, prosody } = ko.phonemizeWithProsody('\uAC00'); // 가
        assert.ok(tokens.length > 0, 'should have tokens');
        assert.equal(tokens.length, prosody.length, 'tokens and prosody should match');
        for (const p of prosody) {
            assert.ok(p !== null, 'prosody entries should not be null');
            assert.equal(p.a1, 0, 'a1 should be 0');
            assert.equal(p.a2, 0, 'a2 should be 0');
            assert.equal(p.a3, 0, 'a3 should be 0');
        }
    });

    it('should set a1=0, a2=0, a3=0 for multi-syllable word', () => {
        const { tokens, prosody } = ko.phonemizeWithProsody('\uD55C\uAE00'); // 한글
        assert.ok(tokens.length > 0);
        for (const p of prosody) {
            assert.ok(p !== null);
            assert.equal(p.a1, 0, 'a1 should be 0');
            assert.equal(p.a2, 0, 'a2 should be 0');
            assert.equal(p.a3, 0, 'a3 should be 0');
        }
    });

    it('should return empty prosody for empty input', () => {
        const { tokens, prosody } = ko.phonemizeWithProsody('');
        assert.deepEqual(tokens, []);
        assert.deepEqual(prosody, []);
    });
});

// ===========================================================================
// Single-character tokens
// ===========================================================================

describe('KoreanG2P -- token format', () => {
    const ko = new KoreanG2P();

    it('should return single-character tokens for Hangul input', () => {
        const { tokens } = ko.phonemizeWithProsody('\uD55C\uAE00'); // 한글
        for (const t of tokens) {
            assert.equal(t.length, 1,
                `Expected single-char token, got "${t}" (length ${t.length})`);
        }
    });
});

// ===========================================================================
// Missing medial vowels (7 of 21 previously untested)
// ===========================================================================

describe('KoreanG2P -- missing medial vowels', () => {
    const ko = new KoreanG2P();

    it('should phonemize ㅒ (yae) in 얘 -> j ɛ', () => {
        // 얘 = ㅇ(silent) + ㅒ(medial=3: j+ɛ) -> j ɛ
        const { tokens } = ko.phonemize('\uC598');
        assert.deepEqual(tokens, ['j', IPA_OPEN_E]);
    });

    it('should phonemize ㅖ (ye) in 예 -> j e', () => {
        // 예 = ㅇ(silent) + ㅖ(medial=7: j+e) -> j e
        const { tokens } = ko.phonemize('\uC608');
        assert.deepEqual(tokens, ['j', 'e']);
    });

    it('should phonemize ㅙ (wae) in 왜 -> w ɛ', () => {
        // 왜 = ㅇ(silent) + ㅙ(medial=10: w+ɛ) -> w ɛ
        const { tokens } = ko.phonemize('\uC65C');
        assert.deepEqual(tokens, ['w', IPA_OPEN_E]);
    });

    it('should phonemize ㅚ (oe) in 외 -> w e', () => {
        // 외 = ㅇ(silent) + ㅚ(medial=11: w+e, modern Seoul) -> w e
        const { tokens } = ko.phonemize('\uC678');
        assert.deepEqual(tokens, ['w', 'e']);
    });

    it('should phonemize ㅝ (wo) in 워 -> w ʌ', () => {
        // 워 = ㅇ(silent) + ㅝ(medial=14: w+ʌ) -> w ʌ
        const { tokens } = ko.phonemize('\uC6CC');
        assert.deepEqual(tokens, ['w', IPA_OPEN_MID_BACK]);
    });

    it('should phonemize ㅞ (we) in 웨 -> w e', () => {
        // 웨 = ㅇ(silent) + ㅞ(medial=15: w+e) -> w e
        const { tokens } = ko.phonemize('\uC6E8');
        assert.deepEqual(tokens, ['w', 'e']);
    });

    it('should phonemize ㅟ (wi) in 위 -> w i', () => {
        // 위 = ㅇ(silent) + ㅟ(medial=16: w+i) -> w i
        const { tokens } = ko.phonemize('\uC704');
        assert.deepEqual(tokens, ['w', 'i']);
    });
});

// ===========================================================================
// Complex finals (겹받침) -- standalone (no liaison)
// ===========================================================================

describe('KoreanG2P -- complex finals', () => {
    const ko = new KoreanG2P();

    it('should phonemize 넋 (ㄳ final=3) -> n ʌ k̚', () => {
        // 넋 = ㄴ(2) + ㅓ(4) + ㄳ(final=3) -> neutralized to k̚
        const { tokens } = ko.phonemize('\uB10B');
        assert.deepEqual(tokens, ['n', IPA_OPEN_MID_BACK, PUA_K_UNREL]);
    });

    it('should phonemize 앉 (ㄵ final=5) -> a n', () => {
        // 앉 = ㅇ(silent) + ㅏ(0) + ㄵ(final=5) -> neutralized to n
        const { tokens } = ko.phonemize('\uC549');
        assert.deepEqual(tokens, ['a', 'n']);
    });

    it('should phonemize 않 (ㄶ final=6) -> a n', () => {
        // 않 = ㅇ(silent) + ㅏ(0) + ㄶ(final=6) -> neutralized to n (ㅎ dropped)
        const { tokens } = ko.phonemize('\uC54A');
        assert.deepEqual(tokens, ['a', 'n']);
    });

    it('should phonemize 읽 (ㄺ final=9) -> i k̚', () => {
        // 읽 = ㅇ(silent) + ㅣ(20) + ㄺ(final=9) -> neutralized to k̚
        const { tokens } = ko.phonemize('\uC77D');
        assert.deepEqual(tokens, ['i', PUA_K_UNREL]);
    });

    it('should phonemize 삶 (ㄻ final=10) -> s a m', () => {
        // 삶 = ㅅ(9) + ㅏ(0) + ㄻ(final=10) -> neutralized to m
        const { tokens } = ko.phonemize('\uC0B6');
        assert.deepEqual(tokens, ['s', 'a', 'm']);
    });

    it('should phonemize 넓 (ㄼ final=11) -> n ʌ l', () => {
        // 넓 = ㄴ(2) + ㅓ(4) + ㄼ(final=11) -> neutralized to l
        const { tokens } = ko.phonemize('\uB113');
        assert.deepEqual(tokens, ['n', IPA_OPEN_MID_BACK, 'l']);
    });

    it('should phonemize 핥 (ㄾ final=13) -> h a l', () => {
        // 핥 = ㅎ(18) + ㅏ(0) + ㄾ(final=13) -> neutralized to l
        const { tokens } = ko.phonemize('\uD565');
        assert.deepEqual(tokens, ['h', 'a', 'l']);
    });

    it('should phonemize 읊 (ㄿ final=14) -> ɯ l', () => {
        // 읊 = ㅇ(silent) + ㅡ(18) + ㄿ(final=14) -> neutralized to l
        const { tokens } = ko.phonemize('\uC74A');
        assert.deepEqual(tokens, [IPA_CLOSE_BACK_UNR, 'l']);
    });

    it('should phonemize 잃 (ㅀ final=15) -> i l', () => {
        // 잃 = ㅇ(silent) + ㅣ(20) + ㅀ(final=15) -> neutralized to l (ㅎ dropped)
        const { tokens } = ko.phonemize('\uC783');
        assert.deepEqual(tokens, ['i', 'l']);
    });

    it('should phonemize 없 (ㅄ final=18) -> ʌ p̚', () => {
        // 없 = ㅇ(silent) + ㅓ(4) + ㅄ(final=18) -> neutralized to p̚
        const { tokens } = ko.phonemize('\uC5C6');
        assert.deepEqual(tokens, [IPA_OPEN_MID_BACK, PUA_P_UNREL]);
    });
});

// ===========================================================================
// NFD Hangul jamo handling (macOS decomposition)
// ===========================================================================

describe('KoreanG2P -- NFD Hangul handling', () => {
    const ko = new KoreanG2P();

    it('should recompose NFD jamo to same result as NFC: 한 (U+1112+U+1161+U+11AB)', () => {
        // NFD: ㅎ(U+1112) + ㅏ(U+1161) + ㄴ(U+11AB) -> should recompose to 한(U+D55C)
        const nfd = String.fromCodePoint(0x1112, 0x1161, 0x11AB);
        const nfc = '\uD55C'; // 한
        const resultNFD = ko.phonemize(nfd);
        const resultNFC = ko.phonemize(nfc);
        assert.deepEqual(resultNFD.tokens, resultNFC.tokens,
            'NFD jamo input should produce same tokens as NFC precomposed');
        assert.deepEqual(resultNFD.tokens, ['h', 'a', 'n']);
    });

    it('should recompose NFD jamo without trailing: 가 (U+1100+U+1161)', () => {
        // NFD: ㄱ(U+1100) + ㅏ(U+1161) -> should recompose to 가(U+AC00)
        const nfd = String.fromCodePoint(0x1100, 0x1161);
        const nfc = '\uAC00'; // 가
        const resultNFD = ko.phonemize(nfd);
        const resultNFC = ko.phonemize(nfc);
        assert.deepEqual(resultNFD.tokens, resultNFC.tokens,
            'NFD without trailing jamo should produce same tokens as NFC');
        assert.deepEqual(resultNFD.tokens, ['k', 'a']);
    });

    it('should recompose multi-syllable NFD: 한글 via jamo', () => {
        // 한 = ㅎ(U+1112) + ㅏ(U+1161) + ㄴ(U+11AB)
        // 글 = ㄱ(U+1100) + ㅡ(U+1173) + ㄹ(U+11AF)
        const nfd = String.fromCodePoint(0x1112, 0x1161, 0x11AB, 0x1100, 0x1173, 0x11AF);
        const nfc = '\uD55C\uAE00'; // 한글
        const resultNFD = ko.phonemize(nfd);
        const resultNFC = ko.phonemize(nfc);
        assert.deepEqual(resultNFD.tokens, resultNFC.tokens,
            'Multi-syllable NFD should match NFC');
        assert.deepEqual(resultNFD.tokens, ['h', 'a', 'n', 'k', IPA_CLOSE_BACK_UNR, 'l']);
    });
});

// ===========================================================================
// Case normalization
// ===========================================================================

describe('KoreanG2P -- normalization', () => {
    const ko = new KoreanG2P();

    it('should normalize Latin uppercase to lowercase', () => {
        const r1 = ko.phonemize('A');
        const r2 = ko.phonemize('a');
        assert.deepEqual(r1.tokens, r2.tokens,
            'uppercase and lowercase should produce same tokens');
    });
});

// ===========================================================================
// Error handling / robustness
// ===========================================================================

describe('KoreanG2P -- error handling', () => {
    const ko = new KoreanG2P();

    it('should handle numeric-only input without crashing', () => {
        const { tokens } = ko.phonemize('12345');
        assert.ok(Array.isArray(tokens), 'should return an array');
    });

    it('should handle symbol-only input without crashing', () => {
        const { tokens } = ko.phonemize('@#$%^&*');
        assert.ok(Array.isArray(tokens), 'should return an array');
    });

    it('should handle very long input (1000+ characters) without crashing', () => {
        const longText = '\uAC00\uB098\uB2E4 '.repeat(250); // ~1000 characters of Hangul
        const { tokens } = ko.phonemize(longText);
        assert.ok(Array.isArray(tokens), 'should return an array');
        assert.ok(tokens.length > 0, 'should produce tokens for valid long input');
    });

    it('should handle phonemizeWithProsody for numeric-only input', () => {
        const { tokens, prosody } = ko.phonemizeWithProsody('12345');
        assert.ok(Array.isArray(tokens), 'should return tokens array');
        assert.ok(Array.isArray(prosody), 'should return prosody array');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });

    it('should handle phonemizeWithProsody for symbol-only input', () => {
        const { tokens, prosody } = ko.phonemizeWithProsody('@#$%^&*');
        assert.ok(Array.isArray(tokens), 'should return tokens array');
        assert.ok(Array.isArray(prosody), 'should return prosody array');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });

    it('should handle phonemizeWithProsody for very long input', () => {
        const longText = '\uD55C\uAE00 '.repeat(400); // ~1200 characters of Hangul
        const { tokens, prosody } = ko.phonemizeWithProsody(longText);
        assert.ok(Array.isArray(tokens), 'should return tokens array');
        assert.ok(tokens.length > 0, 'should produce tokens');
        assert.equal(tokens.length, prosody.length,
            'tokens and prosody should have same length');
    });
});
