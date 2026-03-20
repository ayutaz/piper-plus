//go:build integration

package piperplus

import (
	"fmt"
	"os"
	"testing"
)

func TestMain(m *testing.M) {
	libPath := os.Getenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH")
	if libPath == "" {
		fmt.Println("Skipping integration tests: ONNX_RUNTIME_SHARED_LIBRARY_PATH not set")
		os.Exit(0)
	}
	if err := Init(libPath); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize ONNX Runtime: %v\n", err)
		os.Exit(1)
	}
	code := m.Run()
	Shutdown()
	os.Exit(code)
}

func TestInit_WithEnvVar(t *testing.T) {
	libPath := os.Getenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH")
	if libPath == "" {
		t.Skip("ONNX_RUNTIME_SHARED_LIBRARY_PATH not set")
	}
	// Init was already called by TestMain via sync.Once; calling again is a no-op.
	if err := Init(""); err != nil {
		t.Fatalf("Init with env var fallback returned error: %v", err)
	}
	if !initialized {
		t.Fatal("expected initialized to be true after Init")
	}
}

func TestInit_WithExplicitPath(t *testing.T) {
	libPath := os.Getenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH")
	if libPath == "" {
		t.Skip("ONNX_RUNTIME_SHARED_LIBRARY_PATH not set")
	}
	// sync.Once makes this a no-op returning the cached nil error.
	if err := Init(libPath); err != nil {
		t.Fatalf("Init with explicit path returned error: %v", err)
	}
	if !initialized {
		t.Fatal("expected initialized to be true after Init")
	}
}

func TestShutdown(t *testing.T) {
	if !initialized {
		t.Skip("ONNX Runtime not initialized")
	}
	// Shutdown uses its own sync.Once; first call in-process cleans up.
	if err := Shutdown(); err != nil {
		t.Fatalf("Shutdown returned error: %v", err)
	}
}
