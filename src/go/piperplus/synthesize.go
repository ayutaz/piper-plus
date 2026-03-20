package piperplus

import (
	"context"
	"fmt"
	"log/slog"
	"sort"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
)

// createPhonemizer builds the appropriate Phonemizer based on VoiceConfig.
// For multilingual models, creates MultilingualPhonemizer.
// For single-language models, creates the language-specific phonemizer.
func createPhonemizer(config *VoiceConfig, dataDir string) (phonemize.Phonemizer, error) {
	if config.IsMultilingual() {
		return createMultilingualPhonemizer(config)
	}
	return createSingleLanguagePhonemizer(config)
}

// createMultilingualPhonemizer builds a MultilingualPhonemizer from the config's
// LanguageIDMap. Japanese is skipped if no G2P engine is available.
func createMultilingualPhonemizer(config *VoiceConfig) (phonemize.Phonemizer, error) {
	phonemizers := make(map[string]phonemize.Phonemizer, len(config.LanguageIDMap))
	for lang := range config.LanguageIDMap {
		p, err := phonemizerForLanguage(lang)
		if err != nil {
			if lang == "ja" {
				// Japanese requires a native G2P engine; skip gracefully.
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
func createSingleLanguagePhonemizer(config *VoiceConfig) (phonemize.Phonemizer, error) {
	lang := ""
	if config.Language != nil {
		lang = config.Language.Code
	}

	// Try PhonemeType first, then fall back to language code.
	switch config.PhonemeType {
	case PhonemeTypeOpenJTalk:
		return nil, fmt.Errorf("Japanese requires G2P engine")
	case PhonemeTypeEspeak:
		if lang == "" {
			lang = "en"
		}
	}

	return phonemizerForLanguage(lang)
}

// phonemizerForLanguage creates a single-language phonemizer for the given code.
func phonemizerForLanguage(lang string) (phonemize.Phonemizer, error) {
	switch lang {
	case "ja":
		return nil, fmt.Errorf("Japanese requires G2P engine")
	case "en":
		// TODO: load CMU dict from dataDir when data directory support is added.
		slog.Warn("English phonemizer created without CMU dictionary; all words will use letter-by-letter fallback")
		p := phonemize.NewEnglishPhonemizer(nil)
		if p == nil {
			return nil, fmt.Errorf("failed to create English phonemizer")
		}
		return p, nil
	case "zh":
		// TODO: load pinyin dicts from dataDir when data directory support is added.
		slog.Warn("Chinese phonemizer created without pinyin dictionaries; hanzi phonemization may be degraded")
		p := phonemize.NewChinesePhonemizer(nil, nil)
		if p == nil {
			return nil, fmt.Errorf("failed to create Chinese phonemizer")
		}
		return p, nil
	case "es":
		return phonemize.NewSpanishPhonemizer(), nil
	case "fr":
		return phonemize.NewFrenchPhonemizer(), nil
	case "pt":
		return phonemize.NewPortuguesePhonemizer(), nil
	default:
		return nil, fmt.Errorf("unsupported language %q", lang)
	}
}

// Synthesize converts text to speech using the configured phonemizer.
// This is the high-level API that phonemizes text then runs inference.
func (v *Voice) Synthesize(ctx context.Context, text string, opts ...SynthesisOption) (*SynthesisResult, error) {
	if v.closed.Load() {
		return nil, ErrModelClosed
	}

	if v.phonemizer == nil {
		return nil, fmt.Errorf("piperplus: phonemizer not configured; use SynthesizeFromIDs for direct phoneme input")
	}

	if text == "" {
		return nil, ErrEmptyText
	}

	// Apply options, filling defaults from config.Inference.
	so := defaultSynthesisOptions()
	so.NoiseScale = v.config.Inference.NoiseScale
	so.LengthScale = v.config.Inference.LengthScale
	so.NoiseW = v.config.Inference.NoiseW
	for _, fn := range opts {
		fn(&so)
	}

	// Phonemize text.
	result, err := v.phonemizer.PhonemizeWithProsody(text)
	if err != nil {
		return nil, fmt.Errorf("piperplus: phonemization failed: %w", err)
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
		return nil, ErrEmptyPhonemeIDs
	}

	// Convert prosody to [][3]int64 for SynthesisRequest.
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
			return nil, fmt.Errorf("piperplus: unknown language %q; available: %v", so.Language, v.config.LanguageIDMap)
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

	// Build request and delegate to engine.
	req := &SynthesisRequest{
		PhonemeIDs:      phonemeIDs,
		SpeakerID:       so.SpeakerID,
		LanguageID:      languageID,
		NoiseScale:      so.NoiseScale,
		LengthScale:     so.LengthScale,
		NoiseW:          so.NoiseW,
		ProsodyFeatures: prosodyFeatures,
	}

	return v.engine.Synthesize(ctx, req)
}
