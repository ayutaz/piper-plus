/**
 * SSML (Speech Synthesis Markup Language) basic tag parser.
 *
 * Mirrors the cross-runtime SSML contract implemented in:
 *   - Python: src/python/g2p/piper_plus_g2p/ssml.py
 *   - Rust:   src/rust/piper-plus-g2p/src/ssml.rs
 *   - C#:     src/csharp/PiperPlus.Core/Ssml/SsmlParser.cs
 *   - Go:     src/go/piperplus/ssml/parser.go
 *
 * Supports a subset of the SSML W3C spec:
 *   - `<speak>` root element
 *   - `<break time="500ms"/>` or `<break time="1s"/>` for silence
 *   - `<break strength="medium"/>` for predefined silence durations
 *   - `<prosody rate="slow">text</prosody>` for speech rate control
 *
 * Unknown tags are gracefully degraded by extracting their text content.
 * XML syntax errors cause a fallback to plain-text processing.
 *
 * @module @piper-plus/g2p/ssml
 */

// Limit SSML input size to mitigate XML parsing DoS (e.g. billion laughs).
const MAX_SSML_SIZE = 100_000;

/** Predefined break-strength durations in milliseconds (W3C SSML spec). */
const BREAK_STRENGTH_MS = Object.freeze({
  none: 0,
  'x-weak': 100,
  weak: 200,
  medium: 400,
  strong: 700,
  'x-strong': 1000,
});

/** Named-rate `length_scale` multipliers (`>1.0` = slower, `<1.0` = faster). */
const RATE_NAMES = Object.freeze({
  'x-slow': 1.5,
  slow: 1.25,
  medium: 1.0,
  fast: 0.8,
  'x-fast': 0.6,
});

/**
 * One segment produced by SSML parsing.
 *
 * @typedef {Object} SSMLSegment
 * @property {string} text     - text to phonemize (empty means silence-only).
 * @property {number} breakMs  - silence duration (ms) to insert AFTER segment.
 * @property {number} rate     - length_scale multiplier (1.0 = no change).
 */

/** Detect SSML — text starts with `<speak` (after optional whitespace). */
const RE_SSML = /^\s*<speak[\s>]/s;

/**
 * Return `true` if `text` looks like an SSML document.
 *
 * @param {string} text
 * @returns {boolean}
 */
export function isSsml(text) {
  if (typeof text !== 'string') return false;
  return RE_SSML.test(text);
}

/**
 * Parse a `<break>` `time` attribute (e.g. `"500ms"`, `"1.5s"`, bare numbers).
 * Returns 0 for unparseable values (matches Python/Rust semantics).
 *
 * @param {string} timeStr
 * @returns {number} milliseconds
 */
function parseBreakTime(timeStr) {
  const s = timeStr.trim().toLowerCase();
  if (s.endsWith('ms')) {
    const n = parseFloat(s.slice(0, -2));
    return Number.isFinite(n) ? Math.trunc(n) : 0;
  }
  if (s.endsWith('s')) {
    const n = parseFloat(s.slice(0, -1));
    return Number.isFinite(n) ? Math.trunc(n * 1000) : 0;
  }
  // Bare number — treat as ms.
  const n = parseFloat(s);
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}

/**
 * Parse a `<prosody rate>` attribute.
 *
 * Accepted formats:
 *   - Named: `'slow'`, `'fast'`, etc.
 *   - Percentage: `'120%'` → length_scale `100/120` (faster speech)
 *   - Bare float: direct length_scale multiplier
 *
 * @param {string} rateStr
 * @returns {number} length_scale multiplier (`>1.0` = slower, `<1.0` = faster)
 */
function parseRate(rateStr) {
  const s = rateStr.trim().toLowerCase();
  if (s in RATE_NAMES) return RATE_NAMES[s];
  if (s.endsWith('%')) {
    const pct = parseFloat(s.slice(0, -1));
    if (Number.isFinite(pct) && pct > 0) return 100.0 / pct;
    return 1.0;
  }
  const val = parseFloat(s);
  if (Number.isFinite(val) && val > 0) return val;
  return 1.0;
}

/** Strip XML namespace prefix from a tag (`{ns}tag` → `tag`). */
function localTag(tag) {
  const idx = tag.indexOf('}');
  return idx >= 0 ? tag.slice(idx + 1) : tag;
}

