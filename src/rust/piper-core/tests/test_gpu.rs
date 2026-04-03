#![cfg(feature = "onnx")]
//! Integration tests for the GPU module.
//!
//! Validates device string parsing, device enumeration,
//! and trait implementations on DeviceType / DeviceInfo.

use piper_plus::gpu::{DeviceInfo, DeviceType, list_devices, parse_device_string};

// =========================================================================
// parse_device_string — valid inputs
// =========================================================================

#[test]
fn test_parse_cpu() {
    let dt = parse_device_string("cpu").unwrap();
    assert_eq!(dt, DeviceType::Cpu);
}

#[test]
fn test_parse_cuda_bare() {
    let dt = parse_device_string("cuda").unwrap();
    assert_eq!(dt, DeviceType::Cuda { device_id: 0 });
}

#[test]
fn test_parse_cuda_device_0() {
    let dt = parse_device_string("cuda:0").unwrap();
    assert_eq!(dt, DeviceType::Cuda { device_id: 0 });
}

#[test]
fn test_parse_cuda_device_1() {
    let dt = parse_device_string("cuda:1").unwrap();
    assert_eq!(dt, DeviceType::Cuda { device_id: 1 });
}

#[test]
fn test_parse_coreml() {
    let dt = parse_device_string("coreml").unwrap();
    assert_eq!(dt, DeviceType::CoreML);
}

#[test]
fn test_parse_directml_bare() {
    let dt = parse_device_string("directml").unwrap();
    assert_eq!(dt, DeviceType::DirectML { device_id: 0 });
}

#[test]
fn test_parse_directml_device_2() {
    let dt = parse_device_string("directml:2").unwrap();
    assert_eq!(dt, DeviceType::DirectML { device_id: 2 });
}

#[test]
fn test_parse_tensorrt_bare() {
    let dt = parse_device_string("tensorrt").unwrap();
    assert_eq!(dt, DeviceType::TensorRT { device_id: 0 });
}

#[test]
fn test_parse_tensorrt_device_1() {
    let dt = parse_device_string("tensorrt:1").unwrap();
    assert_eq!(dt, DeviceType::TensorRT { device_id: 1 });
}

#[test]
fn test_parse_auto_returns_valid_device() {
    // "auto" should succeed and return some valid DeviceType
    let dt = parse_device_string("auto").unwrap();
    // We cannot know which device is selected, but it must be one of the
    // known variants. A simple way to verify: it should display without panic.
    let display = format!("{}", dt);
    assert!(
        !display.is_empty(),
        "auto device should have a non-empty display string"
    );
}

// =========================================================================
// parse_device_string — case insensitivity
// =========================================================================

#[test]
fn test_parse_uppercase_cpu() {
    // Case-insensitive parsing: "CPU" should be accepted as "cpu"
    let result = parse_device_string("CPU");
    match result {
        Ok(dt) => assert_eq!(dt, DeviceType::Cpu),
        Err(_) => {
            // If case-insensitive parsing is not supported, that is acceptable.
            // The important thing is that it does not panic.
        }
    }
}

#[test]
fn test_parse_uppercase_cuda() {
    let result = parse_device_string("CUDA");
    match result {
        Ok(dt) => assert_eq!(dt, DeviceType::Cuda { device_id: 0 }),
        Err(_) => {
            // Not supported is acceptable — must not panic.
        }
    }
}

// =========================================================================
// parse_device_string — invalid inputs
// =========================================================================

#[test]
fn test_parse_invalid_string_errors() {
    let result = parse_device_string("invalid");
    assert!(result.is_err(), "\"invalid\" should return an error");
}

#[test]
fn test_parse_empty_string_errors() {
    let result = parse_device_string("");
    assert!(result.is_err(), "empty string should return an error");
}

#[test]
fn test_parse_garbage_errors() {
    let result = parse_device_string("!@#$%");
    assert!(result.is_err(), "garbage input should return an error");
}

#[test]
fn test_parse_cuda_negative_device_accepted_or_rejected() {
    let result = parse_device_string("cuda:-1");
    // Implementation may accept or reject negative device IDs
    // The key is it doesn't panic
    if let Ok(dt) = &result {
        // If accepted, verify it parsed as cuda
        assert!(matches!(dt, DeviceType::Cuda { .. }));
    }
    // Either Ok or Err is fine — no panic is what matters
}

#[test]
fn test_parse_cuda_non_numeric_suffix_errors() {
    let result = parse_device_string("cuda:abc");
    assert!(
        result.is_err(),
        "non-numeric device id should return an error"
    );
}

// =========================================================================
// list_devices
// =========================================================================

#[test]
fn test_list_devices_non_empty() {
    let devices = list_devices();
    assert!(
        !devices.is_empty(),
        "list_devices() should always return at least one device (CPU)"
    );
}

#[test]
fn test_list_devices_includes_cpu() {
    let devices = list_devices();
    let has_cpu = devices.iter().any(|d| d.device_type == DeviceType::Cpu);
    assert!(has_cpu, "list_devices() must always include a CPU device");
}

#[test]
fn test_list_devices_cpu_is_available() {
    let devices = list_devices();
    let cpu = devices.iter().find(|d| d.device_type == DeviceType::Cpu);
    assert!(cpu.is_some(), "CPU device must be present");
    assert!(
        cpu.unwrap().available,
        "CPU device must always be marked as available"
    );
}

