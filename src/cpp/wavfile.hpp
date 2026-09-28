#ifndef WAVFILE_H_
#define WAVFILE_H_

#include <iostream>

struct WavHeader {
  uint8_t RIFF[4] = {'R', 'I', 'F', 'F'};
  uint32_t chunkSize;
  uint8_t WAVE[4] = {'W', 'A', 'V', 'E'};

  // fmt
  uint8_t fmt[4] = {'f', 'm', 't', ' '};
  uint32_t fmtSize = 16;    // bytes
  uint16_t audioFormat = 1; // PCM
  uint16_t numChannels;     // mono
  uint32_t sampleRate;      // Hertz
  uint32_t bytesPerSec;     // sampleRate * sampleWidth
  uint16_t blockAlign = 2;  // 16-bit mono
  uint16_t bitsPerSample = 16;

  // data
  uint8_t data[4] = {'d', 'a', 't', 'a'};
  uint32_t dataSize;
};

// Write WAV file header only
// `numInterleavedSamples` counts SAMPLES, not frames: for stereo, one frame
// contributes two. That is what every caller passes -- `audioBuffer.size()`,
// where the decoder's output is interleaved -- and it is the same convention
// `piper_plus::timing::ConcatCursor` uses (`samples / (sampleRate *
// channels)`).
//
// The parameter used to be named `numSamples` and the body multiplied by
// `channels`, i.e. it read the argument as a FRAME count. The two conventions
// disagreed in opposite directions while the CLI handed the same
// `audioBuffer.size()` to both, so `channels > 1` was guaranteed to break one
// of them: `dataSize` came out `channels` times too large (issue #693).
// Harmless so far only because nothing in the C++ tree sets `channels` above
// 1 -- which is exactly why it went unnoticed rather than why it was safe.
void writeWavHeader(int sampleRate, int sampleWidth, int channels,
                    uint32_t numInterleavedSamples, std::ostream &audioFile) {
  WavHeader header;
  header.dataSize = numInterleavedSamples * sampleWidth;
  header.chunkSize = header.dataSize + sizeof(WavHeader) - 8;
  header.sampleRate = sampleRate;
  header.numChannels = channels;
  header.bytesPerSec = sampleRate * sampleWidth * channels;
  header.blockAlign = sampleWidth * channels;
  audioFile.write(reinterpret_cast<const char *>(&header), sizeof(header));

} /* writeWavHeader */

#endif // WAVFILE_H_