// ---------------------------------------------------------------------------
// Hand-rolled SSML scanner
// ---------------------------------------------------------------------------
//
// We implement only the subset SSML uses: open/close/self-close tags, text,
// and XML entity decoding. This avoids a dependency on a full XML parser
// (the npm package targets zero deps) and keeps semantics aligned with the
// Rust quick-xml-based implementation.
//
// Token kinds:
//   { kind: 'open',  name, attrs }      — <tag attr="v">
//   { kind: 'close', name }              — </tag>
//   { kind: 'self',  name, attrs }      — <tag/>
//   { kind: 'text',  text }              — between tags

const ENTITY_MAP = Object.freeze({
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
});

/** Decode XML entities in a text fragment. */
function decodeEntities(s) {
  return s.replace(/&([a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);/g, (full, name) => {
    if (name.startsWith('#x')) {
      const cp = parseInt(name.slice(2), 16);
      return Number.isFinite(cp) ? String.fromCodePoint(cp) : full;
    }
    if (name.startsWith('#')) {
      const cp = parseInt(name.slice(1), 10);
      return Number.isFinite(cp) ? String.fromCodePoint(cp) : full;
    }
    return name in ENTITY_MAP ? ENTITY_MAP[name] : full;
  });
}

/** Parse the attributes inside an open or self-closing tag. */
function parseAttrs(attrSrc) {
  const attrs = {};
  // attribute name = "value" or 'value' (no entity decoding inside name)
  const re = /([a-zA-Z_:][\w:.-]*)\s*=\s*("([^"]*)"|'([^']*)')/g;
  let m;
  while ((m = re.exec(attrSrc)) !== null) {
    const name = m[1];
    const raw = m[3] !== undefined ? m[3] : m[4];
    attrs[name] = decodeEntities(raw);
  }
  return attrs;
}

/**
 * Tokenize an SSML/XML string. Throws if a tag is malformed.
 *
 * @param {string} src
 * @returns {Array<object>}
 */
function tokenize(src) {
  const tokens = [];
  let i = 0;
  const n = src.length;

  while (i < n) {
    if (src[i] !== '<') {
      // Text up to next `<`
      let j = src.indexOf('<', i);
      if (j === -1) j = n;
      const raw = src.slice(i, j);
      tokens.push({ kind: 'text', text: decodeEntities(raw) });
      i = j;
      continue;
    }

    // Comment / CDATA / PI / declaration — skip but throw on unterminated.
    if (src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i + 4);
      if (end === -1) throw new SyntaxError('unterminated comment');
      i = end + 3;
      continue;
    }
    if (src.startsWith('<![CDATA[', i)) {
      const end = src.indexOf(']]>', i + 9);
      if (end === -1) throw new SyntaxError('unterminated CDATA');
      tokens.push({ kind: 'text', text: src.slice(i + 9, end) });
      i = end + 3;
      continue;
    }
    if (src.startsWith('<?', i)) {
      const end = src.indexOf('?>', i + 2);
      if (end === -1) throw new SyntaxError('unterminated processing instruction');
      i = end + 2;
      continue;
    }
    if (src.startsWith('<!', i)) {
      // <!DOCTYPE …> or <!ENTITY …> — refuse (DTDs are an attack surface).
      throw new SyntaxError('DTD / declaration not supported');
    }

    // Regular tag: find the closing '>'.
    const closeIdx = src.indexOf('>', i + 1);
    if (closeIdx === -1) throw new SyntaxError('unterminated tag');
    let inner = src.slice(i + 1, closeIdx);
    i = closeIdx + 1;

    let isClose = false;
    let isSelf = false;
    if (inner.startsWith('/')) {
      isClose = true;
      inner = inner.slice(1);
    }
    if (inner.endsWith('/')) {
      isSelf = true;
      inner = inner.slice(0, -1);
    }

    // First whitespace separates name from attributes.
    inner = inner.trim();
    if (inner.length === 0) throw new SyntaxError('empty tag');

    const wsIdx = inner.search(/\s/);
    const rawName = wsIdx === -1 ? inner : inner.slice(0, wsIdx);
    const attrSrc = wsIdx === -1 ? '' : inner.slice(wsIdx);
    const name = localTag(rawName);

    if (isClose) {
      if (attrSrc.trim().length > 0) {
        throw new SyntaxError(`close tag with attributes: ${name}`);
      }
      tokens.push({ kind: 'close', name });
    } else if (isSelf) {
      tokens.push({ kind: 'self', name, attrs: parseAttrs(attrSrc) });
    } else {
      tokens.push({ kind: 'open', name, attrs: parseAttrs(attrSrc) });
    }
  }

  return tokens;
}