#[test]
fn test_list_devices_no_duplicate_types() {
    let devices = list_devices();
    let mut seen: Vec<String> = Vec::new();
    for d in &devices {
        let key = format!("{}", d.device_type);
        assert!(!seen.contains(&key), "duplicate device type found: {}", key);
        seen.push(key);
    }
}

#[test]
fn test_list_devices_all_have_names() {
    let devices = list_devices();
    for d in &devices {
        assert!(
            !d.name.is_empty(),
            "device {:?} should have a non-empty name",
            d.device_type
        );
    }
}

// =========================================================================
// DeviceType — Display formatting
// =========================================================================

#[test]
fn test_display_cpu() {
    assert_eq!(format!("{}", DeviceType::Cpu), "cpu");
}

#[test]
fn test_display_cuda_0() {
    let display = format!("{}", DeviceType::Cuda { device_id: 0 });
    // Should contain "cuda" (may also include ":0")
    assert!(
        display.contains("cuda"),
        "Cuda display should contain 'cuda', got: {}",
        display
    );
}

#[test]
fn test_display_cuda_1() {
    let display = format!("{}", DeviceType::Cuda { device_id: 1 });
    assert!(
        display.contains("cuda"),
        "Cuda display should contain 'cuda', got: {}",
        display
    );
    assert!(
        display.contains("1"),
        "Cuda device 1 display should contain '1', got: {}",
        display
    );
}

#[test]
fn test_display_coreml() {
    let display = format!("{}", DeviceType::CoreML);
    assert!(
        display.contains("coreml") || display.contains("CoreML"),
        "CoreML display should contain 'coreml' or 'CoreML', got: {}",
        display
    );
}

#[test]
fn test_display_directml() {
    let display = format!("{}", DeviceType::DirectML { device_id: 0 });
    let lower = display.to_lowercase();
    assert!(
        lower.contains("directml"),
        "DirectML display should contain 'directml', got: {}",
        display
    );
}

#[test]
fn test_display_tensorrt() {
    let display = format!("{}", DeviceType::TensorRT { device_id: 0 });
    let lower = display.to_lowercase();
    assert!(
        lower.contains("tensorrt"),
        "TensorRT display should contain 'tensorrt', got: {}",
        display
    );
}

// =========================================================================
// DeviceType — PartialEq comparisons
// =========================================================================

#[test]
fn test_eq_same_variant() {
    assert_eq!(DeviceType::Cpu, DeviceType::Cpu);
    assert_eq!(
        DeviceType::Cuda { device_id: 0 },
        DeviceType::Cuda { device_id: 0 }
    );
    assert_eq!(DeviceType::CoreML, DeviceType::CoreML);
}

#[test]
fn test_ne_different_variant() {
    assert_ne!(DeviceType::Cpu, DeviceType::CoreML);
    assert_ne!(DeviceType::Cpu, DeviceType::Cuda { device_id: 0 });
}

#[test]
fn test_ne_different_device_id() {
    assert_ne!(
        DeviceType::Cuda { device_id: 0 },
        DeviceType::Cuda { device_id: 1 }
    );
    assert_ne!(
        DeviceType::DirectML { device_id: 0 },
        DeviceType::DirectML { device_id: 1 }
    );
    assert_ne!(
        DeviceType::TensorRT { device_id: 0 },
        DeviceType::TensorRT { device_id: 1 }
    );
}

// =========================================================================
// DeviceType — Clone behavior
// =========================================================================

#[test]
fn test_clone_cpu() {
    let original = DeviceType::Cpu;
    let cloned = original.clone();
    assert_eq!(original, cloned);
}

#[test]
fn test_clone_cuda() {
    let original = DeviceType::Cuda { device_id: 3 };
    let cloned = original.clone();
    assert_eq!(original, cloned);
}

#[test]
fn test_clone_coreml() {
    let original = DeviceType::CoreML;
    let cloned = original.clone();
    assert_eq!(original, cloned);
}

// =========================================================================
// DeviceInfo — construction and field access
// =========================================================================

#[test]
fn test_device_info_construction() {
    let info = DeviceInfo {
        name: "Test CPU".to_string(),
        device_type: DeviceType::Cpu,
        available: true,
    };
    assert_eq!(info.name, "Test CPU");
    assert_eq!(info.device_type, DeviceType::Cpu);
    assert!(info.available);
}

#[test]
fn test_device_info_unavailable() {
    let info = DeviceInfo {
        name: "NVIDIA GeForce RTX 4090".to_string(),
        device_type: DeviceType::Cuda { device_id: 0 },
        available: false,
    };
    assert_eq!(info.name, "NVIDIA GeForce RTX 4090");
    assert_eq!(info.device_type, DeviceType::Cuda { device_id: 0 });
    assert!(!info.available);
}

#[test]
fn test_device_info_debug() {
    let info = DeviceInfo {
        name: "CPU".to_string(),
        device_type: DeviceType::Cpu,
        available: true,
    };
    let debug = format!("{:?}", info);
    // Debug should include the device name
    assert!(
        debug.contains("CPU"),
        "DeviceInfo debug should contain device name: {debug}"
    );
}

// =========================================================================
// Round-trip: parse -> display -> parse
// =========================================================================

#[test]
fn test_roundtrip_cpu() {
    let original = parse_device_string("cpu").unwrap();
    let display = format!("{}", original);
    let reparsed = parse_device_string(&display).unwrap();
    assert_eq!(original, reparsed);
}

#[test]
fn test_roundtrip_coreml() {
    let original = parse_device_string("coreml").unwrap();
    let display = format!("{}", original);
    let reparsed = parse_device_string(&display).unwrap();
    assert_eq!(original, reparsed);
}
