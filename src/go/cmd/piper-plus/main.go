package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

// CLI flags.
var (
	modelPath       string
	configPath      string
	textInput       string
	language        string
	speakerID       int64
	outputFile      string
	outputDir       string
	noiseScale      float32
	lengthScale     float32
	noiseW          float32
	sentenceSilence float64
	device          string
	streaming       bool
	batchFile       string
	timingOutput    string
	timingFormat    string
	debug           bool
	customDictPaths []string // --custom-dict (repeatable)

	// Additional CLI flags matching C++ implementation.
	version        bool     // --version
	quiet          bool     // -q, --quiet
	outputRaw      bool     // --output-raw
	jsonInput      bool     // --json-input
	listModels     bool     // --list-models
	downloadModel  string   // --download-model NAME
	modelDir       string   // --model-dir DIR
	phonemeSilence []string // --phoneme-silence (repeatable, "phoneme:seconds" format)

	// Voice cloning flags
	referenceAudio      string // --reference-audio PATH
	speakerEmbedding    string // --speaker-embedding PATH
	speakerEncoderModel string // --speaker-encoder-model PATH
)

// jsonlInput represents a single line of JSONL input from stdin or batch file.
type jsonlInput struct {
	PhonemeIDs      []int64    `json:"phoneme_ids,omitempty"`
	Text            string     `json:"text,omitempty"`
	SpeakerID       *int64     `json:"speaker_id,omitempty"`
	LanguageID      *int64     `json:"language_id,omitempty"`
	Language        string     `json:"language,omitempty"`
	ProsodyFeatures [][3]int64 `json:"prosody_features,omitempty"`
}

var rootCmd = &cobra.Command{
	Use:          "piper-plus",
	Short:        "Neural text-to-speech synthesis",
	SilenceUsage: true,
	RunE:         runSynthesize,
}

