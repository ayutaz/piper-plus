package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/spf13/cobra"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

// runNoticeCLI runs the root command with args and returns captured stdout
// and stderr. The notice guard and the globals the args touch are reset, and
// ONNX Runtime is made unavailable so every run stops right after model
// resolution without network or a real model.
func runNoticeCLI(t *testing.T, resetGuard bool, args ...string) (string, string, error) {
	t.Helper()
	if resetGuard {
		modelNoticeMu.Lock()
		modelNoticeShown = false
		modelNoticeMu.Unlock()
	}
	t.Setenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH", "")
	t.Setenv("PIPER_PLUS_DEFAULT_MODEL", "")
	// Flag values persist across Execute calls in one test binary: a
	// previous `--help` run leaves the help flag set, which would make this
	// run print help and return before reaching model resolution.
	resetNoticeCLIState()

	var stdout, stderr bytes.Buffer
	rootCmd.SetOut(&stdout)
	rootCmd.SetErr(&stderr)
	rootCmd.SetArgs(args)
	t.Cleanup(func() {
		rootCmd.SetArgs(nil)
		rootCmd.SetOut(nil)
		rootCmd.SetErr(nil)
		resetNoticeCLIState()
		modelNoticeMu.Lock()
		modelNoticeShown = false
		modelNoticeMu.Unlock()
	})
	err := rootCmd.Execute()
	return stdout.String(), stderr.String(), err
}

func resetNoticeCLIState() {
	for _, c := range []*cobra.Command{rootCmd, serveCmd} {
		if f := c.Flags().Lookup("help"); f != nil {
			_ = f.Value.Set("false")
			f.Changed = false
		}
	}
	modelPath = ""
	downloadModel = ""
	modelDir = ""
	quiet = false
	version = false
	listModels = false
	textInput = ""
	batchFile = ""
	referenceAudio = ""
	speakerEmbedding = ""
}

func writeFakeModel(t *testing.T, name string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(p, []byte("not a real model"), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func assertNotice(t *testing.T, stderr string, wantCount int) {
	t.Helper()
	lines := piperplus.ModelNotice("tsukuyomi")
	if len(lines) == 0 {
		t.Fatal("catalog has no tsukuyomi notice")
	}
	if got := strings.Count(stderr, piperplus.ModelNoticeFooter); got != wantCount {
		t.Fatalf("footer printed %d times, want %d; stderr:\n%s", got, wantCount, stderr)
	}
	if wantCount == 0 {
		if strings.Contains(stderr, lines[0]) {
			t.Fatalf("notice printed unexpectedly; stderr:\n%s", stderr)
		}
		return
	}
	block := strings.Join(lines, "\n") + "\n" + piperplus.ModelNoticeFooter + "\n"
	if !strings.Contains(stderr, block) {
		t.Fatalf("stderr missing notice block %q; got:\n%s", block, stderr)
	}
}

func TestCLI_ModelNotice_LocalTsukuyomiPath(t *testing.T) {
	t.Setenv(piperplus.ModelNoticeEnv, "")
	p := writeFakeModel(t, "tsukuyomi.onnx")
	stdout, stderr, err := runNoticeCLI(t, true, "--model", p, "--quiet")
	if err == nil {
		t.Fatal("expected an error after model resolution (no ONNX Runtime)")
	}
	assertNotice(t, stderr, 1)
	if stdout != "" {
		t.Errorf("stdout must stay empty, got %q", stdout)
	}
}

func TestCLI_ModelNotice_OncePerProcess(t *testing.T) {
	t.Setenv(piperplus.ModelNoticeEnv, "")
	p := writeFakeModel(t, "tsukuyomi-chan-6lang-fp16.onnx")
	_, first, err := runNoticeCLI(t, true, "--model", p)
	if err == nil {
		t.Fatal("first run: expected an error after model resolution")
	}
	assertNotice(t, first, 1)
	_, second, err := runNoticeCLI(t, false, "--model", p)
	if err == nil {
		t.Fatal("second run: expected an error after model resolution")
	}
	assertNotice(t, second, 0)
}

func TestCLI_ModelNotice_DisabledByEnv(t *testing.T) {
	for _, v := range []string{"1", " TRUE ", "yes"} {
		t.Run(v, func(t *testing.T) {
			t.Setenv(piperplus.ModelNoticeEnv, v)
			p := writeFakeModel(t, "tsukuyomi.onnx")
			_, stderr, err := runNoticeCLI(t, true, "--model", p)
			if err == nil {
				t.Fatal("expected an error after model resolution")
			}
			assertNotice(t, stderr, 0)
		})
	}
}

func TestCLI_ModelNotice_OtherModel(t *testing.T) {
	t.Setenv(piperplus.ModelNoticeEnv, "")
	p := writeFakeModel(t, "css10-ja-6lang-fp16.onnx")
	_, stderr, err := runNoticeCLI(t, true, "--model", p)
	if err == nil {
		t.Fatal("expected an error after model resolution")
	}
	assertNotice(t, stderr, 0)
}

func TestCLI_ModelNotice_DownloadModelURL(t *testing.T) {
	t.Setenv(piperplus.ModelNoticeEnv, "")
	// Port 1 on loopback refuses connections, so the download fails fast
	// after the notice has been printed.
	url := "http://127.0.0.1:1/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx"
	stdout, stderr, err := runNoticeCLI(t, true, "--download-model", url, "--model-dir", t.TempDir())
	if err == nil {
		t.Fatal("expected the download to fail")
	}
	assertNotice(t, stderr, 1)
	if stdout != "" {
		t.Errorf("stdout must stay empty, got %q", stdout)
	}
}

func TestCLI_ModelNotice_Serve(t *testing.T) {
	t.Setenv(piperplus.ModelNoticeEnv, "")
	p := writeFakeModel(t, "tsukuyomi.onnx")
	_, stderr, err := runNoticeCLI(t, true, "serve", "--model", p)
	if err == nil {
		t.Fatal("expected serve to fail without ONNX Runtime")
	}
	assertNotice(t, stderr, 1)
}
