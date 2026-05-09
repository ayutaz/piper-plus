// Command bench-pipeline measures the effect of issue #383 Phase 1
// (parallel G2P) on Voice.SynthesizeStream by comparing PIPER_G2P_PARALLELISM=1
// (serial path) against unset (auto = up to 4 workers).
//
// Usage:
//
//	go run ./src/go/cmd/bench-pipeline \
//	  --model test/models/multilingual-test-medium.onnx \
//	  --text-file tools/benchmark/texts/ja.txt \
//	  --ns 1,2,5,10,20 --repeats 3 --warmups 1 \
//	  --out tools/benchmark/issue-383/go_bench_results.md
//
// Requires CGO (onnxruntime_go). On Windows without a C toolchain this
// binary will fail to build — run it under Linux/macOS or in CI instead.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

// discardSink swallows audio so we measure synthesis throughput, not I/O.
type discardSink struct{}

func (d *discardSink) WriteAudio(samples []int16, sampleRate int) error { return nil }
func (d *discardSink) Close() error                                     { return nil }

// record holds the timings for one (N, config) cell of the benchmark grid.
type record struct {
	n   int
	cfg string
	ms  []float64
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// run holds the bench logic so ``defer voice.Close()`` actually fires;
// having ``os.Exit`` after a defer in ``main`` was flagged by gocritic
// (exitAfterDefer) — splitting into ``main`` + ``run`` is the standard
// Go idiom for that lint.
func run() error {
	modelFlag := flag.String("model", "test/models/multilingual-test-medium.onnx", "ONNX model path")
	configFlag := flag.String("config", "", "config.json path (defaults to <model>.json)")
	textFile := flag.String("text-file", "tools/benchmark/texts/ja.txt", "seed text path")
	nsFlag := flag.String("ns", "1,2,5,10,20", "comma-separated sentence counts")
	repeats := flag.Int("repeats", 3, "repeats per N")
	warmups := flag.Int("warmups", 1, "warmup runs per N")
	outFile := flag.String("out", "", "Markdown output path (default: stdout)")
	flag.Parse()

	seed, err := loadSentences(*textFile)
	if err != nil {
		return fmt.Errorf("failed to load %s: %w", *textFile, err)
	}
	if len(seed) == 0 {
		return fmt.Errorf("no seed sentences in %s", *textFile)
	}

	ctx := context.Background()

	loadOpts := []piperplus.LoadOption{}
	if *configFlag != "" {
		loadOpts = append(loadOpts, piperplus.WithConfig(*configFlag))
	}
	loadStart := time.Now()
	voice, err := piperplus.LoadVoice(ctx, *modelFlag, loadOpts...)
	if err != nil {
		return fmt.Errorf("LoadVoice failed: %w", err)
	}
	defer voice.Close()
	fmt.Fprintf(os.Stderr, "[bench] voice loaded in %.1f ms\n", float64(time.Since(loadStart).Microseconds())/1000.0)

	// Global warmup so per-N runs don't pay the model first-call cost.
	for i := 0; i < 3; i++ {
		_ = runOnce(ctx, voice, buildText(seed, 2))
	}

	ns, err := parseNs(*nsFlag)
	if err != nil {
		return fmt.Errorf("invalid --ns: %w", err)
	}

	var records []record

	for _, cfg := range []string{"serial", "auto"} {
		if cfg == "serial" {
			if err := os.Setenv("PIPER_G2P_PARALLELISM", "1"); err != nil {
				return fmt.Errorf("setenv PIPER_G2P_PARALLELISM: %w", err)
			}
		} else {
			if err := os.Unsetenv("PIPER_G2P_PARALLELISM"); err != nil {
				return fmt.Errorf("unsetenv PIPER_G2P_PARALLELISM: %w", err)
			}
		}

		fmt.Fprintf(os.Stderr, "\n[bench] === config: %s ===\n", cfg)
		for _, n := range ns {
			text := buildText(seed, n)
			for i := 0; i < *warmups; i++ {
				_ = runOnce(ctx, voice, text)
			}
			ms := make([]float64, 0, *repeats)
			for i := 0; i < *repeats; i++ {
				start := time.Now()
				if err := runOnce(ctx, voice, text); err != nil {
					return fmt.Errorf("synth failed N=%d rep=%d: %w", n, i, err)
				}
				elapsed := float64(time.Since(start).Microseconds()) / 1000.0
				ms = append(ms, elapsed)
				fmt.Fprintf(os.Stderr, "  rep %d: %.1f ms\n", i, elapsed)
			}
			records = append(records, record{n: n, cfg: cfg, ms: ms})
		}
	}

	out := buildMarkdown(records, ns, *modelFlag, *textFile, *repeats, *warmups)
	if *outFile == "" {
		fmt.Print(out)
		return nil
	}
	if err := os.WriteFile(*outFile, []byte(out), 0o644); err != nil {
		return fmt.Errorf("write %s failed: %w", *outFile, err)
	}
	fmt.Fprintf(os.Stderr, "[bench] wrote %s\n", *outFile)
	return nil
}

func runOnce(ctx context.Context, v *piperplus.Voice, text string) error {
	sink := &discardSink{}
	return v.SynthesizeStream(ctx, text, sink)
}

func buildText(seed []string, n int) string {
	var sb strings.Builder
	for i := 0; i < n; i++ {
		sb.WriteString(seed[i%len(seed)])
	}
	return sb.String()
}

func loadSentences(path string) ([]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out []string
	for _, line := range strings.Split(string(data), "\n") {
		if s := strings.TrimSpace(line); s != "" {
			out = append(out, s)
		}
	}
	return out, nil
}

func parseNs(s string) ([]int, error) {
	var out []int
	for _, tok := range strings.Split(s, ",") {
		tok = strings.TrimSpace(tok)
		if tok == "" {
			continue
		}
		v, err := strconv.Atoi(tok)
		if err != nil {
			return nil, fmt.Errorf("not an integer: %q", tok)
		}
		out = append(out, v)
	}
	return out, nil
}

func median(xs []float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	sorted := append([]float64(nil), xs...)
	sort.Float64s(sorted)
	return sorted[len(sorted)/2]
}

func buildMarkdown(records []record, ns []int, model, textFile string, repeats, warmups int) string {
	grouped := map[int]map[string]float64{}
	for _, r := range records {
		if grouped[r.n] == nil {
			grouped[r.n] = map[string]float64{}
		}
		grouped[r.n][r.cfg] = median(r.ms)
	}

	var sb strings.Builder
	fmt.Fprintf(&sb, "# Issue #383 Phase 1 — Go runtime bench\n\n")
	fmt.Fprintf(&sb, "Model: `%s`\n\n", model)
	fmt.Fprintf(&sb, "Seed text: `%s`\n\n", textFile)
	fmt.Fprintf(&sb, "Repeats: %d (warmups: %d) — values are median ms over `Voice.SynthesizeStream`.\n\n", repeats, warmups)
	fmt.Fprintf(&sb, "| N | serial_ms | auto_ms | Δ |\n")
	fmt.Fprintf(&sb, "|---:|---:|---:|---:|\n")
	for _, n := range ns {
		g := grouped[n]
		s := g["serial"]
		a := g["auto"]
		var delta float64
		if s > 0 {
			delta = (a - s) / s * 100.0
		}
		fmt.Fprintf(&sb, "| %d | %.1f | %.1f | %+.1f%% |\n", n, s, a, delta)
	}
	return sb.String()
}
