package main

import (
	"bytes"
	"strings"
	"testing"
)

// TestRootCmd_BasicMetadata pins the rootCmd metadata so renaming the binary
// or losing SilenceUsage requires an explicit test update.
func TestRootCmd_BasicMetadata(t *testing.T) {
	if rootCmd.Use != "piper-plus" {
		t.Errorf("rootCmd.Use = %q, want %q", rootCmd.Use, "piper-plus")
	}
	if rootCmd.Short == "" {
		t.Error("rootCmd.Short should not be empty")
	}
	if !rootCmd.SilenceUsage {
		t.Error("rootCmd.SilenceUsage should be true")
	}
}

// TestRootCmd_HelpRunsCleanly invokes --help via the cobra entry point and
// checks the output contains expected sections.
func TestRootCmd_HelpRunsCleanly(t *testing.T) {
	var buf bytes.Buffer
	rootCmd.SetOut(&buf)
	rootCmd.SetErr(&buf)
	rootCmd.SetArgs([]string{"--help"})
	t.Cleanup(func() {
		rootCmd.SetArgs(nil)
	})

	if err := rootCmd.Execute(); err != nil {
		t.Fatalf("rootCmd --help returned error: %v", err)
	}
	out := buf.String()
	for _, want := range []string{"Usage", "Flags"} {
		if !strings.Contains(out, want) {
			t.Errorf("--help output missing %q; got:\n%s", want, out)
		}
	}
}

// TestRootCmd_RejectsInvalidFlag ensures cobra fails with a non-zero error on
// unknown flags so flag-name typos surface immediately.
func TestRootCmd_RejectsInvalidFlag(t *testing.T) {
	rootCmd.SetArgs([]string{"--definitely-not-a-real-flag"})
	t.Cleanup(func() {
		rootCmd.SetArgs(nil)
	})

	var buf bytes.Buffer
	rootCmd.SetOut(&buf)
	rootCmd.SetErr(&buf)

	if err := rootCmd.Execute(); err == nil {
		t.Fatal("rootCmd should fail on unknown flag")
	}
}

// TestRootCmd_PersistentFlags_Defined pins the persistent flag surface that
// applies to both `piper-plus` and `piper-plus serve` so contracts with
// embedders don't drift.
func TestRootCmd_PersistentFlags_Defined(t *testing.T) {
	persistent := []struct {
		name string
	}{
		{"model"},
		{"config"},
		{"device"},
		{"debug"},
		{"quiet"},
		{"custom-dict"},
		{"model-dir"},
	}
	for _, c := range persistent {
		if rootCmd.PersistentFlags().Lookup(c.name) == nil {
			t.Errorf("persistent flag --%s not registered", c.name)
		}
	}
}

// TestRootCmd_LocalFlags_Defined pins the synthesize-mode flags that are
// shared with the Rust / Python / C# CLIs.
func TestRootCmd_LocalFlags_Defined(t *testing.T) {
	flags := []string{
		"text", "language", "speaker", "output-file", "output-dir",
		"noise-scale", "length-scale", "noise-w", "sentence-silence",
		"streaming", "batch", "output-timing", "timing-format",
		"version", "output-raw", "json-input", "list-models",
		"download-model", "phoneme-silence",
		"reference-audio", "speaker-embedding", "speaker-encoder-model",
	}
	for _, name := range flags {
		if rootCmd.Flags().Lookup(name) == nil {
			t.Errorf("local flag --%s not registered", name)
		}
	}
}

// TestRootCmd_FlagDefaults pins the defaults that are part of the contract.
func TestRootCmd_FlagDefaults(t *testing.T) {
	cases := []struct {
		flag     string
		expected string
	}{
		{"noise-scale", "0.667"},
		{"length-scale", "1"},
		{"noise-w", "0.8"},
		{"sentence-silence", "0.2"},
		{"timing-format", "json"},
		{"output-dir", "."},
		{"device", "cpu"},
	}
	for _, c := range cases {
		f := rootCmd.PersistentFlags().Lookup(c.flag)
		if f == nil {
			f = rootCmd.Flags().Lookup(c.flag)
		}
		if f == nil {
			t.Errorf("flag --%s not registered", c.flag)
			continue
		}
		if f.DefValue != c.expected {
			t.Errorf("flag --%s default = %q, want %q", c.flag, f.DefValue, c.expected)
		}
	}
}

// TestRootCmd_ShortFlags pins the short alias surface for end-user scripts.
func TestRootCmd_ShortFlags(t *testing.T) {
	cases := []struct {
		short string
		long  string
	}{
		{"m", "model"},
		{"c", "config"},
		{"q", "quiet"},
		{"t", "text"},
		{"s", "speaker"},
		{"f", "output-file"},
		{"d", "output-dir"},
	}
	for _, c := range cases {
		f := rootCmd.PersistentFlags().Lookup(c.long)
		if f == nil {
			f = rootCmd.Flags().Lookup(c.long)
		}
		if f == nil {
			t.Errorf("flag --%s not registered", c.long)
			continue
		}
		if f.Shorthand != c.short {
			t.Errorf("flag --%s short alias = %q, want %q", c.long, f.Shorthand, c.short)
		}
	}
}

// TestRootCmd_VersionFlagBoolean confirms --version is a bool flag, not a
// global cobra-managed --version (which would short-circuit before our
// runSynthesize handler).
func TestRootCmd_VersionFlagBoolean(t *testing.T) {
	f := rootCmd.Flags().Lookup("version")
	if f == nil {
		t.Fatal("--version flag not registered")
	}
	if f.Value.Type() != "bool" {
		t.Errorf("--version type = %q, want %q", f.Value.Type(), "bool")
	}
}
