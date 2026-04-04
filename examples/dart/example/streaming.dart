/// Streaming synthesis demo for piper-plus Dart FFI.
///
/// Demonstrates NativeCallable.listener (Dart 3.1+) to receive audio chunks
/// via a Dart Stream, then writes the accumulated PCM data as a WAV file.
///
/// Usage:
///   dart run example/streaming.dart <model.onnx> [dict_dir] [text] [output.wav]
///
/// Example:
///   dart run example/streaming.dart model.onnx /usr/local/share/open_jtalk/dic \
///       "First sentence. Second sentence. Third sentence." streaming.wav
library;

import 'dart:io';
import 'dart:typed_data';

import '../lib/piper_plus.dart';

/// Resolve the platform-specific shared library name.
String _defaultLibraryPath() {
  if (Platform.isLinux) return 'libpiper_plus.so';
  if (Platform.isMacOS) return 'libpiper_plus.dylib';
  if (Platform.isWindows) return 'piper_plus.dll';
  throw UnsupportedError('Unsupported platform: ${Platform.operatingSystem}');
}

/// Write a minimal WAV header for 16-bit mono PCM.
Uint8List _buildWav(Uint8List pcmData, int sampleRate) {
  final dataSize = pcmData.length;
  final fileSize = 36 + dataSize;

  final header = ByteData(44);
  var offset = 0;

  void writeAscii(String s) {
    for (var i = 0; i < s.length; i++) {
      header.setUint8(offset++, s.codeUnitAt(i));
    }
  }

  // RIFF header
  writeAscii('RIFF');
  header.setUint32(offset, fileSize, Endian.little);
  offset += 4;
  writeAscii('WAVE');

  // fmt chunk
  writeAscii('fmt ');
  header.setUint32(offset, 16, Endian.little);
  offset += 4;
  header.setUint16(offset, 1, Endian.little);
  offset += 2; // PCM
  header.setUint16(offset, 1, Endian.little);
  offset += 2; // mono
  header.setUint32(offset, sampleRate, Endian.little);
  offset += 4;
  header.setUint32(offset, sampleRate * 2, Endian.little);
  offset += 4; // byte rate
  header.setUint16(offset, 2, Endian.little);
  offset += 2; // block align
  header.setUint16(offset, 16, Endian.little);
  offset += 2; // bits per sample

  // data chunk
  writeAscii('data');
  header.setUint32(offset, dataSize, Endian.little);
  offset += 4;

  // Concatenate header + PCM data
  final wav = Uint8List(44 + dataSize);
  wav.setAll(0, header.buffer.asUint8List());
  wav.setAll(44, pcmData);
  return wav;
}

Future<void> main(List<String> args) async {
  if (args.isEmpty) {
    stderr.writeln(
      'Usage: dart run example/streaming.dart <model.onnx> '
      '[dict_dir] [text] [output.wav]',
    );
    exit(1);
  }

  final modelPath = args[0];
  final dictDir = args.length > 1 ? args[1] : null;
  final text = args.length > 2
      ? args[2]
      : 'First sentence. Second sentence. Third sentence.';
  final outputPath = args.length > 3 ? args[3] : 'streaming_output.wav';

  // ------------------------------------------------------------------
  // 1. Create engine
  // ------------------------------------------------------------------
  final tts = PiperPlus.load(
    libraryPath: _defaultLibraryPath(),
    modelPath: modelPath,
    dictDir: dictDir,
  );

  print('Streaming synthesis: "$text"');
  print('Sample rate: ${tts.sampleRate} Hz');

  // ------------------------------------------------------------------
  // 2. Stream synthesis — collect PCM chunks
  // ------------------------------------------------------------------
  final pcmChunks = <Uint8List>[];
  var chunkCount = 0;

  await for (final chunk in tts.synthesizeStream(text)) {
    chunkCount++;
    final numSamples = chunk.length ~/ 2; // 16-bit = 2 bytes per sample
    final durationSec = numSamples / tts.sampleRate;
    print('  Chunk $chunkCount: $numSamples samples '
        '(${durationSec.toStringAsFixed(3)} sec)');
    pcmChunks.add(chunk);
  }

  // ------------------------------------------------------------------
  // 3. Concatenate chunks and write WAV
  // ------------------------------------------------------------------
  if (pcmChunks.isNotEmpty) {
    final totalBytes = pcmChunks.fold<int>(0, (s, c) => s + c.length);
    final allPcm = Uint8List(totalBytes);
    var offset = 0;
    for (final chunk in pcmChunks) {
      allPcm.setAll(offset, chunk);
      offset += chunk.length;
    }

    final totalSamples = totalBytes ~/ 2;
    final totalSec = totalSamples / tts.sampleRate;
    print('Done: $chunkCount chunks, $totalSamples samples '
        '(${totalSec.toStringAsFixed(2)} sec)');

    final wav = _buildWav(allPcm, tts.sampleRate);
    File(outputPath).writeAsBytesSync(wav);
    print('Saved: $outputPath');
  }

  // ------------------------------------------------------------------
  // 4. Clean up
  // ------------------------------------------------------------------
  tts.dispose();
  print('Done.');
}
