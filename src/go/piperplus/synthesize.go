package piperplus

import (
	"context"
	"fmt"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
)

// createPhonemizer builds the appropriate Phonemizer based on VoiceConfig.
// For multilingual models, creates MultilingualPhonemizer.
// For single-language models, creates the language-specific phonemizer.
func createPhonemizer(config *VoiceConfig, dataDir string) (phonemize.Phonemizer, error) {
	if config.IsMultilingual() && len(config.LanguageIDMap) > 1 {
		return createMultilingualPhonemizer(config)
	}
	return createSingleLanguagePhonemizer(config)
}

// createMultilingualPhonemizer builds a MultilingualPhonemizer from the config's
// LanguageIDMap. Japanese is skipped if no G2P engine is available.
func createMultilingualPhonemizer(config *VoiceConfig) (phonemize.Phonemizer, error) {
	languages := make([]string, 0, len(config.LanguageIDMap))
	for lang := range config.LanguageIDMap {
		languages = append(languages, lang)
	}

	defaultLatinLang := phonemize.DefaultLatinLanguage(languages)

	phonemizers := make(map[string]phonemize.Phonemizer, len(languages))
	for _, lang := range languages {
		p, err := phonemizerForLanguage(lang)
		if err != nil {
			// Japanese requires a G2P engine; skip gracefully.
			continue
		}
		phonemizers[lang] = p
	}

	if len(phonemizers) == 0 {
		return nil, fmt.Errorf("no phonemizers could be created for languages %v", languages)
	}

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
		return phonemize.NewEnglishPhonemizer(nil), nil
	case "zh":
		return phonemize.NewChinesePhonemizer(nil, nil), nil
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

	if v.config.IsMultilingual() && len(v.config.LanguageIDMap) > 1 {
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
	var languageID int64
	if so.Language != "" {
		if lid, ok := v.config.LanguageIDMap[so.Language]; ok {
			languageID = lid
		}
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
