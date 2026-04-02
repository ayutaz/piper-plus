/**
 * @piper-plus phonemizer compatibility shim.
 *
 * Re-exports the G2P class from @piper-plus/g2p as the primary phonemizer
 * for backward compatibility with the ./phonemizer subpath export.
 *
 * @module piper-plus/phonemizer
 */
export { G2P, KoreanG2P, SwedishG2P, EnglishG2P, ChineseG2P, SpanishG2P, FrenchG2P, PortugueseG2P, JapaneseG2P, UnicodeLanguageDetector, Encoder } from '@piper-plus/g2p';
