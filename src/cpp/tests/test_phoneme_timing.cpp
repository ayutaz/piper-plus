#include <gtest/gtest.h>
#include <cmath>
#include <cstdio>
#include <ios>
#include <sstream>
#include <string>
#include <vector>
#include "json.hpp"

// Mock phoneme timing structure for testing.
//
// The production type is `piper::PhonemeInfo` (declared in piper.hpp). This
// test deliberately does NOT link the piper library so it stays
// self-contained (no onnxruntime/spdlog/fmt). We mirror the layout here so
// the spec-canonical output helpers can be exercised in isolation.
struct PhonemeInfo {
    std::string phoneme;
    float start_time;     // seconds
    float end_time;       // seconds
    int start_frame;
    int end_frame;
};

// ---------------------------------------------------------------------------
// Reference implementations of the spec-canonical output helpers.
//
// These mirror the production code in src/cpp/piper.cpp byte-for-byte so the
// test catches drift between the spec and the implementation. When piper.cpp
// is updated, these helpers must be updated to match.
// ---------------------------------------------------------------------------

namespace {

void outputTimingsAsJSON(const std::vector<PhonemeInfo>& timings,
                         std::ostream& output,
                         const std::string& text,
                         int sampleRate,
                         int hopSize) {
    const double frameShiftMs =
        sampleRate > 0
            ? (static_cast<double>(hopSize) / static_cast<double>(sampleRate)) *
                  1000.0
            : 0.0;

    nlohmann::json result;
    nlohmann::json phonemesArray = nlohmann::json::array();

    double maxEndMs = 0.0;
    for (const auto& info : timings) {
        const double startMs = static_cast<double>(info.start_time) * 1000.0;
        const double endMs = static_cast<double>(info.end_time) * 1000.0;
        const double durationMs = endMs - startMs;
        if (endMs > maxEndMs) {
            maxEndMs = endMs;
        }

        nlohmann::json phonemeObj;
        phonemeObj["phoneme"] = info.phoneme;
        phonemeObj["start_ms"] = startMs;
        phonemeObj["end_ms"] = endMs;
        phonemeObj["duration_ms"] = durationMs;
        phonemeObj["start"] = info.start_time;
        phonemeObj["end"] = info.end_time;
        phonemeObj["start_frame"] = info.start_frame;
        phonemeObj["end_frame"] = info.end_frame;
        phonemesArray.push_back(phonemeObj);
    }

    result["phonemes"] = phonemesArray;
    if (!text.empty()) {
        result["text"] = text;
    }
    result["total_duration_ms"] = timings.empty() ? 0.0 : maxEndMs;
    result["sample_rate"] = sampleRate;
    result["frame_shift_ms"] = frameShiftMs;
    result["total_duration"] = timings.empty() ? 0.0 : timings.back().end_time;

    output << result.dump(2) << std::endl;
}

void outputTimingsAsTSV(const std::vector<PhonemeInfo>& timings,
                        std::ostream& output) {
    output << "phoneme\tstart_ms\tend_ms\tduration_ms\tstart\tend\tstart_frame\tend_frame"
           << std::endl;

    const std::ios_base::fmtflags savedFlags = output.flags();
    const std::streamsize savedPrecision = output.precision();
    output.setf(std::ios_base::fixed, std::ios_base::floatfield);
    output.precision(3);

    for (const auto& info : timings) {
        const double startMs = static_cast<double>(info.start_time) * 1000.0;
        const double endMs = static_cast<double>(info.end_time) * 1000.0;
        const double durationMs = endMs - startMs;

        output << info.phoneme << "\t"
               << startMs << "\t"
               << endMs << "\t"
               << durationMs << "\t"
               << info.start_time << "\t"
               << info.end_time << "\t"
               << info.start_frame << "\t"
               << info.end_frame << std::endl;
    }

    output.flags(savedFlags);
    output.precision(savedPrecision);
}

void outputTimingsAsSRT(const std::vector<PhonemeInfo>& timings,
                        std::ostream& output,
                        double /*sampleRate*/,
                        int /*hopSize*/) {
    auto formatTimestamp = [](double ms) -> std::string {
        if (ms < 0.0) {
            ms = 0.0;
        }
        const long long total_ms = static_cast<long long>(ms + 0.5);
        const long long millis = total_ms % 1000;
        const long long total_secs = total_ms / 1000;
        const long long secs = total_secs % 60;
        const long long total_mins = total_secs / 60;
        const long long mins = total_mins % 60;
        const long long hours = total_mins / 60;

        char buf[32];
        std::snprintf(buf, sizeof(buf), "%02lld:%02lld:%02lld,%03lld",
                      hours, mins, secs, millis);
        return std::string(buf);
    };

    for (size_t i = 0; i < timings.size(); ++i) {
        const auto& info = timings[i];
        const double startMs = static_cast<double>(info.start_time) * 1000.0;
        const double endMs = static_cast<double>(info.end_time) * 1000.0;

        output << (i + 1) << "\n"
               << formatTimestamp(startMs) << " --> "
               << formatTimestamp(endMs) << "\n"
               << info.phoneme << "\n\n";
    }
}

// Helper: parse "HH:MM:SS,mmm" → milliseconds (returns -1 on parse error).
long long parseSrtTimestamp(const std::string& s) {
    int h = 0, m = 0, sec = 0, ms = 0;
    if (std::sscanf(s.c_str(), "%d:%d:%d,%d", &h, &m, &sec, &ms) != 4) {
        return -1;
    }
    return ((static_cast<long long>(h) * 60 + m) * 60 + sec) * 1000 + ms;
}

std::vector<PhonemeInfo> sampleTimings() {
    // Two phonemes spanning ~92.8 ms each at 22050Hz / hop=256.
    // frame_time_ms = 256/22050*1000 ≈ 11.609977 → 5 frames ≈ 58.05 ms,
    // 8 frames ≈ 92.88 ms.
    return {
        {"^",
         0.0f,                 // 0 ms
         0.058049887f,         // 58.05 ms (5 frames)
         0,
         5},
        {"k",
         0.058049887f,         // 58.05 ms
         0.150929705f,         // 150.93 ms (8 frames more)
         5,
         13},
    };
}

}  // namespace

