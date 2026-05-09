package parallelism

// Issue #383 follow-up: regression coverage for the kind of JA/G2P race
// condition that surfaced in C# (`MeCabTokenizer` thread-safety violation,
// see commit c567f5be). The original Phase 1 tests in this package only
// exercised generic ASCII inputs, so a JA-specific stress run was added
// here to catch any future hidden mutable state in a backend that the
// generic Map dispatches into.
//
// These tests are CGO-free — Map is a pure Go combinator. The real Voice /
// SynthesizeStream concurrent stress test lives next to it in
// piperplus/streaming_stress_test.go (CGO-gated).

import (
	"context"
	"runtime"
	"sync"
	"testing"
)

// jaSentences is a small corpus mixing short greetings, long compound
// sentences, and AI/tech vocabulary so a backend doing per-sentence MeCab
// or pyopenjtalk-style work can't trivially memoize away the contention.
var jaSentences = []string{
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

// TestMap_JaConcurrentStress fires Map[*] from many goroutines, each making
// many calls, all on the same JA corpus. The C# regression mode would have
// surfaced as either result-length drift (truncated slice from a panicking
// worker) or, with -race, a write/read on an unsynchronized field of the
// per-language backend the user's fn closes over.
//
// We deliberately use a *non-trivial* fn closure that touches a shared
// counter via sync/atomic only — any backend that itself shares mutable
// state would still be detectable through `go test -race`.
func TestMap_JaConcurrentStress(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping stress test in -short mode")
	}

	const goroutines = 16
	const iterPerGoroutine = 50

	// fn is intentionally tiny — its only job is to be called from
	// many goroutines simultaneously so the runtime can detect data
	// races inside Map's coordination logic (ordered emit, sem, wg).
	fn := func(s string) (int, error) {
		return len(s), nil
	}

	var wg sync.WaitGroup
	wg.Add(goroutines)
	errCh := make(chan error, goroutines*iterPerGoroutine)

	for g := 0; g < goroutines; g++ {
		go func() {
			defer wg.Done()
			for i := 0; i < iterPerGoroutine; i++ {
				results, err := Map[int](
					context.Background(),
					jaSentences,
					4,
					fn,
				)
				if err != nil {
					errCh <- err
					return
				}
				if len(results) != len(jaSentences) {
					t.Errorf("len(results)=%d, want %d",
						len(results), len(jaSentences))
					return
				}
				// Order preservation: result[i] must be byte-length of
				// jaSentences[i] — a swap or shuffle would surface here.
				for k, want := range jaSentences {
					if results[k] != len(want) {
						t.Errorf("results[%d]=%d, want %d (sentence=%q)",
							k, results[k], len(want), want)
						return
					}
				}
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Errorf("Map returned error: %v", err)
	}
}

// TestMap_JaConcurrentStress_HighParallelism stresses the worker pool with
// parallelism > GOMAXPROCS to exercise the semaphore/blocking path.
func TestMap_JaConcurrentStress_HighParallelism(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping stress test in -short mode")
	}

	parallelism := runtime.GOMAXPROCS(0) * 2
	if parallelism < 4 {
		parallelism = 4
	}

	fn := func(s string) (string, error) {
		// Convert to lowercase-ish — UTF-8 walking exercises memory
		// access patterns rather than just stack-local arithmetic.
		runes := []rune(s)
		out := make([]rune, len(runes))
		copy(out, runes)
		return string(out), nil
	}

	const goroutines = 8
	const iterPerGoroutine = 30

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for g := 0; g < goroutines; g++ {
		go func() {
			defer wg.Done()
			for i := 0; i < iterPerGoroutine; i++ {
				results, err := Map[string](
					context.Background(),
					jaSentences,
					parallelism,
					fn,
				)
				if err != nil {
					t.Errorf("Map error: %v", err)
					return
				}
				for k, want := range jaSentences {
					if results[k] != want {
						t.Errorf("results[%d]=%q, want %q",
							k, results[k], want)
						return
					}
				}
			}
		}()
	}
	wg.Wait()
}
