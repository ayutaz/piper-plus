// Timing output formatting (TSV / SRT), shared by src/cpp/piper.cpp and
// src/cpp/tests/test_phoneme_timing_parity.cpp.
//
// These writers lived in piper.cpp, which links onnxruntime, so the
// cross-runtime parity test could not call them -- and the C++ TSV output had
// drifted away from the contract without anything noticing (issue #716):
//
//     contract [output_formats.tsv]: start_ms  end_ms  duration_ms  phoneme
//     C++ before this header:        phoneme  start_ms  end_ms  duration_ms
//                                    start  end  start_frame  end_frame
//
// Eight columns led by `phoneme`, against four led by `start_ms` in the other
// five runtimes. A consumer that reads by column index takes the phoneme for a
// timestamp; one that reads by name still has to special-case C++. The
// divergence survived because the golden fixture held only float milliseconds
// until spec_version 1.2, so no test ever looked at the rendered text.
//
// The extra columns are dropped rather than appended: the contract's `header`
// is pinned byte-for-byte, so any trailing column breaks parity just as a
// reordering does, and every value in them is derivable from the four that
// remain (`start` = `start_ms / 1000`, `start_frame` = `start_ms * sample_rate
// / hop_size / 1000`).
//
// Rows carry milliseconds, not the seconds that `PhonemeInfo` stores. That is
// deliberate: it lets the parity test drive these writers straight from the
// fixture's millisecond values, so what gets compared byte-for-byte is the
// FORMATTING (column order, precision, locale, escaping, separators) rather
// than the float32 seconds round-trip that `PhonemeInfo` imposes on the
// production path. The round-trip is checked separately, to `kAbsTolMs`, by
// the numeric assertions in the same test.
//
// Depends only on the standard library, so the test links neither onnxruntime
// nor spdlog.

#ifndef PIPER_PLUS_TIMING_FORMAT_HPP
#define PIPER_PLUS_TIMING_FORMAT_HPP

#include <cmath>
#include <cstdio>
#include <ios>
#include <locale>
#include <ostream>
#include <string>
#include <vector>

namespace piper {
namespace timing_format {

// docs/spec/phoneme-timing-contract.toml [output_formats.tsv].header
inline constexpr const char *kTsvHeader =
    "start_ms\tend_ms\tduration_ms\tphoneme";

// One row of timing output, in milliseconds.
struct FormatRow {
  std::string phoneme;
  double start_ms = 0.0;
  double end_ms = 0.0;
  double duration_ms = 0.0;
};

// [output_formats.tsv] escape_tab_in_phoneme / escape_newline_in_phoneme.
// A phoneme token holding a literal tab or newline would otherwise invent a
// column or a row. Piper's own token set contains neither, but a custom
// dictionary or a `[[ ... ]]` inline phoneme can, and the other five runtimes
// all escape (python `replace("\t", "\\t")`, rust, go, js, csharp).
inline std::string escapeTsvPhoneme(const std::string &phoneme) {
  std::string out;
  out.reserve(phoneme.size());
  for (const char c : phoneme) {
    if (c == '\t') {
      out += "\\t";
    } else if (c == '\n') {
      out += "\\n";
    } else {
      out += c;
    }
  }
  return out;
}

// [output_formats.srt].timestamp_format = "HH:MM:SS,mmm"
inline std::string formatSrtTimestamp(double ms) {
  if (ms < 0.0) {
    ms = 0.0;
  }
  // std::llround, not `static_cast<long long>(ms + 0.5)`: adding 0.5 can round
  // up in binary64, so the sum idiom disagrees with a true round() at
  // ms = 0.49999999999999994 (the largest double below 0.5), where `ms + 0.5`
  // is exactly 1.0. Rust f64::round, Go math.Round and JS Math.round all yield
  // 0 there. That input is unreachable through PhonemeInfo's float seconds,
  // but the idiom is what the contract pins across six runtimes, so it has to
  // be the correct one rather than one that happens not to be exercised.
  const long long total_ms = std::llround(ms);
  const long long millis = total_ms % 1000;
  const long long total_secs = total_ms / 1000;
  const long long secs = total_secs % 60;
  const long long total_mins = total_secs / 60;
  const long long mins = total_mins % 60;
  const long long hours = total_mins / 60;

  char buf[32];
  std::snprintf(buf, sizeof(buf), "%02lld:%02lld:%02lld,%03lld", hours, mins,
                secs, millis);
  return std::string(buf);
}

// Restores a stream's locale, format flags and precision on scope exit.
//
// The locale must be pinned, not inherited. The CLI installs a global
// "en_US.UTF-8" locale (main.cpp) and every stream constructed afterwards --
// including the ofstream behind --output-timing -- inherits its numpunct,
// which groups thousands. Any entry past one second was then written as
// `1,011.541`, which no TSV consumer parses as a number and which
// float_precision = 3 does not allow. It reproduced only where that locale
// exists, since main.cpp falls back to the classic locale when the runtime
// lacks it. The SRT writer needs the same guard for its integer cue index
// (cue 1000 came out as "1,000"); its timestamps use snprintf and were never
// affected.
class ScopedClassicNumeric {
 public:
  explicit ScopedClassicNumeric(std::ostream &out)
      : out_(out),
        locale_(out.getloc()),
        flags_(out.flags()),
        precision_(out.precision()) {
    out_.imbue(std::locale::classic());
  }
  ~ScopedClassicNumeric() {
    out_.flags(flags_);
    out_.precision(precision_);
    out_.imbue(locale_);
  }
  ScopedClassicNumeric(const ScopedClassicNumeric &) = delete;
  ScopedClassicNumeric &operator=(const ScopedClassicNumeric &) = delete;

 private:
  std::ostream &out_;
  std::locale locale_;
  std::ios_base::fmtflags flags_;
  std::streamsize precision_;
};

// [output_formats.tsv]: header line, `\t` separator, `\n` rows, trailing
// newline, three decimals.
inline void writeTsv(std::ostream &output,
                     const std::vector<FormatRow> &rows) {
  ScopedClassicNumeric guard(output);
  output.setf(std::ios_base::fixed, std::ios_base::floatfield);
  output.precision(3);

  output << kTsvHeader << "\n";
  for (const auto &row : rows) {
    output << row.start_ms << "\t" << row.end_ms << "\t" << row.duration_ms
           << "\t" << escapeTsvPhoneme(row.phoneme) << "\n";
  }
}

// [output_formats.srt]: cue_format = "{index}\n{start} --> {end}\n{phoneme}\n\n"
// with 1-based indexing. The phoneme is NOT escaped here -- SRT has no
// delimiter to protect and the other runtimes emit it raw.
inline void writeSrt(std::ostream &output,
                     const std::vector<FormatRow> &rows) {
  ScopedClassicNumeric guard(output);

  for (std::size_t i = 0; i < rows.size(); ++i) {
    output << (i + 1) << "\n"
           << formatSrtTimestamp(rows[i].start_ms) << " --> "
           << formatSrtTimestamp(rows[i].end_ms) << "\n"
           << rows[i].phoneme << "\n\n";
  }
}

}  // namespace timing_format
}  // namespace piper

#endif  // PIPER_PLUS_TIMING_FORMAT_HPP
