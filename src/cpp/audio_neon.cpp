#include "audio_neon.hpp"

#ifdef USE_ARM64_NEON

#include <arm_neon.h>
#include <algorithm>
#include <cmath>

namespace piper {

float findMaxAudioValueNEON(const float* audio, size_t audioCount) {
    float32x4_t vmax = vdupq_n_f32(0.01f);
    size_t i = 0;
    
    // Process 4 elements at a time
    for (; i + 3 < audioCount; i += 4) {
        float32x4_t vdata = vld1q_f32(audio + i);
        float32x4_t vabs = vabsq_f32(vdata);
        vmax = vmaxq_f32(vmax, vabs);
    }
    
    // Reduce to single value
    float32x2_t vmax_2 = vmax_f32(vget_low_f32(vmax), vget_high_f32(vmax));
    float32x2_t vmax_1 = vpmax_f32(vmax_2, vmax_2);
    float maxValue = vget_lane_f32(vmax_1, 0);
    
    // Handle remaining elements
    for (; i < audioCount; i++) {
        maxValue = std::max(maxValue, std::abs(audio[i]));
    }
    
    return maxValue;
}

void scaleAndConvertAudioNEON(const float* audio, int16_t* output, 
                               size_t audioCount, float audioScale) {
    const float32x4_t vscale = vdupq_n_f32(audioScale);
    const float32x4_t vmin = vdupq_n_f32(static_cast<float>(INT16_MIN));
    const float32x4_t vmax = vdupq_n_f32(static_cast<float>(INT16_MAX));
    
    size_t i = 0;
    
    // Process 8 samples at a time
    for (; i + 7 < audioCount; i += 8) {
        // Load and scale first 4 samples
        float32x4_t v1 = vld1q_f32(audio + i);
        v1 = vmulq_f32(v1, vscale);
        v1 = vminq_f32(vmaxq_f32(v1, vmin), vmax);
        
        // Load and scale next 4 samples
        float32x4_t v2 = vld1q_f32(audio + i + 4);
        v2 = vmulq_f32(v2, vscale);
        v2 = vminq_f32(vmaxq_f32(v2, vmin), vmax);
        
        // Convert to int32
        int32x4_t i1 = vcvtq_s32_f32(v1);
        int32x4_t i2 = vcvtq_s32_f32(v2);
        
        // Pack to int16
        int16x4_t s1 = vqmovn_s32(i1);
        int16x4_t s2 = vqmovn_s32(i2);
        int16x8_t result = vcombine_s16(s1, s2);
        
        // Store
        vst1q_s16(output + i, result);
    }
    
    // Handle remaining samples with 4 at a time
    for (; i + 3 < audioCount; i += 4) {
        float32x4_t v = vld1q_f32(audio + i);
        v = vmulq_f32(v, vscale);
        v = vminq_f32(vmaxq_f32(v, vmin), vmax);
        
        int32x4_t vi = vcvtq_s32_f32(v);
        int16x4_t vs = vqmovn_s32(vi);
        
        vst1_s16(output + i, vs);
    }
    
    // Handle final remaining samples
    for (; i < audioCount; i++) {
        output[i] = static_cast<int16_t>(
            std::clamp(audio[i] * audioScale,
                      static_cast<float>(INT16_MIN),
                      static_cast<float>(INT16_MAX)));
    }
}

} // namespace piper

#endif // USE_ARM64_NEON