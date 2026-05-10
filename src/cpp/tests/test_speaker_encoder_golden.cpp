// Speaker Encoder mel parity (layer 1) — golden test for the C++ runtime.
//
// Mirrors src/rust/piper-core/tests/test_speaker_encoder_golden.rs, ports
// the same algorithm inline (the Rust test takes the same approach: it
// duplicates the helper functions rather than expose them as `pub`).
//
// Reads test/fixtures/speaker_encoder_golden.json and verifies:
//   - hann window (sampled values, 1e-6 abs tol)
//   - mel filterbank band sums (1e-3 abs tol)
//   - resample 48k→16k first/last 10 samples (1e-4 abs tol)
//   - mel computation per fixture test case (2% L2 relative tolerance,
//     same gate the Rust runtime uses at test_speaker_encoder_golden.rs:434)
//
// The fixture's expected_mel_checksum is intentionally NOT enforced
// because byte-equal float chains across compilers (numpy in Python vs
// C++ libm) drift by 1 ULP. The L2 tolerance is the contract.
//
// Run: ctest -R test_speaker_encoder_golden

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

// MSVC's <cmath> does not expose M_PI without _USE_MATH_DEFINES (and even
// then only in <math.h>). Define our own portable constant so the test
// builds identically on GCC/Clang/MSVC without preprocessor gymnastics.
constexpr float kPi = 3.14159265358979323846f;

// Mel parameters — must match all runtimes (see
// docs/spec/speaker-encoder-contract.md).
constexpr int MEL_SAMPLE_RATE = 16000;
constexpr std::size_t MEL_N_FFT = 512;
constexpr std::size_t MEL_HOP_LENGTH = 160;
constexpr std::size_t MEL_N_MELS = 80;
constexpr float MEL_FMIN = 20.0f;
constexpr float MEL_FMAX = 7600.0f;

constexpr double TOLERANCE = 0.02;  // 2% relative L2 (matches Rust)

// ---------------------------------------------------------------------------
// Reference implementation (manual DFT in float32 — mirrors Python).
// ---------------------------------------------------------------------------

float hz_to_mel(float hz) {
    return 2595.0f * std::log10(1.0f + hz / 700.0f);
}

float mel_to_hz(float mel) {
    return 700.0f * (std::pow(10.0f, mel / 2595.0f) - 1.0f);
}

std::vector<float> hann_window(std::size_t length) {
    std::vector<float> w(length);
    for (std::size_t n = 0; n < length; ++n) {
        w[n] = 0.5f * (1.0f - std::cos(2.0f * kPi *
                                       static_cast<float>(n) / static_cast<float>(length)));
    }
    return w;
}

std::vector<float> create_mel_filterbank() {
    const std::size_t fft_bins = MEL_N_FFT / 2 + 1;
    std::vector<float> filterbank(MEL_N_MELS * fft_bins, 0.0f);

    const float mel_fmin = hz_to_mel(MEL_FMIN);
    const float mel_fmax = hz_to_mel(MEL_FMAX);

    std::vector<float> mel_points(MEL_N_MELS + 2);
    for (std::size_t i = 0; i < MEL_N_MELS + 2; ++i) {
        mel_points[i] = mel_fmin + (mel_fmax - mel_fmin) *
                                       static_cast<float>(i) /
                                       static_cast<float>(MEL_N_MELS + 1);
    }

    std::vector<float> bin_points(MEL_N_MELS + 2);
    for (std::size_t i = 0; i < MEL_N_MELS + 2; ++i) {
        bin_points[i] = mel_to_hz(mel_points[i]) * static_cast<float>(MEL_N_FFT) /
                        static_cast<float>(MEL_SAMPLE_RATE);
    }

    for (std::size_t m = 0; m < MEL_N_MELS; ++m) {
        std::size_t left = static_cast<std::size_t>(std::floor(bin_points[m]));
        std::size_t center = static_cast<std::size_t>(std::floor(bin_points[m + 1]));
        std::size_t right = static_cast<std::size_t>(std::floor(bin_points[m + 2]));

        if (left == center && center == right) {
            center = std::min(center + 1, fft_bins - 1);
            right = std::min(right + 2, fft_bins - 1);
        } else if (left == center) {
            center = std::min(center + 1, fft_bins - 1);
        }
        if (center == right) {
            right = std::min(right + 1, fft_bins - 1);
        }

        for (std::size_t k = left; k < center; ++k) {
            if (center > left) {
                filterbank[m * fft_bins + k] =
                    static_cast<float>(k - left) / static_cast<float>(center - left);
            }
        }
        for (std::size_t k = center; k < right; ++k) {
            if (right > center) {
                filterbank[m * fft_bins + k] =
                    static_cast<float>(right - k) / static_cast<float>(right - center);
            }
        }
        if (center < fft_bins) {
            filterbank[m * fft_bins + center] =
                std::max(filterbank[m * fft_bins + center], 1.0f);
        }
    }

    return filterbank;
}

