// ignore_for_file: non_constant_identifier_names, camel_case_types
// ignore_for_file: constant_identifier_names

/// Hand-written skeleton matching the piper_plus.h C API.
///
/// In production, regenerate with:
///   dart run ffigen --config ffigen.yaml
///
/// This file covers the primary API surface. Run ffigen to get the complete
/// bindings including M4 features (custom dict, phoneme timing, G2P).
library;

import 'dart:ffi';

// ---------------------------------------------------------------------------
// Status codes
// ---------------------------------------------------------------------------

/// Maps to enum PiperPlusStatus in piper_plus.h.
abstract final class PiperPlusStatus {
  static const int ok = 0;
  static const int done = 1;
  static const int err = -1;
  static const int errModel = -2;
  static const int errConfig = -3;
  static const int errText = -4;
  static const int errBusy = -5;
  static const int errOrt = -6;
}

// ---------------------------------------------------------------------------
// Opaque engine handle
// ---------------------------------------------------------------------------

/// Opaque C struct. Never instantiate directly.
final class PiperPlusEngine extends Opaque {}

// ---------------------------------------------------------------------------
// Config structs (POD, memset-safe)
// ---------------------------------------------------------------------------

/// Maps to PiperPlusConfig in piper_plus.h.
final class PiperPlusConfig extends Struct {
  external Pointer<Utf8> model_path;
  external Pointer<Utf8> config_path;
  external Pointer<Utf8> provider;

  @Int32()
  external int num_threads;

  @Int32()
  external int gpu_device_id;

  external Pointer<Utf8> dict_dir;

  @Array(7)
  external Array<Int32> _reserved;
}

/// Maps to PiperPlusSynthOptions in piper_plus.h.
final class PiperPlusSynthOptions extends Struct {
  @Int32()
  external int speaker_id;

  @Int32()
  external int language_id;

  @Float()
  external double noise_scale;

  @Float()
  external double length_scale;

  @Float()
  external double noise_w;

  @Float()
  external double sentence_silence_sec;

  @Array(8)
  external Array<Int32> _reserved;
}

/// Maps to PiperPlusAudioChunk in piper_plus.h.
final class PiperPlusAudioChunk extends Struct {
  external Pointer<Float> samples;

  @Int32()
  external int num_samples;

  @Int32()
  external int sample_rate;

  @Int32()
  external int is_last;
}

// ---------------------------------------------------------------------------
// Callback typedefs
// ---------------------------------------------------------------------------

/// void (*PiperPlusAudioCallback)(const float*, int32_t, int32_t, void*)
typedef PiperPlusAudioCallbackNative = Void Function(
    Pointer<Float>, Int32, Int32, Pointer<Void>);
typedef PiperPlusAudioCallbackDart = void Function(
    Pointer<Float>, int, int, Pointer<Void>);

/// int (*PiperPlusAudioCallbackEx)(const float*, int32_t, int32_t, void*)
typedef PiperPlusAudioCallbackExNative = Int32 Function(
    Pointer<Float>, Int32, Int32, Pointer<Void>);

// ---------------------------------------------------------------------------
// Native function typedefs
// ---------------------------------------------------------------------------

// -- Version
typedef _VersionC = Pointer<Utf8> Function();
typedef _VersionDart = Pointer<Utf8> Function();

typedef _ApiVersionC = Int32 Function();
typedef _ApiVersionDart = int Function();

// -- Error
typedef _GetLastErrorC = Pointer<Utf8> Function();
typedef _GetLastErrorDart = Pointer<Utf8> Function();

// -- Lifecycle
typedef _CreateC = Int32 Function(
    Pointer<PiperPlusConfig>, Pointer<Pointer<PiperPlusEngine>>);
typedef _CreateDart = int Function(
    Pointer<PiperPlusConfig>, Pointer<Pointer<PiperPlusEngine>>);

typedef _FreeC = Void Function(Pointer<PiperPlusEngine>);
typedef _FreeDart = void Function(Pointer<PiperPlusEngine>);

// -- Default options
typedef _DefaultOptionsC = PiperPlusSynthOptions Function();
typedef _DefaultOptionsDart = PiperPlusSynthOptions Function();

// -- One-shot synthesis
typedef _SynthesizeC = Int32 Function(
    Pointer<PiperPlusEngine>,
    Pointer<Utf8>,
    Pointer<PiperPlusSynthOptions>,
    Pointer<Pointer<Float>>,
    Pointer<Int32>,
    Pointer<Int32>);
typedef _SynthesizeDart = int Function(
    Pointer<PiperPlusEngine>,
    Pointer<Utf8>,
    Pointer<PiperPlusSynthOptions>,
    Pointer<Pointer<Float>>,
    Pointer<Int32>,
    Pointer<Int32>);

typedef _FreeAudioC = Void Function(Pointer<Float>);
typedef _FreeAudioDart = void Function(Pointer<Float>);

// -- Query
typedef _SampleRateC = Int32 Function(Pointer<PiperPlusEngine>);
typedef _SampleRateDart = int Function(Pointer<PiperPlusEngine>);

