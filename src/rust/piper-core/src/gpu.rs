//! Low-level GPU inference support via ONNX Runtime ExecutionProviders.
//!
//! This module handles the **ort integration layer** -- it configures ONNX
//! Runtime `SessionBuilder` instances with the appropriate `ExecutionProvider`
//! (CUDA, CoreML, DirectML, TensorRT) and manages device string parsing for
//! the engine.
//!
//! Feature-gated: `cuda`, `coreml`, `directml`, `tensorrt` features enable
//! respective providers.  Auto-detection tries available providers and falls
//! back to CPU.
//!
//! For the high-level, user-facing device enumeration and selection API, see
//! [`crate::device`].

use std::sync::OnceLock;

use crate::error::PiperError;

/// Supported GPU device types.
#[derive(Debug, Clone, PartialEq)]
pub enum DeviceType {
    Cpu,
    Cuda { device_id: i32 },
    CoreML,
    DirectML { device_id: i32 },
    TensorRT { device_id: i32 },
}

impl std::fmt::Display for DeviceType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DeviceType::Cpu => write!(f, "cpu"),
            DeviceType::Cuda { device_id } => write!(f, "cuda:{device_id}"),
            DeviceType::CoreML => write!(f, "coreml"),
            DeviceType::DirectML { device_id } => write!(f, "directml:{device_id}"),
            DeviceType::TensorRT { device_id } => write!(f, "tensorrt:{device_id}"),
        }
    }
}

/// Information about an available compute device.
#[derive(Debug, Clone)]
pub struct DeviceInfo {
    pub name: String,
    pub device_type: DeviceType,
    pub available: bool,
}

/// Parse a device string ("cpu", "cuda", "cuda:0", "cuda:1", "coreml",
/// "directml", "directml:2", "tensorrt", "tensorrt:0", "auto") into a
/// [`DeviceType`].
///
/// The string is matched case-insensitively.
pub fn parse_device_string(device: &str) -> Result<DeviceType, PiperError> {
    let device = device.trim();

    if device.eq_ignore_ascii_case("cpu") {
        return Ok(DeviceType::Cpu);
    }

    if device.eq_ignore_ascii_case("auto") {
        return Ok(auto_detect_device());
    }

    if device.eq_ignore_ascii_case("coreml") {
        return Ok(DeviceType::CoreML);
    }

    // Handle devices with optional ":N" suffix by splitting on ':'
    if let Some((prefix, id_str)) = device.split_once(':') {
        // Map prefix to canonical display name for error messages
        let canonical = if prefix.eq_ignore_ascii_case("cuda") {
            Some("CUDA")
        } else if prefix.eq_ignore_ascii_case("directml") {
            Some("DirectML")
        } else if prefix.eq_ignore_ascii_case("tensorrt") {
            Some("TensorRT")
        } else {
            None
        };

        if let Some(kind_name) = canonical {
            let device_id = id_str
                .parse::<i32>()
                .map_err(|_| PiperError::InvalidConfig {
                    reason: format!("invalid {kind_name} device id: '{id_str}'"),
                })?;

            if device_id < 0 {
                return Err(PiperError::InvalidConfig {
                    reason: format!("negative device ID not allowed: {device_id}"),
                });
            }

            return match kind_name {
                "CUDA" => Ok(DeviceType::Cuda { device_id }),
                "DirectML" => Ok(DeviceType::DirectML { device_id }),
                "TensorRT" => Ok(DeviceType::TensorRT { device_id }),
                _ => unreachable!(),
            };
        }
    } else {
        // No colon -- bare name defaults to device_id 0
        if device.eq_ignore_ascii_case("cuda") {
            return Ok(DeviceType::Cuda { device_id: 0 });
        }
        if device.eq_ignore_ascii_case("directml") {
            return Ok(DeviceType::DirectML { device_id: 0 });
        }
        if device.eq_ignore_ascii_case("tensorrt") {
            return Ok(DeviceType::TensorRT { device_id: 0 });
        }
    }

    Err(PiperError::InvalidConfig {
        reason: format!("unknown device: '{device}'"),
    })
}

/// Cached result of `auto_detect_device()`.
///
/// `OnceLock` ensures the detection logic runs at most once per process,
/// avoiding repeated ~100 ms probe overhead when multiple models are loaded.
static AUTO_DEVICE_CACHE: OnceLock<DeviceType> = OnceLock::new();

