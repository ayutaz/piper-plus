package piperplus

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
	"time"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
	"github.com/ayutaz/piper-plus/src/go/piperplus/ssml"
)

// createPhonemizer builds the appropriate Phonemizer based on VoiceConfig.
// For multilingual models, creates MultilingualPhonemizer.
// For single-language models, creates the language-specific phonemizer.
func createPhonemizer(config *VoiceConfig, dicts *dictData) (phonemize.Phonemizer, error) {
	if config.IsMultilingual() {
		return createMultilingualPhonemizer(config, dicts)
	}
	return createSingleLanguagePhonemizer(config, dicts)
}

// createMultilingualPhonemizer builds a MultilingualPhonemizer from the config's
// LanguageIDMap. Japanese is skipped if no G2P engine is available.
func createMultilingualPhonemizer(config *VoiceConfig, dicts *dictData) (phonemize.Phonemizer, error) {
	phonemizers := make(map[string]phonemize.Phonemizer, len(config.LanguageIDMap))
	for lang := range config.LanguageIDMap {
		p, err := phonemizerForLanguage(lang, dicts)
		if err != nil {
			if lang == "ja" && phonemize.NewOpenJTalkEngine == nil {
				// Japanese requires CGO OpenJTalk engine; skip gracefully.
				continue
			}
			slog.Warn("phonemizer creation failed; skipping language",
				"language", lang, "error", err)
			continue
		}
		phonemizers[lang] = p
	}

	if len(phonemizers) == 0 {
		allLangs := make([]string, 0, len(config.LanguageIDMap))
		for lang := range config.LanguageIDMap {
			allLangs = append(allLangs, lang)
		}
		return nil, fmt.Errorf("no phonemizers could be created for languages %v", allLangs)
	}

	// Build the languages list from successfully created phonemizers only.
	// Sort for deterministic order since Go map iteration is non-deterministic.
	languages := make([]string, 0, len(phonemizers))
	for lang := range phonemizers {
		languages = append(languages, lang)
	}
	sort.Strings(languages)

	defaultLatinLang := phonemize.DefaultLatinLanguage(languages)

	return phonemize.NewMultilingualPhonemizer(languages, defaultLatinLang, phonemizers), nil
}

// createSingleLanguagePhonemizer builds a language-specific phonemizer based on
// the config's PhonemeType or Language.Code.
func createSingleLanguagePhonemizer(config *VoiceConfig, dicts *dictData) (phonemize.Phonemizer, error) {
	lang := ""
	if config.Language != nil {
		lang = config.Language.Code
	}

	// Try PhonemeType first, then fall back to language code.
	switch config.PhonemeType {
	case PhonemeTypeOpenJTalk:
		return phonemizerForLanguage("ja", dicts)
	case PhonemeTypeEspeak:
		if lang == "" {
			lang = "en"
		}
	}

	return phonemizerForLanguage(lang, dicts)
}

// phonemizerForLanguage creates a single-language phonemizer for the given code.
func phonemizerForLanguage(lang string, dicts *dictData) (phonemize.Phonemizer, error) {
	switch lang {
	case "ja":
		if phonemize.NewOpenJTalkEngine == nil {
			return nil, fmt.Errorf("japanese G2P requires build tag 'openjtalk' (CGO + libopenjtalk)")
		}
		var dictPath string
		if dicts != nil {
			dictPath = dicts.openjtalkDictDir
		}
		if dictPath == "" {
			return nil, fmt.Errorf("OpenJTalk dictionary not found; set OPENJTALK_DICTIONARY_PATH or place dictionary next to model")
		}
		engine, err := phonemize.NewOpenJTalkEngine(dictPath)
		if err != nil {
			return nil, fmt.Errorf("failed to create OpenJTalk engine: %w", err)
		}
		return phonemize.NewJapanesePhonemizer(engine), nil
	case "en":
		var cmuDict map[string][]string
		if dicts != nil {
			cmuDict = dicts.cmuDict
		}
		if cmuDict == nil {
			slog.Warn("English phonemizer created without CMU dictionary; all words will use letter-by-letter fallback")
		}
		return phonemize.NewEnglishPhonemizer(cmuDict), nil
	case "zh":
		var single map[rune]string
		var phrase map[string]string
		if dicts != nil {
			single = dicts.pinyinSingle
			phrase = dicts.pinyinPhrase
		}
		if single == nil && phrase == nil {
			slog.Warn("Chinese phonemizer created without pinyin dictionaries; hanzi phonemization may be degraded")
		}
		return phonemize.NewChinesePhonemizer(single, phrase), nil
	case "es":
		return phonemize.NewSpanishPhonemizer(), nil
	case "fr":
		return phonemize.NewFrenchPhonemizer(), nil
	case "pt":
		return phonemize.NewPortuguesePhonemizer(), nil
	case "ko":
		return phonemize.NewKoreanPhonemizer(), nil
	case "sv":
		return phonemize.NewSwedishPhonemizer(), nil
	default:
		return nil, fmt.Errorf("unsupported language %q", lang)
	}
}

