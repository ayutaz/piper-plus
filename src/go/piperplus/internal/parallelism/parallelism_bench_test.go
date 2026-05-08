// Microbenchmarks for the issue #383 Phase 1 helpers.
//
// Real Phase 1 measurement requires a CGO toolchain (onnxruntime_go) to
// invoke Voice.SynthesizeStream end-to-end — see cmd/bench-pipeline. These
// microbenchmarks isolate the resolver and ordered Map helpers so the
// per-call overhead and the speedup against a synthetic G2P workload can
// be measured without any C dependency.
//
// Run:
//
//	go test ./piperplus/internal/parallelism/ -bench=. -benchmem -run=^$
package parallelism

import (
	"context"
	"strings"
	"testing"
	"time"
)

// BenchmarkResolve_Auto measures the env+heuristic resolver. The cost is
// what every SynthesizeStream call pays once before deciding whether to
// take the serial fast path or spin up workers.
func BenchmarkResolve_Auto(b *testing.B) {
	b.Setenv(EnvVarName, "")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = Resolve(10)
	}
}

// BenchmarkResolve_ForceSerial covers the PIPER_G2P_PARALLELISM=1 path
// callers hit when they opt out of parallelism.
func BenchmarkResolve_ForceSerial(b *testing.B) {
	b.Setenv(EnvVarName, "1")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = Resolve(10)
	}
}

// fakeG2P simulates a per-sentence G2P call. 5 ms approximates the
// pyopenjtalk-plus/cold-cache cost per typical Japanese sentence on the
// development host (see tools/benchmark/issue-383/baseline_results.json).
func fakeG2P(s string) (string, error) {
	time.Sleep(5 * time.Millisecond)
	return strings.ToUpper(s), nil
}

func benchSentences(n int) []string {
	out := make([]string, n)
	for i := range out {
		out[i] = "sentence_" + strings.Repeat("x", i%32)
	}
	return out
}

// BenchmarkMap_Serial / BenchmarkMap_Parallel quantify the speedup the
// streaming code gets when len(sentences) >= 2 and PIPER_G2P_PARALLELISM is
// not forced to 1. With a 5 ms fakeG2P, parallelism=4 should hit roughly a
// 3.5–4× wall-clock improvement on a multi-core host.

func BenchmarkMap_Serial_N10(b *testing.B) {
	ctx := context.Background()
	sentences := benchSentences(10)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := Map(ctx, sentences, 1, fakeG2P)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkMap_Parallel4_N10(b *testing.B) {
	ctx := context.Background()
	sentences := benchSentences(10)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := Map(ctx, sentences, 4, fakeG2P)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkMap_Serial_N20(b *testing.B) {
	ctx := context.Background()
	sentences := benchSentences(20)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := Map(ctx, sentences, 1, fakeG2P)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkMap_Parallel4_N20(b *testing.B) {
	ctx := context.Background()
	sentences := benchSentences(20)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := Map(ctx, sentences, 4, fakeG2P)
		if err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkMap_Parallel_OneSentence verifies the n=1 zero-overhead claim:
// the parallel path must not spawn goroutines when there is nothing to
// distribute. If this regresses, streaming a single sentence pays goroutine
// scheduling cost it did not pay before Phase 1.
func BenchmarkMap_Parallel_OneSentence(b *testing.B) {
	ctx := context.Background()
	sentences := []string{"only"}
	noop := func(s string) (string, error) { return s, nil }
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := Map(ctx, sentences, 4, noop)
		if err != nil {
			b.Fatal(err)
		}
	}
}
