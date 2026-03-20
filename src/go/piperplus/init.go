package piperplus

import (
	"errors"
	"fmt"
	"os"
	"sync"

	ort "github.com/yalue/onnxruntime_go"
)

var (
	initOnce     sync.Once
	shutdownOnce sync.Once
	initErr      error
	initialized  bool
)

// Init initializes the ONNX Runtime environment. It must be called once before
// any model operations. If libraryPath is empty, the ONNX_RUNTIME_SHARED_LIBRARY_PATH
// environment variable is used as a fallback. Subsequent calls return the result
// of the first initialization attempt.
func Init(libraryPath string) error {
	initOnce.Do(func() {
		if libraryPath == "" {
			libraryPath = os.Getenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH")
		}
		if libraryPath == "" {
			initErr = &ConfigError{
				Path: "",
				Err:  errors.New("ONNX Runtime shared library path not specified; set ONNX_RUNTIME_SHARED_LIBRARY_PATH or pass it to Init"),
			}
			return
		}

		ort.SetSharedLibraryPath(libraryPath)
		if err := ort.InitializeEnvironment(); err != nil {
			initErr = &ModelLoadError{
				Path: libraryPath,
				Err:  fmt.Errorf("failed to initialize ONNX Runtime environment: %w", err),
			}
			return
		}

		initialized = true
	})
	return initErr
}

// Shutdown destroys the ONNX Runtime environment. It is safe to call multiple
// times; only the first call performs cleanup.
func Shutdown() error {
	var err error
	shutdownOnce.Do(func() {
		if initialized {
			err = ort.DestroyEnvironment()
			initialized = false
		}
	})
	return err
}
