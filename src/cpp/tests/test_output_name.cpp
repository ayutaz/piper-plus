// Auto-generated output filenames for --output_dir (issue #696).
//
// The name is composed in main.cpp from a timestamp plus a counter. Two
// properties matter and neither was tested:
//
//  1. Uniqueness. A timestamp alone collides when two utterances land in the
//     same clock tick, and the second file then overwrites the first with exit
//     code 0 and a "Wrote ..." line for both -- silent data loss. Measured on
//     the Python CLI, whose clock is coarser (CPython 3.12 on Windows backs
//     time.monotonic() with GetTickCount64, ~15.6 ms).
//
//  2. No locale grouping. main() installs a global "en_US.UTF-8" locale, and
//     any stream built after that inherits its numpunct. The nanosecond
//     timestamp came out as "1,790,576,108,571,824,000.wav" (measured).
//     Commas are legal in a filename but break shell globbing and any
//     consumer that parses the name. The grouping only appears where that
//     locale exists, which is why it survived.
//
// The composition is reproduced here rather than linked: main.cpp is the CLI
// translation unit with a main() of its own. To keep that from drifting into
// an untested replica -- the failure mode of issue #703 -- the test asserts
// the two PROPERTIES against a helper whose body is three lines, and the CLI
// E2E check in scripts/test_cpp_cli_timing.py asserts the real filenames.

#include <gtest/gtest.h>

#include <algorithm>
#include <atomic>
#include <iomanip>
#include <locale>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

// Same composition as main.cpp's OUTPUT_DIRECTORY branch.
std::string composeName(long long timestamp, unsigned long long counter) {
  std::stringstream outputName;
  outputName.imbue(std::locale::classic());
  outputName << timestamp << "_" << std::setfill('0') << std::setw(4) << counter
             << ".wav";
  return outputName.str();
}

}  // namespace

TEST(OutputName, OneClockTickStillYieldsDistinctNames) {
  const long long frozenClock = 1790576108571824000LL;
  std::set<std::string> names;
  for (unsigned long long i = 0; i < 5; ++i) {
    names.insert(composeName(frozenClock, i));
  }
  EXPECT_EQ(names.size(), 5u)
      << "a single clock value must still produce distinct names";
}

TEST(OutputName, NamesSortInCreationOrder) {
  // The timestamp prefix is what makes a directory listing line up with the
  // input order, so the counter has to be zero-padded: an unpadded suffix
  // sorts 10 before 2.
  const long long frozenClock = 1790576108571824000LL;
  std::vector<std::string> names;
  for (unsigned long long i = 0; i < 12; ++i) {
    names.push_back(composeName(frozenClock, i));
  }
  std::vector<std::string> sorted = names;
  std::sort(sorted.begin(), sorted.end());
  EXPECT_EQ(names, sorted) << "names must sort in creation order";
}

TEST(OutputName, NoThousandsSeparatorUnderAGroupingLocale) {
  // Install a grouping locale globally, exactly as main() does, and check the
  // composition is immune. Without the imbue this produces
  // "1,790,576,108,571,824,000_0000.wav".
  const std::locale previous = std::locale();
  bool installed = false;
  // MSVC does not accept the POSIX-style names; it wants "en-US" or
  // "English_United States.1252". Offering both keeps the check meaningful on
  // Windows instead of silently skipping there -- which matters because
  // Windows is where main()'s global locale is most likely to differ.
  for (const char* name : {"en_US.UTF-8", "en_US.utf8", "en-US",
                           "English_United States.1252", "C.UTF-8"}) {
    try {
      std::locale::global(std::locale(name));
      installed = true;
      break;
    } catch (const std::exception&) {
      continue;
    }
  }
  if (!installed) {
    GTEST_SKIP() << "no grouping locale available on this runtime";
  }

  const std::string name = composeName(1790576108571824000LL, 0);
  std::locale::global(previous);

  EXPECT_EQ(name.find(','), std::string::npos)
      << "filename must not carry locale thousands separators: " << name;
  EXPECT_EQ(name, "1790576108571824000_0000.wav");
}

// Anti-vacuity: prove the grouping locale actually groups on this runtime, so
// NoThousandsSeparatorUnderAGroupingLocale is not passing because the locale
// had no effect. A bare TEST so no fixture can skip it.
TEST(OutputNameGate, GroupingLocaleActuallyGroupsWithoutTheImbue) {
  const std::locale previous = std::locale();
  bool installed = false;
  // MSVC does not accept the POSIX-style names; it wants "en-US" or
  // "English_United States.1252". Offering both keeps the check meaningful on
  // Windows instead of silently skipping there -- which matters because
  // Windows is where main()'s global locale is most likely to differ.
  for (const char* name : {"en_US.UTF-8", "en_US.utf8", "en-US",
                           "English_United States.1252", "C.UTF-8"}) {
    try {
      std::locale::global(std::locale(name));
      installed = true;
      break;
    } catch (const std::exception&) {
      continue;
    }
  }
  if (!installed) {
    GTEST_SKIP() << "no grouping locale available on this runtime";
  }

  std::stringstream unpinned;  // inherits the global locale
  unpinned << 1790576108571824000LL;
  const std::string grouped = unpinned.str();
  std::locale::global(previous);

  EXPECT_NE(grouped.find(','), std::string::npos)
      << "this runtime's grouping locale does not group, so the imbue test "
         "would pass even without the imbue: "
      << grouped;
}
