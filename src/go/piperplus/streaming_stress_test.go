package piperplus

// Issue #383 follow-up: regression coverage for JA-specific G2P races
// (e.g. the C# DotNetG2P MeCabTokenizer issue surfaced in commit c567f5be).
// This test exercises Voice.SynthesizeStream from many goroutines on the
// same Voice instance, using JA text that goes through the real JA
// phonemizer + ORT pipeline. `go test -race` will surface unsynchronized
// state in either Phase 1 parallelism scaffolding or the underlying
// phonemize backend.
//
// Skips when PIPER_TEST_MODEL is unset (no CGO model fixture available).
// This mirrors the CGO-gating already used by every model-loading test in
// this package — keeping the convention avoids duplicating fixture setup
// or introducing a new build tag the CI matrix isn't aware of.

import (
	"bytes"
	"context"
	"io"
	"sync"
	"testing"
)

// jaStressSentences is the same corpus used by the parallelism stress
// test, restated here to keep this file self-contained (the parallelism
// package is internal and not imported by the parent piperplus package).
var jaStressSentences = []string{
	"こんにちは。",
	"東京駅から新幹線で大阪まで約2時間30分かかります。",
	"昨日の会議では、新しいプロジェクトの方針について話し合いました。",
	"この料理のレシピを教えていただけますか?",
	"桜の花が満開になると、多くの人々が公園でお花見を楽しみます。",
	"明日の午後3時に渋谷のカフェで待ち合わせしましょう。",
	"日本語の音声合成技術は、近年大きく進歩しています。",
	"すみません、この近くに郵便局はありますか?",
	"彼女は毎朝6時に起きて、30分間ジョギングをしています。",
	"人工知能の発展により、私たちの生活は大きく変わろうとしています。",
}

// TestSynthesizeStream_JaConcurrent loads a Voice once, then calls
// SynthesizeStream concurrently from N goroutines on JA text. Run with
// `-race` to detect data races in the JA G2P backend or Phase 1 helpers.
//
// Repeat counts are intentionally modest because each call goes through
// real ORT inference; CI overhead matters. The race detector triggers on
// even one bad access, so we don't need huge volumes — just enough
// goroutines to interleave inside the JA phonemizer.
func TestSynthesizeStream_JaConcurrent(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping stress test in -short mode")
	}

	modelPath := testModelPath(t) // skips if PIPER_TEST_MODEL unset

	voice, err := LoadVoice(context.Background(), modelPath)
	if err != nil {
		t.Fatalf("LoadVoice failed: %v", err)
	}
	defer voice.Close()

	if voice == nil {
		t.Fatal("voice is nil after LoadVoice")
	}

	const goroutines = 8
	const iterPerGoroutine = 3

	// Pick a multi-sentence text per goroutine so Phase 1 fan-out is
	// actually exercised (parallelism>1 path inside SynthesizeStream).
	texts := make([]string, goroutines)
	for g := 0; g < goroutines; g++ {
		// 3 sentences each — enough to trigger parallelism (>=2)
		// without ballooning the test runtime.
		texts[g] = jaStressSentences[(g*3)%len(jaStressSentences)] +
			jaStressSentences[(g*3+1)%len(jaStressSentences)] +
			jaStressSentences[(g*3+2)%len(jaStressSentences)]
	}

	var wg sync.WaitGroup
	wg.Add(goroutines)
	errCh := make(chan error, goroutines*iterPerGoroutine)

	for g := 0; g < goroutines; g++ {
		text := texts[g]
		go func() {
			defer wg.Done()
			for i := 0; i < iterPerGoroutine; i++ {
				var buf bytes.Buffer
				sink := NewWriterAudioSink(&buf)
				err := voice.SynthesizeStream(
					context.Background(),
					text,
					sink,
				)
				if err != nil {
					errCh <- err
					return
				}
				if buf.Len() == 0 {
					t.Errorf("empty audio for text %q", text)
					return
				}
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != io.EOF {
			t.Errorf("SynthesizeStream returned error: %v", err)
		}
	}
}

// TestSynthesizeStream_JaConcurrentBothModes asserts that running the same
// JA workload under PIPER_G2P_PARALLELISM=1 (serial) and unset (auto
// parallel) both succeed without crashing. Combined with -race this
// catches regressions where only the parallel path is broken.
func TestSynthesizeStream_JaConcurrentBothModes(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping stress test in -short mode")
	}

	modelPath := testModelPath(t)

	voice, err := LoadVoice(context.Background(), modelPath)
	if err != nil {
		t.Fatalf("LoadVoice failed: %v", err)
	}
	defer voice.Close()

	for _, mode := range []struct {
		name string
		env  string
	}{
		{"serial", "1"},
		{"parallel", ""}, // auto
	} {
		t.Run(mode.name, func(t *testing.T) {
			if mode.env == "" {
				t.Setenv("PIPER_G2P_PARALLELISM", "")
			} else {
				t.Setenv("PIPER_G2P_PARALLELISM", mode.env)
			}

			text := jaStressSentences[0] + jaStressSentences[1] +
				jaStressSentences[2] + jaStressSentences[3]

			const goroutines = 4
			var wg sync.WaitGroup
			wg.Add(goroutines)
			for g := 0; g < goroutines; g++ {
				go func() {
					defer wg.Done()
					var buf bytes.Buffer
					sink := NewWriterAudioSink(&buf)
					if err := voice.SynthesizeStream(
						context.Background(), text, sink,
					); err != nil {
						t.Errorf("[%s] SynthesizeStream failed: %v",
							mode.name, err)
						return
					}
					if buf.Len() == 0 {
						t.Errorf("[%s] empty audio", mode.name)
					}
				}()
			}
			wg.Wait()
		})
	}
}
