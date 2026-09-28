// The sample-count convention must be the SAME on both sides (issue #693).
//
// The CLI hands one value -- `audioBuffer.size()` -- to two consumers:
//
//   writeWavHeader(...)                        -> WAV dataSize
//   piper_plus::timing::ConcatCursor::seconds() -> timing offsets
//
// They used to read it in opposite directions. `writeWavHeader` multiplied by
// `channels`, i.e. treated the argument as a FRAME count, while ConcatCursor
// divided by `channels`, i.e. treated it as interleaved SAMPLES. With one
// value feeding both, `channels > 1` was guaranteed to break one of them:
// dataSize came out `channels` times too large.
//
// Nothing in the C++ tree sets channels above 1 today, so the contradiction
// was invisible -- which is why it needs a test that sets channels explicitly
// rather than waiting for a stereo model to arrive.
//
// Interleaved is the correct reading: the decoder's output tensor is
// interleaved for multi-channel, so buffer.size() is frames x channels.

#include <gtest/gtest.h>

#include <cstdint>
#include <sstream>
#include <string>

#include "phoneme_timing_concat.hpp"
#include "wavfile.hpp"

namespace {

// dataSize is bytes 4..8 of the `data` chunk, which sits at the end of the
// 44-byte canonical header.
uint32_t readDataSize(const std::string &header) {
  const std::size_t offset = 40;  // "data" tag at 36, size at 40
  return static_cast<uint32_t>(static_cast<unsigned char>(header[offset])) |
         (static_cast<uint32_t>(static_cast<unsigned char>(header[offset + 1])) << 8) |
         (static_cast<uint32_t>(static_cast<unsigned char>(header[offset + 2])) << 16) |
         (static_cast<uint32_t>(static_cast<unsigned char>(header[offset + 3])) << 24);
}

uint16_t readChannels(const std::string &header) {
  const std::size_t offset = 22;
  return static_cast<uint16_t>(
      static_cast<uint16_t>(static_cast<unsigned char>(header[offset])) |
      (static_cast<uint16_t>(static_cast<unsigned char>(header[offset + 1])) << 8));
}

}  // namespace

TEST(ChannelsConvention, WavDataSizeTreatsTheCountAsInterleavedSamples) {
  // 1000 interleaved samples of 16-bit stereo = 2000 bytes, regardless of how
  // those samples split into frames. Multiplying by channels would give 4000.
  std::ostringstream out;
  writeWavHeader(/*sampleRate=*/22050, /*sampleWidth=*/2,
                        /*channels=*/2, /*numInterleavedSamples=*/1000, out);
  const std::string header = out.str();
  ASSERT_GE(header.size(), 44u);

  EXPECT_EQ(readDataSize(header), 2000u)
      << "dataSize must be interleaved samples x sample width";
  EXPECT_EQ(readChannels(header), 2u);
}

TEST(ChannelsConvention, MonoIsUnchangedByTheFix) {
  // The one configuration that ships must produce exactly what it did before:
  // channels = 1 makes the two conventions agree, so this pins that the fix
  // did not move the mono case.
  std::ostringstream out;
  writeWavHeader(22050, 2, 1, 1000, out);
  EXPECT_EQ(readDataSize(out.str()), 2000u);
}

TEST(ChannelsConvention, CursorAndWavHeaderAgreeOnTheSameCount) {
  // One buffer size, two consumers. Feed both and check they describe the
  // same amount of audio.
  // 44100 interleaved samples of stereo at 22050 Hz is ONE second:
  // 44100 / (22050 x 2). Halving it would be 0.5 s -- worth spelling out,
  // since the first version of this test asserted 0.5 and the cursor was
  // right while the expectation was wrong.
  const std::size_t interleaved = 44100;
  const int sampleRate = 22050;
  const int channels = 2;
  const int sampleWidth = 2;

  piper_plus::timing::ConcatCursor cursor;
  cursor.samples = interleaved;
  cursor.sampleRate = sampleRate;
  cursor.channels = channels;

  std::ostringstream out;
  writeWavHeader(sampleRate, sampleWidth, channels,
                        static_cast<uint32_t>(interleaved), out);

  const double secondsFromCursor = cursor.seconds();
  const double secondsFromHeader =
      static_cast<double>(readDataSize(out.str())) /
      (static_cast<double>(sampleRate) * sampleWidth * channels);

  EXPECT_NEAR(secondsFromCursor, 1.0, 1e-9);
  EXPECT_NEAR(secondsFromHeader, secondsFromCursor, 1e-9)
      << "the WAV header and the timing cursor must describe the same "
         "duration for one buffer size";
}

TEST(ChannelsConvention, CursorFramesAlsoDividesByChannels) {
  // frames() is what shifts start_frame/end_frame, so it has to divide by
  // channels too -- otherwise timing frames would drift from WAV position on
  // stereo by exactly the channel count.
  piper_plus::timing::ConcatCursor cursor;
  cursor.samples = 2048;
  cursor.hopSize = 256;
  cursor.channels = 2;
  EXPECT_EQ(cursor.frames(), 4u) << "2048 interleaved / (256 hop x 2ch) = 4";

  cursor.channels = 1;
  EXPECT_EQ(cursor.frames(), 8u);
}

// Anti-vacuity: the tests above would all pass against a header writer that
// ignored `channels` entirely. This pins that the field still reaches the
// output, so "channels is not multiplied into dataSize" is not read as
// "channels is dropped".
TEST(ChannelsConventionGate, ChannelsStillReachesTheHeader) {
  for (const int channels : {1, 2, 6}) {
    std::ostringstream out;
    writeWavHeader(22050, 2, channels, 100, out);
    EXPECT_EQ(readChannels(out.str()), static_cast<uint16_t>(channels));
  }
}
