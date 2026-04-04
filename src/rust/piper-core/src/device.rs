//! High-level compute device enumeration and selection.
//!
//! Provides a user-facing interface for discovering and selecting compute
//! devices (CPU, CUDA, CoreML, DirectML) for ONNX Runtime inference.
//!
//! This module operates at the **application layer** -- it handles user input
//! parsing, device discovery, and display formatting.  The actual ONNX Runtime
//! `ExecutionProvider` configuration lives in [`crate::gpu`], which is the
//! **low-level ort integration layer**.  Use [`From<DeviceSelection>`] to
//! convert a high-level selection into a [`crate::gpu::DeviceType`] suitable
//! for passing to [`crate::gpu::configure_session_builder`].

use std::str::FromStr;
use std::sync::OnceLock;

use crate::error::PiperError;

/// Compute device type.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum DeviceKind {
    Cpu,
    Cuda,
    CoreML,
    DirectML,
    TensorRT,
}

impl std::fmt::Display for DeviceKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Cpu => write!(f, "cpu"),
            Self::Cuda => write!(f, "cuda"),
            Self::CoreML => write!(f, "coreml"),
            Self::DirectML => write!(f, "directml"),
            Self::TensorRT => write!(f, "tensorrt"),
        }
    }
}

/// Information about a compute device.
#[derive(Debug, Clone)]
pub struct DeviceInfo {
    pub kind: DeviceKind,
    pub device_id: i32,
    pub name: String,
    pub available: bool,
    pub memory_bytes: Option<u64>,
}

impl std::fmt::Display for DeviceInfo {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // e.g., "cuda:0 (NVIDIA GeForce RTX 3090, 24GB) [available]"
        let id_str = if self.kind == DeviceKind::Cpu {
            format!("{}", self.kind)
        } else {
            format!("{}:{}", self.kind, self.device_id)
        };

        let mem_str = match self.memory_bytes {
            Some(bytes) => {
                let gb = bytes as f64 / (1024.0 * 1024.0 * 1024.0);
                format!(", {gb:.0}GB")
            }
            None => String::new(),
        };

        let status = if self.available {
            "available"
        } else {
            "unavailable"
        };

        write!(f, "{id_str} ({}{mem_str}) [{status}]", self.name)
    }
}

/// Device selection specification.
#[derive(Debug, Clone)]
pub struct DeviceSelection {
    pub kind: DeviceKind,
    pub device_id: i32,
}

impl DeviceSelection {
    /// Select CPU device.
    pub fn cpu() -> Self {
        Self {
            kind: DeviceKind::Cpu,
            device_id: 0,
        }
    }

    /// Select CUDA device by index.
    pub fn cuda(device_id: i32) -> Self {
        Self {
            kind: DeviceKind::Cuda,
            device_id,
        }
    }

    /// Select CoreML device.
    pub fn coreml() -> Self {
        Self {
            kind: DeviceKind::CoreML,
            device_id: 0,
        }
    }

    /// Select DirectML device by index.
    pub fn directml(device_id: i32) -> Self {
        Self {
            kind: DeviceKind::DirectML,
            device_id,
        }
    }

    /// Auto-select the best available device.
    ///
    /// Priority by platform:
    /// - macOS: CoreML > CPU
    /// - Linux: CUDA > CPU
    /// - Windows: DirectML > CPU
    /// - Other: CPU
    ///
    /// Feature flags are checked at compile time; if the preferred accelerator
    /// was not compiled in, falls back to CPU.
    pub fn auto() -> Self {
        #[cfg(target_os = "macos")]
        {
            if is_device_available(&DeviceKind::CoreML) {
                return Self::coreml();
            }
        }

        #[cfg(target_os = "linux")]
        {
            if is_device_available(&DeviceKind::Cuda) {
                return Self::cuda(0);
            }
        }

        #[cfg(target_os = "windows")]
        {
            if is_device_available(&DeviceKind::DirectML) {
                return Self::directml(0);
            }
        }

        Self::cpu()
    }
}

/// Parse from string: `"cpu"`, `"cuda"`, `"cuda:0"`, `"cuda:1"`, `"coreml"`,
/// `"directml"`, `"directml:0"`, `"tensorrt"`, `"tensorrt:0"`, `"auto"`.
///
/// Parsing is case-insensitive.
impl FromStr for DeviceSelection {
    type Err = PiperError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let s = s.trim().to_ascii_lowercase();

        if s.is_empty() {
            return Err(PiperError::InvalidConfig {
                reason: "empty device string".to_string(),
            });
        }

