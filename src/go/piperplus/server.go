package piperplus

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// Server is an HTTP TTS server.
type Server struct {
	voice  *Voice
	logger *slog.Logger
	mux    *http.ServeMux
}

type synthesizeRequest struct {
	Text        string   `json:"text"`
	Language    string   `json:"language,omitempty"`
	SpeakerID   *int64   `json:"speaker_id,omitempty"`
	NoiseScale  *float32 `json:"noise_scale,omitempty"`
	LengthScale *float32 `json:"length_scale,omitempty"`
	NoiseW      *float32 `json:"noise_w,omitempty"`
}

type healthResponse struct {
	Status string `json:"status"`
}

type infoResponse struct {
	NumSpeakers  int               `json:"num_speakers"`
	NumLanguages int               `json:"num_languages"`
	Languages    map[string]int64  `json:"languages,omitempty"`
	Capabilities ModelCapabilities `json:"capabilities"`
	SampleRate   int               `json:"sample_rate"`
}

// NewServer creates a new TTS HTTP server.
func NewServer(voice *Voice, logger *slog.Logger) *Server {
	if logger == nil {
		logger = slog.Default()
	}
	s := &Server{
		voice:  voice,
		logger: logger,
		mux:    http.NewServeMux(),
	}
	s.mux.HandleFunc("/synthesize", s.handleSynthesize)
	s.mux.HandleFunc("/health", s.handleHealth)
	s.mux.HandleFunc("/info", s.handleInfo)
	return s
}

// Handler returns the http.Handler for this server.
func (s *Server) Handler() http.Handler {
	return s.mux
}

// ListenAndServe starts the server on the given address.
func (s *Server) ListenAndServe(addr string) error {
	s.logger.Info("starting TTS server", "addr", addr)
	srv := &http.Server{
		Addr:              addr,
		Handler:           s.mux,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      120 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	return srv.ListenAndServe()
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(healthResponse{Status: "ok"})
}

func (s *Server) handleInfo(w http.ResponseWriter, r *http.Request) {
	cfg := s.voice.Config()
	resp := infoResponse{
		NumSpeakers:  cfg.NumSpeakers,
		NumLanguages: cfg.NumLanguages,
		Languages:    cfg.LanguageIDMap,
		Capabilities: s.voice.Capabilities(),
		SampleRate:   cfg.Audio.SampleRate,
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

func (s *Server) handleSynthesize(w http.ResponseWriter, r *http.Request) {
	var req synthesizeRequest
	var err error

	switch r.Method {
	case http.MethodGet:
		req, err = parseSynthesizeQuery(r)
	case http.MethodPost:
		ct := r.Header.Get("Content-Type")
		if !strings.Contains(ct, "application/json") {
			writeError(w, http.StatusUnsupportedMediaType, "Content-Type must be application/json")
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 1*1024*1024) // 1 MB limit
		err = json.NewDecoder(r.Body).Decode(&req)
	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	if err != nil {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid request: %v", err))
		return
	}

	if req.Text == "" {
		writeError(w, http.StatusBadRequest, "text is required")
		return
	}

	// Build synthesis options.
	var opts []SynthesisOption
	if req.Language != "" {
		opts = append(opts, WithLanguage(req.Language))
	}
	if req.SpeakerID != nil {
		opts = append(opts, WithSpeakerID(*req.SpeakerID))
	}
	if req.NoiseScale != nil {
		opts = append(opts, WithNoiseScale(*req.NoiseScale))
	}
	if req.LengthScale != nil {
		opts = append(opts, WithLengthScale(*req.LengthScale))
	}
	if req.NoiseW != nil {
		opts = append(opts, WithNoiseW(*req.NoiseW))
	}

	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
	defer cancel()

	result, err := s.voice.Synthesize(ctx, req.Text, opts...)
	if err != nil {
		s.logger.Error("synthesis failed", "error", err, "text_len", len(req.Text))
		writeError(w, http.StatusInternalServerError, "synthesis failed")
		return
	}

	s.logger.Info("synthesized",
		"text_len", len(req.Text),
		"duration", result.Duration,
		"rtf", fmt.Sprintf("%.2f", result.RTF()),
	)

	w.Header().Set("Content-Type", "audio/wav")
	if _, err := result.WriteTo(w); err != nil {
		s.logger.Error("failed to write response", "error", err)
	}
}

func parseSynthesizeQuery(r *http.Request) (synthesizeRequest, error) {
	q := r.URL.Query()
	req := synthesizeRequest{
		Text:     q.Get("text"),
		Language: q.Get("lang"),
	}

	if q.Has("speaker") {
		id, err := strconv.ParseInt(q.Get("speaker"), 10, 64)
		if err != nil {
			return req, fmt.Errorf("invalid speaker: %w", err)
		}
		req.SpeakerID = &id
	}
	if q.Has("noise_scale") {
		f, err := strconv.ParseFloat(q.Get("noise_scale"), 32)
		if err != nil {
			return req, fmt.Errorf("invalid noise_scale: %w", err)
		}
		v := float32(f)
		req.NoiseScale = &v
	}
	if q.Has("length_scale") {
		f, err := strconv.ParseFloat(q.Get("length_scale"), 32)
		if err != nil {
			return req, fmt.Errorf("invalid length_scale: %w", err)
		}
		v := float32(f)
		req.LengthScale = &v
	}
	if q.Has("noise_w") {
		f, err := strconv.ParseFloat(q.Get("noise_w"), 32)
		if err != nil {
			return req, fmt.Errorf("invalid noise_w: %w", err)
		}
		v := float32(f)
		req.NoiseW = &v
	}
	return req, nil
}

func writeError(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
