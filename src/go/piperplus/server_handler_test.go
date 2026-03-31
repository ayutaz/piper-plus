package piperplus

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// parseSynthesizeQuery — comprehensive tests
// ---------------------------------------------------------------------------

func TestParseSynthesizeQuery_AllParams(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet,
		"/synthesize?text=hello&lang=ja&speaker=7&noise_scale=0.3&length_scale=1.2&noise_w=0.6", nil)
	req, err := parseSynthesizeQuery(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if req.Text != "hello" {
		t.Errorf("Text = %q, want %q", req.Text, "hello")
	}
	if req.Language != "ja" {
		t.Errorf("Language = %q, want %q", req.Language, "ja")
	}
	if req.SpeakerID == nil || *req.SpeakerID != 7 {
		t.Errorf("SpeakerID = %v, want 7", req.SpeakerID)
	}
	if req.NoiseScale == nil || *req.NoiseScale != 0.3 {
		t.Errorf("NoiseScale = %v, want 0.3", req.NoiseScale)
	}
	if req.LengthScale == nil || *req.LengthScale != 1.2 {
		t.Errorf("LengthScale = %v, want 1.2", req.LengthScale)
	}
	if req.NoiseW == nil || *req.NoiseW != 0.6 {
		t.Errorf("NoiseW = %v, want 0.6", req.NoiseW)
	}
}