        if s == "auto" {
            return Ok(Self::auto());
        }

        // Split on ':' to extract optional device_id
        let (kind_str, device_id) = if let Some((kind_part, id_part)) = s.split_once(':') {
            let id: i32 = id_part.parse().map_err(|_| PiperError::InvalidConfig {
                reason: format!("invalid device id: '{id_part}'"),
            })?;
            if id < 0 {
                return Err(PiperError::InvalidConfig {
                    reason: format!("negative device ID not allowed: {id}"),
                });
            }
            (kind_part, id)
        } else {
            (s.as_str(), 0)
        };

        match kind_str {
            "cpu" => {
                if device_id != 0 {
                    return Err(PiperError::InvalidConfig {
                        reason: "cpu does not accept a device ID".to_string(),
                    });
                }
                Ok(Self {
                    kind: DeviceKind::Cpu,
                    device_id: 0,
                })
            }
            "cuda" => Ok(Self {
                kind: DeviceKind::Cuda,
                device_id,
            }),
            "coreml" => {
                if device_id != 0 {
                    return Err(PiperError::InvalidConfig {
                        reason: "coreml does not accept a device ID".to_string(),
                    });
                }
                Ok(Self {
                    kind: DeviceKind::CoreML,
                    device_id: 0,
                })
            }
            "directml" => Ok(Self {
                kind: DeviceKind::DirectML,
                device_id,
            }),
            "tensorrt" => Ok(Self {
                kind: DeviceKind::TensorRT,
                device_id,
            }),
            _ => Err(PiperError::InvalidConfig {
                reason: format!("unknown device kind: '{kind_str}'"),
            }),
        }
    }
}

impl std::fmt::Display for DeviceSelection {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.kind == DeviceKind::Cpu {
            write!(f, "cpu")
        } else {
            write!(f, "{}:{}", self.kind, self.device_id)
        }
    }
}

/// Enumerate all available compute devices on this system.
///
/// CPU is always included. Accelerators are included only when the
/// corresponding feature flag is compiled in.
///
/// Results are computed once and cached for the lifetime of the process.
pub fn enumerate_devices() -> &'static [DeviceInfo] {
    static DEVICES: OnceLock<Vec<DeviceInfo>> = OnceLock::new();
    DEVICES.get_or_init(|| {
        #[allow(unused_mut)]
        let mut devices = vec![DeviceInfo {
            kind: DeviceKind::Cpu,
            device_id: 0,
            name: "CPU".to_string(),
            available: true,
            memory_bytes: None,
        }];

        // CUDA devices
        #[cfg(feature = "cuda")]
        {
            // When the cuda feature is compiled, report at least device 0.
            // Actual GPU enumeration would require the CUDA runtime; for now
            // we advertise a single device whose availability is best-effort.
            devices.push(DeviceInfo {
                kind: DeviceKind::Cuda,
                device_id: 0,
                name: "CUDA Device 0".to_string(),
                available: true,
                memory_bytes: None,
            });
        }

        // CoreML (macOS only)
        #[cfg(all(feature = "coreml", target_os = "macos"))]
        {
            devices.push(DeviceInfo {
                kind: DeviceKind::CoreML,
                device_id: 0,
                name: "Apple Neural Engine / GPU".to_string(),
                available: true,
                memory_bytes: None,
            });
        }

        // DirectML (Windows only)
        #[cfg(all(feature = "directml", target_os = "windows"))]
        {
            devices.push(DeviceInfo {
                kind: DeviceKind::DirectML,
                device_id: 0,
                name: "DirectML Device 0".to_string(),
                available: true,
                memory_bytes: None,
            });
        }

        // TensorRT (Linux typically)
        #[cfg(feature = "tensorrt")]
        {
            devices.push(DeviceInfo {
                kind: DeviceKind::TensorRT,
                device_id: 0,
                name: "TensorRT Device 0".to_string(),
                available: true,
                memory_bytes: None,
            });
        }

        devices
    })
}