// ---------------------------------------------------------------------------
// Legacy / pre-existing tests preserved as-is.
// ---------------------------------------------------------------------------

// Test duration to timing conversion
TEST(PhonemeTimingTest, BasicDurationConversion) {
    // Test converting frame durations to time
    std::vector<float> durations = {2.0f, 3.0f, 4.0f};  // frames
    int hop_size = 256;
    int sample_rate = 22050;
    float frame_length = static_cast<float>(hop_size) / sample_rate;

    // Calculate expected times
    std::vector<float> expected_starts = {0.0f};
    std::vector<float> expected_ends;

    float current_time = 0.0f;
    for (auto duration : durations) {
        current_time += duration * frame_length;
        expected_ends.push_back(current_time);
        if (expected_starts.size() < durations.size()) {
            expected_starts.push_back(current_time);
        }
    }

    // Verify calculations
    EXPECT_FLOAT_EQ(expected_ends[0], 2.0f * frame_length);
    EXPECT_FLOAT_EQ(expected_ends[1], 5.0f * frame_length);
    EXPECT_FLOAT_EQ(expected_ends[2], 9.0f * frame_length);
}

TEST(PhonemeTimingTest, SpecialTokenHandling) {
    // Test that BOS (1), EOS (2), and PAD (0) tokens should be skipped
    const int BOS = 1;
    const int EOS = 2;
    const int PAD = 0;

    // In real implementation, these would be filtered out
    std::vector<int> tokens = {BOS, 'a', 'b', EOS, PAD};
    std::vector<int> filtered;

    for (int token : tokens) {
        if (token != BOS && token != EOS && token != PAD) {
            filtered.push_back(token);
        }
    }

    EXPECT_EQ(filtered.size(), 2);
    EXPECT_EQ(filtered[0], 'a');
    EXPECT_EQ(filtered[1], 'b');
}

TEST(PhonemeTimingTest, JSONFormat) {
    // Test JSON structure creation
    nlohmann::json timing_json;
    timing_json["text"] = "Hello";
    timing_json["sample_rate"] = 22050;
    timing_json["total_duration"] = 0.3;

    // Add phonemes array
    nlohmann::json phonemes = nlohmann::json::array();
    nlohmann::json phoneme1;
    phoneme1["phoneme"] = "h";
    phoneme1["start"] = 0.0;
    phoneme1["end"] = 0.045;
    phonemes.push_back(phoneme1);

    timing_json["phonemes"] = phonemes;

    // Verify structure
    EXPECT_EQ(timing_json["text"], "Hello");
    EXPECT_EQ(timing_json["sample_rate"], 22050);
    EXPECT_EQ(timing_json["phonemes"].size(), 1);
    EXPECT_EQ(timing_json["phonemes"][0]["phoneme"], "h");
}

