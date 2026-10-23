package piperplus

import (
	"testing"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
)

// newLanguageTestVoice builds a multilingual Voice (en + es) without a model,
// enough for prepareSynthesisRequest. Every phoneme the two phonemizers can
// produce for "perro" has an ID.
func newLanguageTestVoice(t *testing.T) *Voice {
	t.Helper()
	config := &VoiceConfig{
		NumLanguages:  2,
		LanguageIDMap: map[string]int64{"en": 0, "es": 1},
		PhonemeIDMap:  map[string][]int64{"_": {0}, "^": {1}, "$": {2}, " ": {3}},
	}
	next := int64(4)
	for _, tok := range []string{"p", "e", "r", "o", "ɾ", "ˈ", phonemize.RegisterToken("rr")} {
		config.PhonemeIDMap[tok] = []int64{next}
		next++
	}
	dicts := &dictData{}
	ph, err := createMultilingualPhonemizer(config, dicts)
	if err != nil {
		t.Fatalf("createMultilingualPhonemizer: %v", err)
	}
	return &Voice{config: config, phonemizer: ph}
}

// TestPrepareSynthesisRequest_LanguageReachesPhonemizer checks that
// WithLanguage reads Latin text as that language. Latin script cannot tell
// Spanish from English, so without this the text is read as English.
func TestPrepareSynthesisRequest_LanguageReachesPhonemizer(t *testing.T) {
	v := newLanguageTestVoice(t)

	so := defaultSynthesisOptions()
	so.Language = "es"
	req, _, err := v.prepareSynthesisRequest("perro", so)
	if err != nil {
		t.Fatalf("prepareSynthesisRequest: %v", err)
	}
	if req.LanguageID != 1 {
		t.Errorf("LanguageID = %d, want 1", req.LanguageID)
	}

	es, err := phonemize.NewSpanishPhonemizer().PhonemizeWithProsody("perro")
	if err != nil {
		t.Fatalf("Spanish phonemizer: %v", err)
	}
	want, _ := phonemize.PostProcessMultilingualIDs(es, v.config.PhonemeIDMap)
	if !int64SliceEqual(req.PhonemeIDs, want) {
		t.Errorf("PhonemeIDs = %v, want the Spanish reading %v", req.PhonemeIDs, want)
	}
}

func int64SliceEqual(a, b []int64) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