func TestParseSynthesizeQuery_ZeroValues(t *testing.T) {
	// Explicit zero values must be preserved (not treated as absent).
	r := httptest.NewRequest(http.MethodGet,
		"/synthesize?text=test&speaker=0&noise_scale=0&length_scale=0&noise_w=0", nil)
	req, err := parseSynthesizeQuery(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if req.SpeakerID == nil {
		t.Fatal("SpeakerID should not be nil when explicitly set to 0")
	}
	if *req.SpeakerID != 0 {
		t.Errorf("SpeakerID = %d, want 0", *req.SpeakerID)
	}
	if req.NoiseScale == nil {
		t.Fatal("NoiseScale should not be nil when explicitly set to 0")
	}
	if *req.NoiseScale != 0 {
		t.Errorf("NoiseScale = %f, want 0", *req.NoiseScale)
	}
	if req.LengthScale == nil {
		t.Fatal("LengthScale should not be nil when explicitly set to 0")
	}
	if *req.LengthScale != 0 {
		t.Errorf("LengthScale = %f, want 0", *req.LengthScale)
	}
	if req.NoiseW == nil {
		t.Fatal("NoiseW should not be nil when explicitly set to 0")
	}
	if *req.NoiseW != 0 {
		t.Errorf("NoiseW = %f, want 0", *req.NoiseW)
	}
}

func TestParseSynthesizeQuery_AbsentOptionalParams(t *testing.T) {
	// When optional params are absent, pointer fields must be nil.
	r := httptest.NewRequest(http.MethodGet, "/synthesize?text=test", nil)
	req, err := parseSynthesizeQuery(r)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if req.SpeakerID != nil {
		t.Errorf("SpeakerID = %v, want nil", req.SpeakerID)
	}
	if req.NoiseScale != nil {
		t.Errorf("NoiseScale = %v, want nil", req.NoiseScale)
	}
	if req.LengthScale != nil {
		t.Errorf("LengthScale = %v, want nil", req.LengthScale)
	}
	if req.NoiseW != nil {
		t.Errorf("NoiseW = %v, want nil", req.NoiseW)
	}
}

func TestParseSynthesizeQuery_InvalidSpeaker(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/synthesize?text=hello&speaker=abc", nil)
	_, err := parseSynthesizeQuery(r)
	if err == nil {
		t.Fatal("expected error for invalid speaker, got nil")
	}
	if !strings.Contains(err.Error(), "invalid speaker") {
		t.Errorf("error = %q, want to contain %q", err, "invalid speaker")
	}
}

func TestParseSynthesizeQuery_InvalidNoiseScale(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/synthesize?text=hello&noise_scale=notfloat", nil)
	_, err := parseSynthesizeQuery(r)
	if err == nil {
		t.Fatal("expected error for invalid noise_scale, got nil")
	}
	if !strings.Contains(err.Error(), "invalid noise_scale") {
		t.Errorf("error = %q, want to contain %q", err, "invalid noise_scale")
	}
}

func TestParseSynthesizeQuery_InvalidLengthScale(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/synthesize?text=hello&length_scale=xyz", nil)
	_, err := parseSynthesizeQuery(r)
	if err == nil {
		t.Fatal("expected error for invalid length_scale, got nil")
	}
	if !strings.Contains(err.Error(), "invalid length_scale") {
		t.Errorf("error = %q, want to contain %q", err, "invalid length_scale")
	}
}

func TestParseSynthesizeQuery_InvalidNoiseW(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/synthesize?text=hello&noise_w=bad", nil)
	_, err := parseSynthesizeQuery(r)
	if err == nil {
		t.Fatal("expected error for invalid noise_w, got nil")
	}
	if !strings.Contains(err.Error(), "invalid noise_w") {
		t.Errorf("error = %q, want to contain %q", err, "invalid noise_w")
	}
}

// ---------------------------------------------------------------------------
// synthesizeRequest JSON parsing with pointer fields
// ---------------------------------------------------------------------------

func TestSynthesizeRequest_JSON_ZeroValues(t *testing.T) {
	// JSON with explicit zero values must produce non-nil pointers.
	input := `{"text":"test","speaker_id":0,"noise_scale":0,"length_scale":0,"noise_w":0}`
	var req synthesizeRequest
	if err := json.Unmarshal([]byte(input), &req); err != nil {
		t.Fatalf("json.Unmarshal returned unexpected error: %v", err)
	}
	if req.SpeakerID == nil {
		t.Fatal("SpeakerID should not be nil when JSON value is 0")
	}
	if *req.SpeakerID != 0 {
		t.Errorf("SpeakerID = %d, want 0", *req.SpeakerID)
	}
	if req.NoiseScale == nil {
		t.Fatal("NoiseScale should not be nil when JSON value is 0")
	}
	if *req.NoiseScale != 0 {
		t.Errorf("NoiseScale = %f, want 0", *req.NoiseScale)
	}
	if req.LengthScale == nil {
		t.Fatal("LengthScale should not be nil when JSON value is 0")
	}
	if *req.LengthScale != 0 {
		t.Errorf("LengthScale = %f, want 0", *req.LengthScale)
	}
	if req.NoiseW == nil {
		t.Fatal("NoiseW should not be nil when JSON value is 0")
	}
	if *req.NoiseW != 0 {
		t.Errorf("NoiseW = %f, want 0", *req.NoiseW)
	}
}

func TestSynthesizeRequest_JSON_OmittedFields(t *testing.T) {
	// When fields are omitted from JSON, pointers must be nil.
	input := `{"text":"hello"}`
	var req synthesizeRequest
	if err := json.Unmarshal([]byte(input), &req); err != nil {
		t.Fatalf("json.Unmarshal returned unexpected error: %v", err)
	}
	if req.Text != "hello" {
		t.Errorf("Text = %q, want %q", req.Text, "hello")
	}
	if req.SpeakerID != nil {
		t.Errorf("SpeakerID = %v, want nil", req.SpeakerID)
	}
	if req.NoiseScale != nil {
		t.Errorf("NoiseScale = %v, want nil", req.NoiseScale)
	}
	if req.LengthScale != nil {
		t.Errorf("LengthScale = %v, want nil", req.LengthScale)
	}
	if req.NoiseW != nil {
		t.Errorf("NoiseW = %v, want nil", req.NoiseW)
	}
}

// ---------------------------------------------------------------------------
// HTTP handler tests — endpoints that don't require ONNX
// ---------------------------------------------------------------------------

// newTestServerWithMux creates a Server and registers routes, using a nil
// voice. Only use for endpoints that don't call voice methods.
func newTestServerWithMux() *Server {
	s := &Server{
		voice:  nil,
		logger: nil,
		mux:    http.NewServeMux(),
	}
	// Register only handlers that don't need a voice.
	s.mux.HandleFunc("/synthesize", s.handleSynthesize)
	s.mux.HandleFunc("/health", s.handleHealth)
	return s
}

func TestHandler_Health_GET(t *testing.T) {
	s := newTestServerWithMux()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusOK)
	}
	ct := w.Header().Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}
	var resp healthResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if resp.Status != "ok" {
		t.Errorf("status = %q, want %q", resp.Status, "ok")
	}
}

