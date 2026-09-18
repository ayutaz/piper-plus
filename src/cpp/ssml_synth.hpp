// SSML segment synthesis (issue #659).
//
// Lives in its own translation unit rather than inside main.cpp so the
// SSML -> audio path can be driven from a test. The bug this file exists to
// prevent was invisible to src/cpp/tests/test_ssml.cpp, which covers only the
// parser: the parser produced correct segments while the synthesis loop
// emitted zero samples, so every SSML CLI invocation wrote a silent WAV.

#ifndef PIPER_PLUS_SSML_SYNTH_HPP
#define PIPER_PLUS_SSML_SYNTH_HPP

#include <string>
#include <vector>

#include "piper.hpp"

namespace piper {

// Parse `ssmlText` and append the synthesized audio of every segment to
// `audioBuffer`, inserting each segment's <break> silence after it and
// applying its <prosody rate> as a length-scale multiplier.
//
// `result` accumulates inferSeconds / audioSeconds across segments and gets
// realTimeFactor recomputed at the end. `voice.synthesisConfig.lengthScale`
// is restored before returning, including on the per-segment failure path.
void synthesizeSsmlToBuffer(const std::string &ssmlText, PiperConfig &config,
                            Voice &voice, SynthesisResult &result,
                            std::vector<int16_t> &audioBuffer);

} // namespace piper

#endif // PIPER_PLUS_SSML_SYNTH_HPP