/// Auto-detect the best available device.
///
/// Priority: CUDA -> CoreML -> DirectML -> CPU.
/// Only checks providers whose corresponding feature is enabled.
///
/// The result is cached in a process-wide `OnceLock` so that subsequent
/// calls return immediately (~0 ns) instead of re-probing providers.
fn auto_detect_device() -> DeviceType {
    AUTO_DEVICE_CACHE
        .get_or_init(|| {
            #[cfg(feature = "cuda")]
            {
                if is_cuda_available() {
                    tracing::info!("Auto-detected CUDA device");
                    return DeviceType::Cuda { device_id: 0 };
                }
            }

            #[cfg(feature = "coreml")]
            {
                if is_coreml_available() {
                    tracing::info!("Auto-detected CoreML device");
                    return DeviceType::CoreML;
                }
            }

            #[cfg(feature = "directml")]
            {
                if is_directml_available() {
                    tracing::info!("Auto-detected DirectML device");
                    return DeviceType::DirectML { device_id: 0 };
                }
            }

            tracing::info!("No GPU providers available, using CPU");
            DeviceType::Cpu
        })
        .clone()
}

/// List all available compute devices.
///
/// Always includes CPU. Checks for CUDA/CoreML/DirectML/TensorRT availability
/// based on enabled features.
pub fn list_devices() -> Vec<DeviceInfo> {
    #[allow(unused_mut)]
    let mut devices = vec![DeviceInfo {
        name: "CPU".to_string(),
        device_type: DeviceType::Cpu,
        available: true,
    }];

    #[cfg(feature = "cuda")]
    {
        let available = is_cuda_available();
        devices.push(DeviceInfo {
            name: "CUDA".to_string(),
            device_type: DeviceType::Cuda { device_id: 0 },
            available,
        });
    }

    #[cfg(feature = "coreml")]
    {
        let available = is_coreml_available();
        devices.push(DeviceInfo {
            name: "CoreML".to_string(),
            device_type: DeviceType::CoreML,
            available,
        });
    }

    #[cfg(feature = "directml")]
    {
        let available = is_directml_available();
        devices.push(DeviceInfo {
            name: "DirectML".to_string(),
            device_type: DeviceType::DirectML { device_id: 0 },
            available,
        });
    }

    #[cfg(feature = "tensorrt")]
    {
        let available = is_tensorrt_available();
        devices.push(DeviceInfo {
            name: "TensorRT".to_string(),
            device_type: DeviceType::TensorRT { device_id: 0 },
            available,
        });
    }

    devices
}

/// Configure an ONNX Runtime session builder with the appropriate ExecutionProvider.
///
/// Returns the builder and the device actually used (may fall back to CPU if the
/// requested provider is unavailable or registration fails).
///
/// Uses ort v2 API:
/// ```ignore
/// use ort::ep;
/// let builder = Session::builder()?
///     .with_execution_providers([ep::CUDA::default().build()])?;
/// ```
pub fn configure_session_builder(
    builder: ort::session::builder::SessionBuilder,
    device: &DeviceType,
) -> Result<(ort::session::builder::SessionBuilder, DeviceType), PiperError> {
    match device {
        DeviceType::Cpu => Ok(apply_cpu_ep(builder)),

        #[cfg(feature = "cuda")]
        DeviceType::Cuda { device_id } => configure_cuda(builder, *device_id),
        #[cfg(not(feature = "cuda"))]
        DeviceType::Cuda { .. } => {
            tracing::warn!("CUDA requested but 'cuda' feature is not enabled, falling back to CPU");
            Ok(apply_cpu_ep(builder))
        }

        #[cfg(feature = "coreml")]
        DeviceType::CoreML => configure_coreml(builder),
        #[cfg(not(feature = "coreml"))]
        DeviceType::CoreML => {
            tracing::warn!(
                "CoreML requested but 'coreml' feature is not enabled, falling back to CPU"
            );
            Ok(apply_cpu_ep(builder))
        }

        #[cfg(feature = "directml")]
        DeviceType::DirectML { device_id } => configure_directml(builder, *device_id),
        #[cfg(not(feature = "directml"))]
        DeviceType::DirectML { .. } => {
            tracing::warn!(
                "DirectML requested but 'directml' feature is not enabled, falling back to CPU"
            );
            Ok(apply_cpu_ep(builder))
        }

        #[cfg(feature = "tensorrt")]
        DeviceType::TensorRT { device_id } => configure_tensorrt(builder, *device_id),
        #[cfg(not(feature = "tensorrt"))]
        DeviceType::TensorRT { .. } => {
            tracing::warn!(
                "TensorRT requested but 'tensorrt' feature is not enabled, falling back to CPU"
            );
            Ok(apply_cpu_ep(builder))
        }
    }
}

