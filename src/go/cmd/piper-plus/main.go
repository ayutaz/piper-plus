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
	f := rootCmd.Flags()
	f.StringVarP(&modelPath, "model", "m", "", "path to ONNX model file (or $PIPER_DEFAULT_MODEL)")
	f.StringVarP(&configPath, "config", "c", "", "path to config.json (auto-detected if omitted)")
	f.StringVarP(&textInput, "text", "t", "", "text to synthesize (single utterance mode)")
	f.StringVar(&language, "language", "", "language code (e.g. ja, en, zh)")
	f.Int64VarP(&speakerID, "speaker", "s", 0, "speaker ID for multi-speaker models")
	f.StringVarP(&outputFile, "output-file", "f", "", "output WAV path (- for stdout)")
	f.StringVarP(&outputDir, "output-dir", "d", ".", "output directory for generated files")
	f.Float32Var(&noiseScale, "noise-scale", 0.667, "generation noise scale")
	f.Float32Var(&lengthScale, "length-scale", 1.0, "speech rate (length scale)")
	f.Float32Var(&noiseW, "noise-w", 0.8, "duration predictor noise scale")
	f.Float64Var(&sentenceSilence, "sentence-silence", 0.2, "silence between sentences in seconds")
	f.StringVar(&device, "device", "cpu", "inference device (cpu, cuda, coreml, directml)")
	f.BoolVar(&streaming, "streaming", false, "write raw PCM int16 to stdout (no WAV header)")
	f.StringVar(&batchFile, "batch", "", "batch file with one text line per utterance")
	f.StringVar(&timingOutput, "output-timing", "", "write phoneme timing to file")
	f.StringVar(&timingFormat, "timing-format", "json", "timing output format (json or tsv)")
	f.BoolVar(&debug, "debug", false, "enable debug logging")
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func runSynthesize(cmd *cobra.Command, args []string) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	// Configure logging.
	level := slog.LevelInfo
	if debug {
		level = slog.LevelDebug
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level}))

	// Resolve model path: flag > env.
	if modelPath == "" {
		modelPath = os.Getenv("PIPER_DEFAULT_MODEL")
	}
	if modelPath == "" {
		return fmt.Errorf("model path required: use --model or set $PIPER_DEFAULT_MODEL")
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

	voice, err := piperplus.LoadVoice(ctx, modelPath, loadOpts...)
	if err != nil {
		return fmt.Errorf("failed to load voice: %w", err)
	}
	defer voice.Close() //nolint:errcheck

	// Dispatch to the appropriate input mode.
	switch {
	case textInput != "":
		return runTextMode(ctx, voice, logger)
	case batchFile != "":
		return runBatchMode(ctx, voice, logger)
	default:
		return runJSONLMode(ctx, voice, logger)
	}
}

// runTextMode synthesizes a single --text utterance.
func runTextMode(ctx context.Context, voice *piperplus.Voice, logger *slog.Logger) error {
	req := buildRequest(nil, nil)
	result, err := voice.SynthesizeFromIDs(ctx, req)
	if err != nil {
		return fmt.Errorf("synthesis failed: %w", err)
	}

	logger.Info("synthesized",
		"duration", result.Duration,
		"infer_time", result.InferTime,
		"rtf", fmt.Sprintf("%.3f", result.RTF()),
	)

	if err := writeResult(result, outputFile, outputDir, "output.wav"); err != nil {
		return err
	}

	return writeTiming(result, logger)
}

// runBatchMode reads a batch file line by line and synthesizes each.
func runBatchMode(ctx context.Context, voice *piperplus.Voice, logger *slog.Logger) error {
	f, err := os.Open(batchFile)
	if err != nil {
		return fmt.Errorf("failed to open batch file: %w", err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
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

		req := buildRequest(nil, nil)
		result, err := voice.SynthesizeFromIDs(ctx, req)
		if err != nil {
			return fmt.Errorf("synthesis failed on line %d: %w", lineNum, err)
		}

		filename := fmt.Sprintf("line_%03d.wav", lineNum)
		if err := writeResult(result, "", outputDir, filename); err != nil {
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

		req := buildRequest(&input, nil)
		result, err := voice.SynthesizeFromIDs(ctx, req)
		if err != nil {
			return fmt.Errorf("synthesis failed on line %d: %w", lineNum, err)
		}

		filename := fmt.Sprintf("line_%03d.wav", lineNum)
		if err := writeResult(result, "", outputDir, filename); err != nil {
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

// buildRequest constructs a SynthesisRequest from CLI flags and optional JSONL input.
func buildRequest(input *jsonlInput, phonemeIDs []int64) *piperplus.SynthesisRequest {
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

	if phonemeIDs != nil {
		req.PhonemeIDs = phonemeIDs
	}

	return req
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
	return opts
}

// writeResult writes a SynthesisResult to the appropriate output target.
func writeResult(result *piperplus.SynthesisResult, outFile, outDir, defaultName string) error {
	if streaming {
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
	defer f.Close()

	if err := result.WriteWAV(f); err != nil {
		return fmt.Errorf("failed to write WAV to %s: %w", path, err)
	}
	return nil
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