func init() {
	// Persistent flags shared across subcommands (synthesize + serve).
	pf := rootCmd.PersistentFlags()
	pf.StringVarP(&modelPath, "model", "m", "", "path to ONNX model file (or $PIPER_DEFAULT_MODEL)")
	pf.StringVarP(&configPath, "config", "c", "", "path to config.json (auto-detected if omitted)")
	pf.StringVar(&device, "device", "cpu", "inference device (cpu, cuda, coreml, directml)")
	pf.BoolVar(&debug, "debug", false, "enable debug logging")
	pf.BoolVarP(&quiet, "quiet", "q", false, "disable all logging")
	pf.StringArrayVar(&customDictPaths, "custom-dict", nil, "custom dictionary JSON file paths (repeatable)")
	pf.StringVar(&modelDir, "model-dir", "", "model cache directory override")

	// Local flags for synthesis mode only.
	f := rootCmd.Flags()
	f.StringVarP(&textInput, "text", "t", "", "text to synthesize (single utterance mode)")
	f.StringVar(&language, "language", "", "language code (e.g. ja, en, zh, ko)")
	f.Int64VarP(&speakerID, "speaker", "s", 0, "speaker ID for multi-speaker models")
	f.StringVarP(&outputFile, "output-file", "f", "", "output WAV path (- for stdout)")
	f.StringVarP(&outputDir, "output-dir", "d", ".", "output directory for generated files")
	f.Float32Var(&noiseScale, "noise-scale", 0.667, "generation noise scale")
	f.Float32Var(&lengthScale, "length-scale", 1.0, "speech rate (length scale)")
	f.Float32Var(&noiseW, "noise-w", 0.8, "duration predictor noise scale")
	f.Float64Var(&sentenceSilence, "sentence-silence", 0.2, "silence between sentences in seconds")
	f.BoolVar(&streaming, "streaming", false, "write raw PCM int16 to stdout (no WAV header)")
	f.StringVar(&batchFile, "batch", "", "batch file with one text line per utterance")
	f.StringVar(&timingOutput, "output-timing", "", "write phoneme timing to file")
	f.StringVar(&timingFormat, "timing-format", "json", "timing output format (json or tsv)")
	f.BoolVar(&version, "version", false, "print version and exit")
	f.BoolVar(&outputRaw, "output-raw", false, "output raw PCM audio to stdout (no WAV header)")
	f.BoolVar(&jsonInput, "json-input", false, "read stdin as JSON lines")
	f.BoolVar(&listModels, "list-models", false, "list downloaded models in cache directory")
	f.StringVar(&downloadModel, "download-model", "", "download model by URL into cache directory")
	f.StringArrayVar(&phonemeSilence, "phoneme-silence", nil, "per-phoneme silence (format: phoneme:seconds, repeatable)")

	// Voice cloning flags
	f.StringVar(&referenceAudio, "reference-audio", "", "reference audio file for voice cloning (WAV)")
	f.StringVar(&speakerEmbedding, "speaker-embedding", "", "pre-computed speaker embedding file (raw binary float32)")
	f.StringVar(&speakerEncoderModel, "speaker-encoder-model", "", "speaker encoder ONNX model path")

	rootCmd.AddCommand(serveCmd)
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

// stdinHasData reports whether stdin is connected to a pipe or file (i.e. not a
// terminal). This is used to detect whether JSONL is being piped in.
func stdinHasData() bool {
	fi, err := os.Stdin.Stat()
	if err != nil {
		return false
	}
	return fi.Mode()&os.ModeCharDevice == 0
}

func runSynthesize(cmd *cobra.Command, args []string) error {
	// --version: print version and exit immediately.
	if version {
		fmt.Println("piper-plus (Go) v0.2.0")
		return nil
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	// Configure logging.
	level := slog.LevelInfo
	if debug {
		level = slog.LevelDebug
	}
	if quiet {
		level = slog.LevelError + 1 // suppress all output
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level}))

	// --list-models: list downloaded models and exit.
	if listModels {
		mgr := piperplus.NewModelManager(modelDir, logger)
		models, err := mgr.ListModels()
		if err != nil {
			return fmt.Errorf("failed to list models: %w", err)
		}
		if len(models) == 0 {
			fmt.Fprintf(os.Stderr, "no models found in %s\n", mgr.CacheDir())
			return nil
		}
		for _, m := range models {
			fmt.Printf("%-40s %6.1f MB  %s\n", m.Name, m.SizeMB, m.Path)
		}
		return nil
	}

	// --download-model: download a model by URL and exit.
	if downloadModel != "" {
		mgr := piperplus.NewModelManager(modelDir, logger)
		path, err := mgr.DownloadModel(ctx, downloadModel)
		if err != nil {
			return fmt.Errorf("download failed: %w", err)
		}
		fmt.Println(path)
		return nil
	}

	// Resolve model path: flag > env.
	if modelPath == "" {
		modelPath = os.Getenv("PIPER_DEFAULT_MODEL")
	}
	if modelPath == "" {
		return fmt.Errorf("model path required: specify --model /path/to/model.onnx or set $PIPER_DEFAULT_MODEL")
	}

	// Try resolving model name/alias if file doesn't exist.
	if _, err := os.Stat(modelPath); os.IsNotExist(err) {
		mgr := piperplus.NewModelManager(modelDir, logger)
		resolved, resolveErr := mgr.FindModel(modelPath)
		if resolveErr != nil {
			return fmt.Errorf("model not found: %s (try --list-models or --download-model)", modelPath)
		}
		modelPath = resolved
	}

	// Parse --phoneme-silence flags ("phoneme:seconds" format).
	var phonemeSilenceMap map[string]float64
	if len(phonemeSilence) > 0 {
		phonemeSilenceMap = make(map[string]float64, len(phonemeSilence))
		for _, ps := range phonemeSilence {
			parts := strings.SplitN(ps, ":", 2)
			if len(parts) != 2 {
				return fmt.Errorf("invalid --phoneme-silence format %q (expected phoneme:seconds)", ps)
			}
			var secs float64
			if _, err := fmt.Sscanf(parts[1], "%f", &secs); err != nil {
				return fmt.Errorf("invalid silence duration in %q: %w", ps, err)
			}
			phonemeSilenceMap[parts[0]] = secs
		}
	}

	// Validate mutually exclusive input modes (fix #3).
	hasText := textInput != ""
	hasBatch := batchFile != ""
	hasStdin := stdinHasData() || jsonInput
	modeCount := 0
	if hasText {
		modeCount++
	}
	if hasBatch {
		modeCount++
	}
	if hasStdin {
		modeCount++
	}
	if modeCount > 1 {
		return fmt.Errorf("input modes are mutually exclusive: specify only one of --text, --batch, or piped stdin JSONL")
	}

	// Initialize ONNX Runtime.
	if err := piperplus.Init(""); err != nil {
		return fmt.Errorf("failed to initialize ONNX Runtime: %w", err)
	}
	defer piperplus.Shutdown() //nolint:errcheck

	// Load voice.
	var loadOpts []piperplus.LoadOption
	if configPath != "" {
		loadOpts = append(loadOpts, piperplus.WithConfig(configPath))
	}
	loadOpts = append(loadOpts, piperplus.WithDevice(device))
	loadOpts = append(loadOpts, piperplus.WithLogger(logger))
	if len(customDictPaths) > 0 {
		loadOpts = append(loadOpts, piperplus.WithCustomDict(customDictPaths...))
	}
	if phonemeSilenceMap != nil {
		loadOpts = append(loadOpts, piperplus.WithPhonemeSilenceLoad(phonemeSilenceMap))
	}

	voice, err := piperplus.LoadVoice(ctx, modelPath, loadOpts...)
	if err != nil {
		return fmt.Errorf("failed to load voice: %w", err)
	}
	defer voice.Close() //nolint:errcheck

	// Dispatch to the appropriate input mode.
	switch {
	case hasText:
		return runTextMode(ctx, voice, logger)
	case hasBatch:
		return runBatchMode(ctx, voice, logger)
	case hasStdin:
		return runJSONLMode(ctx, voice, logger)
	default:
		return fmt.Errorf("no input provided: use --text, --batch, or pipe JSONL to stdin")
	}
}