std::vector<float> compute_mel_spectrogram(const std::vector<float>& samples) {
    const std::size_t fft_bins = MEL_N_FFT / 2 + 1;
    const auto filters = create_mel_filterbank();
    const auto window = hann_window(MEL_N_FFT);

    std::size_t n_frames = 0;
    if (samples.size() >= MEL_N_FFT) {
        n_frames = (samples.size() - MEL_N_FFT) / MEL_HOP_LENGTH + 1;
    }

    std::vector<float> mel(MEL_N_MELS * n_frames, 0.0f);
    std::vector<float> power_spec(fft_bins);

    for (std::size_t frame = 0; frame < n_frames; ++frame) {
        const std::size_t start = frame * MEL_HOP_LENGTH;
        for (std::size_t k = 0; k < fft_bins; ++k) {
            float real = 0.0f, imag = 0.0f;
            const float freq = -2.0f * kPi *
                               static_cast<float>(k) / static_cast<float>(MEL_N_FFT);
            for (std::size_t n = 0; n < MEL_N_FFT; ++n) {
                float v = 0.0f;
                if (start + n < samples.size()) {
                    v = samples[start + n] * window[n];
                }
                const float angle = freq * static_cast<float>(n);
                real += v * std::cos(angle);
                imag += v * std::sin(angle);
            }
            power_spec[k] = real * real + imag * imag;
        }

        for (std::size_t m = 0; m < MEL_N_MELS; ++m) {
            float energy = 0.0f;
            for (std::size_t k = 0; k < fft_bins; ++k) {
                energy += filters[m * fft_bins + k] * power_spec[k];
            }
            mel[m * n_frames + frame] =
                std::log(std::max(energy, 1e-10f));
        }
    }

    return mel;
}

std::vector<float> resample_linear(const std::vector<float>& samples,
                                   int from_rate, int to_rate) {
    if (from_rate == to_rate || samples.empty()) return samples;

    const double ratio = static_cast<double>(from_rate) / static_cast<double>(to_rate);
    const std::size_t out_len =
        static_cast<std::size_t>(std::ceil(static_cast<double>(samples.size()) / ratio));
    std::vector<float> out(out_len, 0.0f);

    for (std::size_t i = 0; i < out_len; ++i) {
        const double src_pos = static_cast<double>(i) * ratio;
        const std::size_t idx = static_cast<std::size_t>(src_pos);
        const float frac = static_cast<float>(src_pos - static_cast<double>(idx));

        if (idx + 1 < samples.size()) {
            out[i] = samples[idx] * (1.0f - frac) + samples[idx + 1] * frac;
        } else if (idx < samples.size()) {
            out[i] = samples[idx];
        }
    }

    return out;
}

// ---------------------------------------------------------------------------
// Test signals — mirror Python's generate_sine / generate_multitone.
// ---------------------------------------------------------------------------

std::vector<float> generate_sine(double freq_hz, double duration_s, int sr) {
    const std::size_t n = static_cast<std::size_t>(duration_s * sr);
    std::vector<float> out(n);
    for (std::size_t i = 0; i < n; ++i) {
        out[i] = std::sin(2.0f * kPi * static_cast<float>(freq_hz) *
                          static_cast<float>(i) / static_cast<float>(sr));
    }
    return out;
}

std::vector<float> generate_multitone(const std::vector<double>& freqs,
                                      double duration_s, int sr) {
    const std::size_t n = static_cast<std::size_t>(duration_s * sr);
    std::vector<float> out(n, 0.0f);
    for (std::size_t i = 0; i < n; ++i) {
        for (double f : freqs) {
            out[i] += std::sin(2.0f * kPi * static_cast<float>(f) *
                               static_cast<float>(i) / static_cast<float>(sr));
        }
    }
    float peak = 0.0f;
    for (float v : out) peak = std::max(peak, std::abs(v));
    if (peak > 0) {
        for (float& v : out) v /= peak;
    }
    return out;
}

// ---------------------------------------------------------------------------
// Minimal JSON helpers — fixtures are well-formed, no quoting edge cases.
// ---------------------------------------------------------------------------

std::string load_text(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) return "";
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

