// Tests for issue #383 Phase 1 — parallel G2P resolution helper.
//
// Mirrors src/python_run/tests/test_voice_g2p_parallel.py's
// `_resolve_g2p_parallelism` checks. The helper is purely arithmetic /
// env-driven so it can be exercised without loading a real model.

#include <gtest/gtest.h>

#include "g2p_parallelism.hpp"

using piper_plus::resolveG2pParallelism;
using piper_plus::kG2pAutoParallelismCap;

TEST(G2pParallelism, ZeroOrOneSentenceReturnsOne) {
    EXPECT_EQ(1, resolveG2pParallelism(0));
    EXPECT_EQ(1, resolveG2pParallelism(1));

    // Even an explicit override cannot raise parallelism above n_sentences.
    EXPECT_EQ(1, resolveG2pParallelism(0, "8"));
    EXPECT_EQ(1, resolveG2pParallelism(1, "8"));
}

TEST(G2pParallelism, EnvForceSerial) {
    // "1" is the documented opt-out switch — must always return 1.
    EXPECT_EQ(1, resolveG2pParallelism(10, "1"));
    EXPECT_EQ(1, resolveG2pParallelism(50, "1"));

    // Negative / zero values also collapse to serial.
    EXPECT_EQ(1, resolveG2pParallelism(10, "0"));
    EXPECT_EQ(1, resolveG2pParallelism(10, "-3"));
}

TEST(G2pParallelism, EnvExplicitCappedByNSentences) {
    EXPECT_EQ(3, resolveG2pParallelism(3, "8"));
    EXPECT_EQ(8, resolveG2pParallelism(20, "8"));
    EXPECT_EQ(2, resolveG2pParallelism(5, "2"));
}

TEST(G2pParallelism, EnvLeadingWhitespaceTolerated) {
    EXPECT_EQ(4, resolveG2pParallelism(10, "  4"));
    EXPECT_EQ(4, resolveG2pParallelism(10, "\t4"));
}

TEST(G2pParallelism, EnvGarbageFallsBackToAuto) {
    // Garbage strings must fall through to the auto branch.
    int autoVal = resolveG2pParallelism(10);
    EXPECT_EQ(autoVal, resolveG2pParallelism(10, "garbage"));
    EXPECT_EQ(autoVal, resolveG2pParallelism(10, "abc"));
    EXPECT_EQ(autoVal, resolveG2pParallelism(10, ""));
}

TEST(G2pParallelism, AutoCappedByConstantAndNSentences) {
    // Auto branch never returns more than the cap.
    EXPECT_LE(resolveG2pParallelism(100), kG2pAutoParallelismCap);

    // ... and never more than n_sentences.
    EXPECT_LE(resolveG2pParallelism(2), 2);
    EXPECT_LE(resolveG2pParallelism(3), 3);
}

TEST(G2pParallelism, AutoYieldsAtLeastTwoForMultipleSentences) {
    // For 2+ sentences the auto branch must opt into parallelism (>=2)
    // because that is the whole point of the feature.
    EXPECT_GE(resolveG2pParallelism(8), 2);
    EXPECT_GE(resolveG2pParallelism(50), 2);
}