// buildSynthOpts constructs functional SynthesisOption values from CLI flags.
func buildSynthOpts() []piperplus.SynthesisOption {
	var opts []piperplus.SynthesisOption
	if language != "" {
		opts = append(opts, piperplus.WithLanguage(language))
	}
	opts = append(opts, piperplus.WithSpeakerID(speakerID))
	opts = append(opts, piperplus.WithNoiseScale(noiseScale))
	opts = append(opts, piperplus.WithLengthScale(lengthScale))
	opts = append(opts, piperplus.WithNoiseW(noiseW))
	opts = append(opts, piperplus.WithSentenceSilence(sentenceSilence))
	return opts
}

// synthesizeText runs text-level synthesis using Voice.Synthesize with CLI options.
func synthesizeText(ctx context.Context, voice *piperplus.Voice, text string) (*piperplus.SynthesisResult, error) {
	opts := buildSynthOpts()
	return voice.Synthesize(ctx, text, opts...)
}

// synthesizeJSONL dispatches a JSONL entry: if it has phoneme_ids, use
// SynthesizeFromIDs; if it has text, use Synthesize; otherwise error.
func synthesizeJSONL(ctx context.Context, voice *piperplus.Voice, input *jsonlInput) (*piperplus.SynthesisResult, error) {
	if len(input.PhonemeIDs) > 0 {
		req := buildRequest(input)
		return voice.SynthesizeFromIDs(ctx, req)
	}
	if input.Text != "" {
		opts := buildSynthOptsFromJSONL(input)
		return voice.Synthesize(ctx, input.Text, opts...)
	}
	return nil, fmt.Errorf("JSONL entry must contain \"phoneme_ids\" or \"text\"")
}

