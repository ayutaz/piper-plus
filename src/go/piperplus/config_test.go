package piperplus

import (
	"errors"
	"math"
	"os"
	"path/filepath"
	"testing"
)

// ---------------------------------------------------------------------------
// LoadConfig tests
// ---------------------------------------------------------------------------

func TestLoadConfig_ValidMultilingual(t *testing.T) {
	cfg, err := LoadConfig(filepath.Join("testdata", "valid_multilingual_config.json"))
	if err != nil {
		t.Fatalf("LoadConfig returned unexpected error: %v", err)
	}

	if cfg.NumLanguages != 6 {
		t.Errorf("NumLanguages = %d, want 6", cfg.NumLanguages)
	}
	if cfg.NumSpeakers != 1 {
		t.Errorf("NumSpeakers = %d, want 1", cfg.NumSpeakers)
	}
	if cfg.NumSymbols != 173 {
		t.Errorf("NumSymbols = %d, want 173", cfg.NumSymbols)
	}
	if cfg.Audio.SampleRate != 22050 {
		t.Errorf("Audio.SampleRate = %d, want 22050", cfg.Audio.SampleRate)
	}
	if cfg.PhonemeType != PhonemeTypeMultilingual {
		t.Errorf("PhonemeType = %q, want %q", cfg.PhonemeType, PhonemeTypeMultilingual)
	}

	// Float comparison with epsilon.
	const eps = 0.001
	if math.Abs(float64(cfg.Inference.NoiseScale)-0.667) > eps {
		t.Errorf("Inference.NoiseScale = %f, want ~0.667", cfg.Inference.NoiseScale)
	}

	// PhonemeIDMap spot checks.
	if ids, ok := cfg.PhonemeIDMap["_"]; !ok || len(ids) != 1 || ids[0] != 0 {
		t.Errorf("PhonemeIDMap[\"_\"] = %v, want [0]", ids)
	}
	if ids, ok := cfg.PhonemeIDMap["^"]; !ok || len(ids) != 1 || ids[0] != 1 {
		t.Errorf("PhonemeIDMap[\"^\"] = %v, want [1]", ids)
	}

	// LanguageIDMap spot checks.
	if id, ok := cfg.LanguageIDMap["ja"]; !ok || id != 0 {
		t.Errorf("LanguageIDMap[\"ja\"] = %d, want 0", id)
	}
	if id, ok := cfg.LanguageIDMap["en"]; !ok || id != 1 {
		t.Errorf("LanguageIDMap[\"en\"] = %d, want 1", id)
	}
}

func TestLoadConfig_MinimalConfig(t *testing.T) {
	cfg, err := LoadConfig(filepath.Join("testdata", "minimal_config.json"))
	if err != nil {
		t.Fatalf("LoadConfig returned unexpected error: %v", err)
	}

	// Defaults should be applied for fields not present in JSON.
	if cfg.NumSpeakers != 1 {
		t.Errorf("NumSpeakers = %d, want 1 (default)", cfg.NumSpeakers)
	}
	if cfg.NumLanguages != 1 {
		t.Errorf("NumLanguages = %d, want 1 (default)", cfg.NumLanguages)
	}
	if cfg.PhonemeType != PhonemeTypeEspeak {
		t.Errorf("PhonemeType = %q, want %q (default)", cfg.PhonemeType, PhonemeTypeEspeak)
	}
}

