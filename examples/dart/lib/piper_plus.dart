/// High-level Dart wrapper for the piper-plus C API.
///
/// Provides a safe, idiomatic Dart interface over the raw FFI bindings.
///
/// ```dart
/// final tts = PiperPlus.load(
///   libraryPath: 'libpiper_plus.so',
///   modelPath: 'model.onnx',
/// );
/// final wav = tts.synthesize('Hello world.');
/// File('output.wav').writeAsBytesSync(wav);
/// tts.dispose();
/// ```
library;

import 'dart:async';
import 'dart:ffi';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';

import 'piper_plus_bindings.dart';

/// Exception thrown when a piper-plus C API call fails.
class PiperPlusException implements Exception {
  final int statusCode;
  final String message;

  PiperPlusException(this.statusCode, this.message);

  @override
  String toString() => 'PiperPlusException($statusCode): $message';
}

/// High-level wrapper around the piper-plus C shared library.
///
/// Call [dispose] when done to release native resources.
class PiperPlus {
  final PiperPlusBindings _bindings;
  Pointer<PiperPlusEngine>? _engine;

  PiperPlus._(this._bindings, this._engine);

  /// Load the shared library and create an engine.
  ///
  /// [libraryPath] is the path to the piper-plus shared library:
  /// - Linux: `libpiper_plus.so`
  /// - macOS: `libpiper_plus.dylib`
  /// - Windows: `piper_plus.dll`
  ///
  /// [modelPath] is the path to the `.onnx` model file (required).
  /// [configPath] overrides the config JSON path (default: modelPath + ".json").
  /// [dictDir] overrides the OpenJTalk dictionary directory (default: auto-detect).
  /// [provider] selects the ONNX Runtime execution provider
  /// (`"cpu"`, `"cuda"`, `"coreml"`, `"directml"`).
  factory PiperPlus.load({
    required String libraryPath,
    required String modelPath,
    String? configPath,
    String? dictDir,
    String provider = 'cpu',
  }) {
    final lib = DynamicLibrary.open(libraryPath);
    final bindings = PiperPlusBindings(lib);

    // Allocate and populate PiperPlusConfig
    final config = calloc<PiperPlusConfig>();
    config.ref.model_path = modelPath.toNativeUtf8();
    config.ref.config_path =
        configPath != null ? configPath.toNativeUtf8() : nullptr;
    config.ref.provider = provider.toNativeUtf8();
    config.ref.dict_dir = dictDir != null ? dictDir.toNativeUtf8() : nullptr;
    config.ref.num_threads = 0;
    config.ref.gpu_device_id = 0;

    // Create engine
    final enginePtr = calloc<Pointer<PiperPlusEngine>>();
    final rc = bindings.piper_plus_create(config, enginePtr);

    final engine = enginePtr.value;

    // Free temporaries (C API copies the strings it needs)
    calloc.free(config.ref.model_path);
    if (configPath != null) calloc.free(config.ref.config_path);
    calloc.free(config.ref.provider);
    if (dictDir != null) calloc.free(config.ref.dict_dir);
    calloc.free(enginePtr);
    calloc.free(config);

    if (rc != PiperPlusStatus.ok) {
      final msg = bindings.piper_plus_get_last_error().toDartString();
      throw PiperPlusException(rc, msg);
    }

    return PiperPlus._(bindings, engine);
  }

  /// The library version string.
  String get version => _bindings.piper_plus_version().toDartString();

  /// The C API version number.
  int get apiVersion => _bindings.piper_plus_api_version();

  /// Native sample rate of the loaded model (Hz).
  int get sampleRate {
    _ensureNotDisposed();
    return _bindings.piper_plus_sample_rate(_engine!);
  }

  /// Number of speakers in the loaded model.
  int get numSpeakers {
    _ensureNotDisposed();
    return _bindings.piper_plus_num_speakers(_engine!);
  }

  /// Number of languages in the loaded model.
  int get numLanguages {
    _ensureNotDisposed();
    return _bindings.piper_plus_num_languages(_engine!);
  }

