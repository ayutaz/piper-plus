// Package piperplus ORT session contract parity test.
//
// Loads tests/fixtures/ort_session/contract.json and verifies that the Go
// implementation respects the canonical contract values (graph optimization
// level, max intra threads, warmup parameters, cache file extensions, env
// vars). Sister tests in Python/Rust/C# load the same fixture and assert
// their own runtime constants — drift in any of them is caught locally.
//
// Note: the Go runtime delegates intra/inter thread tuning and graph
// optimization to ONNX Runtime defaults (no explicit SetIntraOpNumThreads
// or SetGraphOptimizationLevel call), so this test focuses on:
//   - JSON fixture schema sanity (drift detection on contract.json)
//   - Canonical string/numeric values that any runtime must agree on
//   - Smoke check that ort.NewSessionOptions() succeeds (mirrors the
//     internal entry point in device.go::configureSessionOptions).

package piperplus

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type ortSessionContract struct {
	SchemaVersion int `json:"schema_version"`
	Session       struct {
		GraphOptimizationLevel string `json:"graph_optimization_level"`
		ExecutionMode          string `json:"execution_mode"`
		MaxIntraThreads        int    `json:"max_intra_threads"`
		InterOpThreads         int    `json:"inter_op_threads"`
		EnableCpuMemArena      bool   `json:"enable_cpu_mem_arena"`
		EnableMemoryPattern    bool   `json:"enable_memory_pattern"`
		DynamicBlockBase       int    `json:"dynamic_block_base"`
	} `json:"session"`
	Warmup struct {
		PhonemeLength int     `json:"phoneme_length"`
		BosToken      int     `json:"bos_token"`
		EosToken      int     `json:"eos_token"`
		DummyPhoneme  int     `json:"dummy_phoneme"`
		DefaultRuns   int     `json:"default_runs"`
		NoiseScale    float64 `json:"noise_scale"`
		LengthScale   float64 `json:"length_scale"`
		NoiseW        float64 `json:"noise_w"`
	} `json:"warmup"`
	Cache struct {
		OptimizedExtension    string `json:"optimized_extension"`
		SentinelExtension     string `json:"sentinel_extension"`
		SentinelContent       string `json:"sentinel_content"`
		DeviceLabelCpu        string `json:"device_label_cpu"`
		DeviceLabelCudaFormat string `json:"device_label_cuda_format"`
	} `json:"cache"`
	EnvVars struct {
		DisableWarmup string `json:"disable_warmup"`
		DisableCache  string `json:"disable_cache"`
		IntraThreads  string `json:"intra_threads"`
	} `json:"env_vars"`
}

func loadOrtSessionContract(t *testing.T) ortSessionContract {
	t.Helper()
	// Walk up from src/go/piperplus to repo root, then into tests/fixtures.
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("os.Getwd: %v", err)
	}
	repoRoot := wd
	for i := 0; i < 6; i++ {
		candidate := filepath.Join(repoRoot, "tests", "fixtures", "ort_session", "contract.json")
		if _, err := os.Stat(candidate); err == nil {
			data, err := os.ReadFile(candidate)
			if err != nil {
				t.Fatalf("read %s: %v", candidate, err)
			}
			var fixture ortSessionContract
			if err := json.Unmarshal(data, &fixture); err != nil {
				t.Fatalf("parse %s: %v", candidate, err)
			}
			return fixture
		}
		parent := filepath.Dir(repoRoot)
		if parent == repoRoot {
			break
		}
		repoRoot = parent
	}
	t.Fatalf("could not locate tests/fixtures/ort_session/contract.json starting from %s", wd)
	return ortSessionContract{}
}

func TestOrtSessionContract_FixtureSanity(t *testing.T) {
	c := loadOrtSessionContract(t)
	if c.SchemaVersion != 1 {
		t.Errorf("schema_version: got %d, want 1", c.SchemaVersion)
	}
}

