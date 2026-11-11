/**
 * Strips control characters from a text before it is read, by the rule every
 * runtime shares (docs/spec/input-sanitize-contract.toml).
 */

// VT, FF and NEL separate words, so they become a space.
// eslint-disable-next-line no-control-regex -- matching them is the point
const WORD_SEPARATORS = /[\u000B\u000C\u0085]/g;
// Every other control character (Unicode category Cc: U+0000-001F, U+007F,
// U+0080-009F) except newline, tab and carriage return.
// eslint-disable-next-line no-control-regex -- matching them is the point
const REMOVED = /[\u0000-\u0008\u000E-\u001F\u007F-\u0084\u0086-\u009F]/g;

/**
 * Return `text` cleaned by the input-sanitize rule: `\n`, `\t` and `\r` stay
 * (sentence splitting and SSML use them); VT, FF and NEL (U+000B, U+000C,
 * U+0085) become a space; every other control character is removed. Format
 * characters (U+200D, U+FEFF), separators (U+2028), NBSP and lone surrogates
 * stay. Idempotent. A value that is not a string is returned as it is, so the
 * callers keep their own checks for it.
 *
 * @param {string} text
 * @returns {string}
 */
export function stripControlChars(text) {
  if (typeof text !== "string") {
    return text;
  }
  return text.replace(WORD_SEPARATORS, " ").replace(REMOVED, "");
}
