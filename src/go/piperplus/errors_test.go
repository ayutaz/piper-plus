package piperplus

import (
	"errors"
	"io"
	"os"
	"strings"
	"testing"
)

func TestModelLoadError(t *testing.T) {
	err := &ModelLoadError{Path: "/path/to/model.onnx", Err: io.ErrUnexpectedEOF}

	t.Run("Error", func(t *testing.T) {
		msg := err.Error()
		for _, want := range []string{"piperplus:", "/path/to/model.onnx", io.ErrUnexpectedEOF.Error()} {
			if !strings.Contains(msg, want) {
				t.Errorf("Error() = %q, want substring %q", msg, want)
			}
		}
	})

	t.Run("Unwrap", func(t *testing.T) {
		if got := err.Unwrap(); got != io.ErrUnexpectedEOF {
			t.Errorf("Unwrap() = %v, want %v", got, io.ErrUnexpectedEOF)
		}
	})

	t.Run("ErrorsIs", func(t *testing.T) {
		if !errors.Is(err, io.ErrUnexpectedEOF) {
			t.Error("errors.Is(err, io.ErrUnexpectedEOF) = false, want true")
		}
	})

	t.Run("ErrorsAs", func(t *testing.T) {
		var target *ModelLoadError
		if !errors.As(err, &target) {
			t.Error("errors.As(err, &ModelLoadError{}) = false, want true")
		}
		if target.Path != "/path/to/model.onnx" {
			t.Errorf("target.Path = %q, want %q", target.Path, "/path/to/model.onnx")
		}
	})
}

func TestConfigError(t *testing.T) {
	err := &ConfigError{Path: "/path/to/config.json", Err: os.ErrNotExist}

	t.Run("Error", func(t *testing.T) {
		msg := err.Error()
		for _, want := range []string{"piperplus:", "/path/to/config.json", os.ErrNotExist.Error()} {
			if !strings.Contains(msg, want) {
				t.Errorf("Error() = %q, want substring %q", msg, want)
			}
		}
	})

	t.Run("Unwrap", func(t *testing.T) {
		if got := err.Unwrap(); got != os.ErrNotExist {
			t.Errorf("Unwrap() = %v, want %v", got, os.ErrNotExist)
		}
	})

	t.Run("ErrorsIs", func(t *testing.T) {
		if !errors.Is(err, os.ErrNotExist) {
			t.Error("errors.Is(err, os.ErrNotExist) = false, want true")
		}
	})
}

func TestInferenceError(t *testing.T) {
	wrapped := errors.New("underlying cause")

	t.Run("WithErr", func(t *testing.T) {
		err := &InferenceError{Msg: "tensor shape mismatch", Err: wrapped}

		msg := err.Error()
		for _, want := range []string{"tensor shape mismatch", wrapped.Error()} {
			if !strings.Contains(msg, want) {
				t.Errorf("Error() = %q, want substring %q", msg, want)
			}
		}

		if got := err.Unwrap(); got != wrapped {
			t.Errorf("Unwrap() = %v, want %v", got, wrapped)
		}
	})

	t.Run("NilErr", func(t *testing.T) {
		err := &InferenceError{Msg: "tensor shape mismatch", Err: nil}

		msg := err.Error()
		if !strings.Contains(msg, "tensor shape mismatch") {
			t.Errorf("Error() = %q, want substring %q", msg, "tensor shape mismatch")
		}

		if got := err.Unwrap(); got != nil {
			t.Errorf("Unwrap() = %v, want nil", got)
		}
	})
}

func TestPhonemeError(t *testing.T) {
	err := &PhonemeError{Phoneme: "\u00fc", Language: "de", Msg: "unsupported"}

	t.Run("Error", func(t *testing.T) {
		msg := err.Error()
		for _, want := range []string{"\u00fc", "de", "unsupported"} {
			if !strings.Contains(msg, want) {
				t.Errorf("Error() = %q, want substring %q", msg, want)
			}
		}
	})

	t.Run("NoUnwrap", func(t *testing.T) {
		// PhonemeError does not implement Unwrap; verify errors.As still matches
		// the concrete type but errors.Is against a sentinel does not.
		var target *PhonemeError
		if !errors.As(err, &target) {
			t.Error("errors.As(err, &PhonemeError{}) = false, want true")
		}
	})
}

func TestPhonemeIDNotFoundError(t *testing.T) {
	err := &PhonemeIDNotFoundError{Token: "xyz"}

	t.Run("Error", func(t *testing.T) {
		msg := err.Error()
		if !strings.Contains(msg, "xyz") {
			t.Errorf("Error() = %q, want substring %q", msg, "xyz")
		}
	})

	t.Run("NoUnwrap", func(t *testing.T) {
		var target *PhonemeIDNotFoundError
		if !errors.As(err, &target) {
			t.Error("errors.As(err, &PhonemeIDNotFoundError{}) = false, want true")
		}
		if target.Token != "xyz" {
			t.Errorf("target.Token = %q, want %q", target.Token, "xyz")
		}
	})
}

func TestSentinelErrors(t *testing.T) {
	sentinels := []struct {
		name string
		err  error
	}{
		{"ErrModelClosed", ErrModelClosed},
		{"ErrEmptyText", ErrEmptyText},
		{"ErrEmptyPhonemeIDs", ErrEmptyPhonemeIDs},
		{"ErrUnsupportedLang", ErrUnsupportedLang},
	}

	for _, s := range sentinels {
		t.Run(s.name+"/Identity", func(t *testing.T) {
			if !errors.Is(s.err, s.err) {
				t.Errorf("errors.Is(%s, %s) = false, want true", s.name, s.name)
			}
		})

		t.Run(s.name+"/Prefix", func(t *testing.T) {
			if !strings.HasPrefix(s.err.Error(), "piperplus:") {
				t.Errorf("%s.Error() = %q, want prefix %q", s.name, s.err.Error(), "piperplus:")
			}
		})
	}

	t.Run("Distinct", func(t *testing.T) {
		for i := 0; i < len(sentinels); i++ {
			for j := i + 1; j < len(sentinels); j++ {
				a, b := sentinels[i], sentinels[j]
				if errors.Is(a.err, b.err) {
					t.Errorf("errors.Is(%s, %s) = true, want false", a.name, b.name)
				}
			}
		}
	})
}