typedef _NumSpeakersC = Int32 Function(Pointer<PiperPlusEngine>);
typedef _NumSpeakersDart = int Function(Pointer<PiperPlusEngine>);

typedef _NumLanguagesC = Int32 Function(Pointer<PiperPlusEngine>);
typedef _NumLanguagesDart = int Function(Pointer<PiperPlusEngine>);

typedef _LanguageIdC = Int32 Function(
    Pointer<PiperPlusEngine>, Pointer<Utf8>);
typedef _LanguageIdDart = int Function(
    Pointer<PiperPlusEngine>, Pointer<Utf8>);

// -- Streaming callback
typedef _SynthesizeStreamingC = Int32 Function(
    Pointer<PiperPlusEngine>,
    Pointer<Utf8>,
    Pointer<PiperPlusSynthOptions>,
    Pointer<NativeFunction<PiperPlusAudioCallbackNative>>,
    Pointer<Void>);
typedef _SynthesizeStreamingDart = int Function(
    Pointer<PiperPlusEngine>,
    Pointer<Utf8>,
    Pointer<PiperPlusSynthOptions>,
    Pointer<NativeFunction<PiperPlusAudioCallbackNative>>,
    Pointer<Void>);

// -- Iterator pattern
typedef _SynthStartC = Int32 Function(
    Pointer<PiperPlusEngine>,
    Pointer<Utf8>,
    Pointer<PiperPlusSynthOptions>);
typedef _SynthStartDart = int Function(
    Pointer<PiperPlusEngine>,
    Pointer<Utf8>,
    Pointer<PiperPlusSynthOptions>);

typedef _SynthNextC = Int32 Function(
    Pointer<PiperPlusEngine>, Pointer<PiperPlusAudioChunk>);
typedef _SynthNextDart = int Function(
    Pointer<PiperPlusEngine>, Pointer<PiperPlusAudioChunk>);

// ---------------------------------------------------------------------------
// Bindings class
// ---------------------------------------------------------------------------

/// Low-level FFI bindings to libpiper_plus.
///
/// Usage:
/// ```dart
/// final lib = DynamicLibrary.open('libpiper_plus.so');
/// final bindings = PiperPlusBindings(lib);
/// ```
class PiperPlusBindings {
  final DynamicLibrary _lib;

  PiperPlusBindings(this._lib);

  // -- Version -----------------------------------------------------------

  late final piper_plus_version =
      _lib.lookupFunction<_VersionC, _VersionDart>('piper_plus_version');

  late final piper_plus_api_version =
      _lib.lookupFunction<_ApiVersionC, _ApiVersionDart>(
          'piper_plus_api_version');

  // -- Error -------------------------------------------------------------

  late final piper_plus_get_last_error =
      _lib.lookupFunction<_GetLastErrorC, _GetLastErrorDart>(
          'piper_plus_get_last_error');

  // -- Lifecycle ---------------------------------------------------------

  late final piper_plus_create =
      _lib.lookupFunction<_CreateC, _CreateDart>('piper_plus_create');

  late final piper_plus_free =
      _lib.lookupFunction<_FreeC, _FreeDart>('piper_plus_free');

  // -- Default options ---------------------------------------------------

  late final piper_plus_default_options =
      _lib.lookupFunction<_DefaultOptionsC, _DefaultOptionsDart>(
          'piper_plus_default_options');

  // -- One-shot synthesis ------------------------------------------------

  late final piper_plus_synthesize =
      _lib.lookupFunction<_SynthesizeC, _SynthesizeDart>(
          'piper_plus_synthesize');

  late final piper_plus_free_audio =
      _lib.lookupFunction<_FreeAudioC, _FreeAudioDart>(
          'piper_plus_free_audio');

  // -- Query -------------------------------------------------------------

  late final piper_plus_sample_rate =
      _lib.lookupFunction<_SampleRateC, _SampleRateDart>(
          'piper_plus_sample_rate');

  late final piper_plus_num_speakers =
      _lib.lookupFunction<_NumSpeakersC, _NumSpeakersDart>(
          'piper_plus_num_speakers');

  late final piper_plus_num_languages =
      _lib.lookupFunction<_NumLanguagesC, _NumLanguagesDart>(
          'piper_plus_num_languages');

  late final piper_plus_language_id =
      _lib.lookupFunction<_LanguageIdC, _LanguageIdDart>(
          'piper_plus_language_id');

  // -- Streaming callback ------------------------------------------------

  late final piper_plus_synthesize_streaming =
      _lib.lookupFunction<_SynthesizeStreamingC, _SynthesizeStreamingDart>(
          'piper_plus_synthesize_streaming');

  // -- Iterator pattern --------------------------------------------------

  late final piper_plus_synth_start =
      _lib.lookupFunction<_SynthStartC, _SynthStartDart>(
          'piper_plus_synth_start');

  late final piper_plus_synth_next =
      _lib.lookupFunction<_SynthNextC, _SynthNextDart>(
          'piper_plus_synth_next');
}
