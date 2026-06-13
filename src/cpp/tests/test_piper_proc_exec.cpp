// Unit tests for piper_proc_exec.h argv-based exec helpers.
//
// PR #401 introduced piper_run_argv / piper_capture_argv to replace shell
// system()/popen() and clear CodeQL cpp/command-line-injection alerts. Until
// now those helpers were only exercised indirectly through model_manager and
// openjtalk_dictionary_manager. This file adds direct coverage:
//
//   - piper_proc_exec_supported() returns the platform's expected value.
//   - piper_run_argv() runs a known-good binary and returns its exit code.
//   - piper_run_argv() refuses NULL / empty argv.
//   - piper_run_argv() returns -1 when argv[0] does not exist on PATH.
//   - piper_capture_argv() captures stdout into the caller's buffer.
//   - piper_capture_argv() truncates safely when the buffer is too small.
//   - piper_capture_argv() refuses NULL argv / NULL buffer / zero size.
//
// Self-contained: links gtest_main + compiles piper_proc_exec.c directly,
// no other piper-library symbols required.

#include <gtest/gtest.h>

#include <cstdlib>
#include <cstring>
#include <string>

#if defined(__APPLE__)
#include <TargetConditionals.h>
#endif

extern "C" {
#include "piper_proc_exec.h"
}

namespace {

#if defined(_WIN32)
constexpr const char* kTrueProgram = "cmd.exe";
constexpr const char* kEchoProgram = "cmd.exe";
#else
// posix_spawnp resolves through PATH when no slash is present. Different
// distros put true/echo in different absolute paths (Linux: /bin/, macOS:
// /usr/bin/), so rely on PATH instead of a hard-coded absolute path.
constexpr const char* kTrueProgram = "true";
constexpr const char* kEchoProgram = "echo";
#endif

// Return true when the platform should support process spawning. Apple
// embedded targets (iOS / tvOS / watchOS / visionOS) have App Sandbox and
// piper_proc_exec_supported() returns 0 there.
bool ShouldSupportSpawn() {
#if defined(__APPLE__) && \
    (TARGET_OS_IPHONE || TARGET_OS_TV || TARGET_OS_WATCH || \
     (defined(TARGET_OS_VISION) && TARGET_OS_VISION))
    return false;
#else
    return true;
#endif
}

}  // namespace

TEST(PiperProcExec, SupportedMatchesPlatform) {
    int supported = piper_proc_exec_supported();
    if (ShouldSupportSpawn()) {
        EXPECT_EQ(supported, 1) << "Expected spawn supported on this platform";
    } else {
        EXPECT_EQ(supported, 0) << "Expected spawn disabled on Apple-embedded";
    }
}

TEST(PiperProcExec, RunArgvNullReturnsError) {
    EXPECT_EQ(piper_run_argv(nullptr), -1);
}

TEST(PiperProcExec, RunArgvEmptyReturnsError) {
    const char* argv[] = {nullptr};
    EXPECT_EQ(piper_run_argv(argv), -1);
}

TEST(PiperProcExec, RunArgvSucceedsOnTrue) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP() << "process spawn disabled on this platform";
    }
#if defined(_WIN32)
    const char* argv[] = {"cmd.exe", "/c", "exit", "0", nullptr};
#else
    const char* argv[] = {kTrueProgram, nullptr};
#endif
    EXPECT_EQ(piper_run_argv(argv), 0);
}

TEST(PiperProcExec, RunArgvPropagatesNonZeroExit) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
#if defined(_WIN32)
    const char* argv[] = {"cmd.exe", "/c", "exit", "3", nullptr};
#else
    // sh -c "exit 3" — POSIX-portable across busybox / dash / bash. /bin/sh
    // is mandated by POSIX so the absolute path is portable here.
    const char* argv[] = {"/bin/sh", "-c", "exit 3", nullptr};
#endif
    int rc = piper_run_argv(argv);
    EXPECT_EQ(rc, 3) << "non-zero exit code must propagate verbatim";
}

TEST(PiperProcExec, RunArgvNonexistentBinaryReturnsError) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
    // A binary that cannot exist on PATH (random suffix, leading slash to
    // bypass PATH lookup on POSIX). On POSIX posix_spawnp returns non-zero
    // (e.g. ENOENT). On Windows _spawnvp returns -1.
    const char* argv[] = {"/nonexistent/__piper_test_no_such_binary_xyz", nullptr};
    int rc = piper_run_argv(argv);
    EXPECT_NE(rc, 0) << "spawn of missing binary must not silently succeed";
}

TEST(PiperProcExec, CaptureArgvNullArgsReturnsError) {
    char buf[16] = {0};
    size_t n = 0;
    EXPECT_EQ(piper_capture_argv(nullptr, buf, sizeof(buf), &n), -1);
    EXPECT_EQ(n, 0u);
}

TEST(PiperProcExec, CaptureArgvNullBufferReturnsError) {
    const char* argv[] = {kEchoProgram, "hi", nullptr};
    size_t n = 0;
    EXPECT_EQ(piper_capture_argv(argv, nullptr, 16, &n), -1);
    EXPECT_EQ(n, 0u);
}

TEST(PiperProcExec, CaptureArgvZeroSizeReturnsError) {
    const char* argv[] = {kEchoProgram, "hi", nullptr};
    char buf[1] = {0};
    size_t n = 0;
    EXPECT_EQ(piper_capture_argv(argv, buf, 0, &n), -1);
}

TEST(PiperProcExec, CaptureArgvCapturesStdout) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
#if defined(_WIN32)
    // cmd /c echo emits "hello\r\n"
    const char* argv[] = {"cmd.exe", "/c", "echo", "piper-test-token", nullptr};
