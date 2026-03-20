package piperplus

import (
	"errors"
	"fmt"
	"os"
	"sync"

	ort "github.com/yalue/onnxruntime_go"
)

var (
	mu          sync.Mutex
	initErr     error
	initialized bool
)

// Init initializes the ONNX Runtime environment. It must be called once before
// any model operations. If libraryPath is empty, the ONNX_RUNTIME_SHARED_LIBRARY_PATH
// environment variable is used as a fallback. If the environment is already
// initialized, Init returns nil immediately. After Shutdown(), Init may be
// called again to re-initialize.
func Init(libraryPath string) error {
	mu.Lock()
	defer mu.Unlock()

	if initialized {
		return nil
	}

	if libraryPath == "" {
		libraryPath = os.Getenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH")
	}
	if libraryPath == "" {
		initErr = &ConfigError{
			Path: "",
			Err:  errors.New("ONNX Runtime shared library path not specified; set ONNX_RUNTIME_SHARED_LIBRARY_PATH or pass it to Init"),
		}
		return initErr
	}

	ort.SetSharedLibraryPath(libraryPath)
	if err := ort.InitializeEnvironment(); err != nil {
		initErr = &ModelLoadError{
			Path: libraryPath,
			Err:  fmt.Errorf("failed to initialize ONNX Runtime environment: %w", err),
		}
		return initErr
	}

	initialized = true
	initErr = nil
	return nil
}

// Shutdown destroys the ONNX Runtime environment. It is safe to call multiple
// times; calling Shutdown on an already shut-down environment is a no-op.
// After Shutdown(), Init may be called again to re-initialize.
func Shutdown() error {
	mu.Lock()
	defer mu.Unlock()

	if !initialized {
		return nil
	}

	err := ort.DestroyEnvironment()
	initialized = false
	initErr = nil
	return err
}