/// Check if a specific device kind is available.
///
/// A device is considered available when both:
/// 1. The corresponding feature flag was compiled in, and
/// 2. The runtime can plausibly support it (e.g., correct OS).
///
/// CPU is always available.
///
/// Results are computed once and cached for the lifetime of the process.
pub fn is_device_available(kind: &DeviceKind) -> bool {
    /// Cached availability results for all device kinds.
    struct Availability {
        cuda: bool,
        coreml: bool,
        directml: bool,
        tensorrt: bool,
    }

    static AVAIL: OnceLock<Availability> = OnceLock::new();
    let avail = AVAIL.get_or_init(|| Availability {
        cuda: {
            #[cfg(feature = "cuda")]
            {
                true
            }
            #[cfg(not(feature = "cuda"))]
            {
                false
            }
        },
        coreml: {
            #[cfg(all(feature = "coreml", target_os = "macos"))]
            {
                true
            }
            #[cfg(not(all(feature = "coreml", target_os = "macos")))]
            {
                false
            }
        },
        directml: {
            #[cfg(all(feature = "directml", target_os = "windows"))]
            {
                true
            }
            #[cfg(not(all(feature = "directml", target_os = "windows")))]
            {
                false
            }
        },
        tensorrt: {
            #[cfg(feature = "tensorrt")]
            {
                true
            }
            #[cfg(not(feature = "tensorrt"))]
            {
                false
            }
        },
    });

    match kind {
        DeviceKind::Cpu => true,
        DeviceKind::Cuda => avail.cuda,
        DeviceKind::CoreML => avail.coreml,
        DeviceKind::DirectML => avail.directml,
        DeviceKind::TensorRT => avail.tensorrt,
    }
}

/// Get the recommended device for this platform.
///
/// This is equivalent to [`DeviceSelection::auto()`] but returned as a
/// standalone function for convenience.
pub fn recommended_device() -> DeviceSelection {
    DeviceSelection::auto()
}

// ---------------------------------------------------------------------------
// Bridge to gpu::DeviceType
// ---------------------------------------------------------------------------

