// Layer-2 E2E cosine gate for the speaker encoder (C++ runtime).
//
// Mirrors test/test_speaker_encoder_e2e.py and the corresponding tests in
// Rust/Go/C#/WASM. See docs/spec/speaker-encoder-contract.md.
//
// Opt-in: skips by default unless both
//   1. The fixture has an e2e_cosine_gate block, AND
//   2. PIPER_SPEAKER_ENCODER_ONNX_PATH points at a local encoder ONNX.
//
// The C API speaker encoder is currently a stub (see piper_plus_c_api.cpp:1104
// "EXPERIMENTAL — not yet implemented"). This test exercises the encoder
// directly via the same algorithm the C/C++ runtime would use once wired
// up — port from src/rust/piper-core/src/speaker_encoder.rs. When the C API
// stub is replaced by a real impl, this test will continue to pass against
// the same fixture.
//
// Run: PIPER_SPEAKER_ENCODER_ONNX_PATH=/path/to/encoder.onnx
//      ctest -R test_speaker_encoder_e2e

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <vector>

#include <onnxruntime_cxx_api.h>

namespace {

// Portable π — see test_speaker_encoder_golden.cpp for rationale (MSVC's
// <cmath> does not expose M_PI without _USE_MATH_DEFINES).
constexpr float kPi = 3.14159265358979323846f;

// Reuse the mel parameters from layer 1.
constexpr int MEL_SAMPLE_RATE = 16000;
constexpr std::size_t MEL_N_FFT = 512;
constexpr std::size_t MEL_HOP_LENGTH = 160;
constexpr std::size_t MEL_N_MELS = 80;
constexpr float MEL_FMIN = 20.0f;
constexpr float MEL_FMAX = 7600.0f;

// ---------------------------------------------------------------------------
// Mel computation — port from Rust speaker_encoder.rs (see also
// test_speaker_encoder_golden.cpp which tests the same algorithm).
// ---------------------------------------------------------------------------

float hz_to_mel_e2e(float hz) {
    return 2595.0f * std::log10(1.0f + hz / 700.0f);
}

float mel_to_hz_e2e(float mel) {
    return 700.0f * (std::pow(10.0f, mel / 2595.0f) - 1.0f);
}

std::vector<float> hann_window_e2e(std::size_t length) {
    std::vector<float> w(length);
    for (std::size_t n = 0; n < length; ++n) {
        w[n] = 0.5f * (1.0f - std::cos(2.0f * kPi *
                                       static_cast<float>(n) / static_cast<float>(length)));
    }
    return w;
}

std::vector<float> create_mel_filterbank_e2e() {
    const std::size_t fft_bins = MEL_N_FFT / 2 + 1;
    std::vector<float> fb(MEL_N_MELS * fft_bins, 0.0f);

    const float mel_fmin = hz_to_mel_e2e(MEL_FMIN);
    const float mel_fmax = hz_to_mel_e2e(MEL_FMAX);

    std::vector<float> mel_points(MEL_N_MELS + 2);
    for (std::size_t i = 0; i < MEL_N_MELS + 2; ++i) {
        mel_points[i] = mel_fmin + (mel_fmax - mel_fmin) *
                                       static_cast<float>(i) /
                                       static_cast<float>(MEL_N_MELS + 1);
    }
    std::vector<float> bin_points(MEL_N_MELS + 2);
    for (std::size_t i = 0; i < MEL_N_MELS + 2; ++i) {
        bin_points[i] = mel_to_hz_e2e(mel_points[i]) *
                        static_cast<float>(MEL_N_FFT) /
                        static_cast<float>(MEL_SAMPLE_RATE);
    }

    for (std::size_t m = 0; m < MEL_N_MELS; ++m) {
        std::size_t l = static_cast<std::size_t>(std::floor(bin_points[m]));
        std::size_t c = static_cast<std::size_t>(std::floor(bin_points[m + 1]));
        std::size_t r = static_cast<std::size_t>(std::floor(bin_points[m + 2]));
        if (l == c && c == r) {
            c = std::min(c + 1, fft_bins - 1);
            r = std::min(r + 2, fft_bins - 1);
        } else if (l == c) {
            c = std::min(c + 1, fft_bins - 1);
        }
        if (c == r) r = std::min(r + 1, fft_bins - 1);

        for (std::size_t k = l; k < c; ++k) {
            if (c > l) fb[m * fft_bins + k] =
                static_cast<float>(k - l) / static_cast<float>(c - l);
        }
        for (std::size_t k = c; k < r; ++k) {
            if (r > c) fb[m * fft_bins + k] =
                static_cast<float>(r - k) / static_cast<float>(r - c);
        }
        if (c < fft_bins) fb[m * fft_bins + c] =
            std::max(fb[m * fft_bins + c], 1.0f);
    }
    return fb;
}

std::vector<float> compute_mel_spectrogram_e2e(const std::vector<float>& samples) {
    const std::size_t fft_bins = MEL_N_FFT / 2 + 1;
    const auto fb = create_mel_filterbank_e2e();
    const auto win = hann_window_e2e(MEL_N_FFT);

    std::size_t n_frames = 0;
    if (samples.size() >= MEL_N_FFT) {
        n_frames = (samples.size() - MEL_N_FFT) / MEL_HOP_LENGTH + 1;
    }
    std::vector<float> mel(MEL_N_MELS * n_frames, 0.0f);
    std::vector<float> power(fft_bins);

    for (std::size_t f = 0; f < n_frames; ++f) {
        const std::size_t start = f * MEL_HOP_LENGTH;
        for (std::size_t k = 0; k < fft_bins; ++k) {
            float real = 0.0f, imag = 0.0f;
            const float freq = -2.0f * kPi *
                               static_cast<float>(k) / static_cast<float>(MEL_N_FFT);
            for (std::size_t n = 0; n < MEL_N_FFT; ++n) {
                float v = 0.0f;
                if (start + n < samples.size()) v = samples[start + n] * win[n];
                const float a = freq * static_cast<float>(n);
                real += v * std::cos(a);
                imag += v * std::sin(a);
            }
            power[k] = real * real + imag * imag;
        }
        for (std::size_t m = 0; m < MEL_N_MELS; ++m) {
            float energy = 0.0f;
            for (std::size_t k = 0; k < fft_bins; ++k) {
                energy += fb[m * fft_bins + k] * power[k];
            }
            mel[m * n_frames + f] = std::log(std::max(energy, 1e-10f));
        }
    }
    return mel;
}

std::vector<float> resample_linear_e2e(const std::vector<float>& src, int from, int to) {
    if (from == to || src.empty()) return src;
    const double ratio = static_cast<double>(from) / static_cast<double>(to);
    const std::size_t out_len =
        static_cast<std::size_t>(std::ceil(static_cast<double>(src.size()) / ratio));
    std::vector<float> out(out_len, 0.0f);
    for (std::size_t i = 0; i < out_len; ++i) {
        const double pos = static_cast<double>(i) * ratio;
        const std::size_t idx = static_cast<std::size_t>(pos);
        const float frac = static_cast<float>(pos - static_cast<double>(idx));
        if (idx + 1 < src.size()) out[i] = src[idx] * (1.0f - frac) + src[idx + 1] * frac;
        else if (idx < src.size()) out[i] = src[idx];
    }
    return out;
}

// ---------------------------------------------------------------------------
// Minimal mono PCM WAV reader (16-bit / 32-bit). No new dep.
// ---------------------------------------------------------------------------

struct WavData { std::vector<float> samples; int sample_rate = 0; };

WavData read_mono_wav(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) throw std::runtime_error("cannot open WAV: " + path);
    std::vector<char> buf((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
    auto u32le = [&](std::size_t off) {
        return static_cast<std::uint32_t>(static_cast<unsigned char>(buf[off])) |
               (static_cast<std::uint32_t>(static_cast<unsigned char>(buf[off + 1])) << 8) |
               (static_cast<std::uint32_t>(static_cast<unsigned char>(buf[off + 2])) << 16) |
               (static_cast<std::uint32_t>(static_cast<unsigned char>(buf[off + 3])) << 24);
    };
    auto u16le = [&](std::size_t off) {
        return static_cast<std::uint16_t>(static_cast<unsigned char>(buf[off]) |
               (static_cast<unsigned>(static_cast<unsigned char>(buf[off + 1])) << 8));
    };
    auto i16le = [&](std::size_t off) -> int16_t {
        return static_cast<int16_t>(u16le(off));
    };
    auto i32le = [&](std::size_t off) -> int32_t {
        return static_cast<int32_t>(u32le(off));
    };

    if (buf.size() < 44) throw std::runtime_error("WAV too short");
    if (std::strncmp(&buf[0], "RIFF", 4) != 0) throw std::runtime_error("not RIFF");
    if (std::strncmp(&buf[8], "WAVE", 4) != 0) throw std::runtime_error("not WAVE");

    std::size_t off = 12;
    int audio_format = 0, channels = 0, bits = 0;
    std::size_t data_off = 0, data_size = 0;
    int sample_rate = 0;
    while (off + 8 <= buf.size()) {
        std::string tag(&buf[off], 4);
        const std::uint32_t size = u32le(off + 4);
        if (tag == "fmt ") {
            audio_format = u16le(off + 8);
            channels = u16le(off + 10);
            sample_rate = static_cast<int>(u32le(off + 12));
            bits = u16le(off + 22);
        } else if (tag == "data") {
            data_off = off + 8;
            data_size = size;
            break;
        }
        off += 8 + size + (size & 1);
    }
    if (channels != 1) throw std::runtime_error("WAV must be mono");
    if (audio_format != 1) throw std::runtime_error("only PCM supported");
    if (data_off == 0) throw std::runtime_error("missing data chunk");

    WavData w;
    w.sample_rate = sample_rate;
    if (bits == 16) {
        const std::size_t n = data_size / 2;
        w.samples.resize(n);
        for (std::size_t i = 0; i < n; ++i) {
            w.samples[i] = static_cast<float>(i16le(data_off + i * 2)) / 32768.0f;
        }
    } else if (bits == 32) {
        const std::size_t n = data_size / 4;
        w.samples.resize(n);
        for (std::size_t i = 0; i < n; ++i) {
            w.samples[i] = static_cast<float>(i32le(data_off + i * 4)) / 2147483648.0f;
        }
    } else {
        throw std::runtime_error("unsupported bits per sample");
    }
    return w;
}

// ---------------------------------------------------------------------------
// JSON helpers (same minimal extractors as test_speaker_encoder_golden.cpp)
// ---------------------------------------------------------------------------

std::string load_text_e2e(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return "";
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

std::string fixture_text_e2e() {
    static const std::string s = []() {
        const std::vector<std::string> candidates = {
            "test/fixtures/speaker_encoder_golden.json",
            "../test/fixtures/speaker_encoder_golden.json",
            "../../test/fixtures/speaker_encoder_golden.json",
            "../../../test/fixtures/speaker_encoder_golden.json",
            "../../../../test/fixtures/speaker_encoder_golden.json",
        };
        for (const auto& p : candidates) {
            std::ifstream f(p);
            if (f.is_open()) return load_text_e2e(p);
        }
        return std::string{};
    }();
    return s;
}

std::string extract_value_after(const std::string& text, const std::string& key) {
    const std::string needle = "\"" + key + "\":";
    auto pos = text.find(needle);
    if (pos == std::string::npos) return {};
    pos += needle.size();
    while (pos < text.size() && std::isspace(static_cast<unsigned char>(text[pos]))) ++pos;
    if (pos >= text.size()) return {};

    if (text[pos] == '[') {
        std::size_t depth = 1, start = pos + 1, end = start;
        while (end < text.size() && depth > 0) {
            if (text[end] == '[') ++depth;
            else if (text[end] == ']') --depth;
            if (depth > 0) ++end;
        }
        return text.substr(start, end - start);
    }
    if (text[pos] == '"') {
        std::size_t end = pos + 1;
        while (end < text.size() && text[end] != '"') ++end;
        return text.substr(pos + 1, end - pos - 1);
    }
    if (text[pos] == '{') {
        std::size_t depth = 1, start = pos + 1, end = start;
        while (end < text.size() && depth > 0) {
            if (text[end] == '{') ++depth;
            else if (text[end] == '}') --depth;
            if (depth > 0) ++end;
        }
        return text.substr(start, end - start);
    }
    std::size_t end = pos;
    while (end < text.size() && text[end] != ',' && text[end] != '}' && text[end] != '\n') ++end;
    return text.substr(pos, end - pos);
}

std::vector<float> parse_float_array_e2e(const std::string& body) {
    std::vector<float> out;
    std::size_t i = 0;
    while (i < body.size()) {
        while (i < body.size() &&
               (std::isspace(static_cast<unsigned char>(body[i])) || body[i] == ',')) ++i;
        if (i >= body.size()) break;
        std::size_t j = i;
        while (j < body.size() && body[j] != ',' && !std::isspace(static_cast<unsigned char>(body[j]))) ++j;
        try {
            out.push_back(std::stof(body.substr(i, j - i)));
        } catch (...) {}
        i = j;
    }
    return out;
}

bool file_exists(const std::string& p) {
    struct stat st;
    return stat(p.c_str(), &st) == 0;
}

float cosine_e2e(const std::vector<float>& a, const std::vector<float>& b) {
    double dot = 0, na = 0, nb = 0;
    for (std::size_t i = 0; i < a.size() && i < b.size(); ++i) {
        dot += static_cast<double>(a[i]) * static_cast<double>(b[i]);
        na += static_cast<double>(a[i]) * static_cast<double>(a[i]);
        nb += static_cast<double>(b[i]) * static_cast<double>(b[i]);
    }
    if (na == 0 || nb == 0) return 0.0f;
    return static_cast<float>(dot / (std::sqrt(na) * std::sqrt(nb)));
}

}  // namespace

// ===========================================================================
// Test
// ===========================================================================

TEST(SpeakerEncoderE2E, CosineGateAgainstPinnedEmbedding) {
    const std::string text = fixture_text_e2e();
    if (text.empty()) GTEST_SKIP() << "fixture not loadable from test CWD";

    auto gate_block = extract_value_after(text, "e2e_cosine_gate");
    if (gate_block.empty()) {
        GTEST_SKIP() << "fixture has no e2e_cosine_gate block — generator was "
                        "run without --encoder-onnx; layer-1 mel parity tests "
                        "still apply";
    }
    const std::string gate = "{" + gate_block + "}";

    const char* env_path = std::getenv("PIPER_SPEAKER_ENCODER_ONNX_PATH");
    if (!env_path || env_path[0] == '\0') {
        GTEST_SKIP() << "PIPER_SPEAKER_ENCODER_ONNX_PATH not set — opt-in test";
    }
    const std::string encoder_path = env_path;
    if (!file_exists(encoder_path)) {
        FAIL() << "PIPER_SPEAKER_ENCODER_ONNX_PATH=" << encoder_path << " does not exist";
    }

    auto wav_block = extract_value_after(gate, "reference_wav");
    auto wav_path_extracted = extract_value_after("{" + wav_block + "}", "path");
    std::string wav_path = wav_path_extracted;
    if (wav_path.empty()) GTEST_SKIP() << "reference_wav.path missing";
    if (!wav_path.empty() && wav_path[0] != '/') {
        // Resolve relative to the same parent the fixture used.
        const std::vector<std::string> roots = {"./", "../", "../../", "../../../", "../../../../"};
        for (const auto& r : roots) {
            if (file_exists(r + wav_path)) { wav_path = r + wav_path; break; }
        }
    }
    if (!file_exists(wav_path)) GTEST_SKIP() << "reference WAV not found at " << wav_path;

    auto threshold_str = extract_value_after(gate, "cosine_threshold");
    float cosine_threshold = 0.999f;
    try { cosine_threshold = std::stof(threshold_str); } catch (...) {}

    auto expected_block = extract_value_after(gate, "expected_embedding");
    auto expected_values = parse_float_array_e2e(
        extract_value_after("{" + expected_block + "}", "values"));
    ASSERT_FALSE(expected_values.empty()) << "expected_embedding.values missing or empty";

    // Load WAV, resample, compute mel.
    WavData wav = read_mono_wav(wav_path);
    auto resampled = (wav.sample_rate != MEL_SAMPLE_RATE)
        ? resample_linear_e2e(wav.samples, wav.sample_rate, MEL_SAMPLE_RATE)
        : wav.samples;
    auto mel = compute_mel_spectrogram_e2e(resampled);
    const std::size_t n_frames = mel.size() / MEL_N_MELS;

    // ONNX inference.
    Ort::Env env(OrtLoggingLevel::ORT_LOGGING_LEVEL_WARNING, "speaker_encoder_e2e");
    Ort::SessionOptions opts;
    opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    opts.SetIntraOpNumThreads(2);

    Ort::Session session(env, encoder_path.c_str(), opts);

    Ort::AllocatorWithDefaultOptions alloc;
    const auto input_name_ptr = session.GetInputNameAllocated(0, alloc);
    const auto output_name_ptr = session.GetOutputNameAllocated(0, alloc);
    const std::vector<const char*> input_names{input_name_ptr.get()};
    const std::vector<const char*> output_names{output_name_ptr.get()};

    // Default layout: [1, N_MELS, T]. If model expects [1, T, N_MELS],
    // transpose. (Read input shape metadata.)
    Ort::TypeInfo input_info = session.GetInputTypeInfo(0);
    auto input_shape = input_info.GetTensorTypeAndShapeInfo().GetShape();

    std::vector<int64_t> shape;
    std::vector<float> tensor_data;
    if (input_shape.size() == 3 && input_shape[1] == static_cast<int64_t>(MEL_N_MELS)) {
        shape = {1, static_cast<int64_t>(MEL_N_MELS), static_cast<int64_t>(n_frames)};
        tensor_data = mel;
    } else if (input_shape.size() == 3 && input_shape[2] == static_cast<int64_t>(MEL_N_MELS)) {
        // Transpose mel from [N_MELS, T] (mel-major) to [T, N_MELS].
        tensor_data.resize(MEL_N_MELS * n_frames);
        for (std::size_t m = 0; m < MEL_N_MELS; ++m) {
            for (std::size_t t = 0; t < n_frames; ++t) {
                tensor_data[t * MEL_N_MELS + m] = mel[m * n_frames + t];
            }
        }
        shape = {1, static_cast<int64_t>(n_frames), static_cast<int64_t>(MEL_N_MELS)};
    } else {
        // Fall back to [1, N_MELS, T].
        shape = {1, static_cast<int64_t>(MEL_N_MELS), static_cast<int64_t>(n_frames)};
        tensor_data = mel;
    }

    auto memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
        memory_info, tensor_data.data(), tensor_data.size(),
        shape.data(), shape.size());

    auto outputs = session.Run(Ort::RunOptions{nullptr}, input_names.data(),
                               &input_tensor, 1, output_names.data(), 1);
    auto& out = outputs[0];
    auto out_info = out.GetTensorTypeAndShapeInfo();
    const std::size_t out_elements = out_info.GetElementCount();
    std::vector<float> actual_embedding(out_elements);
    std::memcpy(actual_embedding.data(), out.GetTensorMutableData<float>(),
                sizeof(float) * out_elements);

    ASSERT_EQ(actual_embedding.size(), expected_values.size())
        << "embedding dim drift";

    const float cos = cosine_e2e(actual_embedding, expected_values);
    EXPECT_GE(cos, cosine_threshold)
        << "cosine gate failed: cos=" << cos
        << " < threshold=" << cosine_threshold
        << " (encoder=" << encoder_path << ", wav=" << wav_path << ")";
}