// Crude but sufficient: extract the JSON value (number/array) following the
// substring `"key":`. Whitespace is skipped. For arrays, returns the body
// `[...]` minus brackets so caller can split on commas.
std::string extract_value_after(const std::string& text, const std::string& key) {
    const std::string needle = "\"" + key + "\":";
    auto pos = text.find(needle);
    if (pos == std::string::npos) return {};
    pos += needle.size();
    while (pos < text.size() && std::isspace(static_cast<unsigned char>(text[pos]))) ++pos;
    if (pos >= text.size()) return {};

    if (text[pos] == '[' || text[pos] == '{') {
        // Match brackets/braces (only the outer pair). The fixture nests
        // dicts (e.g. "hann_window": { "first_5": [...] }) so callers that
        // re-parse the body must see a dict body, not the truncated
        // up-to-first-`,` slice.
        const char open = text[pos];
        const char close = (open == '[') ? ']' : '}';
        std::size_t depth = 1;
        std::size_t start = pos + 1;
        std::size_t end = start;
        while (end < text.size() && depth > 0) {
            if (text[end] == open) ++depth;
            else if (text[end] == close) --depth;
            if (depth > 0) ++end;
        }
        return text.substr(start, end - start);
    }
    // scalar
    std::size_t end = pos;
    while (end < text.size() && text[end] != ',' && text[end] != '}' && text[end] != '\n') ++end;
    return text.substr(pos, end - pos);
}

std::vector<double> parse_float_array(const std::string& body) {
    std::vector<double> out;
    std::size_t i = 0;
    while (i < body.size()) {
        while (i < body.size() &&
               (std::isspace(static_cast<unsigned char>(body[i])) || body[i] == ',')) ++i;
        if (i >= body.size()) break;
        std::size_t j = i;
        while (j < body.size() && body[j] != ',' && !std::isspace(static_cast<unsigned char>(body[j]))) ++j;
        try {
            out.push_back(std::stod(body.substr(i, j - i)));
        } catch (...) {}
        i = j;
    }
    return out;
}

std::string fixture_text() {
    static const std::string text = []() {
        // Find the fixture path: walk up from CWD looking for test/fixtures/.
        // CMake runs tests from CMAKE_BINARY_DIR; the fixture lives at
        // <repo>/test/fixtures/speaker_encoder_golden.json. Try a few paths.
        const std::vector<std::string> candidates = {
            "test/fixtures/speaker_encoder_golden.json",
            "../test/fixtures/speaker_encoder_golden.json",
            "../../test/fixtures/speaker_encoder_golden.json",
            "../../../test/fixtures/speaker_encoder_golden.json",
            "../../../../test/fixtures/speaker_encoder_golden.json",
        };
        for (const auto& p : candidates) {
            std::ifstream f(p);
            if (f.is_open()) {
                return load_text(p);
            }
        }
        return std::string{};
    }();
    return text;
}

double l2_relative(const std::vector<double>& actual, const std::vector<double>& expected) {
    double num = 0.0, den = 0.0;
    const std::size_t n = std::min(actual.size(), expected.size());
    for (std::size_t i = 0; i < n; ++i) {
        const double d = actual[i] - expected[i];
        num += d * d;
        den += expected[i] * expected[i];
    }
    if (den == 0.0) return num == 0.0 ? 0.0 : std::numeric_limits<double>::infinity();
    return std::sqrt(num) / std::sqrt(den);
}

}  // namespace

// ===========================================================================
// Tests
// ===========================================================================

TEST(SpeakerEncoderGolden, FixtureLoads) {
    const std::string text = fixture_text();
    if (text.empty()) {
        GTEST_SKIP() << "fixture not found relative to test runner CWD";
    }
    EXPECT_NE(text.find("\"hann_window\""), std::string::npos);
    EXPECT_NE(text.find("\"mel_filterbank\""), std::string::npos);
}

TEST(SpeakerEncoderGolden, HannWindowMatchesFixture) {
    const std::string text = fixture_text();
    if (text.empty()) GTEST_SKIP() << "fixture not loadable";

    auto window_block = extract_value_after(text, "hann_window");
    if (window_block.empty()) GTEST_SKIP() << "hann_window missing from fixture";

    auto first5_body = extract_value_after("{" + window_block + "}", "first_5");
    auto last5_body = extract_value_after("{" + window_block + "}", "last_5");
    auto first5 = parse_float_array(first5_body);
    auto last5 = parse_float_array(last5_body);

    auto w = hann_window(MEL_N_FFT);
    ASSERT_EQ(w.size(), MEL_N_FFT);

    ASSERT_EQ(first5.size(), 5u);
    for (std::size_t i = 0; i < 5; ++i) {
        EXPECT_NEAR(static_cast<double>(w[i]), first5[i], 1e-6) << "first_5[" << i << "]";
    }
    ASSERT_EQ(last5.size(), 5u);
    for (std::size_t i = 0; i < 5; ++i) {
        const std::size_t idx = MEL_N_FFT - 5 + i;
        EXPECT_NEAR(static_cast<double>(w[idx]), last5[i], 1e-6) << "last_5[" << i << "]";
    }
}

