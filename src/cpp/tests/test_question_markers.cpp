#include <gtest/gtest.h>
#include "../openjtalk_phonemize_utils.hpp"

using namespace piper;

// =========================================================================
// Issue #204: Question Type Marker Tests
// Tests for getQuestionType() — determines EOS token type from text ending
// =========================================================================

// --- Declarative (non-question) ---

TEST(QuestionMarkersTest, Declarative_Period) {
    // 平叙文（句点あり）
    EXPECT_EQ(getQuestionType("こんにちは。"), "$");
}

TEST(QuestionMarkersTest, Declarative_NoPunctuation) {
    // 平叙文（句読点なし）
    EXPECT_EQ(getQuestionType("ありがとう"), "$");
}

TEST(QuestionMarkersTest, Declarative_ExclamationOnly) {
    // 感嘆文（疑問符なし）
    EXPECT_EQ(getQuestionType("すごい！"), "$");
}

// --- Simple question ---

TEST(QuestionMarkersTest, SimpleQuestion_Fullwidth) {
    // 汎用疑問（全角）
    EXPECT_EQ(getQuestionType("本当ですか？"), "?");
}

TEST(QuestionMarkersTest, SimpleQuestion_Halfwidth) {
    // 汎用疑問（半角）
    EXPECT_EQ(getQuestionType("本当?"), "?");
}

// --- Emphatic question ---

TEST(QuestionMarkersTest, EmphasisQuestion_HalfwidthQE) {
    // 強調疑問 ?!
    EXPECT_EQ(getQuestionType("本当?!"), "?!");
}

TEST(QuestionMarkersTest, EmphasisQuestion_HalfwidthEQ) {
    // 強調疑問 !?
    EXPECT_EQ(getQuestionType("本当!?"), "?!");
}

TEST(QuestionMarkersTest, EmphasisQuestion_FullwidthQE) {
    // 強調疑問 ？！（全角）
    EXPECT_EQ(getQuestionType("マジ？！"), "?!");
}

TEST(QuestionMarkersTest, EmphasisQuestion_FullwidthEQ) {
    // 強調疑問 ！？（全角）
    EXPECT_EQ(getQuestionType("マジ！？"), "?!");
}

// --- Declarative question ---

TEST(QuestionMarkersTest, DeclarativeQuestion_HalfwidthQP) {
    // 平叙疑問 ?.
    EXPECT_EQ(getQuestionType("そうなの?."), "?.");
}

TEST(QuestionMarkersTest, DeclarativeQuestion_FullwidthQP) {
    // 平叙疑問 ？。
    EXPECT_EQ(getQuestionType("そうなの？。"), "?.");
}

TEST(QuestionMarkersTest, DeclarativeQuestion_FullwidthPQ) {
    // 平叙疑問 。？
    EXPECT_EQ(getQuestionType("そうなの。？"), "?.");
}

// --- Confirmation question ---

TEST(QuestionMarkersTest, ConfirmQuestion_HalfwidthQT) {
    // 確認疑問 ?~
    EXPECT_EQ(getQuestionType("行くよね?~"), "?~");
}

TEST(QuestionMarkersTest, ConfirmQuestion_FullwidthQT) {
    // 確認疑問 ？～
    EXPECT_EQ(getQuestionType("行くよね？～"), "?~");
}

TEST(QuestionMarkersTest, ConfirmQuestion_FullwidthTQ) {
    // 確認疑問 ～？
    EXPECT_EQ(getQuestionType("行くよね～？"), "?~");
}

// --- Edge cases ---

TEST(QuestionMarkersTest, EmptyString) {
    EXPECT_EQ(getQuestionType(""), "$");
}

TEST(QuestionMarkersTest, TrailingWhitespace) {
    // 末尾の空白は除去される
    EXPECT_EQ(getQuestionType("本当？  \n"), "?");
}

TEST(QuestionMarkersTest, TrailingTab) {
    EXPECT_EQ(getQuestionType("本当？\t"), "?");
}

TEST(QuestionMarkersTest, OnlyWhitespace) {
    EXPECT_EQ(getQuestionType("   "), "$");
}
