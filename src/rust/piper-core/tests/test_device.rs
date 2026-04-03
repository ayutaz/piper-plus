#![cfg(feature = "onnx")]
//! Integration tests for the device module.
//!
//! Validates DeviceSelection constructors, from_str parsing (valid & invalid),
//! DeviceKind / DeviceSelection / DeviceInfo Display formatting,
//! enumerate_devices, is_device_available, auto(), recommended_device(),
//! and trait implementations (Clone, PartialEq, Hash).

use std::str::FromStr;

use piper_plus::device::*;

// =========================================================================
// DeviceSelection constructors
// =========================================================================

#[test]
fn test_constructor_cpu() {
    let sel = DeviceSelection::cpu();
    assert_eq!(sel.kind, DeviceKind::Cpu);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_constructor_cuda() {
    let sel = DeviceSelection::cuda(3);
    assert_eq!(sel.kind, DeviceKind::Cuda);
    assert_eq!(sel.device_id, 3);
}

#[test]
fn test_constructor_cuda_zero() {
    let sel = DeviceSelection::cuda(0);
    assert_eq!(sel.kind, DeviceKind::Cuda);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_constructor_coreml() {
    let sel = DeviceSelection::coreml();
    assert_eq!(sel.kind, DeviceKind::CoreML);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_constructor_directml() {
    let sel = DeviceSelection::directml(1);
    assert_eq!(sel.kind, DeviceKind::DirectML);
    assert_eq!(sel.device_id, 1);
}

#[test]
fn test_constructor_directml_zero() {
    let sel = DeviceSelection::directml(0);
    assert_eq!(sel.kind, DeviceKind::DirectML);
    assert_eq!(sel.device_id, 0);
}

// =========================================================================
// DeviceSelection::from_str — valid inputs
// =========================================================================

#[test]
fn test_from_str_cpu() {
    let sel = DeviceSelection::from_str("cpu").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cpu);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_from_str_cuda_bare() {
    let sel = DeviceSelection::from_str("cuda").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cuda);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_from_str_cuda_with_id_0() {
    let sel = DeviceSelection::from_str("cuda:0").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cuda);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_from_str_cuda_with_id_1() {
    let sel = DeviceSelection::from_str("cuda:1").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cuda);
    assert_eq!(sel.device_id, 1);
}

#[test]
fn test_from_str_coreml() {
    let sel = DeviceSelection::from_str("coreml").unwrap();
    assert_eq!(sel.kind, DeviceKind::CoreML);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_from_str_directml_bare() {
    let sel = DeviceSelection::from_str("directml").unwrap();
    assert_eq!(sel.kind, DeviceKind::DirectML);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_from_str_directml_with_id() {
    let sel = DeviceSelection::from_str("directml:2").unwrap();
    assert_eq!(sel.kind, DeviceKind::DirectML);
    assert_eq!(sel.device_id, 2);
}

#[test]
fn test_from_str_tensorrt_bare() {
    let sel = DeviceSelection::from_str("tensorrt").unwrap();
    assert_eq!(sel.kind, DeviceKind::TensorRT);
    assert_eq!(sel.device_id, 0);
}

#[test]
fn test_from_str_tensorrt_with_id() {
    let sel = DeviceSelection::from_str("tensorrt:1").unwrap();
    assert_eq!(sel.kind, DeviceKind::TensorRT);
    assert_eq!(sel.device_id, 1);
}

#[test]
fn test_from_str_auto_returns_valid_device() {
    let sel = DeviceSelection::from_str("auto").unwrap();
    // auto always returns a valid device; on any platform CPU is the fallback
    assert!(
        sel.kind == DeviceKind::Cpu
            || sel.kind == DeviceKind::Cuda
            || sel.kind == DeviceKind::CoreML
            || sel.kind == DeviceKind::DirectML
            || sel.kind == DeviceKind::TensorRT
    );
    assert!(sel.device_id >= 0);
}

// =========================================================================
// DeviceSelection::from_str — case insensitivity
// =========================================================================

#[test]
fn test_from_str_case_insensitive_uppercase() {
    let sel = DeviceSelection::from_str("CPU").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cpu);

    let sel2 = DeviceSelection::from_str("CUDA").unwrap();
    assert_eq!(sel2.kind, DeviceKind::Cuda);
}

#[test]
fn test_from_str_case_insensitive_mixed_case() {
    let sel = DeviceSelection::from_str("Cuda:1").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cuda);
    assert_eq!(sel.device_id, 1);

    let sel2 = DeviceSelection::from_str("CoreML").unwrap();
    assert_eq!(sel2.kind, DeviceKind::CoreML);

    let sel3 = DeviceSelection::from_str("DirectML:0").unwrap();
    assert_eq!(sel3.kind, DeviceKind::DirectML);
    assert_eq!(sel3.device_id, 0);
}

#[test]
fn test_from_str_case_insensitive_auto() {
    let sel = DeviceSelection::from_str("AUTO").unwrap();
    assert!(sel.device_id >= 0);
}

// =========================================================================
// DeviceSelection::from_str — whitespace handling
// =========================================================================

#[test]
fn test_from_str_leading_trailing_whitespace() {
    let sel = DeviceSelection::from_str("  cpu  ").unwrap();
    assert_eq!(sel.kind, DeviceKind::Cpu);
    assert_eq!(sel.device_id, 0);
}

// =========================================================================
// DeviceSelection::from_str — error cases
// =========================================================================

#[test]
fn test_from_str_empty_string_errors() {
    let result = DeviceSelection::from_str("");
    assert!(result.is_err(), "empty string should return an error");
}

#[test]
fn test_from_str_whitespace_only_errors() {
    let result = DeviceSelection::from_str("   ");
    assert!(
        result.is_err(),
        "whitespace-only string should return an error"
    );
}

#[test]
fn test_from_str_unknown_device_errors() {
    let result = DeviceSelection::from_str("gpu");
    assert!(result.is_err(), "\"gpu\" is not a valid device kind");
}

#[test]
fn test_from_str_garbage_errors() {
    let result = DeviceSelection::from_str("!@#$%");
    assert!(result.is_err(), "garbage input should return an error");
}

#[test]
fn test_from_str_invalid_device_id_non_numeric() {
    let result = DeviceSelection::from_str("cuda:abc");
    assert!(
        result.is_err(),
        "non-numeric device id should return an error"
    );
}

#[test]
fn test_from_str_invalid_device_id_float() {
    let result = DeviceSelection::from_str("cuda:1.5");
    assert!(result.is_err(), "float device id should return an error");
}

#[test]
fn test_from_str_completely_unknown() {
    let result = DeviceSelection::from_str("vulkan");
    assert!(
        result.is_err(),
        "unknown device kind should return an error"
    );
}

// =========================================================================
// DeviceKind — Display formatting
// =========================================================================

#[test]
fn test_device_kind_display_all_variants() {
    assert_eq!(DeviceKind::Cpu.to_string(), "cpu");
    assert_eq!(DeviceKind::Cuda.to_string(), "cuda");
    assert_eq!(DeviceKind::CoreML.to_string(), "coreml");
    assert_eq!(DeviceKind::DirectML.to_string(), "directml");
    assert_eq!(DeviceKind::TensorRT.to_string(), "tensorrt");
}

// =========================================================================
// DeviceSelection — Display formatting
// =========================================================================

#[test]
fn test_device_selection_display_cpu_no_id() {
    // CPU display should not include ":0"
    let sel = DeviceSelection::cpu();
    assert_eq!(sel.to_string(), "cpu");
}

#[test]
fn test_device_selection_display_cuda_includes_id() {
    let sel = DeviceSelection::cuda(0);
    assert_eq!(sel.to_string(), "cuda:0");

    let sel1 = DeviceSelection::cuda(1);
    assert_eq!(sel1.to_string(), "cuda:1");
}

#[test]
fn test_device_selection_display_coreml() {
    // CoreML has no device_id, but DeviceSelection stores device_id = 0
    // Display should show "coreml:0" since kind != Cpu
    let sel = DeviceSelection::coreml();
    let display = sel.to_string();
    assert!(
        display.contains("coreml"),
        "CoreML display should contain 'coreml', got: {}",
        display
    );
}

#[test]
fn test_device_selection_display_directml() {
    let sel = DeviceSelection::directml(2);
    assert_eq!(sel.to_string(), "directml:2");
}

// =========================================================================
// DeviceInfo — Display formatting
// =========================================================================

#[test]
fn test_device_info_display_cpu() {
    let info = DeviceInfo {
        kind: DeviceKind::Cpu,
        device_id: 0,
        name: "CPU".to_string(),
        available: true,
        memory_bytes: None,
    };
    assert_eq!(info.to_string(), "cpu (CPU) [available]");
}

#[test]
fn test_device_info_display_cuda_with_memory() {
    let info = DeviceInfo {
        kind: DeviceKind::Cuda,
        device_id: 0,
        name: "NVIDIA GeForce RTX 3090".to_string(),
        available: true,
        memory_bytes: Some(24 * 1024 * 1024 * 1024), // 24 GB
    };
    assert_eq!(
        info.to_string(),
        "cuda:0 (NVIDIA GeForce RTX 3090, 24GB) [available]"
    );
}

#[test]
fn test_device_info_display_unavailable() {
    let info = DeviceInfo {
        kind: DeviceKind::Cuda,
        device_id: 1,
        name: "CUDA Device 1".to_string(),
        available: false,
        memory_bytes: None,
    };
    assert_eq!(info.to_string(), "cuda:1 (CUDA Device 1) [unavailable]");
}

#[test]
fn test_device_info_display_no_memory() {
    let info = DeviceInfo {
        kind: DeviceKind::DirectML,
        device_id: 0,
        name: "DirectML Device 0".to_string(),
        available: true,
        memory_bytes: None,
    };
    let s = info.to_string();
    assert!(
        !s.contains("GB"),
        "no memory_bytes should omit the GB suffix, got: {}",
        s
    );
    assert!(s.contains("[available]"));
}

// =========================================================================
// enumerate_devices
// =========================================================================

#[test]
fn test_enumerate_devices_non_empty() {
    let devices = enumerate_devices();
    assert!(
        !devices.is_empty(),
        "enumerate_devices() should always return at least one device"
    );
}

#[test]
fn test_enumerate_devices_includes_cpu() {
    let devices = enumerate_devices();
    let has_cpu = devices.iter().any(|d| d.kind == DeviceKind::Cpu);
    assert!(
        has_cpu,
        "enumerate_devices() must always include a CPU entry"
    );
}

#[test]
fn test_enumerate_devices_cpu_is_available() {
    let devices = enumerate_devices();
    let cpu = devices
        .iter()
        .find(|d| d.kind == DeviceKind::Cpu)
        .expect("CPU device must be present");
    assert!(
        cpu.available,
        "CPU device must always be marked as available"
    );
    assert_eq!(cpu.device_id, 0, "CPU device_id should be 0");
}

#[test]
fn test_enumerate_devices_all_have_names() {
    let devices = enumerate_devices();
    for d in devices {
        assert!(
            !d.name.is_empty(),
            "device {:?} should have a non-empty name",
            d.kind
        );
    }
}

#[test]
fn test_enumerate_devices_cpu_first() {
    let devices = enumerate_devices();
    assert_eq!(
        devices[0].kind,
        DeviceKind::Cpu,
        "CPU should be the first device in the enumeration"
    );
}

// =========================================================================
// is_device_available
// =========================================================================

#[test]
fn test_cpu_always_available() {
    assert!(
        is_device_available(&DeviceKind::Cpu),
        "CPU must always be available"
    );
}

#[test]
fn test_is_device_available_consistency_with_enumerate() {
    // Every device reported by enumerate_devices as available should also
    // return true from is_device_available.
    let devices = enumerate_devices();
    for d in devices {
        if d.available {
            assert!(
                is_device_available(&d.kind),
                "enumerate_devices says {:?} is available, but is_device_available disagrees",
                d.kind
            );
        }
    }
}

// =========================================================================
// auto() and recommended_device() — must not panic
// =========================================================================

#[test]
fn test_auto_returns_valid_device() {
    let sel = DeviceSelection::auto();
    assert!(
        sel.kind == DeviceKind::Cpu
            || sel.kind == DeviceKind::Cuda
            || sel.kind == DeviceKind::CoreML
            || sel.kind == DeviceKind::DirectML
            || sel.kind == DeviceKind::TensorRT
    );
    assert!(sel.device_id >= 0);
}

#[test]
fn test_auto_selects_available_device() {
    let sel = DeviceSelection::auto();
    assert!(
        is_device_available(&sel.kind),
        "auto() should only select a device that is available"
    );
}

#[test]
fn test_recommended_device_returns_valid() {
    let sel = recommended_device();
    assert!(
        sel.kind == DeviceKind::Cpu
            || sel.kind == DeviceKind::Cuda
            || sel.kind == DeviceKind::CoreML
            || sel.kind == DeviceKind::DirectML
            || sel.kind == DeviceKind::TensorRT
    );
    assert!(sel.device_id >= 0);
}

#[test]
fn test_recommended_device_matches_auto() {
    let auto_sel = DeviceSelection::auto();
    let rec_sel = recommended_device();
    assert_eq!(
        auto_sel.kind, rec_sel.kind,
        "recommended_device() and auto() should select the same device kind"
    );
    assert_eq!(
        auto_sel.device_id, rec_sel.device_id,
        "recommended_device() and auto() should select the same device id"
    );
}

// =========================================================================
// DeviceKind — PartialEq, Clone, Hash
// =========================================================================

#[test]
fn test_device_kind_eq() {
    assert_eq!(DeviceKind::Cpu, DeviceKind::Cpu);
    assert_eq!(DeviceKind::Cuda, DeviceKind::Cuda);
    assert_eq!(DeviceKind::CoreML, DeviceKind::CoreML);
    assert_eq!(DeviceKind::DirectML, DeviceKind::DirectML);
    assert_eq!(DeviceKind::TensorRT, DeviceKind::TensorRT);
}

#[test]
fn test_device_kind_ne() {
    assert_ne!(DeviceKind::Cpu, DeviceKind::Cuda);
    assert_ne!(DeviceKind::Cuda, DeviceKind::CoreML);
    assert_ne!(DeviceKind::CoreML, DeviceKind::DirectML);
    assert_ne!(DeviceKind::DirectML, DeviceKind::TensorRT);
}

#[test]
fn test_device_kind_clone() {
    let original = DeviceKind::Cuda;
    let cloned = original.clone();
    assert_eq!(original, cloned);
}

#[test]
fn test_device_kind_hash_dedup() {
    use std::collections::HashSet;
    let mut set = HashSet::new();
    set.insert(DeviceKind::Cpu);
    set.insert(DeviceKind::Cuda);
    set.insert(DeviceKind::Cpu); // duplicate
    set.insert(DeviceKind::CoreML);
    assert_eq!(set.len(), 3);
    assert!(set.contains(&DeviceKind::Cpu));
    assert!(set.contains(&DeviceKind::Cuda));
    assert!(set.contains(&DeviceKind::CoreML));
    assert!(!set.contains(&DeviceKind::DirectML));
}

// =========================================================================
// Round-trip: from_str -> Display -> from_str
// =========================================================================

#[test]
fn test_roundtrip_cpu() {
    let original = DeviceSelection::from_str("cpu").unwrap();
    let display = original.to_string();
    let reparsed = DeviceSelection::from_str(&display).unwrap();
    assert_eq!(reparsed.kind, original.kind);
    assert_eq!(reparsed.device_id, original.device_id);
}

#[test]
fn test_roundtrip_cuda_0() {
    let original = DeviceSelection::from_str("cuda:0").unwrap();
    let display = original.to_string();
    let reparsed = DeviceSelection::from_str(&display).unwrap();
    assert_eq!(reparsed.kind, DeviceKind::Cuda);
    assert_eq!(reparsed.device_id, 0);
}

#[test]
fn test_roundtrip_cuda_1() {
    let original = DeviceSelection::from_str("cuda:1").unwrap();
    let display = original.to_string();
    let reparsed = DeviceSelection::from_str(&display).unwrap();
    assert_eq!(reparsed.kind, DeviceKind::Cuda);
    assert_eq!(reparsed.device_id, 1);
}

#[test]
fn test_roundtrip_directml_2() {
    let original = DeviceSelection::from_str("directml:2").unwrap();
    let display = original.to_string();
    let reparsed = DeviceSelection::from_str(&display).unwrap();
    assert_eq!(reparsed.kind, DeviceKind::DirectML);
    assert_eq!(reparsed.device_id, 2);
}

#[test]
fn test_roundtrip_tensorrt() {
    let original = DeviceSelection::from_str("tensorrt:0").unwrap();
    let display = original.to_string();
    let reparsed = DeviceSelection::from_str(&display).unwrap();
    assert_eq!(reparsed.kind, DeviceKind::TensorRT);
    assert_eq!(reparsed.device_id, 0);
}