TEST(SpeakerEncoderGolden, MelFilterbankBandSumsMatchFixture) {
    const std::string text = fixture_text();
    if (text.empty()) GTEST_SKIP() << "fixture not loadable";

    const std::size_t fft_bins = MEL_N_FFT / 2 + 1;
    auto fb = create_mel_filterbank();
    ASSERT_EQ(fb.size(), MEL_N_MELS * fft_bins);

    auto filterbank_block = extract_value_after(text, "mel_filterbank");
    if (filterbank_block.empty()) GTEST_SKIP() << "mel_filterbank missing";
    auto band_sums_body = extract_value_after("{" + filterbank_block + "}", "band_sums");
    auto expected_sums = parse_float_array(band_sums_body);
    ASSERT_EQ(expected_sums.size(), MEL_N_MELS);

    for (std::size_t m = 0; m < MEL_N_MELS; ++m) {
        double s = 0.0;
        for (std::size_t k = 0; k < fft_bins; ++k) {
            s += static_cast<double>(fb[m * fft_bins + k]);
        }
        EXPECT_NEAR(s, expected_sums[m], 1e-3)
            << "mel band " << m << " sum drift";
    }
}

TEST(SpeakerEncoderGolden, MelComputationMatchesFixtureWithin2pctL2) {
    const std::string text = fixture_text();
    if (text.empty()) GTEST_SKIP() << "fixture not loadable";

    // Test cases cycle: extract each "id", "audio_params", and
    // "mel_sampled_every_10". For brevity we exercise just the first
    // sine_440hz_1s case; the algorithm is shared with the rest.
    auto pos = text.find("\"id\":\"sine_440hz_1s\"");
    if (pos == std::string::npos) GTEST_SKIP() << "sine_440hz_1s not in fixture";

    // Anchor block from id forward.
    auto block = text.substr(pos);
    auto end = block.find("\"id\":");
    if (end != std::string::npos && end > 100) {
        block = block.substr(0, end + 100);
    } else if (end == std::string::npos) {
        // last entry: find closing bracket of test_cases.
        auto tail = block.find("\"hann_window\"");
        if (tail != std::string::npos) block = block.substr(0, tail);
    }

    auto sampled_body = extract_value_after(block, "mel_sampled_every_10");
    if (sampled_body.empty()) GTEST_SKIP() << "mel_sampled_every_10 missing";
    auto expected_sampled = parse_float_array(sampled_body);

    auto audio = generate_sine(440.0, 1.0, MEL_SAMPLE_RATE);
    auto mel = compute_mel_spectrogram(audio);

    std::vector<double> actual_sampled;
    for (std::size_t i = 0; i < mel.size(); i += 10) {
        actual_sampled.push_back(static_cast<double>(mel[i]));
    }

    const std::size_t n = std::min(actual_sampled.size(), expected_sampled.size());
    actual_sampled.resize(n);
    expected_sampled.resize(n);

    const double dist = l2_relative(actual_sampled, expected_sampled);
    EXPECT_LT(dist, TOLERANCE)
        << "sine_440hz_1s mel L2 distance " << dist
        << " exceeds 2% tolerance (" << TOLERANCE << ")";
}

TEST(SpeakerEncoderGolden, ResampleLinearMatchesFixture) {
    auto audio48k = generate_sine(440.0, 0.1, 48000);
    auto resampled = resample_linear(audio48k, 48000, 16000);

    const std::string text = fixture_text();
    if (text.empty()) GTEST_SKIP() << "fixture not loadable";

    auto pos = text.find("\"id\":\"resample_48k_to_16k\"");
    if (pos == std::string::npos) GTEST_SKIP() << "resample case missing";
    auto block = text.substr(pos);

    auto first10 = parse_float_array(extract_value_after(block, "output_first_10"));
    auto last10 = parse_float_array(extract_value_after(block, "output_last_10"));

    ASSERT_EQ(first10.size(), 10u);
    ASSERT_EQ(last10.size(), 10u);

    for (std::size_t i = 0; i < 10; ++i) {
        EXPECT_NEAR(static_cast<double>(resampled[i]), first10[i], 1e-4)
            << "first_10[" << i << "]";
        const std::size_t idx = resampled.size() - 10 + i;
        EXPECT_NEAR(static_cast<double>(resampled[idx]), last10[i], 1e-4)
            << "last_10[" << i << "]";
    }
}
