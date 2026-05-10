package parallelism

import (
	"context"
	"errors"
	"fmt"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// Resolve
// ---------------------------------------------------------------------------

func TestResolve_NoSentencesReturns1(t *testing.T) {
	t.Setenv(EnvVarName, "")
	if got := Resolve(0); got != 1 {
		t.Errorf("Resolve(0) = %d, want 1", got)
	}
	if got := Resolve(1); got != 1 {
		t.Errorf("Resolve(1) = %d, want 1", got)
	}
}

func TestResolve_AutoIsBoundedByCap(t *testing.T) {
	t.Setenv(EnvVarName, "")
	got := Resolve(100)
	if got < 2 || got > AutoParallelismCap {
		t.Errorf("Resolve(100) = %d; want in [2, %d]", got, AutoParallelismCap)
	}
}

func TestResolve_AutoIsBoundedBySentenceCount(t *testing.T) {
	t.Setenv(EnvVarName, "")
	if got := Resolve(2); got > 2 {
		t.Errorf("Resolve(2) = %d; must not exceed 2", got)
	}
	if got := Resolve(3); got > 3 {
		t.Errorf("Resolve(3) = %d; must not exceed 3", got)
	}
}

func TestResolve_EnvForce1(t *testing.T) {
	t.Setenv(EnvVarName, "1")
	if got := Resolve(20); got != 1 {
		t.Errorf("Resolve(20) with env=1 = %d, want 1", got)
	}
}

func TestResolve_EnvExplicitN(t *testing.T) {
	t.Setenv(EnvVarName, "8")
	// Capped by sentence count.
	if got := Resolve(3); got != 3 {
		t.Errorf("Resolve(3) with env=8 = %d, want 3", got)
	}
	if got := Resolve(20); got != 8 {
		t.Errorf("Resolve(20) with env=8 = %d, want 8", got)
	}
}

func TestResolve_EnvExplicitOverridesCap(t *testing.T) {
	// Explicit env values are honored even if they exceed AutoParallelismCap.
	want := AutoParallelismCap + 4
	t.Setenv(EnvVarName, fmt.Sprintf("%d", want))
	if got := Resolve(want * 2); got != want {
		t.Errorf("Resolve(%d) with env=%d = %d, want %d", want*2, want, got, want)
	}
}

func TestResolve_EnvInvalidFallsBackToAuto(t *testing.T) {
	t.Setenv(EnvVarName, "garbage")
	if got := Resolve(8); got < 2 {
		t.Errorf("Resolve(8) with invalid env = %d, want >= 2", got)
	}
}

func TestResolve_EnvNegativeForce1(t *testing.T) {
	t.Setenv(EnvVarName, "-3")
	if got := Resolve(8); got != 1 {
		t.Errorf("Resolve(8) with env=-3 = %d, want 1 (treated as <=1)", got)
	}
}

func TestResolve_EnvZeroForce1(t *testing.T) {
	t.Setenv(EnvVarName, "0")
	if got := Resolve(8); got != 1 {
		t.Errorf("Resolve(8) with env=0 = %d, want 1", got)
	}
}

// TestResolve_EnvWhitespaceTrimmed pins the contract that env values with
// surrounding whitespace (e.g. trailing newline from a shell rc) parse the
// same as the unpadded value. Mirrors Python (.strip()) and Rust (.trim())
// — Issue #383 follow-up review (PR #403 Copilot comment).
func TestResolve_EnvWhitespaceTrimmed(t *testing.T) {
	cases := []struct {
		env  string
		want int
		desc string
	}{
		{"  4", 4, "leading spaces"},
		{"4  ", 4, "trailing spaces"},
		{"  4  ", 4, "both sides"},
		{"\t4", 4, "leading tab"},
		{"4\n", 4, "trailing newline"},
		{"\t  1  \t", 1, "tabs and spaces around 1 still forces serial"},
	}
	for _, c := range cases {
		t.Run(c.desc, func(t *testing.T) {
			t.Setenv(EnvVarName, c.env)
			if got := Resolve(20); got != c.want {
				t.Errorf("Resolve(20) with env=%q = %d, want %d (whitespace must be trimmed)",
					c.env, got, c.want)
			}
		})
	}
}

// TestResolve_EnvWhitespaceOnlyFallsBackToAuto pins that an env value
// containing only whitespace is treated like "unset" (auto path), not as
// an invalid value that warns and then falls back. Trim must happen before
// the empty check.
func TestResolve_EnvWhitespaceOnlyFallsBackToAuto(t *testing.T) {
	t.Setenv(EnvVarName, "   \t  ")
	if got := Resolve(8); got < 2 {
		t.Errorf("Resolve(8) with whitespace-only env = %d, want >= 2 (auto path)", got)
	}
}

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------

func TestMap_Empty(t *testing.T) {
	out, err := Map(context.Background(), []string{}, 4, func(s string) (string, error) {
		return s, nil
	})
	if err != nil {
		t.Fatalf("Map empty returned error: %v", err)
	}
	if len(out) != 0 {
		t.Errorf("expected empty output, got %d items", len(out))
	}
}

func TestMap_SerialPath(t *testing.T) {
	in := []string{"a", "b", "c"}
	out, err := Map(context.Background(), in, 1, func(s string) (string, error) {
		return strings.ToUpper(s), nil
	})
	if err != nil {
		t.Fatalf("Map serial returned error: %v", err)
	}
	want := []string{"A", "B", "C"}
	if !slicesEqual(out, want) {
		t.Errorf("got %v, want %v", out, want)
	}
}

func TestMap_SerialPath_OneSentence_DoesNotSpawnGoroutine(t *testing.T) {
	// Even with parallelism=4, a single sentence must take the serial path:
	// there should be no goroutine leak. We verify by counting goroutines
	// before/after a single-sentence call.
	before := runtime.NumGoroutine()
	out, err := Map(context.Background(), []string{"only"}, 4,
		func(s string) (string, error) { return s + "!", nil })
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(out) != 1 || out[0] != "only!" {
		t.Errorf("got %v, want [only!]", out)
	}
	// Goroutine count may not return to exactly `before` due to runtime
	// internals, but it should not have grown unbounded. A loose tolerance:
	after := runtime.NumGoroutine()
	if after-before > 4 {
		t.Errorf("goroutine count grew by %d (before=%d, after=%d) — single-sentence path leaked",
			after-before, before, after)
	}
}

func TestMap_ParallelPreservesOrder(t *testing.T) {
	in := []string{"a", "b", "c", "d", "e", "f", "g", "h", "i", "j"}
	out, err := Map(context.Background(), in, 4, func(s string) (string, error) {
		// Vary delay to encourage out-of-order completion.
		switch s {
		case "a", "e", "i":
			time.Sleep(2 * time.Millisecond)
		case "b", "f", "j":
			time.Sleep(1 * time.Millisecond)
		}
		return s + s, nil
	})
	if err != nil {
		t.Fatalf("Map returned error: %v", err)
	}
	want := []string{"aa", "bb", "cc", "dd", "ee", "ff", "gg", "hh", "ii", "jj"}
	if !slicesEqual(out, want) {
		t.Errorf("got %v, want %v", out, want)
	}
}

func TestMap_ParallelMatchesSerial(t *testing.T) {
	in := make([]string, 50)
	for i := range in {
		in[i] = fmt.Sprintf("sentence_%d", i)
	}
	fn := func(s string) (string, error) { return strings.ToUpper(s), nil }

	serial, err := Map(context.Background(), in, 1, fn)
	if err != nil {
		t.Fatalf("serial: %v", err)
	}
	parallel, err := Map(context.Background(), in, 8, fn)
	if err != nil {
		t.Fatalf("parallel: %v", err)
	}
	if !slicesEqual(serial, parallel) {
		t.Errorf("serial != parallel\n  serial:   %v\n  parallel: %v", serial, parallel)
	}
}

func TestMap_ConcurrencyDoesNotExceedParallelism(t *testing.T) {
	const parallelism = 3
	in := make([]string, 20)
	for i := range in {
		in[i] = fmt.Sprintf("s%d", i)
	}
	var inFlight int32
	var maxInFlight int32

	_, err := Map(context.Background(), in, parallelism, func(s string) (string, error) {
		cur := atomic.AddInt32(&inFlight, 1)
		// Track high-water mark.
		for {
			hwm := atomic.LoadInt32(&maxInFlight)
			if cur <= hwm || atomic.CompareAndSwapInt32(&maxInFlight, hwm, cur) {
				break
			}
		}
		time.Sleep(2 * time.Millisecond)
		atomic.AddInt32(&inFlight, -1)
		return s, nil
	})
	if err != nil {
		t.Fatalf("Map: %v", err)
	}
	got := atomic.LoadInt32(&maxInFlight)
	if got > int32(parallelism) {
		t.Errorf("max in-flight workers = %d, must not exceed parallelism=%d", got, parallelism)
	}
	if got < 2 {
		t.Errorf("max in-flight workers = %d; expected at least 2 (parallel path was not exercised)", got)
	}
}

func TestMap_PropagatesError(t *testing.T) {
	in := []string{"ok1", "ok2", "boom", "ok3", "ok4"}
	wantErr := errors.New("kaboom")

	out, err := Map(context.Background(), in, 4, func(s string) (string, error) {
		if s == "boom" {
			return "", wantErr
		}
		// Slow other workers down a touch so the error has time to land.
		time.Sleep(time.Millisecond)
		return s, nil
	})
	if !errors.Is(err, wantErr) {
		t.Errorf("expected %v, got %v", wantErr, err)
	}
	if out != nil {
		t.Errorf("expected nil slice on error, got %v", out)
	}
}

func TestMap_ContextCancelStopsBeforeCompletion(t *testing.T) {
	in := make([]string, 200)
	for i := range in {
		in[i] = fmt.Sprintf("s%d", i)
	}

	ctx, cancel := context.WithCancel(context.Background())
	var calls int32
	var once sync.Once

	_, err := Map(ctx, in, 4, func(s string) (string, error) {
		n := atomic.AddInt32(&calls, 1)
		if n == 5 {
			once.Do(cancel)
		}
		time.Sleep(time.Millisecond)
		if err := ctx.Err(); err != nil {
			return "", err
		}
		return s, nil
	})
	if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled, got %v", err)
	}
	if atomic.LoadInt32(&calls) >= int32(len(in)) {
		t.Errorf("expected early termination but processed all %d items", len(in))
	}
}

func TestMap_PreCanceledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	out, err := Map(ctx, []string{"a", "b", "c"}, 4, func(s string) (string, error) {
		t.Errorf("fn must not be called when ctx is pre-canceled, got %q", s)
		return s, nil
	})
	if !errors.Is(err, context.Canceled) {
		t.Errorf("expected context.Canceled, got %v", err)
	}
	if out != nil {
		t.Errorf("expected nil output, got %v", out)
	}
}

// slicesEqual is a simple equality helper that avoids pulling in external
// helpers.
func slicesEqual[T comparable](a, b []T) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