// buildSynthOptsFromJSONL builds SynthesisOption values by merging JSONL fields
// over CLI flag defaults.
func buildSynthOptsFromJSONL(input *jsonlInput) []piperplus.SynthesisOption {
	opts := buildSynthOpts()
	if input.Language != "" {
		opts = append(opts, piperplus.WithLanguage(input.Language))
	}
	if input.SpeakerID != nil {
		opts = append(opts, piperplus.WithSpeakerID(*input.SpeakerID))
	}
	return opts
}

// runTextMode synthesizes a single --text utterance (fix #1).
func runTextMode(ctx context.Context, voice *piperplus.Voice, logger *slog.Logger) error {
	result, err := synthesizeText(ctx, voice, textInput)
	if err != nil {
		return fmt.Errorf("synthesis failed: %w", err)
	}

	logger.Info("synthesized",
		"duration", result.Duration,
		"infer_time", result.InferTime,
		"rtf", fmt.Sprintf("%.3f", result.RTF()),
	)

	outPath := outputFilePath(outputFile, outputDir, "output.wav")
	if err := writeResult(ctx, result, outputFile, outputDir, "output.wav"); err != nil {
		cleanupPartial(outPath, logger)
		return err
	}

	return writeTiming(result, logger)
}

// runBatchMode reads a batch file line by line and synthesizes each (fix #2).
// Each line is treated as either plain text or JSONL (if it starts with '{').
func runBatchMode(ctx context.Context, voice *piperplus.Voice, logger *slog.Logger) error {
	f, err := os.Open(batchFile)
	if err != nil {
		return fmt.Errorf("failed to open batch file: %w", err)
	}
	defer func() { _ = f.Close() }()

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	lineNum := 0
	for scanner.Scan() {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		lineNum++
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		result, err := synthesizeLine(ctx, voice, line)
		if err != nil {
			return fmt.Errorf("synthesis failed on line %d: %w", lineNum, err)
		}

		filename := fmt.Sprintf("line_%03d.wav", lineNum)
		outPath := outputFilePath("", outputDir, filename)
		if err := writeResult(ctx, result, "", outputDir, filename); err != nil {
			cleanupPartial(outPath, logger)
			return err
		}

		logger.Info("synthesized",
			"line", lineNum,
			"duration", result.Duration,
			"rtf", fmt.Sprintf("%.3f", result.RTF()),
		)
	}
	return scanner.Err()
}

// runJSONLMode reads JSONL from stdin and synthesizes each entry.
func runJSONLMode(ctx context.Context, voice *piperplus.Voice, logger *slog.Logger) error {
	scanner := bufio.NewScanner(os.Stdin)
	// Allow up to 1 MB per line.
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	lineNum := 0
	for scanner.Scan() {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		lineNum++
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		var input jsonlInput
		if err := json.Unmarshal([]byte(line), &input); err != nil {
			return fmt.Errorf("invalid JSON on line %d: %w", lineNum, err)
		}

		result, err := synthesizeJSONL(ctx, voice, &input)
		if err != nil {
			return fmt.Errorf("synthesis failed on line %d: %w", lineNum, err)
		}

		filename := fmt.Sprintf("line_%03d.wav", lineNum)
		outPath := outputFilePath("", outputDir, filename)
		if err := writeResult(ctx, result, "", outputDir, filename); err != nil {
			cleanupPartial(outPath, logger)
			return err
		}

		logger.Info("synthesized",
			"line", lineNum,
			"duration", result.Duration,
			"rtf", fmt.Sprintf("%.3f", result.RTF()),
		)
	}
	return scanner.Err()
}

// synthesizeLine dispatches a single line from batch mode: if the line looks
// like JSON (starts with '{'), parse as JSONL; otherwise treat as plain text.
func synthesizeLine(ctx context.Context, voice *piperplus.Voice, line string) (*piperplus.SynthesisResult, error) {
	if strings.HasPrefix(line, "{") {
		var input jsonlInput
		if err := json.Unmarshal([]byte(line), &input); err != nil {
			return nil, fmt.Errorf("invalid JSON: %w", err)
		}
		return synthesizeJSONL(ctx, voice, &input)
	}
	return synthesizeText(ctx, voice, line)
}

