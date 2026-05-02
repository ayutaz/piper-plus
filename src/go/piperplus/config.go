package piperplus

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// PhonemeType represents the phonemization method.
type PhonemeType string

const (
	// PhonemeTypeEspeak is retained for legacy config.json compatibility only.
	//
	// Deprecated: piper-plus does NOT depend on espeak-ng (GPL-free design — see
	// CONTRIBUTING.md "espeak-ng Policy"). New models should not set
	// phoneme_type="espeak"; use PhonemeTypeOpenJTalk or PhonemeTypeMultilingual.
	PhonemeTypeEspeak    PhonemeType = "espeak"
	PhonemeTypeOpenJTalk PhonemeType = "openjtalk"
	// PhonemeTypeBilingual is retained for legacy v3/v4 JA+EN datasets.
	//
	// Deprecated: bilingual mode was replaced by 6-language multilingual training
	// in v1.7 (PR #218). New models should use PhonemeTypeMultilingual.
	PhonemeTypeBilingual    PhonemeType = "bilingual"
	PhonemeTypeMultilingual PhonemeType = "multilingual"
	PhonemeTypeText         PhonemeType = "text"
)

// VoiceConfig mirrors the piper-plus config.json structure.
type VoiceConfig struct {
	Dataset           string              `json:"dataset,omitempty"`
	Audio             AudioConfig         `json:"audio"`
	Espeak            *EspeakConfig       `json:"espeak,omitempty"`
	Language          *LanguageConfig     `json:"language,omitempty"`
	Inference         InferenceConfig     `json:"inference"`
	PhonemeType       PhonemeType         `json:"phoneme_type,omitempty"`
	PhonemeMap        map[string][]string `json:"phoneme_map,omitempty"`
	PhonemeIDMap      map[string][]int64  `json:"phoneme_id_map"`
	NumSymbols        int                 `json:"num_symbols"`
	NumSpeakers       int                 `json:"num_speakers"`
	SpeakerIDMap      map[string]int64    `json:"speaker_id_map,omitempty"`
	PiperVersion      string              `json:"piper_version,omitempty"`
	NumLanguages      int                 `json:"num_languages"`
	LanguageIDMap     map[string]int64    `json:"language_id_map,omitempty"`
	ProsodyNumSymbols int                 `json:"prosody_num_symbols,omitempty"`
	ProsodyIDMap      map[string][]int64  `json:"prosody_id_map,omitempty"`
}

// AudioConfig holds audio output parameters.
type AudioConfig struct {
	SampleRate int    `json:"sample_rate"`
	Quality    string `json:"quality,omitempty"`
	HopSize    int    `json:"hop_size,omitempty"`
}

// InferenceConfig holds noise/length scale parameters for synthesis.
type InferenceConfig struct {
	NoiseScale  float32 `json:"noise_scale"`
	LengthScale float32 `json:"length_scale"`
	NoiseW      float32 `json:"noise_w"`
}

// EspeakConfig holds espeak-ng voice configuration.
type EspeakConfig struct {
	Voice string `json:"voice,omitempty"`
}

// LanguageConfig holds language metadata.
type LanguageConfig struct {
	Code string `json:"code,omitempty"`
}

// LoadConfig reads a config.json file from path, applies defaults, and validates it.
func LoadConfig(path string) (*VoiceConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, &ConfigError{Path: path, Err: err}
	}

	cfg := &VoiceConfig{
		Audio: AudioConfig{
			SampleRate: 22050,
		},
		NumSpeakers:  1,
		NumLanguages: 1,
		PhonemeType:  PhonemeTypeEspeak,
		Inference: InferenceConfig{
			NoiseScale:  0.667,
			LengthScale: 1.0,
			NoiseW:      0.8,
		},
	}

	if err := json.Unmarshal(data, cfg); err != nil {
		return nil, &ConfigError{Path: path, Err: fmt.Errorf("invalid JSON: %w", err)}
	}

	if err := cfg.Validate(); err != nil {
		return nil, &ConfigError{Path: path, Err: err}
	}

	return cfg, nil
}

