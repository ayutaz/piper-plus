package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	rdebug "runtime/debug"
	"strings"
	"testing"
)

func buildInfo(mainVersion string) func() (*rdebug.BuildInfo, bool) {
	return func() (*rdebug.BuildInfo, bool) {
		return &rdebug.BuildInfo{Main: rdebug.Module{Version: mainVersion}}, true
	}
}

func noBuildInfo() (*rdebug.BuildInfo, bool) { return nil, false }

func TestResolveVersion(t *testing.T) {
	cases := []struct {
		name    string
		ldflags string
		info    func() (*rdebug.BuildInfo, bool)
		want    string
	}{
		// `go install github.com/ayutaz/piper-plus/src/go/cmd/piper-plus@v0.3.2`
		// records the module version in the binary.
		{"go install records the module version", "", buildInfo("v0.3.2"), "v0.3.2"},
		// `make build` passes -X main.version=...; it wins over build info.
		{"ldflags wins", "v9.8.7", buildInfo("v0.3.2"), "v9.8.7"},
		{"go build in a checkout", "", buildInfo("(devel)"), "(devel)"},
		{"empty module version", "", buildInfo(""), "(devel)"},
		{"no build info", "", noBuildInfo, "(devel)"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := resolveVersion(tc.ldflags, tc.info); got != tc.want {
				t.Errorf("resolveVersion(%q) = %q, want %q", tc.ldflags, got, tc.want)
			}
		})
	}
}

// v0.3.0 and v0.3.1 printed a hard-coded "v0.2.0".
func TestVersionFlagPrintsResolvedVersion(t *testing.T) {
	saved := version
	t.Cleanup(func() {
		version = saved
		showVersion = false
		rootCmd.SetOut(nil)
	})
	version = "v9.8.7"
	showVersion = true
	var out bytes.Buffer
	rootCmd.SetOut(&out)

	if err := runSynthesize(rootCmd, nil); err != nil {
		t.Fatalf("runSynthesize: %v", err)
	}
	if got, want := out.String(), "piper-plus (Go) v9.8.7\n"; got != want {
		t.Errorf("--version printed %q, want %q", got, want)
	}
}

// The Makefile builds with -ldflags "-X main.version=$(VERSION)". The linker
// rejects -X for a variable that is not a string, which broke `make build`
// while the --version flag itself was a bool named `version`.
func TestLdflagsVersionReachesBinary(t *testing.T) {
	if testing.Short() {
		t.Skip("builds the CLI")
	}
	bin := filepath.Join(t.TempDir(), "piper-plus")
	if runtime.GOOS == "windows" {
		bin += ".exe"
	}
	build := exec.Command("go", "build", "-ldflags", "-X main.version=v9.8.7", "-o", bin, ".")
	build.Env = os.Environ()
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build with -X main.version failed: %v\n%s", err, out)
	}
	out, err := exec.Command(bin, "--version").Output()
	if err != nil {
		t.Fatalf("%s --version: %v", bin, err)
	}
	if got := strings.TrimSpace(string(out)); got != "piper-plus (Go) v9.8.7" {
		t.Errorf("--version printed %q, want %q", got, "piper-plus (Go) v9.8.7")
	}
}
