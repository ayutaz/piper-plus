#pragma once

// Phase 1 of issue #383: parallel-G2P helpers shared between
// piper_plus_c_api.cpp and the unit tests in tests/test_g2p_parallelism.cpp.
//
// Mirrors src/python_run/piper/voice.py::_resolve_g2p_parallelism.

#include <algorithm>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <thread>

namespace piper_plus {

// Auto cap is 4 because the ORT session itself uses ~4 intra-op threads;
// going wider tends to oversubscribe physical cores. PIPER_G2P_PARALLELISM
// is the public knob — set "1" to force the strictly-serial pre-issue-383
// path if a third-party G2P backend turns out not to be thread-safe.
constexpr int kG2pAutoParallelismCap = 4;

// Resolve effective G2P parallelism for nSentences phonemizations.
//
// * 0 / 1 sentences  → returns 1 (skip thread pool entirely).
// * PIPER_G2P_PARALLELISM=1   → returns 1 (legacy serial path).
// * PIPER_G2P_PARALLELISM=N>=2 → returns min(N, nSentences).
// * unset / garbage  → auto = min(nSentences, max(2, hwc/2),
//                                 kG2pAutoParallelismCap).
//
// envOverride is provided for testing; pass nullptr for production.
inline int resolveG2pParallelism(std::size_t nSentences,
                                 const char *envOverride = nullptr) {
    if (nSentences <= 1) {
        return 1;
    }

    const char *env = envOverride ? envOverride : std::getenv("PIPER_G2P_PARALLELISM");
    if (env) {
        const char *p = env;
        while (*p == ' ' || *p == '\t') ++p;
        if (*p != '\0') {
            try {
                std::size_t consumed = 0;
                int n = std::stoi(std::string(p), &consumed);
                if (n <= 1) {
                    return 1;
                }
                int capped = std::min<int>(n, static_cast<int>(nSentences));
                return std::max(1, capped);
            } catch (const std::exception &) {
                // Fall through to auto on garbage input.
            }
        }
    }

    unsigned hw = std::thread::hardware_concurrency();
    if (hw == 0) hw = 2;
    int half = static_cast<int>(hw / 2);
    int autoN = std::min<int>(static_cast<int>(nSentences),
                              std::max(2, half));
    autoN = std::min(autoN, kG2pAutoParallelismCap);
    return std::max(1, autoN);
}

}  // namespace piper_plus
