package main

import (
	"testing"
)

func TestServeCmd_Registered(t *testing.T) {
	found := false
	for _, cmd := range rootCmd.Commands() {
		if cmd.Use == "serve" {
			found = true
			break
		}
	}
	if !found {
		t.Fatal("serve subcommand not registered on rootCmd")
	}
}

func TestServeCmd_AddrFlag(t *testing.T) {
	f := serveCmd.Flags().Lookup("addr")
	if f == nil {
		t.Fatal("--addr flag not found on serveCmd")
	}
	if f.DefValue != ":8080" {
		t.Errorf("--addr default = %q, want %q", f.DefValue, ":8080")
	}
}

func TestServeCmd_PersistentFlagsAccessible(t *testing.T) {
	// Persistent flags defined on rootCmd should be accessible from serveCmd.
	persistentFlags := []string{"model", "config", "device", "debug", "quiet", "custom-dict", "model-dir"}
	for _, name := range persistentFlags {
		f := serveCmd.InheritedFlags().Lookup(name)
		if f == nil {
			t.Errorf("persistent flag --%s not accessible from serveCmd", name)
		}
	}
}

func TestServeCmd_SynthesisFlagsNotInherited(t *testing.T) {
	// Synthesis-only flags (local to rootCmd) should NOT be accessible from serveCmd.
	localFlags := []string{"text", "speaker", "output-file", "output-dir", "batch", "streaming"}
	for _, name := range localFlags {
		f := serveCmd.InheritedFlags().Lookup(name)
		if f != nil {
			t.Errorf("synthesis-only flag --%s should not be inherited by serveCmd", name)
		}
		f = serveCmd.Flags().Lookup(name)
		if f != nil {
			t.Errorf("synthesis-only flag --%s should not be on serveCmd", name)
		}
	}
}

func TestServeCmd_RunESet(t *testing.T) {
	// We can't fully execute the serve command here because it depends on
	// ONNX Runtime, but we can verify the command is configured with a RunE
	// handler.
	if serveCmd.RunE == nil {
		t.Fatal("serveCmd.RunE is nil")
	}
}