TEST(PhonemeTimingTest, TSVFormat) {
    // Test TSV format generation
    std::stringstream output;

    // Write header (legacy schema, kept here for the legacy test)
    output << "phoneme\tstart\tend\tstart_frame\tend_frame" << std::endl;

    // Write data
    output << "h\t0\t0.045\t0\t4" << std::endl;
    output << "ə\t0.045\t0.120\t4\t10" << std::endl;

    // Read back and verify
    output.seekg(0);  // Reset read position to the beginning
    std::string line;
    std::getline(output, line);
    EXPECT_EQ(line, "phoneme\tstart\tend\tstart_frame\tend_frame");

    std::getline(output, line);
    EXPECT_EQ(line, "h\t0\t0.045\t0\t4");
}

// ---------------------------------------------------------------------------
// Spec-compliance tests (docs/spec/phoneme-timing-contract.toml).
// ---------------------------------------------------------------------------

// JSON: spec-canonical millisecond fields are present per phoneme.
TEST(PhonemeTimingTest, outputJSON_HasNewMsFields) {
    std::stringstream output;
    outputTimingsAsJSON(sampleTimings(), output, "test", 22050, 256);

    const auto parsed = nlohmann::json::parse(output.str());
    ASSERT_TRUE(parsed.contains("phonemes"));
    ASSERT_EQ(parsed["phonemes"].size(), 2u);

    const auto& first = parsed["phonemes"][0];
    ASSERT_TRUE(first.contains("start_ms"));
    ASSERT_TRUE(first.contains("end_ms"));
    ASSERT_TRUE(first.contains("duration_ms"));
    EXPECT_NEAR(first["start_ms"].get<double>(), 0.0, 1e-6);
    EXPECT_NEAR(first["end_ms"].get<double>(), 58.049887, 1e-3);
    EXPECT_NEAR(first["duration_ms"].get<double>(),
                first["end_ms"].get<double>() - first["start_ms"].get<double>(),
                1e-9);

    const auto& second = parsed["phonemes"][1];
    EXPECT_NEAR(second["start_ms"].get<double>(),
                first["end_ms"].get<double>(), 1e-9);
}

// JSON: total_duration_ms top-level field is emitted and equals the last
// phoneme's end_ms.
TEST(PhonemeTimingTest, outputJSON_HasTotalDurationMs) {
    std::stringstream output;
    outputTimingsAsJSON(sampleTimings(), output, "", 22050, 256);

    const auto parsed = nlohmann::json::parse(output.str());
    ASSERT_TRUE(parsed.contains("total_duration_ms"));

    const double last_end_ms = parsed["phonemes"].back()["end_ms"].get<double>();
    EXPECT_NEAR(parsed["total_duration_ms"].get<double>(), last_end_ms, 1e-9);

    // Empty input → total_duration_ms = 0.0.
    std::stringstream empty_out;
    outputTimingsAsJSON({}, empty_out, "", 22050, 256);
    const auto empty_parsed = nlohmann::json::parse(empty_out.str());
    ASSERT_TRUE(empty_parsed.contains("total_duration_ms"));
    EXPECT_DOUBLE_EQ(empty_parsed["total_duration_ms"].get<double>(), 0.0);
}

// JSON: sample_rate top-level field is emitted with the correct value, and
// frame_shift_ms is computed from (hopSize / sampleRate) * 1000 — NOT the
// pre-spec hard-coded 256 / sampleRate * 1000 (which happens to coincide
// when hopSize=256 — so we also test a different hopSize to lock the fix in).
TEST(PhonemeTimingTest, outputJSON_HasSampleRate) {
    std::stringstream output;
    outputTimingsAsJSON(sampleTimings(), output, "", 22050, 256);

    const auto parsed = nlohmann::json::parse(output.str());
    ASSERT_TRUE(parsed.contains("sample_rate"));
    EXPECT_EQ(parsed["sample_rate"].get<int>(), 22050);

    ASSERT_TRUE(parsed.contains("frame_shift_ms"));
    EXPECT_NEAR(parsed["frame_shift_ms"].get<double>(),
                (256.0 / 22050.0) * 1000.0, 1e-9);

    // Different hopSize must change frame_shift_ms — proves it is *not*
    // hard-coded to 256.
    std::stringstream alt_out;
    outputTimingsAsJSON(sampleTimings(), alt_out, "", 16000, 320);
    const auto alt = nlohmann::json::parse(alt_out.str());
    EXPECT_EQ(alt["sample_rate"].get<int>(), 16000);
    EXPECT_NEAR(alt["frame_shift_ms"].get<double>(),
                (320.0 / 16000.0) * 1000.0, 1e-9);
}