  /// Resolve a language name (e.g. "ja", "en") to its numeric ID.
  /// Returns -1 if not found.
  int languageId(String name) {
    _ensureNotDisposed();
    final namePtr = name.toNativeUtf8();
    final id = _bindings.piper_plus_language_id(_engine!, namePtr);
    calloc.free(namePtr);
    return id;
  }

  /// Synthesize text to a WAV byte buffer (16-bit PCM mono).
  ///
  /// Returns the complete WAV file as [Uint8List].
  Uint8List synthesize(
    String text, {
    int speakerId = 0,
    int languageId = -1,
    double noiseScale = 0.0,
    double lengthScale = 0.0,
    double noiseW = 0.0,
  }) {
    _ensureNotDisposed();

    final textPtr = text.toNativeUtf8();
    final opts = calloc<PiperPlusSynthOptions>();
    opts.ref.speaker_id = speakerId;
    opts.ref.language_id = languageId;
    opts.ref.noise_scale = noiseScale;
    opts.ref.length_scale = lengthScale;
    opts.ref.noise_w = noiseW;

    final outSamples = calloc<Pointer<Float>>();
    final outNumSamples = calloc<Int32>();
    final outSampleRate = calloc<Int32>();

    try {
      final rc = _bindings.piper_plus_synthesize(
        _engine!,
        textPtr,
        opts,
        outSamples,
        outNumSamples,
        outSampleRate,
      );

      if (rc != PiperPlusStatus.ok) {
        final msg = _bindings.piper_plus_get_last_error().toDartString();
        throw PiperPlusException(rc, msg);
      }

      final numSamples = outNumSamples.value;
      final sr = outSampleRate.value;
      final samplesPtr = outSamples.value;

      // Copy float samples and convert to WAV
      final floats = samplesPtr.asTypedList(numSamples);
      final wav = _encodeWav(floats, sr);

      // Free native audio buffer
      _bindings.piper_plus_free_audio(samplesPtr);

      return wav;
    } finally {
      calloc.free(textPtr);
      calloc.free(opts);
      calloc.free(outSamples);
      calloc.free(outNumSamples);
      calloc.free(outSampleRate);
    }
  }

  /// Synthesize text with streaming, yielding raw PCM chunks via a [Stream].
  ///
  /// Each emitted [Uint8List] contains raw 16-bit PCM samples (no WAV header)
  /// for one sentence. Collect all chunks and prepend a WAV header to produce
  /// a complete file, or feed chunks directly to an audio player.
  ///
  /// Uses [NativeCallable.listener] (Dart 3.1+) to bridge the C callback
  /// into a Dart [Stream].
  ///
  /// **Important:** Do not call [dispose] while this stream is active.
  /// The stream completes synchronously (within a microtask) so disposal
  /// after awaiting the stream is safe.
  Stream<Uint8List> synthesizeStream(
    String text, {
    int speakerId = 0,
    int languageId = -1,
    double noiseScale = 0.0,
    double lengthScale = 0.0,
    double noiseW = 0.0,
  }) {
    _ensureNotDisposed();

    final controller = StreamController<Uint8List>();

    // IMPORTANT: NativeCallable lifetime management.
    //
    // The NativeCallable must be stored in a local variable so it is not
    // garbage-collected before the C callback completes.  The variable
    // `nativeCallback` is captured by the closures below, which keeps it
    // alive for the duration of the microtask.  We call `.close()` in the
    // `finally` block after piper_plus_synthesize_streaming returns, which
    // guarantees the native trampoline is released exactly once and only
    // after all callback invocations have finished (the C function is
    // synchronous and invokes all callbacks before returning).
    late final NativeCallable<PiperPlusAudioCallbackNative> nativeCallback;

    nativeCallback = NativeCallable<PiperPlusAudioCallbackNative>.listener(
      (Pointer<Float> samples, int numSamples, int sr, Pointer<Void> _) {
        // Copy samples before the pointer becomes invalid.
        // The C API only guarantees the samples pointer is valid for the
        // duration of this callback invocation.
        final floats = samples.asTypedList(numSamples);
        final pcm = _floatToPcm16(floats);
        controller.add(pcm);
      },
    );

    // Run synthesis in a microtask so the stream is returned immediately.
    // Note: piper_plus_synthesize_streaming is synchronous on the C side
    // and invokes the callback on the caller's thread.  In a real Flutter
    // app you would run this in an Isolate.  Here we use scheduleMicrotask
    // for simplicity so the caller can listen to the stream first.
    // Capture the engine pointer at scheduling time so that a concurrent
    // dispose() does not leave us with a dangling pointer.
    final engine = _engine;
    scheduleMicrotask(() {
      if (engine == null || _engine == null) {
        controller.addError(StateError('PiperPlus engine has been disposed'));
        nativeCallback.close();
        controller.close();
        return;
      }
      final textPtr = text.toNativeUtf8();
      final opts = calloc<PiperPlusSynthOptions>();
      opts.ref.speaker_id = speakerId;
      opts.ref.language_id = languageId;
      opts.ref.noise_scale = noiseScale;
      opts.ref.length_scale = lengthScale;
      opts.ref.noise_w = noiseW;

      try {
        final rc = _bindings.piper_plus_synthesize_streaming(
          engine,
          textPtr,
          opts,
          nativeCallback.nativeFunction,
          nullptr,
        );

        if (rc != PiperPlusStatus.ok) {
          final msg = _bindings.piper_plus_get_last_error().toDartString();
          controller.addError(PiperPlusException(rc, msg));
        }
      } catch (e) {
        controller.addError(e);
      } finally {
        nativeCallback.close();
        controller.close();
        calloc.free(textPtr);
        calloc.free(opts);
      }
    });

    return controller.stream;
  }

