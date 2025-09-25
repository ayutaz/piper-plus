#include <array>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <onnxruntime_cxx_api.h>

#include "tashkeel.hpp"
#include "uni_algo.h"

namespace tashkeel {

std::map<char32_t, int> inputVocab{
    {U'\u0009', 8},   {U'\u0020', 28},  {U'\u00a0', 84},  {U'\u00ab', 74},
    {U'\u00ad', 40},  {U'\u00b0', 5},   {U'\u00b4', 110}, {U'\u00bb', 30},
    {U'\u03ad', 69},  {U'\u03af', 112}, {U'\u03b1', 47},  {U'\u03b3', 80},
    {U'\u03b5', 7},   {U'\u03b8', 51},  {U'\u03b9', 36},  {U'\u03ba', 35},
    {U'\u03bc', 54},  {U'\u03bd', 63},  {U'\u03bf', 114}, {U'\u03c0', 116},
    {U'\u03c1', 26},  {U'\u03c3', 27},  {U'\u03c4', 78},  {U'\u03c5', 20},
    {U'\u03c7', 14},  {U'\u03c8', 12},  {U'\u03c9', 89},  {U'\u03cc', 77},
    {U'\u03ce', 103}, {U'\u05d5', 64},  {U'\u061b', 17},  {U'\u061f', 101},
    {U'\u0621', 120}, {U'\u0622', 15},  {U'\u0623', 73},  {U'\u0624', 50},
    {U'\u0625', 119}, {U'\u0626', 56},  {U'\u0627', 68},  {U'\u0628', 118},
    {U'\u0629', 107}, {U'\u062a', 22},  {U'\u062b', 71},  {U'\u062c', 59},
    {U'\u062d', 86},  {U'\u062e', 19},  {U'\u062f', 104}, {U'\u0630', 97},
    {U'\u0631', 65},  {U'\u0632', 92},  {U'\u0633', 82},  {U'\u0634', 18},
    {U'\u0635', 75},  {U'\u0636', 111}, {U'\u0637', 93},  {U'\u0638', 11},
    {U'\u0639', 95},  {U'\u063a', 24},  {U'\u0640', 9},   {U'\u0641', 46},
    {U'\u0642', 38},  {U'\u0643', 72},  {U'\u0644', 29},  {U'\u0645', 48},
    {U'\u0646', 81},  {U'\u0647', 49},  {U'\u0648', 6},   {U'\u0649', 39},
    {U'\u064a', 70},  {U'\u066a', 91},  {U'\u0670', 45},  {U'\u0671', 67},
    {U'\u06cc', 105}, {U'\u06d2', 37},  {U'\u06f5', 109}, {U'\u06f7', 106},
    {U'\u06f8', 10},  {U'\u200b', 52},  {U'\u200d', 31},  {U'\u200e', 117},
    {U'\u200f', 60},  {U'\u2013', 42},  {U'\u2018', 34},  {U'\u2019', 41},
    {U'\u201c', 55},  {U'\u201d', 85},  {U'\u2022', 62},  {U'\u2026', 23},
    {U'\u202b', 94},  {U'\u202c', 108}, {U'\u2030', 115}, {U'\ufb90', 53},
    {U'\ufd3e', 44},  {U'\ufd3f', 25},  {U'\ufe81', 16},  {U'\ufe82', 96},
    {U'\ufe83', 87},  {U'\ufe84', 61},  {U'\ufe87', 57},  {U'\ufe88', 58},
    {U'\ufe8b', 100}, {U'\ufe8c', 90},  {U'\ufe91', 32},  {U'\ufe92', 113},
    {U'\ufe94', 76},  {U'\ufed3', 33},  {U'\ufedb', 13},  {U'\ufedf', 99},
    {U'\ufee0', 66},  {U'\ufee3', 43},  {U'\ufee7', 102}, {U'\ufef4', 88},
    {U'\ufef5', 83},  {U'\ufef7', 98},  {U'\ufef9', 21},  {U'\ufefb', 79},
};

std::map<int, std::vector<char32_t>> outputVocab{
    {4, {U'\u0640'}},
    {5, {U'\u064e'}},
    {6, {U'\u064f', U'\u0651'}},
    {7, {U'\u064e', U'\u0651'}},
    {8, {U'\u0640'}},
    {9, {U'\u0651', U'\u0650'}},
    {10, {U'\u0651'}},
    {11, {U'\u0652', U'\u0651'}},
    {12, {U'\u0651', U'\u064d'}},
    {13, {U'\u0650', U'\u0651'}},
    {14, {U'\u064d', U'\u0651'}},
    {15, {U'\u064c', U'\u0651'}},
    {16, {U'\u0651', U'\u064e'}},
    {17, {U'\u064f'}},
    {18, {U'\u0651', U'\u064c'}},
    {19, {U'\u0651', U'\u064b'}},
    {20, {U'\u0652'}},
    {21, {U'\u064d'}},
    {22, {U'\u0650'}},
    {23, {U'\u0651', U'\u064f'}},
    {24, {U'\u064b', U'\u0651'}},
    {25, {U'\u064c'}},
    {26, {U'\u064b'}},
    {27, {U'\u0651', U'\u0651'}},
};

std::set<char32_t> HARAKAT_CHARS{
    U'\u064c', U'\u064d', U'\u064e', U'\u064f', U'\u0650', U'\u0651', U'\u0652',
};

std::set<int> INVALID_HARAKA_IDS{UNK_ID, 8};

PIPERPHONEMIZE_EXPORT void tashkeel_load(std::string modelPath, State &state) {
  state.env = Ort::Env(OrtLoggingLevel::ORT_LOGGING_LEVEL_WARNING,
                       instanceName.c_str());
  state.env.DisableTelemetryEvents();
  state.options.SetExecutionMode(ExecutionMode::ORT_PARALLEL);

#ifdef _WIN32
  auto modelPathW = std::wstring(modelPath.begin(), modelPath.end());
  auto modelPathStr = modelPathW.c_str();
#else
  auto modelPathStr = modelPath.c_str();
#endif

  state.onnx = Ort::Session(state.env, modelPathStr, state.options);
}

PIPERPHONEMIZE_EXPORT std::string tashkeel_run(std::string text, State &state) {
  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  std::vector<Ort::Value> inputTensors;

  // Strip haraka and convert to vocab ints
  std::string strippedText = std::string_view(text) | una::views::utf8 |
                             una::views::filter([](char32_t c) {
                               return HARAKAT_CHARS.count(c) < 1;
                             }) |
                             una::ranges::to_utf8<std::string>();

  auto inputIdRange = std::string_view(strippedText) | una::views::utf8 |
                      una::views::transform([](char32_t c) {
                        return inputVocab.count(c) > 0 ? inputVocab[c] : UNK_ID;
                      });

  std::vector<float> inputIds;
  for (auto id : inputIdRange) {
    inputIds.push_back(id);
  }

  // Model has a fixed input size
  inputIds.resize(MAX_INPUT_CHARS, PAD_ID);

  std::vector<int64_t> inputIdsShape{1, (int64_t)inputIds.size()};
  inputTensors.push_back(Ort::Value::CreateTensor<float>(
      memoryInfo, inputIds.data(), inputIds.size(), inputIdsShape.data(),
      inputIdsShape.size()));

  // From tashkeel model.
  // These can be pulled from the onnx session, but it's a pain.
  std::array<const char *, 1> inputNames = {"embedding_7_input"};
  std::array<const char *, 1> outputNames = {"dense_7"};

  auto outputTensors = state.onnx.Run(
      Ort::RunOptions{nullptr}, inputNames.data(), inputTensors.data(),
      inputTensors.size(), outputNames.data(), outputNames.size());

  if ((outputTensors.size() != 1) || (!outputTensors.front().IsTensor())) {
    throw std::runtime_error("Invalid output tensors");
  }

  const float *outputIdProbs = outputTensors.front().GetTensorData<float>();
  auto outputIdsShape =
      outputTensors.front().GetTensorTypeAndShapeInfo().GetShape();

  // batch x chars x probabilities
  std::size_t numOutputChars = outputIdsShape[1];
  std::size_t numOutputProbs = outputIdsShape[2];

  // Add predicted haraka to stripped string
  auto strippedView = std::string_view(strippedText) | una::views::utf8;
  std::u32string processedText;
  std::size_t i = 0;
  for (auto c : strippedView) {
    processedText += c;

    if (i < numOutputChars) {
      int maxId = 0;
      float maxIdProb = 0.0f;

      // Get the id with the maximum probability
      for (std::size_t j = 0; j < numOutputProbs; j++) {
        float currentProb = outputIdProbs[(i * numOutputProbs) + j];
        if (currentProb > maxIdProb) {
          maxIdProb = currentProb;
          maxId = j;
        }
      }

      if ((INVALID_HARAKA_IDS.count(maxId) < 1) &&
          (outputVocab.count(maxId) > 0)) {
        // Add predicted haraka
        for (auto haraka : outputVocab[maxId]) {
          processedText += haraka;
        }
      }
    }

    // Next output char
    i++;
  }

  // Clean up
  for (std::size_t i = 0; i < outputTensors.size(); i++) {
    Ort::detail::OrtRelease(outputTensors[i].release());
  }

  for (std::size_t i = 0; i < inputTensors.size(); i++) {
    Ort::detail::OrtRelease(inputTensors[i].release());
  }

  // Result is UTF-8
  return una::utf32to8(processedText);
}

} // namespace tashkeel
