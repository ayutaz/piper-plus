/// One-shot synthesis demo for piper-plus Dart FFI.
///
/// Usage:
///   dart run example/main.dart <model.onnx> [dict_dir] [text] [output.wav]
///
/// Example:
///   dart run example/main.dart model.onnx /usr/local/share/open_jtalk/dic \
///       "Hello, this is piper-plus." output.wav
library;

import 'dart:ffi';
import 'dart:io';

import '../lib/piper_plus.dart';

/// Resolve the platform-specific shared library name.
String _defaultLibraryPath() {
  if (Platform.isLinux) return 'libpiper_plus.so';
  if (Platform.isMacOS) return 'libpiper_plus.dylib';
  if (Platform.isWindows) return 'piper_plus.dll';
  throw UnsupportedError('Unsupported platform: ${Platform.operatingSystem}');
}

void main(List<String> args) {
  if (args.isEmpty) {
    stderr.writeln(
      'Usage: dart run example/main.dart <model.onnx> '
      '[dict_dir] [text] [output.wav]',
    );
    exit(1);
  }

  final modelPath = args[0];
  final dictDir = args.length > 1 ? args[1] : null;
  final text = args.length > 2 ? args[2] : 'Hello, this is piper-plus.';
  final outputPath = args.length > 3 ? args[3] : 'output.wav';

  // ------------------------------------------------------------------
  // 1. Create engine
  // ------------------------------------------------------------------
  final tts = PiperPlus.load(
    libraryPath: _defaultLibraryPath(),
    modelPath: modelPath,
    dictDir: dictDir,
  );

  print('piper-plus version: ${tts.version}');
  print('API version: ${tts.apiVersion}');
  print('Sample rate: ${tts.sampleRate} Hz');
  print('Speakers: ${tts.numSpeakers}, Languages: ${tts.numLanguages}');

  // ------------------------------------------------------------------
  // 2. Synthesize (one-shot)
  // ------------------------------------------------------------------
  print('Synthesizing: "$text"');

  final wav = tts.synthesize(text);

  // ------------------------------------------------------------------
  // 3. Write WAV file
  // ------------------------------------------------------------------
  File(outputPath).writeAsBytesSync(wav);
  print('Saved ${wav.length} bytes to $outputPath');

  // ------------------------------------------------------------------
  // 4. Clean up
  // ------------------------------------------------------------------
  tts.dispose();
  print('Done.');
}