#else
    const char* argv[] = {kEchoProgram, "piper-test-token", nullptr};
#endif
    char buf[64] = {0};
    size_t n = 0;
    int rc = piper_capture_argv(argv, buf, sizeof(buf), &n);
    EXPECT_EQ(rc, 0) << "echo must succeed";
    EXPECT_GT(n, 0u);
    // Trailing newline / CRLF tolerated.
    EXPECT_NE(std::string(buf).find("piper-test-token"), std::string::npos)
        << "captured stdout must contain the token: '" << buf << "'";
}

TEST(PiperProcExec, CaptureArgvTruncatesSafely) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
#if defined(_WIN32)
    const char* argv[] = {"cmd.exe", "/c", "echo",
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ", nullptr};
#else
    const char* argv[] = {kEchoProgram, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", nullptr};
#endif
    // Buffer smaller than the expected output (26 letters + newline) so we
    // exercise the truncation path. The function must still NUL-terminate.
    char buf[8] = {0};
    size_t n = 0;
    int rc = piper_capture_argv(argv, buf, sizeof(buf), &n);
    EXPECT_EQ(rc, 0);
    EXPECT_LT(n, sizeof(buf));
    EXPECT_EQ(buf[n], '\0') << "buffer must be NUL-terminated after truncation";
}

TEST(PiperProcExec, CaptureArgvNonexistentBinaryReturnsError) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
    const char* argv[] = {"/nonexistent/__piper_test_no_such_binary_xyz",
                          nullptr};
    char buf[32] = {0};
    size_t n = 12345;  // sentinel
    int rc = piper_capture_argv(argv, buf, sizeof(buf), &n);
    EXPECT_NE(rc, 0);
    // After failure the buffer is allowed to be untouched — but the function
    // must not have crashed and must report bytes_read in a defined way.
    EXPECT_LE(n, sizeof(buf));
}

#if defined(_WIN32)
// Windows-only regression guard for the --download-model PowerShell bug.
//
// model_manager.cpp / openjtalk_dictionary_manager.c previously built
// `powershell -NoProfile -Command "Invoke-WebRequest -Uri $args[0] ..."` and
// passed the URL / OutFile as trailing positional argv elements. PowerShell's
// -Command (unlike -File) does NOT bind positional arguments to $args, so
// $args[0] was empty and Invoke-WebRequest failed with "argument is null or
// empty", breaking model + dictionary downloads on Windows entirely.
//
// The fix passes those values via environment variables referenced as
// $env:VAR. These two tests pin both halves of that fact so the regression
// cannot silently return.
//
// Both use piper_run_argv (which spawns via _spawnvp directly) and assert on
// the child *exit code*, NOT captured stdout: piper_capture_argv routes
// through `cmd.exe /c` with per-arg quoting, whose outer-quote-stripping
// mangles a multi-arg `powershell` command line. The real download path also
// uses piper_run_argv, so this matches production.

TEST(PiperProcExec, PowerShellCommandDoesNotBindPositionalArgsToDollarArgs) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
    // OLD (broken) pattern: the token is passed positionally. Under -Command
    // $args[0] is NOT bound, so the comparison fails and the script exits 7.
    const char* argv[] = {
        "powershell", "-NoProfile", "-Command",
        "if ($args[0] -eq 'PIPER_TOK') { exit 0 } else { exit 7 }",
        "PIPER_TOK", nullptr,
    };
    int rc = piper_run_argv(argv);
    EXPECT_NE(rc, 0)
        << "PowerShell -Command must NOT bind positional args to $args (root "
           "cause of the old --download-model failure); the $args[0] match "
           "unexpectedly succeeded (rc=0).";
}

TEST(PiperProcExec, PowerShellEnvVarBindingDeliversValue) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
    // NEW (fixed) pattern: deliver the value via an environment variable and
    // reference it as $env:VAR. The _spawnvp child inherits the parent
    // environment, so the comparison succeeds and the script exits 0.
    _putenv_s("PIPER_PROC_EXEC_TEST_VAL", "PIPER_TOK");
    const char* argv[] = {
        "powershell", "-NoProfile", "-Command",
        "if ($env:PIPER_PROC_EXEC_TEST_VAL -eq 'PIPER_TOK') "
        "{ exit 0 } else { exit 7 }",
        nullptr,
    };
    int rc = piper_run_argv(argv);
    _putenv_s("PIPER_PROC_EXEC_TEST_VAL", "");  // clear
    EXPECT_EQ(rc, 0)
        << "PowerShell must resolve $env:VAR from the inherited environment "
           "(how the fixed download path passes URL/OutFile); rc=" << rc;
}
#endif

#if !defined(_WIN32)
// POSIX-only: shell metacharacters in argv must NOT be interpreted by a
// shell — the whole point of argv-based exec. Pass a string with `;` and
// `$(...)` and assert /bin/echo prints it back verbatim.
TEST(PiperProcExec, ShellMetacharsAreNotInterpreted) {
    if (!piper_proc_exec_supported()) {
        GTEST_SKIP();
    }
    const char* hostile = "a;b $(rm -rf /) `echo x` |y &z";
    const char* argv[] = {kEchoProgram, hostile, nullptr};
    char buf[256] = {0};
    size_t n = 0;
    int rc = piper_capture_argv(argv, buf, sizeof(buf), &n);
    ASSERT_EQ(rc, 0);
    // Strip trailing newline to compare.
    std::string captured(buf, n);
    while (!captured.empty() &&
           (captured.back() == '\n' || captured.back() == '\r')) {
        captured.pop_back();
    }
    EXPECT_EQ(captured, std::string(hostile))
        << "argv must be passed verbatim, never interpreted by a shell";
}
#endif