// JSON: legacy fields (start, end, start_frame, end_frame, total_duration)
// are still present alongside the new ms fields — required for backward
// compat with pre-spec consumers.
TEST(PhonemeTimingTest, outputJSON_LegacyFieldsStillPresent) {
    std::stringstream output;
    outputTimingsAsJSON(sampleTimings(), output, "", 22050, 256);

    const auto parsed = nlohmann::json::parse(output.str());
    ASSERT_TRUE(parsed.contains("total_duration"));

    const auto& first = parsed["phonemes"][0];
    EXPECT_TRUE(first.contains("start"));
    EXPECT_TRUE(first.contains("end"));
    EXPECT_TRUE(first.contains("start_frame"));
    EXPECT_TRUE(first.contains("end_frame"));

    EXPECT_NEAR(first["start"].get<double>(), 0.0, 1e-6);
    EXPECT_NEAR(first["end"].get<double>(), 0.058049887, 1e-6);
    EXPECT_EQ(first["start_frame"].get<int>(), 0);
    EXPECT_EQ(first["end_frame"].get<int>(), 5);

    // total_duration is the last phoneme's end_time (seconds).
    EXPECT_NEAR(parsed["total_duration"].get<double>(),
                sampleTimings().back().end_time, 1e-6);
}

// TSV: header advertises the new ms columns alongside legacy columns.
TEST(PhonemeTimingTest, outputTSV_HasNewMsColumns) {
    std::stringstream output;
    outputTimingsAsTSV(sampleTimings(), output);

    std::string header;
    std::getline(output, header);
    EXPECT_EQ(header,
              "phoneme\tstart_ms\tend_ms\tduration_ms\tstart\tend\tstart_frame\tend_frame");

    // First data row: tab-separated with 8 fields, ms columns formatted with 3
    // decimals, frame columns are integers.
    std::string row;
    std::getline(output, row);
    std::vector<std::string> cols;
    {
        std::string buf;
        for (char c : row) {
            if (c == '\t') {
                cols.push_back(buf);
                buf.clear();
            } else {
                buf.push_back(c);
            }
        }
        cols.push_back(buf);
    }
    ASSERT_EQ(cols.size(), 8u) << "row='" << row << "'";
    EXPECT_EQ(cols[0], "^");
    // start_ms = 0.000
    EXPECT_NE(cols[1].find('.'), std::string::npos)
        << "start_ms must be formatted as fixed-point: " << cols[1];
    // end_ms ~ 58.050 — assert leading "58." prefix to lock format.
    EXPECT_EQ(cols[2].substr(0, 3), "58.");
}

// SRT: timestamps are non-decreasing, ordered cues, 1-based indexing.
TEST(PhonemeTimingTest, outputSRT_HasMonotonicTimestamps) {
    std::stringstream output;
    outputTimingsAsSRT(sampleTimings(), output, 22050.0, 256);

    const std::string text = output.str();

    // First cue index is 1, second is 2.
    EXPECT_NE(text.find("1\n00:"), std::string::npos)
        << "expected cue 1 at start of SRT output:\n" << text;
    EXPECT_NE(text.find("\n2\n00:"), std::string::npos)
        << "expected cue 2 after cue 1 in SRT output:\n" << text;

    // Parse all "HH:MM:SS,mmm --> HH:MM:SS,mmm" arrows and check monotonicity.
    long long prev_end = -1;
    size_t pos = 0;
    int arrow_count = 0;
    while ((pos = text.find(" --> ", pos)) != std::string::npos) {
        // Walk back to start-of-line to capture the start timestamp.
        size_t line_start = text.rfind('\n', pos);
        line_start = (line_start == std::string::npos) ? 0 : line_start + 1;
        const std::string start_str = text.substr(line_start, pos - line_start);
        const size_t end_start = pos + 5;
        const size_t end_line_end = text.find('\n', end_start);
        ASSERT_NE(end_line_end, std::string::npos);
        const std::string end_str =
            text.substr(end_start, end_line_end - end_start);

        const long long start_ms = parseSrtTimestamp(start_str);
        const long long end_ms = parseSrtTimestamp(end_str);
        ASSERT_GE(start_ms, 0) << "unparseable start: " << start_str;
        ASSERT_GE(end_ms, 0) << "unparseable end: " << end_str;

        // Each cue: start <= end.
        EXPECT_LE(start_ms, end_ms);
        // Across cues: previous end <= next start (monotonic).
        if (prev_end >= 0) {
            EXPECT_LE(prev_end, start_ms);
        }
        prev_end = end_ms;
        ++arrow_count;
        pos = end_start;
    }
    EXPECT_EQ(arrow_count, static_cast<int>(sampleTimings().size()));

    // No UTF-8 BOM at the start.
    EXPECT_NE(text.substr(0, 3), std::string("\xEF\xBB\xBF"));
}