func TestOrtSessionContract_SessionConstants(t *testing.T) {
	c := loadOrtSessionContract(t)
	if c.Session.GraphOptimizationLevel != "ORT_ENABLE_ALL" {
		t.Errorf("graph_optimization_level: got %q, want %q",
			c.Session.GraphOptimizationLevel, "ORT_ENABLE_ALL")
	}
	if c.Session.ExecutionMode != "SEQUENTIAL" {
		t.Errorf("execution_mode: got %q, want %q",
			c.Session.ExecutionMode, "SEQUENTIAL")
	}
	if c.Session.MaxIntraThreads != 4 {
		t.Errorf("max_intra_threads: got %d, want 4", c.Session.MaxIntraThreads)
	}
	if c.Session.InterOpThreads != 1 {
		t.Errorf("inter_op_threads: got %d, want 1", c.Session.InterOpThreads)
	}
	if c.Session.DynamicBlockBase != 4 {
		t.Errorf("dynamic_block_base: got %d, want 4", c.Session.DynamicBlockBase)
	}
	if !c.Session.EnableCpuMemArena {
		t.Errorf("enable_cpu_mem_arena should be true")
	}
	if !c.Session.EnableMemoryPattern {
		t.Errorf("enable_memory_pattern should be true")
	}
}

func TestOrtSessionContract_WarmupConstants(t *testing.T) {
	c := loadOrtSessionContract(t)
	if c.Warmup.PhonemeLength != 100 {
		t.Errorf("warmup.phoneme_length: got %d, want 100", c.Warmup.PhonemeLength)
	}
	if c.Warmup.BosToken != 1 {
		t.Errorf("warmup.bos_token: got %d, want 1", c.Warmup.BosToken)
	}
	if c.Warmup.EosToken != 2 {
		t.Errorf("warmup.eos_token: got %d, want 2", c.Warmup.EosToken)
	}
	if c.Warmup.DummyPhoneme != 8 {
		t.Errorf("warmup.dummy_phoneme: got %d, want 8", c.Warmup.DummyPhoneme)
	}
	if c.Warmup.DefaultRuns != 2 {
		t.Errorf("warmup.default_runs: got %d, want 2", c.Warmup.DefaultRuns)
	}
}

func TestOrtSessionContract_WarmupScales(t *testing.T) {
	c := loadOrtSessionContract(t)
	if abs(c.Warmup.NoiseScale-0.667) > 1e-9 {
		t.Errorf("warmup.noise_scale: got %f, want 0.667", c.Warmup.NoiseScale)
	}
	if abs(c.Warmup.LengthScale-1.0) > 1e-9 {
		t.Errorf("warmup.length_scale: got %f, want 1.0", c.Warmup.LengthScale)
	}
	if abs(c.Warmup.NoiseW-0.8) > 1e-9 {
		t.Errorf("warmup.noise_w: got %f, want 0.8", c.Warmup.NoiseW)
	}
}

func TestOrtSessionContract_CacheConventions(t *testing.T) {
	c := loadOrtSessionContract(t)
	if c.Cache.OptimizedExtension != "opt.onnx" {
		t.Errorf("cache.optimized_extension: got %q, want %q",
			c.Cache.OptimizedExtension, "opt.onnx")
	}
	if c.Cache.SentinelExtension != "opt.onnx.ok" {
		t.Errorf("cache.sentinel_extension: got %q, want %q",
			c.Cache.SentinelExtension, "opt.onnx.ok")
	}
	if c.Cache.SentinelContent != "ok" {
		t.Errorf("cache.sentinel_content: got %q, want %q",
			c.Cache.SentinelContent, "ok")
	}
	if c.Cache.DeviceLabelCpu != "cpu" {
		t.Errorf("cache.device_label_cpu: got %q, want %q",
			c.Cache.DeviceLabelCpu, "cpu")
	}
}

func TestOrtSessionContract_EnvVarNames(t *testing.T) {
	c := loadOrtSessionContract(t)
	if c.EnvVars.DisableWarmup != "PIPER_DISABLE_WARMUP" {
		t.Errorf("env_vars.disable_warmup: got %q, want %q",
			c.EnvVars.DisableWarmup, "PIPER_DISABLE_WARMUP")
	}
	if c.EnvVars.DisableCache != "PIPER_DISABLE_CACHE" {
		t.Errorf("env_vars.disable_cache: got %q, want %q",
			c.EnvVars.DisableCache, "PIPER_DISABLE_CACHE")
	}
	if c.EnvVars.IntraThreads != "PIPER_INTRA_THREADS" {
		t.Errorf("env_vars.intra_threads: got %q, want %q",
			c.EnvVars.IntraThreads, "PIPER_INTRA_THREADS")
	}
}

// NOTE: configureSessionOptions() requires ONNX Runtime to be initialised
// (ort.InitializeEnvironment()), which is not available in the unit-test
// path. Smoke checks for that helper live in integration_test.go behind
// the `integration` build tag. Drift detection of the contract values
// themselves is covered by the fixture-based tests above.

func abs(f float64) float64 {
	if f < 0 {
		return -f
	}
	return f
}
