package piperplus

// Voice strips control characters before it reads a text.
//
// Contract: docs/spec/input-sanitize-contract.toml (runtime "go").
// Cases: tests/fixtures/g2p/input_sanitize_cases.json.
//
// Regression focus: before this, only the phonemizers stripped. A NUL in
// front of <speak> hid the SSML (its markup was read as words),
// SynthesizeStream split the raw text (a NUL inside "3.5" cut it in two, a
// NUL after the last sentence became an empty sentence), a custom text
// dictionary missed a word with a NUL inside it, and twenty NULs made
// "hola" too long for the short-text padding.
//
// These tests need no model: a recording phonemizer shows the text that
// reaches G2P. input_sanitize_integration_test.go compares real audio.

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
)

type sanitizeTextCase struct {
	Name     string `json:"name"`
	Language string `json:"language"`
	Control  string `json:"control"`
	Clean    string `json:"clean"`
	Dirty    string `json:"dirty"`
}

// sanitizeCasesFor returns the word cases of language and every pipeline
// case, from the shared fixture.
func sanitizeCasesFor(t *testing.T, language string) []sanitizeTextCase {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "..", "tests", "fixtures", "g2p", "input_sanitize_cases.json"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var doc struct {
		WordCases     []sanitizeTextCase `json:"word_cases"`
		PipelineCases []sanitizeTextCase `json:"pipeline_cases"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("parse fixture: %v", err)
	}
	var out []sanitizeTextCase
	for _, c := range doc.WordCases {
		if c.Language == language {
			out = append(out, c)
		}
	}
	if len(out) == 0 || len(doc.PipelineCases) == 0 {
		t.Fatalf("fixture has no %s word case or no pipeline case", language)
	}
	return append(out, doc.PipelineCases...)
}

// goLocalSanitizeCases are read only by Go: SSML is detected by the TTS
// runtime, and a control character in front of <speak> must not hide it.
var goLocalSanitizeCases = []sanitizeTextCase{
	{Name: "ssml_after_nul", Language: "es", Clean: "<speak>hola</speak>", Dirty: "\x00<speak>hola</speak>"},
	{Name: "ssml_after_ff", Language: "es", Clean: "<speak>hola</speak>", Dirty: "\f<speak>hola</speak>"},
}

func (c sanitizeTextCase) label() string {
	if c.Name != "" {
		return c.Name
	}
	return c.Language + " " + c.Control
}

var errRecorded = errors.New("recorded")

// recordingPhonemizer records each text that reaches G2P. With fail set it
// returns errRecorded, so Synthesize and SynthesizeStream stop before
// inference and need no model.
type recordingPhonemizer struct {
	inner phonemize.Phonemizer
	fail  bool
	mu    sync.Mutex
	texts []string
}

func (r *recordingPhonemizer) record(text string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.texts = append(r.texts, text)
	if r.fail {
		return errRecorded
	}
	return nil
}

func (r *recordingPhonemizer) PhonemizeWithProsody(text string) (*phonemize.PhonemizeResult, error) {
	if err := r.record(text); err != nil {
		return nil, err
	}
	return r.inner.PhonemizeWithProsody(text)
}

func (r *recordingPhonemizer) PhonemizeWithLanguage(text, language string) (*phonemize.PhonemizeResult, error) {
	if err := r.record(text); err != nil {
		return nil, err
	}
	return r.inner.(languagePhonemizer).PhonemizeWithLanguage(text, language)
}

func (r *recordingPhonemizer) LanguageCode() string { return r.inner.LanguageCode() }

func (r *recordingPhonemizer) take() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := r.texts
	r.texts = nil
	return out
}

func newRecordingVoice(t *testing.T, fail bool) (*Voice, *recordingPhonemizer) {
	t.Helper()
	v := newLanguageTestVoice(t)
	rec := &recordingPhonemizer{inner: v.phonemizer, fail: fail}
	v.phonemizer = rec
	return v, rec
}

func spanishOptions() SynthesisOptions {
	so := defaultSynthesisOptions()
	so.Language = "es"
	return so
}

// prepareSynthesisRequest is where Synthesize and every sentence of
// SynthesizeStream turn text into phoneme IDs.
func TestInputSanitize_PrepareSynthesisRequest(t *testing.T) {
	v, rec := newRecordingVoice(t, false)
	for _, c := range append(sanitizeCasesFor(t, "es"), goLocalSanitizeCases...) {
		if strings.HasPrefix(c.Name, "ssml") {
			continue // SSML is parsed by Synthesize, before this.
		}
		read := func(text string) ([]string, *SynthesisRequest, bool) {
			req, pad, err := v.prepareSynthesisRequest(text, spanishOptions())
			if err != nil {
				t.Fatalf("%s: prepareSynthesisRequest(%q): %v", c.label(), text, err)
			}
			return rec.take(), req, pad
		}
		dirtyTexts, dirtyReq, dirtyPad := read(c.Dirty)
		cleanTexts, cleanReq, cleanPad := read(c.Clean)
		if !reflect.DeepEqual(dirtyTexts, cleanTexts) {
			t.Errorf("%s: G2P got %q, want %q", c.label(), dirtyTexts, cleanTexts)
		}
		if !reflect.DeepEqual(dirtyReq, cleanReq) || dirtyPad != cleanPad {
			t.Errorf("%s: request differs (pad %v, want %v)", c.label(), dirtyPad, cleanPad)
		}
	}
}

func TestInputSanitize_ShortTextPaddingCountsStrippedText(t *testing.T) {
	v, _ := newRecordingVoice(t, false)
	_, cleanPad, err := v.prepareSynthesisRequest("hola", spanishOptions())
	if err != nil {
		t.Fatal(err)
	}
	if !cleanPad {
		t.Fatal(`"hola" should get the short-text padding`)
	}
	_, dirtyPad, err := v.prepareSynthesisRequest("ho"+strings.Repeat("\x00", 20)+"la", spanishOptions())
	if err != nil {
		t.Fatal(err)
	}
	if !dirtyPad {
		t.Error("twenty NULs inside \"hola\" lost the short-text padding")
	}
}

func TestInputSanitize_TextDictionaryFindsTheWord(t *testing.T) {
	path := filepath.Join(t.TempDir(), "dict.json")
	if err := os.WriteFile(path, []byte(`{"version":"2.0","entries":{"hola":{"pronunciation":"pero","priority":9}}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	td, err := phonemize.LoadTextDictJSON(path)
	if err != nil {
		t.Fatal(err)
	}
	v, rec := newRecordingVoice(t, false)
	v.textDict = td
	for _, text := range []string{"ho\x00la", "hola"} {
		if _, _, err := v.prepareSynthesisRequest(text, spanishOptions()); err != nil {
			t.Fatal(err)
		}
	}
	if got := rec.take(); !reflect.DeepEqual(got, []string{"pero", "pero"}) {
		t.Errorf("G2P got %q, want the dictionary reading twice", got)
	}
}

// readUntilG2P runs an entry point with a phonemizer that fails, and returns
// the texts that reached G2P before it stopped.
func readUntilG2P(t *testing.T, label string, run func(v *Voice) error) []string {
	t.Helper()
	v, rec := newRecordingVoice(t, true)
	if err := run(v); !errors.Is(err, errRecorded) {
		t.Fatalf("%s: want the recording error, got %v", label, err)
	}
	return rec.take()
}

func TestInputSanitize_Synthesize(t *testing.T) {
	for _, c := range append(sanitizeCasesFor(t, "es"), goLocalSanitizeCases...) {
		read := func(text string) []string {
			return readUntilG2P(t, c.label(), func(v *Voice) error {
				_, err := v.Synthesize(context.Background(), text, WithLanguage("es"))
				return err
			})
		}
		if dirty, clean := read(c.Dirty), read(c.Clean); !reflect.DeepEqual(dirty, clean) {
			t.Errorf("%s: G2P got %q, want %q", c.label(), dirty, clean)
		}
	}
}

func TestInputSanitize_SynthesizeStream(t *testing.T) {
	// One worker: the first sentence is phonemized first, and its text
	// shows where the text was split.
	t.Setenv("PIPER_PLUS_G2P_PARALLELISM", "1")
	for _, c := range append(sanitizeCasesFor(t, "es"), goLocalSanitizeCases...) {
		read := func(text string) []string {
			return readUntilG2P(t, c.label(), func(v *Voice) error {
				var buf strings.Builder
				return v.SynthesizeStream(context.Background(), text, NewWriterAudioSink(&buf), WithLanguage("es"))
			})
		}
		if dirty, clean := read(c.Dirty), read(c.Clean); !reflect.DeepEqual(dirty, clean) {
			t.Errorf("%s: G2P got %q, want %q", c.label(), dirty, clean)
		}
	}
}

// SynthesizeStream splits sentences after stripping. With a phonemizer that
// does not fail and an engine with no session, a stream that phonemized
// every sentence stops at inference with ErrModelClosed.
func TestInputSanitize_SynthesizeStreamSplitsTheStrippedText(t *testing.T) {
	t.Setenv("PIPER_PLUS_G2P_PARALLELISM", "1")
	cases := []sanitizeTextCase{
		// A NUL after the last sentence was a sentence of its own, and
		// stripping it there left an empty text (ErrEmptyText).
		{Name: "nul_after_last_sentence", Clean: "hola.", Dirty: "hola. \x00"},
		// A NUL between "3." and "5" hid the decimal point from the splitter.
		{Name: "nul_in_decimal", Clean: "3.5 metros.", Dirty: "3.\x005 metros."},
	}
	for _, c := range cases {
		read := func(text string) []string {
			v, rec := newRecordingVoice(t, false)
			v.engine = &OnnxEngine{}
			var buf strings.Builder
			err := v.SynthesizeStream(context.Background(), text, NewWriterAudioSink(&buf), WithLanguage("es"))
			if !errors.Is(err, ErrModelClosed) {
				t.Errorf("%s: SynthesizeStream(%q) = %v, want it to reach inference", c.Name, text, err)
			}
			return rec.take()
		}
		if dirty, clean := read(c.Dirty), read(c.Clean); !reflect.DeepEqual(dirty, clean) {
			t.Errorf("%s: G2P got %q, want %q", c.Name, dirty, clean)
		}
	}
}
