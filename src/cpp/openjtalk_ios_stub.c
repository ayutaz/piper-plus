/*
 * openjtalk_ios_stub.c — iOS / Apple-embedded stub for OpenJTalk symbols.
 *
 * On iOS / Mac Catalyst / tvOS / watchOS / visionOS, the four desktop-only
 * translation units (openjtalk_wrapper.c, openjtalk_optimized.c,
 * openjtalk_dictionary_manager.c, model_manager.cpp) are excluded from the
 * piper_common OBJECT library because they call std::system / popen / fork —
 * unavailable in the App Sandbox.
 *
 * However, openjtalk_phonemize.cpp and openjtalk_api.c remain in the build
 * (their non-network logic is still useful — phoneme post-processing, NJD
 * pipeline, etc.). They reference symbols defined in the excluded files,
 * which would cause undefined-symbol link errors when the consumer Xcode
 * project links libpiper_plus.a.
 *
 * This stub TU provides minimal implementations for those symbols so the
 * static archive resolves cleanly. Every entry point fails fast (returns
 * NULL / 0 / -1) so callers get a clean "OpenJTalk unavailable" path
 * without runtime crashes.
 *
 * Consumers that need Japanese TTS on iOS must:
 *   1. Pre-bundle the OpenJTalk MeCab dictionary in their app bundle, AND
 *   2. Use a future iOS-specific OpenJTalk binding (e.g. swift-openjtalk,
 *      pyopenjtalk via Python.framework) — outside the scope of v1.13.0.
 *
 * Issue: #377  Linked from cmake/PiperCommon.cmake.
 */

#include <stddef.h>
#include <stdlib.h>

/* Mirror of OpenJTalkProsodyResult declared in openjtalk_phonemize.hpp.
 * Re-declared here because that header is C++ (it includes piper.hpp); we
 * need only the layout, which is identical. */
typedef struct {
    char* phonemes;
    int*  prosody_a1;
    int*  prosody_a2;
    int*  prosody_a3;
    int   count;
} OpenJTalkProsodyResult;

/* ---- openjtalk_wrapper.c stand-ins ---- */

int openjtalk_is_available(void) {
    return 0;  /* unavailable on Apple-embedded platforms */
}

int openjtalk_ensure_dictionary(void) {
    return 0;  /* false: dictionary cannot be located */
}

char* openjtalk_text_to_phonemes(const char* text) {
    (void)text;
    return NULL;
}

void openjtalk_free_phonemes(char* phonemes) {
    /* In the desktop build, openjtalk_text_to_phonemes mallocs the result.
     * Stay symmetric with std::malloc/std::free so any caller that obtained
     * a buffer from a different allocator path can still be freed safely. */
    free(phonemes);
}

OpenJTalkProsodyResult* openjtalk_text_to_phonemes_with_prosody(const char* text) {
    (void)text;
    return NULL;
}

void openjtalk_free_prosody_result(OpenJTalkProsodyResult* result) {
    if (!result) {
        return;
    }
    free(result->phonemes);
    free(result->prosody_a1);
    free(result->prosody_a2);
    free(result->prosody_a3);
    free(result);
}

/* ---- openjtalk_optimized.c stand-ins ---- */

char* openjtalk_text_to_phonemes_optimized(const char* text) {
    (void)text;
    return NULL;
}

/* ---- openjtalk_dictionary_manager.c stand-ins ---- */

const char* get_openjtalk_dictionary_path(void) {
    return NULL;
}

int ensure_openjtalk_dictionary(void) {
    return -1;  /* non-zero: dictionary cannot be ensured */
}

void reset_openjtalk_dictionary_cache(void) {
    /* no-op */
}

void force_openjtalk_dictionary_path(const char* path) {
    (void)path;
    /* no-op */
}
