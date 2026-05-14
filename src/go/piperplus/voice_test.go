package piperplus

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// LoadVoice tests intentionally exercise only the error paths that fail
// BEFORE the ONNX Runtime initialization. Heavy integration tests that
// require a real .onnx model live elsewhere (see engine_test.go).

// TestLoadVoice_MissingModelPath: the model file does not exist on disk.
// FindConfigPath is called first; with a non-existent model path and no
// sidecar/dir-config, it returns *ConfigError before any ONNX work.
func TestLoadVoice_MissingModelPath(t *testing.T) {
	// Hermetic: clear PIPER_DEFAULT_CONFIG so the host environment cannot
	// redirect FindConfigPath to a real config file and mask the missing model.
	t.Setenv("PIPER_DEFAULT_CONFIG", "")

	ctx := context.Background()

	tmpDir := t.TempDir()
	missingModel := filepath.Join(tmpDir, "does-not-exist.onnx")

	v, err := LoadVoice(ctx, missingModel)
	if err == nil {
		if v != nil {
			_ = v.Close()
		}
		t.Fatal("LoadVoice should fail for a non-existent model path")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError (config resolution must fail first)", err)
	}
}

// TestLoadVoice_ExplicitConfigNotFound: WithConfig points at a path that
// does not exist. FindConfigPath must fail with *ConfigError.
func TestLoadVoice_ExplicitConfigNotFound(t *testing.T) {
	ctx := context.Background()

	tmpDir := t.TempDir()
	missingConfig := filepath.Join(tmpDir, "no-such-config.json")
	dummyModel := filepath.Join(tmpDir, "dummy.onnx")

	_, err := LoadVoice(ctx, dummyModel, WithConfig(missingConfig))
	if err == nil {
		t.Fatal("LoadVoice should fail when explicit config path does not exist")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError", err)
	}
	if cfgErr != nil && cfgErr.Path != missingConfig {
		t.Errorf("ConfigError.Path = %q, want %q", cfgErr.Path, missingConfig)
	}
}

// TestLoadVoice_CorruptedConfig: config.json contains malformed JSON. The
// failure must surface as *ConfigError from LoadConfig, not as an opaque
// JSON error or a downstream ONNX failure.
func TestLoadVoice_CorruptedConfig(t *testing.T) {
	ctx := context.Background()

	tmpDir := t.TempDir()
	corruptedConfig := filepath.Join(tmpDir, "broken.json")
	if err := os.WriteFile(corruptedConfig, []byte("{ this is not valid json"), 0o644); err != nil {
		t.Fatalf("setup: failed to write corrupted config: %v", err)
	}
	dummyModel := filepath.Join(tmpDir, "dummy.onnx")

	_, err := LoadVoice(ctx, dummyModel, WithConfig(corruptedConfig))
	if err == nil {
		t.Fatal("LoadVoice should fail when config.json is malformed")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError for malformed JSON", err)
	}
}

// TestLoadVoice_ConfigValidationFailure: well-formed JSON but missing the
// required phoneme_id_map. LoadConfig.Validate() must reject it as
// *ConfigError before any ONNX session is created.
func TestLoadVoice_ConfigValidationFailure(t *testing.T) {
	ctx := context.Background()

	tmpDir := t.TempDir()
	emptyMapConfig := filepath.Join(tmpDir, "empty-map.json")
	// Valid JSON, valid sample_rate, but empty phoneme_id_map → Validate() rejects.
	body := `{"audio":{"sample_rate":22050},"phoneme_id_map":{}}`
	if err := os.WriteFile(emptyMapConfig, []byte(body), 0o644); err != nil {
		t.Fatalf("setup: failed to write config: %v", err)
	}
	dummyModel := filepath.Join(tmpDir, "dummy.onnx")

	_, err := LoadVoice(ctx, dummyModel, WithConfig(emptyMapConfig))
	if err == nil {
		t.Fatal("LoadVoice should fail when phoneme_id_map is empty")
	}

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) {
		t.Errorf("error type = %T, want *ConfigError for validation failure", err)
	}
}