// ---------------------------------------------------------------------------
// CPU EP helper — applies arena allocator to any builder falling back to CPU
// ---------------------------------------------------------------------------

/// Register the CPU ExecutionProvider with arena allocator enabled.
///
/// If registration fails, logs a warning and returns the recovered builder
/// (matching the fault-tolerant pattern used throughout this module).
fn apply_cpu_ep(
    builder: ort::session::builder::SessionBuilder,
) -> (ort::session::builder::SessionBuilder, DeviceType) {
    let ep = ort::ep::CPU::default().with_arena_allocator(true).build();
    match builder.with_execution_providers([ep]) {
        Ok(b) => (b, DeviceType::Cpu),
        Err(e) => {
            tracing::warn!(
                "CPU arena allocator registration failed: {e}, continuing with defaults"
            );
            (e.recover(), DeviceType::Cpu)
        }
    }
}

// ---------------------------------------------------------------------------
// Feature-gated provider helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "cuda")]
fn is_cuda_available() -> bool {
    use ort::ep::{CUDA, ExecutionProvider};
    CUDA::default().is_available().unwrap_or(false)
}

#[cfg(feature = "cuda")]
fn configure_cuda(
    builder: ort::session::builder::SessionBuilder,
    device_id: i32,
) -> Result<(ort::session::builder::SessionBuilder, DeviceType), PiperError> {
    let ep = ort::ep::CUDA::default().with_device_id(device_id).build();
    match builder.with_execution_providers([ep]) {
        Ok(b) => {
            tracing::info!("CUDA execution provider registered (device_id={device_id})");
            Ok((b, DeviceType::Cuda { device_id }))
        }
        Err(e) => {
            tracing::warn!("Failed to register CUDA EP: {e}, falling back to CPU");
            Ok(apply_cpu_ep(e.recover()))
        }
    }
}

#[cfg(feature = "coreml")]
fn is_coreml_available() -> bool {
    use ort::ep::{CoreML, ExecutionProvider};
    CoreML::default().is_available().unwrap_or(false)
}

#[cfg(feature = "coreml")]
fn configure_coreml(
    builder: ort::session::builder::SessionBuilder,
) -> Result<(ort::session::builder::SessionBuilder, DeviceType), PiperError> {
    let ep = ort::ep::CoreML::default().build();
    match builder.with_execution_providers([ep]) {
        Ok(b) => {
            tracing::info!("CoreML execution provider registered");
            Ok((b, DeviceType::CoreML))
        }
        Err(e) => {
            tracing::warn!("Failed to register CoreML EP: {e}, falling back to CPU");
            Ok(apply_cpu_ep(e.recover()))
        }
    }
}

#[cfg(feature = "directml")]
fn is_directml_available() -> bool {
    use ort::ep::{DirectML, ExecutionProvider};
    DirectML::default().is_available().unwrap_or(false)
}

#[cfg(feature = "directml")]
fn configure_directml(
    builder: ort::session::builder::SessionBuilder,
    device_id: i32,
) -> Result<(ort::session::builder::SessionBuilder, DeviceType), PiperError> {
    let ep = ort::ep::DirectML::default()
        .with_device_id(device_id)
        .build();
    match builder.with_execution_providers([ep]) {
        Ok(b) => {
            tracing::info!("DirectML execution provider registered (device_id={device_id})");
            Ok((b, DeviceType::DirectML { device_id }))
        }
        Err(e) => {
            tracing::warn!("Failed to register DirectML EP: {e}, falling back to CPU");
            Ok(apply_cpu_ep(e.recover()))
        }
    }
}

#[cfg(feature = "tensorrt")]
fn is_tensorrt_available() -> bool {
    use ort::ep::{ExecutionProvider, TensorRT};
    TensorRT::default().is_available().unwrap_or(false)
}