// FindConfigPath resolves the config file path using the following search order:
//  1. explicitPath (if non-empty, must exist)
//  2. PIPER_DEFAULT_CONFIG env var (if set and file exists)
//  3. {modelPath}.json (sidecar)
//  4. {modelDir}/config.json
func FindConfigPath(explicitPath, modelPath string) (string, error) {
	// 1. Explicit path — must exist.
	if explicitPath != "" {
		if _, err := os.Stat(explicitPath); err != nil {
			return "", &ConfigError{Path: explicitPath, Err: err}
		}
		return explicitPath, nil
	}

	// 2. Environment variable — if explicitly set, file must exist.
	if envPath := os.Getenv("PIPER_DEFAULT_CONFIG"); envPath != "" {
		if _, err := os.Stat(envPath); err != nil {
			return "", &ConfigError{
				Path: envPath,
				Err:  fmt.Errorf("PIPER_DEFAULT_CONFIG set but file not found: %w", err),
			}
		}
		return envPath, nil
	}

	if modelPath != "" {
		// 3. Sidecar: model.onnx -> model.onnx.json
		sidecar := modelPath + ".json"
		if _, err := os.Stat(sidecar); err == nil {
			return sidecar, nil
		}

		// 4. Same directory: {modelDir}/config.json
		dirConfig := filepath.Join(filepath.Dir(modelPath), "config.json")
		if _, err := os.Stat(dirConfig); err == nil {
			return dirConfig, nil
		}
	}

	return "", &ConfigError{
		Path: modelPath,
		Err:  fmt.Errorf("no config found for model %q", modelPath),
	}
}

// Validate checks that required fields are present and valid.
func (c *VoiceConfig) Validate() error {
	if len(c.PhonemeIDMap) == 0 {
		return fmt.Errorf("phoneme_id_map is empty")
	}
	if c.Audio.SampleRate <= 0 {
		return fmt.Errorf("audio.sample_rate must be > 0, got %d", c.Audio.SampleRate)
	}
	if c.NumSpeakers <= 0 {
		return fmt.Errorf("num_speakers must be > 0, got %d", c.NumSpeakers)
	}
	if c.NumLanguages <= 0 {
		return fmt.Errorf("num_languages must be > 0, got %d", c.NumLanguages)
	}
	if c.NumLanguages > 1 && len(c.LanguageIDMap) == 0 {
		return fmt.Errorf("language_id_map is required for multilingual models (num_languages=%d)", c.NumLanguages)
	}
	if c.NumSpeakers > 1 && len(c.SpeakerIDMap) == 0 {
		return fmt.Errorf("speaker_id_map is required for multi-speaker models (num_speakers=%d)", c.NumSpeakers)
	}
	return nil
}

// IsMultiSpeaker reports whether the model supports multiple speakers.
func (c *VoiceConfig) IsMultiSpeaker() bool {
	return c.NumSpeakers > 1
}

// IsMultilingual reports whether the model supports multiple languages.
func (c *VoiceConfig) IsMultilingual() bool {
	return c.NumLanguages > 1
}

// NeedsSID reports whether speaker ID input is required for inference.
func (c *VoiceConfig) NeedsSID() bool {
	return c.IsMultiSpeaker() || c.IsMultilingual()
}

// NeedsLID reports whether language ID input is required for inference.
func (c *VoiceConfig) NeedsLID() bool {
	return c.IsMultilingual()
}

// NeedsProsody reports whether prosody features are used by the model.
// This is true for phoneme types that carry prosodic information:
// openjtalk, bilingual, and multilingual.
func (c *VoiceConfig) NeedsProsody() bool {
	switch c.PhonemeType {
	case PhonemeTypeOpenJTalk, PhonemeTypeBilingual, PhonemeTypeMultilingual:
		return true
	default:
		return false
	}
}