// TestLoadVoice_ContextCancelled: a pre-cancelled context must short-circuit
// before any filesystem or ONNX I/O.
func TestLoadVoice_ContextCancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel before invocation

	tmpDir := t.TempDir()
	dummyModel := filepath.Join(tmpDir, "dummy.onnx")

	_, err := LoadVoice(ctx, dummyModel)
	if err == nil {
		t.Fatal("LoadVoice should fail for a cancelled context")
	}
	if !errors.Is(err, context.Canceled) {
		t.Errorf("err = %v, want context.Canceled", err)
	}
}

// ---------------------------------------------------------------------------
// Voice.Close() idempotency
// ---------------------------------------------------------------------------

// TestVoiceClose_IdempotentNoPanic verifies that Close() is safe to call
// repeatedly on a Voice that is ALREADY in the closed state.
//
// We pre-set closed=true, so EVERY Close() call here (including the first
// one in the loop) observes the flag as already-set and takes the
// early-return branch — CompareAndSwap(false, true) returns false and
// engine.Close() is NOT invoked. This is the "already-closed idempotency"
// path: it exercises only the early-return guard and deliberately avoids
// the first-close cleanup path (which would require a real engine).
//
// The complementary first-close CAS transition (false → true) is covered
// by TestVoiceClose_FlagCompareAndSwap below.
//
// Documented contract under test: "It is safe to call multiple times;
// only the first call performs cleanup."
func TestVoiceClose_IdempotentNoPanic(t *testing.T) {
	v := &Voice{}
	v.closed.Store(true) // simulate an already-closed Voice

	for i := 0; i < 5; i++ {
		err := v.Close()
		if err != nil {
			t.Errorf("Close() call #%d returned %v, want nil", i+1, err)
		}
	}
}

// TestVoiceClose_FlagCompareAndSwap verifies that after a successful CAS
// from false→true, additional Close() calls take the early-return path
// (CompareAndSwap returns false on subsequent attempts).
func TestVoiceClose_FlagCompareAndSwap(t *testing.T) {
	v := &Voice{}

	// First CAS: false → true. We simulate the "first successful close"
	// without invoking engine.Close() (nil engine would panic).
	if !v.closed.CompareAndSwap(false, true) {
		t.Fatal("initial CompareAndSwap(false, true) should succeed")
	}

	// Subsequent Close() calls must take the early-return branch and
	// return nil without touching the nil engine.
	for i := 0; i < 3; i++ {
		if err := v.Close(); err != nil {
			t.Errorf("Close() call #%d after CAS returned %v, want nil", i+1, err)
		}
	}
}

// TestSynthesizeFromIDs_ClosedReturnsErr: SynthesizeFromIDs on a closed
// Voice must surface ErrModelClosed, not panic on the nil engine.
func TestSynthesizeFromIDs_ClosedReturnsErr(t *testing.T) {
	v := &Voice{}
	v.closed.Store(true)

	_, err := v.SynthesizeFromIDs(context.Background(), &SynthesisRequest{})
	if !errors.Is(err, ErrModelClosed) {
		t.Errorf("err = %v, want ErrModelClosed", err)
	}
}

// TestSynthesizeFromIDs_NilRequestOnOpenVoice: a non-closed Voice with a
// nil request must reject the request before reaching the engine. We use a
// non-closed flag but still expect the nil-request guard to fire first.
func TestSynthesizeFromIDs_NilRequestOnOpenVoice(t *testing.T) {
	v := &Voice{}
	// closed flag defaults to false; SynthesizeFromIDs reaches the nil-request guard.

	_, err := v.SynthesizeFromIDs(context.Background(), nil)
	if err == nil {
		t.Fatal("SynthesizeFromIDs(nil) should return an error")
	}
	// The error message should mention the nil request.
	if !strings.Contains(err.Error(), "nil synthesis request") {
		t.Errorf("err = %q, want substring %q", err.Error(), "nil synthesis request")
	}
}