#[cfg(feature = "tensorrt")]
fn configure_tensorrt(
    builder: ort::session::builder::SessionBuilder,
    device_id: i32,
) -> Result<(ort::session::builder::SessionBuilder, DeviceType), PiperError> {
    let ep = ort::ep::TensorRT::default()
        .with_device_id(device_id)
        .build();
    match builder.with_execution_providers([ep]) {
        Ok(b) => {
            tracing::info!("TensorRT execution provider registered (device_id={device_id})");
            Ok((b, DeviceType::TensorRT { device_id }))
        }
        Err(e) => {
            tracing::warn!("Failed to register TensorRT EP: {e}, falling back to CPU");
            Ok(apply_cpu_ep(e.recover()))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // parse_device_string tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_parse_cpu() {
        let dt = parse_device_string("cpu").unwrap();
        assert_eq!(dt, DeviceType::Cpu);
    }

    #[test]
    fn test_parse_cpu_uppercase() {
        let dt = parse_device_string("CPU").unwrap();
        assert_eq!(dt, DeviceType::Cpu);
    }

    #[test]
    fn test_parse_cuda_default() {
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
    fn test_parse_cuda_mixed_case() {
        let dt = parse_device_string("CUDA:2").unwrap();
        assert_eq!(dt, DeviceType::Cuda { device_id: 2 });
    }

    #[test]
    fn test_parse_coreml() {
        let dt = parse_device_string("coreml").unwrap();
        assert_eq!(dt, DeviceType::CoreML);
    }

    #[test]
    fn test_parse_coreml_uppercase() {
        let dt = parse_device_string("CoreML").unwrap();
        assert_eq!(dt, DeviceType::CoreML);
    }

    #[test]
    fn test_parse_directml_default() {
        let dt = parse_device_string("directml").unwrap();
        assert_eq!(dt, DeviceType::DirectML { device_id: 0 });
    }

    #[test]
    fn test_parse_directml_device_2() {
        let dt = parse_device_string("directml:2").unwrap();
        assert_eq!(dt, DeviceType::DirectML { device_id: 2 });
    }

    #[test]
    fn test_parse_tensorrt_default() {
        let dt = parse_device_string("tensorrt").unwrap();
        assert_eq!(dt, DeviceType::TensorRT { device_id: 0 });
    }

    #[test]
    fn test_parse_tensorrt_device_0() {
        let dt = parse_device_string("tensorrt:0").unwrap();
        assert_eq!(dt, DeviceType::TensorRT { device_id: 0 });
    }

    #[test]
    fn test_parse_auto() {
        // Auto should always succeed (falls back to CPU when no GPU features enabled)
        let dt = parse_device_string("auto").unwrap();
        // Without GPU features, auto resolves to CPU
        #[cfg(not(any(feature = "cuda", feature = "coreml", feature = "directml")))]
        assert_eq!(dt, DeviceType::Cpu);
        // With any GPU feature, it may resolve to a GPU device (still valid)
        #[cfg(any(feature = "cuda", feature = "coreml", feature = "directml"))]
        let _ = dt; // just ensure no error
    }

    // -----------------------------------------------------------------------
    // parse_device_string error cases
    // -----------------------------------------------------------------------

    #[test]
    fn test_parse_invalid_device() {
        let result = parse_device_string("vulkan");
        assert!(result.is_err());
        let err_msg = format!("{}", result.unwrap_err());
        assert!(err_msg.contains("unknown device"));
    }

    #[test]
    fn test_parse_cuda_invalid_id() {
        let result = parse_device_string("cuda:abc");
        assert!(result.is_err());
        let err_msg = format!("{}", result.unwrap_err());
        assert!(err_msg.contains("invalid CUDA device id"));
    }

    #[test]
    fn test_parse_directml_invalid_id() {
        let result = parse_device_string("directml:xyz");
        assert!(result.is_err());
        let err_msg = format!("{}", result.unwrap_err());
        assert!(err_msg.contains("invalid DirectML device id"));
    }

    #[test]
    fn test_parse_tensorrt_invalid_id() {
        let result = parse_device_string("tensorrt:bad");
        assert!(result.is_err());
        let err_msg = format!("{}", result.unwrap_err());
        assert!(err_msg.contains("invalid TensorRT device id"));
    }

    #[test]
    fn test_parse_empty_string() {
        let result = parse_device_string("");
        assert!(result.is_err());
    }

    // -----------------------------------------------------------------------
    // list_devices tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_list_devices_contains_cpu() {
        let devices = list_devices();
        assert!(!devices.is_empty());
        assert!(devices.iter().any(|d| d.device_type == DeviceType::Cpu));
    }

    #[test]
    fn test_list_devices_cpu_always_available() {
        let devices = list_devices();
        let cpu = devices
            .iter()
            .find(|d| d.device_type == DeviceType::Cpu)
            .unwrap();
        assert!(cpu.available);
        assert_eq!(cpu.name, "CPU");
    }

    #[test]
    fn test_list_devices_first_is_cpu() {
        let devices = list_devices();
        assert_eq!(devices[0].device_type, DeviceType::Cpu);
    }

    // -----------------------------------------------------------------------
    // DeviceType Display tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_display_cpu() {
        assert_eq!(format!("{}", DeviceType::Cpu), "cpu");
    }

    #[test]
    fn test_display_cuda() {
        assert_eq!(format!("{}", DeviceType::Cuda { device_id: 0 }), "cuda:0");
        assert_eq!(format!("{}", DeviceType::Cuda { device_id: 3 }), "cuda:3");
    }

    #[test]
    fn test_display_coreml() {
        assert_eq!(format!("{}", DeviceType::CoreML), "coreml");
    }

    #[test]
    fn test_display_directml() {
        assert_eq!(
            format!("{}", DeviceType::DirectML { device_id: 1 }),
            "directml:1"
        );
    }

    #[test]
    fn test_display_tensorrt() {
        assert_eq!(
            format!("{}", DeviceType::TensorRT { device_id: 0 }),
            "tensorrt:0"
        );
    }

    // -----------------------------------------------------------------------
    // DeviceInfo tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_device_info_construction() {
        let info = DeviceInfo {
            name: "TestGPU".to_string(),
            device_type: DeviceType::Cuda { device_id: 1 },
            available: true,
        };
        assert_eq!(info.name, "TestGPU");
        assert_eq!(info.device_type, DeviceType::Cuda { device_id: 1 });
        assert!(info.available);
    }

    #[test]
    fn test_device_info_debug() {
        let info = DeviceInfo {
            name: "CPU".to_string(),
            device_type: DeviceType::Cpu,
            available: true,
        };
        let debug = format!("{:?}", info);
        assert!(debug.contains("CPU"));
        assert!(debug.contains("available: true"));
    }

    #[test]
    fn test_device_info_clone() {
        let info = DeviceInfo {
            name: "CUDA".to_string(),
            device_type: DeviceType::Cuda { device_id: 0 },
            available: false,
        };
        let cloned = info.clone();
        assert_eq!(cloned.name, info.name);
        assert_eq!(cloned.device_type, info.device_type);
        assert_eq!(cloned.available, info.available);
    }

    // -----------------------------------------------------------------------
    // DeviceType equality and clone tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_device_type_equality() {
        assert_eq!(DeviceType::Cpu, DeviceType::Cpu);
        assert_eq!(
            DeviceType::Cuda { device_id: 0 },
            DeviceType::Cuda { device_id: 0 }
        );
        assert_ne!(
            DeviceType::Cuda { device_id: 0 },
            DeviceType::Cuda { device_id: 1 }
        );
        assert_ne!(DeviceType::Cpu, DeviceType::CoreML);
    }

    #[test]
    fn test_device_type_clone() {
        let dt = DeviceType::TensorRT { device_id: 2 };
        let cloned = dt.clone();
        assert_eq!(dt, cloned);
    }

    // -----------------------------------------------------------------------
    // Feature-gated availability tests
    // -----------------------------------------------------------------------

    #[cfg(feature = "cuda")]
    #[test]
    fn test_cuda_listed_when_feature_enabled() {
        let devices = list_devices();
        assert!(
            devices
                .iter()
                .any(|d| matches!(d.device_type, DeviceType::Cuda { .. }))
        );
    }

    #[cfg(feature = "coreml")]
    #[test]
    fn test_coreml_listed_when_feature_enabled() {
        let devices = list_devices();
        assert!(devices.iter().any(|d| d.device_type == DeviceType::CoreML));
    }

    #[cfg(feature = "directml")]
    #[test]
    fn test_directml_listed_when_feature_enabled() {
        let devices = list_devices();
        assert!(
            devices
                .iter()
                .any(|d| matches!(d.device_type, DeviceType::DirectML { .. }))
        );
    }

    #[cfg(feature = "tensorrt")]
    #[test]
    fn test_tensorrt_listed_when_feature_enabled() {
        let devices = list_devices();
        assert!(
            devices
                .iter()
                .any(|d| matches!(d.device_type, DeviceType::TensorRT { .. }))
        );
    }

    // -----------------------------------------------------------------------
    // configure_session_builder CPU test
    // -----------------------------------------------------------------------

    #[test]
    fn test_configure_cpu_returns_cpu() {
        // CPU configuration should always succeed without needing an actual model
        let builder = ort::session::Session::builder().expect("session builder");
        let (_, actual_device) = configure_session_builder(builder, &DeviceType::Cpu).unwrap();
        assert_eq!(actual_device, DeviceType::Cpu);
    }

    #[test]
    fn test_configure_cpu_with_arena_allocator() {
        let ep = ort::ep::CPU::default().with_arena_allocator(true).build();
        let builder = ort::session::Session::builder().expect("session builder");
        let result = builder.with_execution_providers([ep]);
        match result {
            Ok(_) => {}
            Err(err) => {
                let _ = err.recover();
            }
        }
    }

    // -----------------------------------------------------------------------
    // Fallback tests (feature not enabled)
    // -----------------------------------------------------------------------

    #[cfg(not(feature = "cuda"))]
    #[test]
    fn test_cuda_fallback_without_feature() {
        let builder = ort::session::Session::builder().expect("session builder");
        let (_, actual_device) =
            configure_session_builder(builder, &DeviceType::Cuda { device_id: 0 }).unwrap();
        assert_eq!(actual_device, DeviceType::Cpu);
    }

    #[cfg(not(feature = "coreml"))]
    #[test]
    fn test_coreml_fallback_without_feature() {
        let builder = ort::session::Session::builder().expect("session builder");
        let (_, actual_device) = configure_session_builder(builder, &DeviceType::CoreML).unwrap();
        assert_eq!(actual_device, DeviceType::Cpu);
    }

    #[cfg(not(feature = "directml"))]
    #[test]
    fn test_directml_fallback_without_feature() {
        let builder = ort::session::Session::builder().expect("session builder");
        let (_, actual_device) =
            configure_session_builder(builder, &DeviceType::DirectML { device_id: 0 }).unwrap();
        assert_eq!(actual_device, DeviceType::Cpu);
    }

    #[cfg(not(feature = "tensorrt"))]
    #[test]
    fn test_tensorrt_fallback_without_feature() {
        let builder = ort::session::Session::builder().expect("session builder");
        let (_, actual_device) =
            configure_session_builder(builder, &DeviceType::TensorRT { device_id: 0 }).unwrap();
        assert_eq!(actual_device, DeviceType::Cpu);
    }

    // -----------------------------------------------------------------------
    // Additional TDD tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_auto_detect_device_returns_valid() {
        let dt = parse_device_string("auto").unwrap();
        // Regardless of features, the result must be a valid DeviceType variant
        match dt {
            DeviceType::Cpu
            | DeviceType::Cuda { .. }
            | DeviceType::CoreML
            | DeviceType::DirectML { .. }
            | DeviceType::TensorRT { .. } => {} // all valid
        }
    }

    #[test]
    fn test_auto_detect_device_is_deterministic() {
        // OnceLock cache guarantees the same result within a single process.
        let d1 = auto_detect_device();
        let d2 = auto_detect_device();
        assert_eq!(d1, d2);
    }

    #[test]
    fn test_parse_device_string_whitespace() {
        // parse_device_string trims whitespace before matching.
        let dt = parse_device_string(" cuda ").unwrap();
        assert_eq!(dt, DeviceType::Cuda { device_id: 0 });
    }

    #[test]
    fn test_parse_device_string_large_device_id() {
        let dt = parse_device_string("cuda:999").unwrap();
        assert_eq!(dt, DeviceType::Cuda { device_id: 999 });
    }

    #[test]
    fn test_device_type_default_display_roundtrip() {
        // For each variant, Display then parse back should produce the same value
        let variants = vec![
            DeviceType::Cpu,
            DeviceType::Cuda { device_id: 0 },
            DeviceType::Cuda { device_id: 7 },
            DeviceType::CoreML,
            DeviceType::DirectML { device_id: 0 },
            DeviceType::DirectML { device_id: 3 },
            DeviceType::TensorRT { device_id: 0 },
            DeviceType::TensorRT { device_id: 5 },
        ];
        for variant in variants {
            let displayed = format!("{variant}");
            let parsed = parse_device_string(&displayed).unwrap();
            assert_eq!(parsed, variant, "roundtrip failed for '{displayed}'");
        }
    }
}
