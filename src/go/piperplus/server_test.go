package piperplus

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// healthResponse JSON serialization
// ---------------------------------------------------------------------------

func TestHealthResponse(t *testing.T) {
	resp := healthResponse{Status: "ok"}
	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("json.Marshal returned unexpected error: %v", err)
	}
	if !strings.Contains(string(data), `"status":"ok"`) {
		t.Errorf("expected JSON to contain status ok, got %s", data)
	}
}

// ---------------------------------------------------------------------------
// infoResponse JSON serialization
// ---------------------------------------------------------------------------

func TestInfoResponse(t *testing.T) {
	info := infoResponse{
		NumSpeakers:  1,
		NumLanguages: 6,
		Languages:    map[string]int64{"ja": 0, "en": 1},
		SampleRate:   22050,
	}
	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("json.Marshal returned unexpected error: %v", err)
	}
	s := string(data)
	if !strings.Contains(s, `"num_speakers":1`) {
		t.Errorf("missing num_speakers in %s", s)
	}
	if !strings.Contains(s, `"sample_rate":22050`) {
		t.Errorf("missing sample_rate in %s", s)
	}
	if !strings.Contains(s, `"ja":0`) {
		t.Errorf("missing language ja in %s", s)
	}
}

// ---------------------------------------------------------------------------
// synthesizeRequest JSON parsing
// ---------------------------------------------------------------------------

func TestSynthesizeRequest_JSON(t *testing.T) {
	input := `{"text":"hello","language":"en","speaker_id":5}`
	var req synthesizeRequest
	if err := json.Unmarshal([]byte(input), &req); err != nil {
		t.Fatalf("json.Unmarshal returned unexpected error: %v", err)
	}
	if req.Text != "hello" {
		t.Errorf("Text = %q, want %q", req.Text, "hello")
	}
	if req.Language != "en" {
		t.Errorf("Language = %q, want %q", req.Language, "en")
	}
	if req.SpeakerID == nil || *req.SpeakerID != 5 {
		t.Errorf("SpeakerID = %v, want 5", req.SpeakerID)
	}
}

func TestSynthesizeRequest_EmptyText(t *testing.T) {
	input := `{"text":"","language":"ja"}`
	var req synthesizeRequest
	if err := json.Unmarshal([]byte(input), &req); err != nil {
		t.Fatalf("json.Unmarshal returned unexpected error: %v", err)
	}
	if req.Text != "" {
		t.Errorf("Text = %q, want empty", req.Text)
	}
}

// ---------------------------------------------------------------------------
// parseSynthesizeQuery
// ---------------------------------------------------------------------------

func TestParseSynthesizeQuery(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/synthesize?text=hello&lang=en&speaker=3&noise_scale=0.5", nil)
	req, err := parseSynthesizeQuery(r)
	if err != nil {
		t.Fatalf("parseSynthesizeQuery returned unexpected error: %v", err)
	}
	if req.Text != "hello" {
		t.Errorf("Text = %q, want %q", req.Text, "hello")
	}
	if req.Language != "en" {
		t.Errorf("Language = %q, want %q", req.Language, "en")
	}
	if req.SpeakerID == nil || *req.SpeakerID != 3 {
		t.Errorf("SpeakerID = %v, want 3", req.SpeakerID)
	}
	if req.NoiseScale == nil || *req.NoiseScale != 0.5 {
		t.Errorf("NoiseScale = %v, want 0.5", req.NoiseScale)
	}
}
