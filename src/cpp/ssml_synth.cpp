#include "ssml_synth.hpp"

#include <exception>

#include <spdlog/spdlog.h>

#include "ssml.hpp"

namespace piper {

void synthesizeSsmlToBuffer(const std::string &ssmlText, PiperConfig &config,
                            Voice &voice, SynthesisResult &result,
                            std::vector<int16_t> &audioBuffer) {
  auto segments = piper::ssml::parse(ssmlText);
  spdlog::info("SSML: parsed {} segment(s)", segments.size());

  const float originalLengthScale = voice.synthesisConfig.lengthScale;
  const int sampleRate = voice.synthesisConfig.sampleRate;

  for (std::size_t segIdx = 0; segIdx < segments.size(); ++segIdx) {
    const auto &seg = segments[segIdx];

    if (!seg.text.empty()) {
      voice.synthesisConfig.lengthScale = originalLengthScale * seg.rate;
      std::vector<int16_t> segAudio;
      SynthesisResult segResult;
      try {
        // The audioCallback MUST be null here. textToAudio clears the output
        // buffer after every sentence when a callback is installed, on the
        // contract that the callback has already copied the samples out. A
        // do-nothing lambda satisfies the `if (audioCallback)` test without
        // copying anything, so segAudio came back empty and this whole path
        // emitted silence (issue #659).
        textToAudio(config, voice, seg.text, segAudio, segResult,
                    nullptr /* audioCallback */, nullptr);
      } catch (const std::exception &e) {
        spdlog::warn("SSML segment {} synthesis failed: {}", segIdx, e.what());
        voice.synthesisConfig.lengthScale = originalLengthScale;
        continue;
      }
      audioBuffer.insert(audioBuffer.end(), segAudio.begin(), segAudio.end());
      result.inferSeconds += segResult.inferSeconds;
      // Measure the segment as the samples it actually contributed rather
      // than trusting segResult.audioSeconds, which the trim branches of
      // synthesize() re-assign from the whole accumulated buffer (issue
      // #654). For a single-phrase segment the two agree; for a segment
      // holding several sentences they do not.
      result.audioSeconds += static_cast<double>(segAudio.size()) /
                             static_cast<double>(sampleRate);
    }

    if (seg.breakMs > 0) {
      const std::size_t silenceSamples =
          static_cast<std::size_t>((static_cast<double>(seg.breakMs) / 1000.0) *
                                   static_cast<double>(sampleRate));
      audioBuffer.insert(audioBuffer.end(), silenceSamples, int16_t{0});
      result.audioSeconds +=
          static_cast<double>(silenceSamples) / static_cast<double>(sampleRate);
    }
  }

  voice.synthesisConfig.lengthScale = originalLengthScale;
  result.realTimeFactor = (result.audioSeconds > 0.0)
                              ? (result.inferSeconds / result.audioSeconds)
                              : 0.0;
}

} // namespace piper