func TestLoadConfig_InvalidEmptyPhonemeMap(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_empty_phoneme_map.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error for empty phoneme_id_map")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_InvalidJSON(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_json.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error for malformed JSON")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_NonExistentFile(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "does_not_exist.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error for non-existent file")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_InvalidMissingAudio(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_missing_audio.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error when audio.sample_rate == 0")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_InvalidZeroSpeakers(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_zero_speakers.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error when num_speakers == 0")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_InvalidZeroLanguages(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_zero_languages.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error when num_languages == 0")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_InvalidMultilingualNoLangMap(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_multilingual_no_lang_map.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error for multilingual model with empty language_id_map")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestLoadConfig_InvalidMultiSpeakerNoSpeakerMap(t *testing.T) {
	_, err := LoadConfig(filepath.Join("testdata", "invalid_multispeaker_no_speaker_map.json"))
	if err == nil {
		t.Fatal("LoadConfig should return an error for multi-speaker model with empty speaker_id_map")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

// ---------------------------------------------------------------------------
// FindConfigPath tests
// ---------------------------------------------------------------------------

func TestFindConfigPath_ExplicitPath(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "my_config.json")
	if err := os.WriteFile(cfgPath, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create temp config: %v", err)
	}

	got, err := FindConfigPath(cfgPath, "")
	if err != nil {
		t.Fatalf("FindConfigPath returned unexpected error: %v", err)
	}
	if got != cfgPath {
		t.Errorf("FindConfigPath = %q, want %q", got, cfgPath)
	}
}

func TestFindConfigPath_Sidecar(t *testing.T) {
	dir := t.TempDir()
	modelPath := filepath.Join(dir, "model.onnx")
	sidecar := modelPath + ".json"

	// Create the sidecar file.
	if err := os.WriteFile(sidecar, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create sidecar: %v", err)
	}

	got, err := FindConfigPath("", modelPath)
	if err != nil {
		t.Fatalf("FindConfigPath returned unexpected error: %v", err)
	}
	if got != sidecar {
		t.Errorf("FindConfigPath = %q, want %q", got, sidecar)
	}
}

func TestFindConfigPath_DirConfig(t *testing.T) {
	dir := t.TempDir()
	modelPath := filepath.Join(dir, "model.onnx")
	dirConfig := filepath.Join(dir, "config.json")

	// Create config.json in the model directory (no sidecar).
	if err := os.WriteFile(dirConfig, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create dir config: %v", err)
	}

	got, err := FindConfigPath("", modelPath)
	if err != nil {
		t.Fatalf("FindConfigPath returned unexpected error: %v", err)
	}
	if got != dirConfig {
		t.Errorf("FindConfigPath = %q, want %q", got, dirConfig)
	}
}

func TestFindConfigPath_NotFound(t *testing.T) {
	dir := t.TempDir()
	modelPath := filepath.Join(dir, "model.onnx")

	_, err := FindConfigPath("", modelPath)
	if err == nil {
		t.Fatal("FindConfigPath should return an error when no config is found")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestFindConfigPath_EnvVarFileNotFound(t *testing.T) {
	// When PIPER_DEFAULT_CONFIG is explicitly set but the file doesn't exist,
	// FindConfigPath should return an error instead of silently falling through.
	t.Setenv("PIPER_DEFAULT_CONFIG", "/nonexistent/path/config.json")

	dir := t.TempDir()
	modelPath := filepath.Join(dir, "model.onnx")
	_, err := FindConfigPath("", modelPath)
	if err == nil {
		t.Fatal("FindConfigPath should return an error when PIPER_DEFAULT_CONFIG points to a non-existent file")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
}

func TestFindConfigPath_EnvVar(t *testing.T) {
	dir := t.TempDir()
	envConfig := filepath.Join(dir, "env_config.json")
	if err := os.WriteFile(envConfig, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create env config: %v", err)
	}

	// t.Setenv automatically restores the original value after the test.
	t.Setenv("PIPER_DEFAULT_CONFIG", envConfig)

	modelPath := filepath.Join(dir, "model.onnx")
	got, err := FindConfigPath("", modelPath)
	if err != nil {
		t.Fatalf("FindConfigPath returned unexpected error: %v", err)
	}
	if got != envConfig {
		t.Errorf("FindConfigPath = %q, want %q", got, envConfig)
	}
}

// ---------------------------------------------------------------------------
// VoiceConfig helper method tests
// ---------------------------------------------------------------------------

func TestVoiceConfig_HelperMethods(t *testing.T) {
	tests := []struct {
		name         string
		cfg          VoiceConfig
		multiSpeaker bool
		multilingual bool
		needsSID     bool
		needsLID     bool
		needsProsody bool
	}{
		{
			name:         "single speaker, single language, espeak",
			cfg:          VoiceConfig{NumSpeakers: 1, NumLanguages: 1, PhonemeType: PhonemeTypeEspeak},
			multiSpeaker: false, multilingual: false,
			needsSID: false, needsLID: false, needsProsody: false,
		},
		{
			name:         "multi speaker, single language, espeak",
			cfg:          VoiceConfig{NumSpeakers: 10, NumLanguages: 1, PhonemeType: PhonemeTypeEspeak},
			multiSpeaker: true, multilingual: false,
			needsSID: true, needsLID: false, needsProsody: false,
		},
		{
			name:         "single speaker, multilingual, multilingual type",
			cfg:          VoiceConfig{NumSpeakers: 1, NumLanguages: 6, PhonemeType: PhonemeTypeMultilingual},
			multiSpeaker: false, multilingual: true,
			needsSID: true, needsLID: true, needsProsody: true,
		},
		{
			name:         "multi speaker, multilingual, bilingual type",
			cfg:          VoiceConfig{NumSpeakers: 330, NumLanguages: 2, PhonemeType: PhonemeTypeBilingual},
			multiSpeaker: true, multilingual: true,
			needsSID: true, needsLID: true, needsProsody: true,
		},
		{
			name:         "single speaker, single language, openjtalk type",
			cfg:          VoiceConfig{NumSpeakers: 1, NumLanguages: 1, PhonemeType: PhonemeTypeOpenJTalk},
			multiSpeaker: false, multilingual: false,
			needsSID: false, needsLID: false, needsProsody: true,
		},
		{
			name:         "single speaker, single language, text type",
			cfg:          VoiceConfig{NumSpeakers: 1, NumLanguages: 1, PhonemeType: PhonemeTypeText},
			multiSpeaker: false, multilingual: false,
			needsSID: false, needsLID: false, needsProsody: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.cfg.IsMultiSpeaker(); got != tt.multiSpeaker {
				t.Errorf("IsMultiSpeaker() = %v, want %v", got, tt.multiSpeaker)
			}
			if got := tt.cfg.IsMultilingual(); got != tt.multilingual {
				t.Errorf("IsMultilingual() = %v, want %v", got, tt.multilingual)
			}
			if got := tt.cfg.NeedsSID(); got != tt.needsSID {
				t.Errorf("NeedsSID() = %v, want %v", got, tt.needsSID)
			}
			if got := tt.cfg.NeedsLID(); got != tt.needsLID {
				t.Errorf("NeedsLID() = %v, want %v", got, tt.needsLID)
			}
			if got := tt.cfg.NeedsProsody(); got != tt.needsProsody {
				t.Errorf("NeedsProsody() = %v, want %v", got, tt.needsProsody)
			}
		})
	}
}
