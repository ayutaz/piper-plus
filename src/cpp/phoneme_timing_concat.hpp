// Phoneme-timing concatenation helper (issue #652).
//
// When one text->audio call performs more than one `synthesize()` inference
// (inline `[[ ]]` phoneme notation, `phonemeSilenceSeconds` phrase splits,
// streaming sentence/chunk loops), every inference reports phoneme timings
// that start at 0. The aggregating function must shift each unit's entries by
// the amount of audio it has already emitted before concatenating them, so a
// timing value stays a position in the stream the caller actually receives.
//
// The offset is measured as output-buffer growth by the caller. It is
// deliberately NOT taken from:
//   - `SynthesisResult::audioSeconds`, which the trim branches re-assign from
//     the WHOLE accumulated buffer rather than from the unit just produced
//     (piper.cpp:1457-1461 / :1470-1474; measured 1.53x over on a 3-unit
//     utterance) -- issue #654;
//   - a sum over the ONNX `durations` tensor, which is exported pre-`ceil` and
//     therefore runs 0.55-0.83x of the real audio length -- issue #653.
//
// `channels` sits in both divisors because the aggregators compute their
// silence padding in interleaved samples (`seconds * sampleRate * channels`,
// piper.cpp:1941-1944 / :2019-2029), so the cursor counts interleaved samples
// too. `channels` is hard-wired to 1 today, which makes the factor a no-op,
// but keeping it here means the cursor stays correct if that ever changes.
//
// Frame fields truncate, so they can drift by up to one frame per silence gap.
// The millisecond/second fields are canonical across unit boundaries.
//
// stdlib-only on purpose: piper.hpp pulls in <onnxruntime_cxx_api.h>, so a
// model-free unit test cannot include it. Templating on the entry type lets
// piper.cpp instantiate this for `piper::PhonemeInfo` while the test
// instantiates it for a stand-in struct with the same five fields.

#ifndef PIPER_PLUS_PHONEME_TIMING_CONCAT_HPP
#define PIPER_PLUS_PHONEME_TIMING_CONCAT_HPP

#include <algorithm>
#include <cstddef>
#include <utility>
#include <vector>

namespace piper_plus {
namespace timing {

// Position, in interleaved PCM samples, that the next unit's timings must be
// shifted by. `samples` is the number of samples the aggregating function has
// already emitted into the caller's stream (unit audio + inter-unit silence).
struct ConcatCursor {
    std::size_t samples = 0;
    int sampleRate = 22050;
    int channels = 1;
    int hopSize = 256;

    // Cursor position in seconds. Returns 0.0 for a non-positive divisor
    // instead of dividing.
    double seconds() const {
        const int frameRate = sampleRate * std::max(1, channels);
        if (frameRate <= 0) {
            return 0.0;
        }
        return static_cast<double>(samples) / static_cast<double>(frameRate);
    }

    // Cursor position in decoder frames. Returns 0 for a non-positive divisor
    // instead of dividing.
    std::size_t frames() const {
        const int samplesPerFrame = hopSize * std::max(1, channels);
        if (samplesPerFrame <= 0) {
            return 0;
        }
        return samples / static_cast<std::size_t>(samplesPerFrame);
    }
};

// Append `unit`'s entries to `out`, shifting each one by `cursor`. A zero
// cursor is the identity, so single-unit output is bit-identical to an
// unshifted copy.
template <typename Entry>
void appendShifted(
    std::vector<Entry> &out,
    const std::vector<Entry> &unit,
    const ConcatCursor &cursor) {
    if (unit.empty()) {
        return;
    }

    const float offsetSeconds = static_cast<float>(cursor.seconds());
    const int offsetFrames = static_cast<int>(cursor.frames());

    // Grow geometrically. `reserve` allocates exactly what is asked for, so
    // reserving the precise total on every unit reallocates and copy-constructs
    // all previously accumulated entries each time -- quadratic across many
    // units. Only ask when the current capacity is short, and then at least
    // double it so vector's usual amortisation is preserved.
    const std::size_t needed = out.size() + unit.size();
    if (out.capacity() < needed) {
        out.reserve(std::max(needed, out.capacity() * 2));
    }
    for (const Entry &entry : unit) {
        Entry shifted = entry;
        shifted.start_time += offsetSeconds;
        shifted.end_time += offsetSeconds;
        shifted.start_frame += offsetFrames;
        shifted.end_frame += offsetFrames;
        out.push_back(std::move(shifted));
    }
}

} // namespace timing
} // namespace piper_plus

#endif // PIPER_PLUS_PHONEME_TIMING_CONCAT_HPP
