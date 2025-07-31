# License Compliance Documentation

## Overview

This document explains how the Piper CLI enhancements were implemented to avoid GPL-3.0 license issues while being inspired by OHF-Voice Piper features.

## Original License Context

- **OHF-Voice Piper**: GPL-3.0 License
- **Piper (rhasspy/piper)**: MIT License
- **Our Implementation**: MIT License (compatible with original Piper)

## Implementation Approach

### 1. No Code Copying

We did NOT copy any code from OHF-Voice Piper. Instead, we:

- Analyzed the **feature descriptions** from their documentation
- Designed our own implementation from scratch
- Used different implementation patterns and code structure

### 2. Feature Inspiration vs Implementation

| Feature | OHF-Voice Approach | Our Implementation |
|---------|-------------------|-------------------|
| Volume Control | Unknown internal implementation | Applied in `audio_float_to_int16()` normalization |
| Auto-play | Unknown method | Platform detection + subprocess calls |
| File Input | Unknown pattern | Generator-based with multiple file support |
| Direct Text | Unknown parsing | Positional argument with nargs="?" |

### 3. Key Differences

#### Volume Implementation
```python
# Our implementation (util.py)
def audio_float_to_int16(audio: np.ndarray, max_wav_value: float = 32767.0, volume: float = 1.0) -> np.ndarray:
    # Apply volume adjustment
    audio = audio * volume
    # Then normalize...
```

This is a straightforward mathematical approach we designed independently.

#### Auto-play Implementation
```python
# Our implementation (__main__.py)
def play_audio_file(file_path: str, sample_rate: int = 22050) -> None:
    system = platform.system()
    # Platform-specific commands...
```

We created our own platform detection and command execution logic.

#### Configuration Management
```python
# Our implementation (inference_config.py)
@dataclass
class InferenceConfig:
    # Our own design for configuration management
```

This is an original design using Python dataclasses, not copied from any source.

### 4. Clean Room Implementation

The implementation followed a "clean room" approach:

1. **Requirements Analysis**: We read only the feature descriptions and user-facing documentation
2. **Design Phase**: Created our own design without looking at OHF-Voice code
3. **Implementation**: Wrote all code from scratch
4. **Testing**: Developed our own test cases

### 5. Unique Additions

We added features not mentioned in OHF-Voice Piper:

- `InferenceConfig` dataclass for structured configuration
- Multi-file input with `--input-file` (can be used multiple times)
- Generator-based input handling for memory efficiency
- Comprehensive platform support for auto-play

## License Declaration

All code in this implementation is:

1. Written from scratch by the contributors
2. Not derived from GPL-3.0 licensed code
3. Compatible with the MIT license of the original Piper project
4. Free to be used under the same terms as rhasspy/piper

## Verification

To verify no GPL code was used:

1. Code structure is completely different
2. Variable names and function signatures are unique
3. Implementation patterns follow Python best practices, not any specific codebase
4. No GPL license headers or attributions are required

## Future Contributions

When implementing the phoneme input feature (Issue #122), we will:

1. Continue the clean room approach
2. Design our own phoneme parsing logic
3. Not reference OHF-Voice implementation details
4. Maintain MIT license compatibility

## Conclusion

This implementation demonstrates that similar features can be implemented independently without license conflicts. The features are inspired by OHF-Voice Piper's capabilities but implemented through original engineering effort.