func TestHandler_Synthesize_BadContentType(t *testing.T) {
	s := newTestServerWithMux()
	body := strings.NewReader(`{"text":"hello"}`)
	req := httptest.NewRequest(http.MethodPost, "/synthesize", body)
	req.Header.Set("Content-Type", "text/plain")
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusUnsupportedMediaType {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusUnsupportedMediaType)
	}
	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to decode error response: %v", err)
	}
	if !strings.Contains(errResp["error"], "Content-Type") {
		t.Errorf("error = %q, want to contain %q", errResp["error"], "Content-Type")
	}
}

func TestHandler_Synthesize_InvalidJSON(t *testing.T) {
	s := newTestServerWithMux()
	body := strings.NewReader(`{invalid json}`)
	req := httptest.NewRequest(http.MethodPost, "/synthesize", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to decode error response: %v", err)
	}
	if !strings.Contains(errResp["error"], "invalid request") {
		t.Errorf("error = %q, want to contain %q", errResp["error"], "invalid request")
	}
}

func TestHandler_Synthesize_MissingText(t *testing.T) {
	s := newTestServerWithMux()
	body := strings.NewReader(`{"language":"en"}`)
	req := httptest.NewRequest(http.MethodPost, "/synthesize", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to decode error response: %v", err)
	}
	if !strings.Contains(errResp["error"], "text is required") {
		t.Errorf("error = %q, want to contain %q", errResp["error"], "text is required")
	}
}

func TestHandler_Synthesize_EmptyTextInJSON(t *testing.T) {
	s := newTestServerWithMux()
	body := strings.NewReader(`{"text":""}`)
	req := httptest.NewRequest(http.MethodPost, "/synthesize", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
}

func TestHandler_Synthesize_EmptyTextInQuery(t *testing.T) {
	s := newTestServerWithMux()
	req := httptest.NewRequest(http.MethodGet, "/synthesize?text=", nil)
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
}

func TestHandler_Synthesize_MethodNotAllowed(t *testing.T) {
	s := newTestServerWithMux()
	req := httptest.NewRequest(http.MethodDelete, "/synthesize", nil)
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusMethodNotAllowed)
	}
}

func TestHandler_Synthesize_GET_QueryParsing(t *testing.T) {
	// Verify that GET with query params reaches the text-required check
	// (which means parsing succeeded).
	s := newTestServerWithMux()
	req := httptest.NewRequest(http.MethodGet,
		"/synthesize?text=&speaker=0&noise_scale=0.5", nil)
	w := httptest.NewRecorder()
	s.mux.ServeHTTP(w, req)

	// Empty text -> 400
	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
}

// ---------------------------------------------------------------------------
// writeError
// ---------------------------------------------------------------------------

func TestWriteError(t *testing.T) {
	w := httptest.NewRecorder()
	writeError(w, http.StatusTeapot, "I'm a teapot")

	if w.Code != http.StatusTeapot {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusTeapot)
	}
	ct := w.Header().Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}
	var resp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to decode error response: %v", err)
	}
	if resp["error"] != "I'm a teapot" {
		t.Errorf("error = %q, want %q", resp["error"], "I'm a teapot")
	}
}