// languagePhonemizer is implemented by phonemizers that can read Latin-script
// text as a given language (phonemize.MultilingualPhonemizer).
type languagePhonemizer interface {
	PhonemizeWithLanguage(text, language string) (*phonemize.PhonemizeResult, error)
}

// phonemizeText phonemizes text, reading Latin-script text as language when
// one is given (WithLanguage / --language). es / fr / pt / sv cannot be told
// apart from English by script, so without this a multilingual model reads
// them as its default Latin language. Python's training data is phonemized
// with the utterance language as that default.
func phonemizeText(p phonemize.Phonemizer, text, language string) (*phonemize.PhonemizeResult, error) {
	if lp, ok := p.(languagePhonemizer); ok && language != "" {
		return lp.PhonemizeWithLanguage(text, language)
	}
	return p.PhonemizeWithProsody(text)
}

// prepareSynthesisRequest converts text into a SynthesisRequest ready for
// engine.Synthesize. Carries no state, performs no inference, and is safe to
// invoke concurrently from multiple goroutines as long as the underlying
// phonemizer is — which the bundled phonemizers all are (Japanese guards its
// CGO MeCab handle with a mutex; the others are pure Go with no shared
// mutable state).
//
// The second return value (`needsBreakPad`) is the Strategy C detection bit
// the caller must apply *after* engine.Synthesize.
func (v *Voice) prepareSynthesisRequest(text string, so SynthesisOptions) (*SynthesisRequest, bool, error) {
	if v.phonemizer == nil {
		return nil, false, fmt.Errorf("piperplus: phonemizer not configured; use SynthesizeFromIDs for direct phoneme input")
	}
	if text == "" {
		return nil, false, ErrEmptyText
	}

	// Apply custom dictionary text substitution before phonemization.
	if v.textDict != nil {
		text = v.textDict.ApplyToText(text)
	}

	result, err := phonemizeText(v.phonemizer, text, so.Language)
	if err != nil {
		return nil, false, fmt.Errorf("piperplus: phonemization failed: %w", err)
	}

	// Convert tokens to IDs and post-process.
	var phonemeIDs []int64
	var prosody []*phonemize.ProsodyInfo
	if v.config.IsMultilingual() {
		phonemeIDs, prosody = phonemize.PostProcessMultilingualIDs(result, v.config.PhonemeIDMap)
	} else {
		ids := phonemize.TokensToIDs(result.Tokens, v.config.PhonemeIDMap)
		phonemeIDs, prosody = phonemize.PostProcessIDs(ids, result.Prosody, v.config.PhonemeIDMap, result.EOSToken)
	}

	if len(phonemeIDs) == 0 {
		return nil, false, ErrEmptyPhonemeIDs
	}

	var prosodyFeatures [][3]int64
	if len(prosody) > 0 {
		prosodyFeatures = make([][3]int64, len(prosody))
		for i, p := range prosody {
			if p != nil {
				prosodyFeatures[i] = [3]int64{int64(p.A1), int64(p.A2), int64(p.A3)}
			}
		}
	}

	// Resolve language ID from options + config.
	// When language is not specified but the model is multilingual, default to the
	// phonemizer's primary language so the language ID matches the phonemized output.
	// TODO: support per-segment language detection for mixed-language text.
	var languageID int64
	if so.Language != "" {
		lid, ok := v.config.LanguageIDMap[so.Language]
		if !ok {
			return nil, false, fmt.Errorf("piperplus: unknown language %q; available: %v", so.Language, v.config.LanguageIDMap)
		}
		languageID = lid
	} else if v.config.IsMultilingual() {
		defaultLang := v.phonemizer.LanguageCode()
		if lid, ok := v.config.LanguageIDMap[defaultLang]; ok {
			languageID = lid
		}
		slog.Warn("multilingual model but no language specified; using phonemizer default",
			"default_language", defaultLang, "language_id", languageID)
	}

	// --- Strategy C: detect short text and mark for silence padding ---
	_, needsBreakPad := wrapShortTextWithBreaks(text)

	req := &SynthesisRequest{
		PhonemeIDs:       phonemeIDs,
		SpeakerID:        so.SpeakerID,
		LanguageID:       languageID,
		NoiseScale:       so.NoiseScale,
		LengthScale:      so.LengthScale,
		NoiseW:           so.NoiseW,
		ProsodyFeatures:  prosodyFeatures,
		SpeakerEmbedding: so.SpeakerEmbedding,
	}
	return req, needsBreakPad, nil
}

