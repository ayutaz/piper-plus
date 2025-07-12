#ifndef AUDIO_NEON_HPP
#define AUDIO_NEON_HPP

#include <cstdint>
#include <cstddef>

namespace piper {

#ifdef USE_ARM64_NEON

// Find maximum absolute value in audio buffer using NEON
float findMaxAudioValueNEON(const float* audio, size_t audioCount);

// Scale and convert audio from float to int16 using NEON
void scaleAndConvertAudioNEON(const float* audio, int16_t* output, 
                               size_t audioCount, float audioScale);

#endif // USE_ARM64_NEON

} // namespace piper

#endif // AUDIO_NEON_HPP