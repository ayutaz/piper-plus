// Package parallelism provides Phase 1 helpers for issue #383: a small
// resolver that picks an effective worker count for parallel G2P, and a
// generic ordered mapper that runs a function over each sentence with
// optional concurrency.
//
// It is intentionally an internal subpackage so it can be unit-tested
// without depending on the parent piperplus package's CGO transitive
// requirements (onnxruntime_go).
package parallelism

import (
	"context"
	"log/slog"
	"os"
	"runtime"
	"strconv"
	"sync"
)

// AutoParallelismCap caps automatic G2P parallelism. The Python side picks
// 4 for the same reason: the ORT session uses ~4 intra-op threads we do not
// want to oversubscribe, and the Japanese G2P engine serializes on a mutex
// around MeCab, so high parallelism degrades to lock contention. Setting
// PIPER_G2P_PARALLELISM=1 restores the strictly-serial path.
const AutoParallelismCap = 4

// EnvVarName is the environment variable consulted by Resolve.
const EnvVarName = "PIPER_G2P_PARALLELISM"

// Resolve returns the effective worker count for parallel G2P across
// nSentences sentences. Mirrors voice.py:_resolve_g2p_parallelism.
//
// Resolution order:
//   - PIPER_G2P_PARALLELISM=1     → 1 (serial, zero-overhead path)
//   - PIPER_G2P_PARALLELISM=N≥2   → N (capped at nSentences)
//   - unset / invalid             → auto = min(nSentences, max(2, cores/2),
//     AutoParallelismCap)
//   - nSentences ≤ 1              → 1
func Resolve(nSentences int) int {
	if raw := os.Getenv(EnvVarName); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil {
			slog.Warn("ignoring invalid PIPER_G2P_PARALLELISM; falling back to auto",
				"value", raw)
		} else {
			if n <= 1 {
				return 1
			}
			if nSentences > 0 && n > nSentences {
				return nSentences
			}
			return n
		}
	}

	if nSentences <= 1 {
		return 1
	}

	cores := runtime.NumCPU()
	if cores < 2 {
		cores = 2
	}
	auto := cores / 2
	if auto < 2 {
		auto = 2
	}
	if auto > AutoParallelismCap {
		auto = AutoParallelismCap
	}
	if auto > nSentences {
		auto = nSentences
	}
	return auto
}

// Map applies fn to each sentence and returns the results in input order.
// When parallelism ≤ 1 (or len(sentences) ≤ 1) it takes a strictly-serial
// path with no goroutine overhead. Otherwise up to parallelism workers run
// concurrently.
//
// Errors short-circuit: the first error encountered is returned, and other
// in-flight workers are signaled to skip their fn call where possible. The
// returned slice is nil on error.
//
// Map honors ctx cancellation between iterations. Each worker also re-checks
// ctx.Err() before invoking fn to avoid wasted work after a late cancel.
func Map[T any](
	ctx context.Context,
	sentences []string,
	parallelism int,
	fn func(string) (T, error),
) ([]T, error) {
	if len(sentences) == 0 {
		var empty []T
		return empty, nil
	}

	out := make([]T, len(sentences))

	if parallelism <= 1 || len(sentences) == 1 {
		for i, s := range sentences {
			if err := ctx.Err(); err != nil {
				return nil, err
			}
			v, err := fn(s)
			if err != nil {
				return nil, err
			}
			out[i] = v
		}
		return out, nil
	}

	if parallelism > len(sentences) {
		parallelism = len(sentences)
	}

	sem := make(chan struct{}, parallelism)
	var wg sync.WaitGroup
	var errMu sync.Mutex
	var firstErr error

	setErr := func(e error) {
		errMu.Lock()
		if firstErr == nil {
			firstErr = e
		}
		errMu.Unlock()
	}
	hasErr := func() bool {
		errMu.Lock()
		defer errMu.Unlock()
		return firstErr != nil
	}

	for i, s := range sentences {
		if err := ctx.Err(); err != nil {
			setErr(err)
			break
		}
		if hasErr() {
			break
		}
		wg.Add(1)
		sem <- struct{}{}
		go func(idx int, sentence string) {
			defer wg.Done()
			defer func() { <-sem }()
			if hasErr() {
				return
			}
			if err := ctx.Err(); err != nil {
				setErr(err)
				return
			}
			v, err := fn(sentence)
			if err != nil {
				setErr(err)
				return
			}
			out[idx] = v
		}(i, s)
	}
	wg.Wait()

	if firstErr != nil {
		return nil, firstErr
	}
	return out, nil
}