// applyShortTextPadding rewrites the synthesis result in-place to add the
// Strategy C silence padding mandated by the short-text contract. No-op
// when needsBreakPad is false or the audio buffer is empty.
func applyShortTextPadding(result *SynthesisResult, needsBreakPad bool) {
	if !needsBreakPad || result == nil || len(result.Audio) == 0 {
		return
	}
	result.Audio = prependSilence(result.Audio, result.SampleRate, silencePadMs)
	result.Audio = appendSilence(result.Audio, result.SampleRate, silencePadMs)
	if result.SampleRate > 0 {
		result.Duration = time.Duration(int64(len(result.Audio)) * int64(time.Second) / int64(result.SampleRate))
	}
}

// Synthesize converts text to speech using the configured phonemizer.
// This is the high-level API that phonemizes text then runs inference.
func (v *Voice) Synthesize(ctx context.Context, text string, opts ...SynthesisOption) (*SynthesisResult, error) {
	if v.closed.Load() {
		return nil, ErrModelClosed
	}

	// Apply options, filling defaults from config.Inference.
	so := defaultSynthesisOptions()
	so.NoiseScale = v.config.Inference.NoiseScale
	so.LengthScale = v.config.Inference.LengthScale
	so.NoiseW = v.config.Inference.NoiseW
	for _, fn := range opts {
		fn(&so)
	}
	if ssml.IsSSML(text) {
		return synthesizeSSML(ctx, text, v.config.Audio.SampleRate, func(part string, rate float32) (*SynthesisResult, error) {
			segmentOpts := append([]SynthesisOption(nil), opts...)
			segmentOpts = append(segmentOpts, WithLengthScale(so.LengthScale*rate))
			return v.Synthesize(ctx, part, segmentOpts...)
		})
	}

	req, needsBreakPad, err := v.prepareSynthesisRequest(text, so)
	if err != nil {
		return nil, err
	}

	synthResult, synthErr := v.engine.Synthesize(ctx, req)
	if synthErr != nil {
		return nil, synthErr
	}

	applyShortTextPadding(synthResult, needsBreakPad)

	return synthResult, nil
}

// Segments are synthesized separately so markup never reaches G2P. A joined
// result has no single model duration tensor; it must not report fabricated
// phoneme alignment for the inserted breaks.
func synthesizeSSML(ctx context.Context, text string, sampleRate int, synthesize func(string, float32) (*SynthesisResult, error)) (*SynthesisResult, error) {
	result := &SynthesisResult{SampleRate: sampleRate}
	for _, segment := range ssml.Parse(text) {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		if segment.Text != "" {
			part, err := synthesize(segment.Text, segment.Rate)
			if err != nil {
				return nil, err
			}
			if part.SampleRate != sampleRate {
				return nil, fmt.Errorf("SSML segment sample rate mismatch")
			}
			result.Audio = append(result.Audio, part.Audio...)
			result.InferTime += part.InferTime
		}
		result.Audio = append(result.Audio, make([]int16, segment.BreakMs*sampleRate/1000)...)
	}
	result.Duration = time.Duration(float64(len(result.Audio)) / float64(sampleRate) * float64(time.Second))
	return result, nil
}