// buildRequest constructs a SynthesisRequest from CLI flags and optional JSONL input.
// Used only for the phoneme-ID path (SynthesizeFromIDs).
func buildRequest(input *jsonlInput) *piperplus.SynthesisRequest {
	req := &piperplus.SynthesisRequest{
		SpeakerID:   speakerID,
		NoiseScale:  noiseScale,
		LengthScale: lengthScale,
		NoiseW:      noiseW,
	}

	if input != nil {
		// Use phoneme IDs from JSONL if provided.
		if len(input.PhonemeIDs) > 0 {
			req.PhonemeIDs = input.PhonemeIDs
		}
		// Override speaker ID from JSONL.
		if input.SpeakerID != nil {
			req.SpeakerID = *input.SpeakerID
		}
		// Override language ID from JSONL.
		if input.LanguageID != nil {
			req.LanguageID = *input.LanguageID
		}
		// Set prosody features from JSONL.
		if input.ProsodyFeatures != nil {
			req.ProsodyFeatures = input.ProsodyFeatures
		}
	}

	return req
}

// outputFilePath returns the resolved output path for a given file, used for
// cleanup tracking.
func outputFilePath(outFile, outDir, defaultName string) string {
	if streaming || outputRaw || outFile == "-" {
		return ""
	}
	if outFile != "" {
		return outFile
	}
	return filepath.Join(outDir, defaultName)
}

// writeResult writes a SynthesisResult to the appropriate output target.
// It checks for context cancellation before writing to catch interrupt signals.
func writeResult(_ context.Context, result *piperplus.SynthesisResult, outFile, outDir, defaultName string) error {
	if streaming || outputRaw {
		_, err := io.Copy(os.Stdout, result.RawPCMReader())
		return err
	}

	if outFile == "-" {
		return result.WriteWAV(os.Stdout)
	}

	path := outFile
	if path == "" {
		path = filepath.Join(outDir, defaultName)
	}

	// Ensure output directory exists.
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("failed to create output directory %s: %w", dir, err)
	}

	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("failed to create output file %s: %w", path, err)
	}
	defer func() { _ = f.Close() }()

	if err := result.WriteWAV(f); err != nil {
		return fmt.Errorf("failed to write WAV to %s: %w", path, err)
	}
	return nil
}

// cleanupPartial removes a partial output file on cancellation or error.
// Failures are logged but not propagated.
func cleanupPartial(path string, logger *slog.Logger) {
	if path == "" {
		return
	}
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		logger.Warn("failed to clean up partial output", "path", path, "error", err)
	}
}

// writeTiming writes phoneme timing data if --output-timing is set and durations are available.
func writeTiming(result *piperplus.SynthesisResult, logger *slog.Logger) error {
	if timingOutput == "" || result.Durations == nil {
		return nil
	}

	// Build placeholder phoneme tokens (indices as strings).
	tokens := make([]string, len(result.Durations))
	for i := range tokens {
		tokens[i] = fmt.Sprintf("p%d", i)
	}

	hopLength := piperplus.DefaultHopLength
	timing, err := piperplus.DurationsToTiming(result.Durations, tokens, result.SampleRate, hopLength)
	if err != nil {
		return fmt.Errorf("failed to compute timing: %w", err)
	}

	var data []byte
	switch strings.ToLower(timingFormat) {
	case "tsv":
		data = []byte(timing.ToTSV())
	default:
		data, err = timing.ToJSON()
		if err != nil {
			return fmt.Errorf("failed to marshal timing JSON: %w", err)
		}
		data = append(data, '\n')
	}

	if timingOutput == "-" {
		_, err = os.Stdout.Write(data)
		return err
	}

	if err := os.WriteFile(timingOutput, data, 0o644); err != nil {
		return fmt.Errorf("failed to write timing to %s: %w", timingOutput, err)
	}

	logger.Info("timing written", "path", timingOutput, "format", timingFormat)
	return nil
}