/** Compute break duration (ms) from a `<break>` element's attrs. */
function resolveBreak(attrs) {
  if (attrs.time !== undefined) return parseBreakTime(attrs.time);
  if (attrs.strength !== undefined) {
    const s = attrs.strength.toLowerCase();
    return BREAK_STRENGTH_MS[s] ?? 400;
  }
  return BREAK_STRENGTH_MS.medium;
}

/**
 * Walk the token stream, building segments and validating tag balance.
 *
 * @param {Array<object>} tokens
 * @returns {Array<SSMLSegment>}
 */
function walk(tokens) {
  const segments = [];
  // Stack of (tagName, rateAtThisLevel) — used to restore rate on close.
  const stack = [];
  let currentRate = 1.0;

  for (const tok of tokens) {
    if (tok.kind === 'text') {
      const trimmed = tok.text.trim();
      if (trimmed) segments.push({ text: trimmed, breakMs: 0, rate: currentRate });
    } else if (tok.kind === 'open') {
      let pushedRate = currentRate;
      if (tok.name === 'prosody' && tok.attrs.rate !== undefined) {
        // New rate active until the matching </prosody>.
        currentRate = parseRate(tok.attrs.rate);
      }
      // unknown tags: just keep going (text inside is still collected).
      stack.push({ name: tok.name, prevRate: pushedRate });
    } else if (tok.kind === 'self') {
      if (tok.name === 'break') {
        segments.push({
          text: '',
          breakMs: resolveBreak(tok.attrs),
          rate: currentRate,
        });
      } else if (tok.name === 'prosody' && tok.attrs.rate !== undefined) {
        // <prosody rate="…"/> — meaningless without children, but accept it.
      }
      // unknown self-closing tags ignored.
    } else if (tok.kind === 'close') {
      // Pop matching open.
      let popped;
      // Tolerate well-formed-only documents but unwind the stack until match.
      while (stack.length > 0) {
        popped = stack.pop();
        if (popped.name === tok.name) break;
      }
      if (popped === undefined) {
        throw new SyntaxError(`unmatched close tag: ${tok.name}`);
      }
      currentRate = popped.prevRate;
    }
  }

  if (stack.length > 0) {
    const names = stack.map((s) => s.name).join(', ');
    throw new SyntaxError(`unclosed tag(s): ${names}`);
  }

  return segments;
}

/** Drop empty-text zero-break segments (no-ops). */
function mergeSegments(segments) {
  return segments.filter((s) => s.text.trim().length > 0 || s.breakMs > 0);
}

/**
 * Strip any tags from a chunk of text, returning only the inner text.
 * Used as a fallback when XML parsing fails.
 */
function stripTags(text) {
  return text.replace(/<[^>]*>/g, '').trim();
}

/**
 * Parse an SSML string into a list of {@link SSMLSegment}.
 *
 * If `ssmlText` is not SSML, returns `[{text: ssmlText, breakMs:0, rate:1}]`.
 * If parsing fails, falls back to tag-stripped text (so the caller still
 * gets audio, never silence).
 *
 * @param {string} ssmlText
 * @returns {Array<SSMLSegment>}
 */
export function parseSsml(ssmlText) {
  if (typeof ssmlText !== 'string') {
    throw new TypeError('parseSsml: expected a string');
  }
  if (!isSsml(ssmlText)) {
    return [{ text: ssmlText, breakMs: 0, rate: 1.0 }];
  }
  if (ssmlText.length > MAX_SSML_SIZE) {
    throw new RangeError(
      `SSML input too large: ${ssmlText.length} bytes (max: ${MAX_SSML_SIZE})`,
    );
  }

  let tokens;
  try {
    tokens = tokenize(ssmlText);
  } catch (_err) {
    const stripped = stripTags(ssmlText);
    return [{ text: stripped || ssmlText, breakMs: 0, rate: 1.0 }];
  }

  let segments;
  try {
    segments = walk(tokens);
  } catch (_err) {
    const stripped = stripTags(ssmlText);
    return [{ text: stripped || ssmlText, breakMs: 0, rate: 1.0 }];
  }

  const merged = mergeSegments(segments);
  return merged.length > 0 ? merged : [{ text: '', breakMs: 0, rate: 1.0 }];
}

/**
 * Convenience class wrapper mirroring the Python/Rust API surface.
 * All methods are static (the parser carries no mutable state).
 */
export class SsmlParser {
  static isSsml(text) {
    return isSsml(text);
  }

  static parse(text) {
    return parseSsml(text);
  }
}

export const __internal = {
  parseBreakTime,
  parseRate,
  tokenize,
  walk,
  mergeSegments,
  BREAK_STRENGTH_MS,
  RATE_NAMES,
};