  /// Release all native resources.
  ///
  /// After calling [dispose], no other methods may be called.
  void dispose() {
    if (_engine != null) {
      _bindings.piper_plus_free(_engine!);
      _engine = null;
    }
  }

  // -----------------------------------------------------------------------
  // Private helpers
  // -----------------------------------------------------------------------

  void _ensureNotDisposed() {
    if (_engine == null) {
      throw StateError('PiperPlus engine has been disposed');
    }
  }

  /// Convert float32 samples [-1, 1] to 16-bit signed PCM bytes (LE).
  static Uint8List _floatToPcm16(Float32List floats) {
    final pcm = ByteData(floats.length * 2);
    for (var i = 0; i < floats.length; i++) {
      var s = floats[i];
      if (s > 1.0) s = 1.0;
      if (s < -1.0) s = -1.0;
      pcm.setInt16(i * 2, (s * 32767).toInt(), Endian.little);
    }
    return pcm.buffer.asUint8List();
  }

  /// Encode float32 samples as a complete WAV file (16-bit PCM mono).
  static Uint8List _encodeWav(Float32List samples, int sampleRate) {
    final numSamples = samples.length;
    final dataSize = numSamples * 2;
    final fileSize = 36 + dataSize;

    final buf = ByteData(44 + dataSize);
    var offset = 0;

    // RIFF header
    void writeAscii(String s) {
      for (var i = 0; i < s.length; i++) {
        buf.setUint8(offset++, s.codeUnitAt(i));
      }
    }

    writeAscii('RIFF');
    buf.setUint32(offset, fileSize, Endian.little);
    offset += 4;
    writeAscii('WAVE');

    // fmt chunk
    writeAscii('fmt ');
    buf.setUint32(offset, 16, Endian.little);
    offset += 4; // chunk size
    buf.setUint16(offset, 1, Endian.little);
    offset += 2; // PCM
    buf.setUint16(offset, 1, Endian.little);
    offset += 2; // mono
    buf.setUint32(offset, sampleRate, Endian.little);
    offset += 4;
    buf.setUint32(offset, sampleRate * 2, Endian.little);
    offset += 4; // byte rate
    buf.setUint16(offset, 2, Endian.little);
    offset += 2; // block align
    buf.setUint16(offset, 16, Endian.little);
    offset += 2; // bits per sample

    // data chunk
    writeAscii('data');
    buf.setUint32(offset, dataSize, Endian.little);
    offset += 4;

    // PCM samples
    for (var i = 0; i < numSamples; i++) {
      var s = samples[i];
      if (s > 1.0) s = 1.0;
      if (s < -1.0) s = -1.0;
      buf.setInt16(offset, (s * 32767).toInt(), Endian.little);
      offset += 2;
    }

    return buf.buffer.asUint8List();
  }
}
