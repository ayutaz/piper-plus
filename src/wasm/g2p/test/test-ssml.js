/**
 * SSML parser tests for `@piper-plus/g2p`.
 *
 * These mirror the Rust unit tests in
 * src/rust/piper-plus-g2p/src/ssml.rs and the Python tests in
 * src/python/g2p/tests/test_ssml.py — every assertion here corresponds
 * to a behaviour pinned in at least one other runtime.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isSsml,
  parseSsml,
  SsmlParser,
  __internal,
} from '../src/ssml.js';

const { parseBreakTime, parseRate, BREAK_STRENGTH_MS, RATE_NAMES } = __internal;

// ===========================================================================
// isSsml — detection rules
// ===========================================================================

test('isSsml: <speak> tag is detected', () => {
  assert.equal(isSsml('<speak>Hello</speak>'), true);
});

test('isSsml: leading whitespace is allowed', () => {
  assert.equal(isSsml('  \n <speak>Hello</speak>'), true);
});

test('isSsml: <speak> with attributes is detected', () => {
  assert.equal(
    isSsml('<speak xml:lang="en-US" version="1.0">Hi</speak>'),
    true,
  );
});

test('isSsml: plain text is not SSML', () => {
  assert.equal(isSsml('Hello, world!'), false);
});

test('isSsml: other XML tags are not SSML', () => {
  assert.equal(isSsml('<root>Hello</root>'), false);
});

test('isSsml: empty string is not SSML', () => {
  assert.equal(isSsml(''), false);
});

test('isSsml: non-string input does not throw', () => {
  assert.equal(isSsml(null), false);
  assert.equal(isSsml(undefined), false);
  assert.equal(isSsml(42), false);
});

// ===========================================================================
// parseSsml — plain-text and basic structure
// ===========================================================================

test('parseSsml: plain text returns a single segment', () => {
  const segs = parseSsml('Hello, world!');
  assert.deepEqual(segs, [{ text: 'Hello, world!', breakMs: 0, rate: 1.0 }]);
});

test('parseSsml: <speak>Hello</speak> returns one text segment', () => {
  const segs = parseSsml('<speak>Hello</speak>');
  assert.equal(segs.length, 1);
  assert.equal(segs[0].text, 'Hello');
  assert.equal(segs[0].breakMs, 0);
  assert.equal(segs[0].rate, 1.0);
});

test('parseSsml: SsmlParser.parse is an alias for parseSsml', () => {
  assert.deepEqual(
    SsmlParser.parse('<speak>X</speak>'),
    parseSsml('<speak>X</speak>'),
  );
});

test('parseSsml: SsmlParser.isSsml is an alias for isSsml', () => {
  // Cross-runtime contract: detection requires `<speak` followed by `\s` or
  // `>`, mirroring the Python/Rust regex `^\s*<speak[\s>]`. A self-closing
  // root `<speak/>` is not a valid SSML body and is intentionally rejected.
  assert.equal(SsmlParser.isSsml('<speak>x</speak>'), true);
  assert.equal(SsmlParser.isSsml('plain'), false);
});

// ===========================================================================
// <break> handling
// ===========================================================================

test('parseSsml: <break time="500ms"/> emits 500ms silence segment', () => {
  const segs = parseSsml('<speak>A<break time="500ms"/>B</speak>');
  assert.equal(segs.length, 3);
  assert.equal(segs[0].text, 'A');
  assert.equal(segs[1].text, '');
  assert.equal(segs[1].breakMs, 500);
  assert.equal(segs[2].text, 'B');
});

test('parseSsml: <break time="1s"/> converts seconds → ms', () => {
  const segs = parseSsml('<speak><break time="1s"/></speak>');
  // The <speak> may contribute an empty leading segment that gets pruned;
  // the break must be present with breakMs=1000.
  const breakSeg = segs.find((s) => s.breakMs > 0);
  assert.ok(breakSeg, 'must have a break segment');
  assert.equal(breakSeg.breakMs, 1000);
});

test('parseSsml: <break strength="medium"/> uses 400ms', () => {
  const segs = parseSsml('<speak><break strength="medium"/></speak>');
  const breakSeg = segs.find((s) => s.breakMs > 0);
  assert.ok(breakSeg);
  assert.equal(breakSeg.breakMs, BREAK_STRENGTH_MS.medium);
  assert.equal(breakSeg.breakMs, 400);
});

test('parseSsml: <break/> with no attrs defaults to medium (400ms)', () => {
  const segs = parseSsml('<speak><break/></speak>');
  const breakSeg = segs.find((s) => s.breakMs > 0);
  assert.ok(breakSeg);
  assert.equal(breakSeg.breakMs, 400);
});

test('parseSsml: unknown <break strength> falls back to 400ms', () => {
  const segs = parseSsml('<speak><break strength="yolo"/></speak>');
  const breakSeg = segs.find((s) => s.breakMs > 0);
  assert.ok(breakSeg);
  assert.equal(breakSeg.breakMs, 400);
});

// ===========================================================================
// <prosody> handling
// ===========================================================================

test('parseSsml: <prosody rate="slow"> applies length_scale=1.25', () => {
  const segs = parseSsml('<speak><prosody rate="slow">slow text</prosody></speak>');
  const slow = segs.find((s) => s.text === 'slow text');
  assert.ok(slow, 'must include the text segment');
  assert.equal(slow.rate, RATE_NAMES.slow);
  assert.equal(slow.rate, 1.25);
});

test('parseSsml: <prosody rate="x-fast"> applies length_scale=0.6', () => {
  const segs = parseSsml('<speak><prosody rate="x-fast">go</prosody></speak>');
  const seg = segs.find((s) => s.text === 'go');
  assert.ok(seg);
  assert.equal(seg.rate, 0.6);
});

test('parseSsml: <prosody rate="120%"> = length_scale 100/120', () => {
  const segs = parseSsml('<speak><prosody rate="120%">faster</prosody></speak>');
  const seg = segs.find((s) => s.text === 'faster');
  assert.ok(seg);
  assert.ok(Math.abs(seg.rate - 100 / 120) < 1e-9);
});

test('parseSsml: <prosody rate="0.5"> = bare float length_scale', () => {
  const segs = parseSsml('<speak><prosody rate="0.5">fast</prosody></speak>');
  const seg = segs.find((s) => s.text === 'fast');
  assert.ok(seg);
  assert.equal(seg.rate, 0.5);
});

test('parseSsml: prosody rate is restored after </prosody>', () => {
  const segs = parseSsml(
    '<speak>before<prosody rate="slow">slow</prosody>after</speak>',
  );
  const before = segs.find((s) => s.text === 'before');
  const after = segs.find((s) => s.text === 'after');
  assert.equal(before.rate, 1.0);
  assert.equal(after.rate, 1.0);
});

test('parseSsml: prosody without rate attr leaves rate unchanged', () => {
  const segs = parseSsml('<speak><prosody>x</prosody></speak>');
  const seg = segs.find((s) => s.text === 'x');
  assert.ok(seg);
  assert.equal(seg.rate, 1.0);
});

test('parseSsml: unrecognized rate name → 1.0 (no-op)', () => {
  const segs = parseSsml(
    '<speak><prosody rate="lightspeed">x</prosody></speak>',
  );
  const seg = segs.find((s) => s.text === 'x');
  assert.ok(seg);
  assert.equal(seg.rate, 1.0);
});

// ===========================================================================
// Helpers (parseBreakTime / parseRate) — pin numeric semantics
// ===========================================================================

test('parseBreakTime: ms suffix', () => {
  assert.equal(parseBreakTime('250ms'), 250);
});

test('parseBreakTime: s suffix', () => {
  assert.equal(parseBreakTime('1.5s'), 1500);
});

test('parseBreakTime: bare number = ms', () => {
  assert.equal(parseBreakTime('300'), 300);
});

test('parseBreakTime: invalid input → 0', () => {
  assert.equal(parseBreakTime('invalid'), 0);
});

test('parseRate: percentage', () => {
  assert.ok(Math.abs(parseRate('200%') - 0.5) < 1e-9);
});

test('parseRate: invalid → 1.0', () => {
  assert.equal(parseRate('not a rate'), 1.0);
});

test('parseRate: zero / negative → 1.0', () => {
  assert.equal(parseRate('0'), 1.0);
  assert.equal(parseRate('-1'), 1.0);
  assert.equal(parseRate('0%'), 1.0);
});

// ===========================================================================
// Unknown tags / graceful degradation
// ===========================================================================

test('parseSsml: unknown tag <foo>text</foo> still extracts text', () => {
  const segs = parseSsml('<speak>before<foo>inner</foo>after</speak>');
  // Implementation pins the inner text appears as its own segment.
  const inner = segs.find((s) => s.text === 'inner');
  assert.ok(inner, 'unknown tag content must surface');
});

test('parseSsml: text outside and inside prosody is preserved', () => {
  const segs = parseSsml(
    '<speak>before<prosody rate="slow">middle</prosody>after</speak>',
  );
  const texts = segs.map((s) => s.text);
  assert.deepEqual(texts, ['before', 'middle', 'after']);
});

test('parseSsml: whitespace-only <speak> produces a placeholder segment', () => {
  const segs = parseSsml('<speak>   </speak>');
  assert.equal(segs.length, 1);
  assert.equal(segs[0].text, '');
  assert.equal(segs[0].breakMs, 0);
});

// ===========================================================================
// Malformed XML — must not throw, must not silently produce empty audio
// ===========================================================================

test('parseSsml: unclosed tag falls back to plain-text (tag-stripped)', () => {
  const segs = parseSsml('<speak>hello<unclosed</speak>');
  assert.equal(segs.length, 1);
  // No throw, and we get some text back.
  assert.equal(typeof segs[0].text, 'string');
  // The `<unclosed` portion is not a valid tag — fallback strips tags and
  // returns whatever plain text remains.
  assert.ok(segs[0].text.length > 0, 'fallback must yield non-empty text');
});

test('parseSsml: mismatched end tag falls back gracefully', () => {
  const segs = parseSsml('<speak>hi</wrong>');
  assert.equal(segs.length, 1);
  assert.equal(typeof segs[0].text, 'string');
});

// ===========================================================================
// Attack vectors (mirrors test_ssml_attacks.{rs,py,go,cs})
// ===========================================================================

test('attack: oversized SSML throws RangeError before parsing', () => {
  const big = '<speak>' + 'A'.repeat(200_000) + '</speak>';
  assert.throws(() => parseSsml(big), RangeError);
});

test('attack: deeply nested unknown tags do not blow the stack', () => {
  // 200 nested tags.
  let inner = 'x';
  for (let i = 0; i < 200; i++) {
    inner = `<n${i}>${inner}</n${i}>`;
  }
  const ssml = `<speak>${inner}</speak>`;
  const segs = parseSsml(ssml);
  // Walker accepts it (well-balanced) and the leaf text 'x' surfaces.
  assert.ok(
    segs.some((s) => s.text.includes('x')),
    'leaf text must reach a segment',
  );
});

test('attack: <!DOCTYPE … > is rejected (DTD = entity-expansion attack surface)', () => {
  const ssml =
    '<!DOCTYPE foo [<!ENTITY lol "lol">]>\n' +
    '<speak>&lol;</speak>';
  // is_ssml is false because <speak> is not at the start, so plain-text
  // fallback returns the input as-is. No expansion occurs.
  const segs = parseSsml(ssml);
  assert.equal(segs.length, 1);
  // The literal entity reference is preserved (no expansion).
  assert.ok(segs[0].text.includes('&lol;'));
});

test('attack: unterminated <!--comment is detected and falls back', () => {
  const segs = parseSsml('<speak><!-- never closes</speak>');
  // tokenizer throws → fallback emits stripped text
  assert.equal(segs.length, 1);
  assert.equal(typeof segs[0].text, 'string');
});

test('attack: CDATA content is treated as text (not parsed as XML)', () => {
  const segs = parseSsml('<speak><![CDATA[<break/>]]></speak>');
  // The literal "<break/>" string survives as text — no break segment emitted.
  assert.equal(segs.length, 1);
  assert.equal(segs[0].text, '<break/>');
  assert.equal(segs[0].breakMs, 0);
});

test('attack: XML entities in text are decoded (&amp; → &)', () => {
  const segs = parseSsml('<speak>A &amp; B &lt;1&gt;</speak>');
  assert.equal(segs.length, 1);
  assert.equal(segs[0].text, 'A & B <1>');
});

test('attack: numeric character references are decoded', () => {
  const segs = parseSsml('<speak>&#65;&#x42;</speak>');
  assert.equal(segs.length, 1);
  assert.equal(segs[0].text, 'AB');
});

// ===========================================================================
// Merge semantics — drop empty zero-break segments
// ===========================================================================

test('merge: empty text + zero break is dropped', () => {
  const segs = parseSsml('<speak>only<prosody></prosody>text</speak>');
  // The empty <prosody></prosody> must not contribute a segment.
  assert.deepEqual(
    segs.map((s) => s.text),
    ['only', 'text'],
  );
});