/// Convert a high-level [`DeviceSelection`] into the low-level
/// [`crate::gpu::DeviceType`] used by the ONNX Runtime session builder.
impl From<DeviceSelection> for crate::gpu::DeviceType {
    fn from(sel: DeviceSelection) -> Self {
        match sel.kind {
            DeviceKind::Cpu => crate::gpu::DeviceType::Cpu,
            DeviceKind::Cuda => crate::gpu::DeviceType::Cuda {
                device_id: sel.device_id,
            },
            DeviceKind::CoreML => crate::gpu::DeviceType::CoreML,
            DeviceKind::DirectML => crate::gpu::DeviceType::DirectML {
                device_id: sel.device_id,
            },
            DeviceKind::TensorRT => crate::gpu::DeviceType::TensorRT {
                device_id: sel.device_id,
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- DeviceSelection -> gpu::DeviceType conversion ---

    #[test]
    fn test_from_device_selection_cpu() {
        let sel = DeviceSelection::cpu();
        let dt: crate::gpu::DeviceType = sel.into();
        assert_eq!(dt, crate::gpu::DeviceType::Cpu);
    }

    #[test]
    fn test_from_device_selection_cuda() {
        let sel = DeviceSelection::cuda(2);
        let dt: crate::gpu::DeviceType = sel.into();
        assert_eq!(dt, crate::gpu::DeviceType::Cuda { device_id: 2 });
    }

    #[test]
    fn test_from_device_selection_coreml() {
        let sel = DeviceSelection::coreml();
        let dt: crate::gpu::DeviceType = sel.into();
        assert_eq!(dt, crate::gpu::DeviceType::CoreML);
    }

    #[test]
    fn test_from_device_selection_directml() {
        let sel = DeviceSelection::directml(1);
        let dt: crate::gpu::DeviceType = sel.into();
        assert_eq!(dt, crate::gpu::DeviceType::DirectML { device_id: 1 });
    }

    #[test]
    fn test_from_device_selection_tensorrt() {
        let sel = DeviceSelection {
            kind: DeviceKind::TensorRT,
            device_id: 0,
        };
        let dt: crate::gpu::DeviceType = sel.into();
        assert_eq!(dt, crate::gpu::DeviceType::TensorRT { device_id: 0 });
    }

    // --- DeviceSelection::from_str ---

    #[test]
    fn test_from_str_cpu() {
        let sel = DeviceSelection::from_str("cpu").unwrap();
        assert_eq!(sel.kind, DeviceKind::Cpu);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_from_str_cuda_default() {
        let sel = DeviceSelection::from_str("cuda").unwrap();
        assert_eq!(sel.kind, DeviceKind::Cuda);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_from_str_cuda_with_id() {
        let sel = DeviceSelection::from_str("cuda:1").unwrap();
        assert_eq!(sel.kind, DeviceKind::Cuda);
        assert_eq!(sel.device_id, 1);
    }

    #[test]
    fn test_from_str_cuda_zero() {
        let sel = DeviceSelection::from_str("cuda:0").unwrap();
        assert_eq!(sel.kind, DeviceKind::Cuda);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_from_str_coreml() {
        let sel = DeviceSelection::from_str("coreml").unwrap();
        assert_eq!(sel.kind, DeviceKind::CoreML);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_from_str_directml() {
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
    fn test_from_str_tensorrt() {
        let sel = DeviceSelection::from_str("tensorrt").unwrap();
        assert_eq!(sel.kind, DeviceKind::TensorRT);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_from_str_auto() {
        let sel = DeviceSelection::from_str("auto").unwrap();
        // auto always returns a valid device; on any platform CPU is the fallback
        assert!(
            sel.kind == DeviceKind::Cpu
                || sel.kind == DeviceKind::Cuda
                || sel.kind == DeviceKind::CoreML
                || sel.kind == DeviceKind::DirectML
        );
    }

    #[test]
    fn test_from_str_case_insensitive() {
        let sel = DeviceSelection::from_str("CUDA").unwrap();
        assert_eq!(sel.kind, DeviceKind::Cuda);
        assert_eq!(sel.device_id, 0);

        let sel2 = DeviceSelection::from_str("Cuda:1").unwrap();
        assert_eq!(sel2.kind, DeviceKind::Cuda);
        assert_eq!(sel2.device_id, 1);

        let sel3 = DeviceSelection::from_str("CPU").unwrap();
        assert_eq!(sel3.kind, DeviceKind::Cpu);

        let sel4 = DeviceSelection::from_str("CoreML").unwrap();
        assert_eq!(sel4.kind, DeviceKind::CoreML);
    }

    // --- Error cases ---

    #[test]
    fn test_from_str_invalid() {
        let err = DeviceSelection::from_str("invalid");
        assert!(err.is_err());
    }

    #[test]
    fn test_from_str_gpu_unknown() {
        let err = DeviceSelection::from_str("gpu");
        assert!(err.is_err());
    }

    #[test]
    fn test_from_str_empty() {
        let err = DeviceSelection::from_str("");
        assert!(err.is_err());
    }

    #[test]
    fn test_from_str_bad_device_id() {
        let err = DeviceSelection::from_str("cuda:abc");
        assert!(err.is_err());
    }

    // --- Constructors ---

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

    // --- DeviceKind Display ---

    #[test]
    fn test_device_kind_display() {
        assert_eq!(DeviceKind::Cpu.to_string(), "cpu");
        assert_eq!(DeviceKind::Cuda.to_string(), "cuda");
        assert_eq!(DeviceKind::CoreML.to_string(), "coreml");
        assert_eq!(DeviceKind::DirectML.to_string(), "directml");
        assert_eq!(DeviceKind::TensorRT.to_string(), "tensorrt");
    }

    // --- DeviceInfo Display ---

    #[test]
    fn test_device_info_display_cpu() {
        let info = DeviceInfo {
            kind: DeviceKind::Cpu,
            device_id: 0,
            name: "CPU".to_string(),
            available: true,
            memory_bytes: None,
        };
        let s = info.to_string();
        assert_eq!(s, "cpu (CPU) [available]");
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
        let s = info.to_string();
        assert_eq!(s, "cuda:0 (NVIDIA GeForce RTX 3090, 24GB) [available]");
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
        let s = info.to_string();
        assert_eq!(s, "cuda:1 (CUDA Device 1) [unavailable]");
    }

    // --- enumerate_devices ---

    #[test]
    fn test_enumerate_devices_always_includes_cpu() {
        let devices = enumerate_devices();
        assert!(!devices.is_empty());
        assert!(devices.iter().any(|d| d.kind == DeviceKind::Cpu));
        // CPU must be available
        let cpu = devices.iter().find(|d| d.kind == DeviceKind::Cpu).unwrap();
        assert!(cpu.available);
    }

    // --- is_device_available ---

    #[test]
    fn test_cpu_always_available() {
        assert!(is_device_available(&DeviceKind::Cpu));
    }

    // --- auto / recommended ---

    #[test]
    fn test_auto_returns_valid_device() {
        let sel = DeviceSelection::auto();
        // Must be one of the known device kinds
        assert!(
            sel.kind == DeviceKind::Cpu
                || sel.kind == DeviceKind::Cuda
                || sel.kind == DeviceKind::CoreML
                || sel.kind == DeviceKind::DirectML
        );
        assert!(sel.device_id >= 0);
    }

    #[test]
    fn test_recommended_device_returns_valid() {
        let sel = recommended_device();
        assert!(
            sel.kind == DeviceKind::Cpu
                || sel.kind == DeviceKind::Cuda
                || sel.kind == DeviceKind::CoreML
                || sel.kind == DeviceKind::DirectML
        );
        assert!(sel.device_id >= 0);
    }

    // --- DeviceSelection Display ---

    #[test]
    fn test_device_selection_display_cpu() {
        let sel = DeviceSelection::cpu();
        assert_eq!(sel.to_string(), "cpu");
    }

    #[test]
    fn test_device_selection_display_cuda() {
        let sel = DeviceSelection::cuda(1);
        assert_eq!(sel.to_string(), "cuda:1");
    }

    // --- DeviceKind equality / Hash ---

    #[test]
    fn test_device_kind_eq_and_hash() {
        use std::collections::HashSet;
        let mut set = HashSet::new();
        set.insert(DeviceKind::Cpu);
        set.insert(DeviceKind::Cuda);
        set.insert(DeviceKind::Cpu); // duplicate
        assert_eq!(set.len(), 2);
        assert!(set.contains(&DeviceKind::Cpu));
        assert!(set.contains(&DeviceKind::Cuda));
        assert!(!set.contains(&DeviceKind::CoreML));
    }

    // -----------------------------------------------------------------------
    // Additional TDD tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_device_selection_from_str_negative_id() {
        // "cuda:-1" must be rejected -- negative device IDs are not allowed.
        let result = DeviceSelection::from_str("cuda:-1");
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(
            err_msg.contains("negative device ID"),
            "error should mention negative device ID, got: {err_msg}"
        );
    }

    #[test]
    fn test_device_selection_from_str_cpu_with_id_rejected() {
        // "cpu:1" must be rejected -- cpu does not accept a device ID.
        let result = DeviceSelection::from_str("cpu:1");
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(
            err_msg.contains("cpu does not accept a device ID"),
            "error should mention cpu device ID, got: {err_msg}"
        );
    }

    #[test]
    fn test_device_selection_from_str_cpu_zero_ok() {
        // "cpu:0" is accepted (equivalent to bare "cpu").
        let sel = DeviceSelection::from_str("cpu:0").unwrap();
        assert_eq!(sel.kind, DeviceKind::Cpu);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_device_selection_from_str_coreml_with_id_rejected() {
        // "coreml:1" must be rejected -- coreml does not accept a device ID.
        let result = DeviceSelection::from_str("coreml:1");
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(
            err_msg.contains("coreml does not accept a device ID"),
            "error should mention coreml device ID, got: {err_msg}"
        );
    }

    #[test]
    fn test_device_selection_from_str_coreml_zero_ok() {
        // "coreml:0" is accepted (equivalent to bare "coreml").
        let sel = DeviceSelection::from_str("coreml:0").unwrap();
        assert_eq!(sel.kind, DeviceKind::CoreML);
        assert_eq!(sel.device_id, 0);
    }

    #[test]
    fn test_device_selection_display_roundtrip() {
        // Display then parse back should produce the same value.
        let cases = vec![
            DeviceSelection::cpu(),
            DeviceSelection::cuda(0),
            DeviceSelection::cuda(3),
            DeviceSelection::coreml(),
            DeviceSelection::directml(0),
            DeviceSelection::directml(2),
        ];
        for sel in cases {
            let displayed = sel.to_string();
            let parsed = DeviceSelection::from_str(&displayed).unwrap();
            assert_eq!(
                parsed.kind, sel.kind,
                "roundtrip kind failed for '{displayed}'"
            );
            assert_eq!(
                parsed.device_id, sel.device_id,
                "roundtrip id failed for '{displayed}'"
            );
        }
    }

    #[test]
    fn test_enumerate_devices_no_duplicates() {
        let devices = enumerate_devices();
        let mut seen_kinds: Vec<DeviceKind> = Vec::new();
        for d in devices {
            assert!(
                !seen_kinds.contains(&d.kind),
                "duplicate device kind: {:?}",
                d.kind
            );
            seen_kinds.push(d.kind.clone());
        }
    }

    #[test]
    fn test_device_info_memory_display_large() {
        // 80 GB VRAM (A100-class) -- verify no overflow in display formatting
        let memory: u64 = 80 * 1024 * 1024 * 1024;
        let info = DeviceInfo {
            kind: DeviceKind::Cuda,
            device_id: 0,
            name: "NVIDIA A100".to_string(),
            available: true,
            memory_bytes: Some(memory),
        };
        let s = info.to_string();
        assert!(s.contains("80GB"), "expected '80GB' in: {s}");
        assert!(s.contains("[available]"));
        assert!(s.contains("cuda:0"));
    }
}
