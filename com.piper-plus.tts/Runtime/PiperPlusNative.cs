// PiperPlusNative.cs — P/Invoke declarations for libpiper_plus C API
// Auto-generated from piper_plus.h (API version 1)

using System;
using System.Runtime.InteropServices;

namespace PiperPlus
{
    /// <summary>
    /// Status codes returned by native piper-plus functions.
    /// </summary>
    public enum PiperPlusStatus : int
    {
        Ok        =  0,
        Done      =  1,
        Err       = -1,
        ErrModel  = -2,
        ErrConfig = -3,
        ErrText   = -4,
        ErrBusy   = -5,
        ErrOrt    = -6,
    }

    /// <summary>
    /// Engine configuration. Mirrors PiperPlusConfig from piper_plus.h.
    /// All fields must be zero-initialized before populating.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct PiperPlusConfig
    {
        public IntPtr model_path;      // const char* — UTF-8
        public IntPtr config_path;     // const char* — UTF-8, NULL = model_path + ".json"
        public IntPtr provider;        // const char* — "cpu","cuda","coreml","directml", NULL = "cpu"
        public int    num_threads;     // ONNX intra-op threads (0 = auto)
        public int    gpu_device_id;   // GPU device index (ignored for cpu)
        public IntPtr dict_dir;        // const char* — OpenJTalk dict dir, NULL = auto-detect

        // _reserved[7] — must be zero
        private int _reserved0;
        private int _reserved1;
        private int _reserved2;
        private int _reserved3;
        private int _reserved4;
        private int _reserved5;
        private int _reserved6;
    }

    /// <summary>
    /// Synthesis options. Mirrors PiperPlusSynthOptions from piper_plus.h.
    /// Zero-init safe: noise_scale, length_scale, noise_w of 0.0 use defaults.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct PiperPlusSynthOptions
    {
        public int   speaker_id;           // Speaker index (default: 0)
        public int   language_id;          // Language index (-1 = auto-detect)
        public float noise_scale;          // VITS noise_scale (default: 0.667)
        public float length_scale;         // VITS length_scale (default: 1.0)
        public float noise_w;              // VITS noise_w (default: 0.8)
        public float sentence_silence_sec; // Silence between sentences (default: 0.2)

        // _reserved[8] — must be zero
        private int _reserved0;
        private int _reserved1;
        private int _reserved2;
        private int _reserved3;
        private int _reserved4;
        private int _reserved5;
        private int _reserved6;
        private int _reserved7;
    }

    /// <summary>
    /// Audio chunk for streaming synthesis. Mirrors PiperPlusAudioChunk.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct PiperPlusAudioChunk
    {
        public IntPtr samples;       // const float* — BORROWED
        public int    num_samples;
        public int    sample_rate;
        public int    is_last;       // 1 if last chunk
    }

    /// <summary>
    /// Phoneme timing entry. Mirrors PiperPlusPhonemeInfo.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct PiperPlusPhonemeInfo
    {
        public IntPtr phoneme;     // const char* — BORROWED, UTF-8
        public float  start_time;
        public float  end_time;
    }

    /// <summary>
    /// Phoneme timing result. Mirrors PiperPlusTimingResult.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct PiperPlusTimingResult
    {
        public IntPtr entries;   // const PiperPlusPhonemeInfo*
        public int    count;
    }

    /// <summary>
    /// Phonemization result. Mirrors PiperPlusPhonemeResult.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct PiperPlusPhonemeResult
    {
        public IntPtr phonemes;       // const char* — BORROWED
        public IntPtr language;       // const char* — BORROWED
        public int    num_phonemes;
        private int   _reserved0;
        private int   _reserved1;
        private int   _reserved2;
        private int   _reserved3;
    }

    /// <summary>
    /// Streaming audio callback delegate.
    /// </summary>
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    internal delegate void PiperPlusAudioCallback(
        IntPtr samples,
        int    numSamples,
        int    sampleRate,
        IntPtr userData);

    /// <summary>
    /// Cancellable streaming audio callback delegate.
    /// Return 0 to continue, non-zero to abort.
    /// </summary>
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    internal delegate int PiperPlusAudioCallbackEx(
        IntPtr samples,
        int    numSamples,
        int    sampleRate,
        IntPtr userData);

    /// <summary>
    /// P/Invoke declarations for the piper-plus native shared library.
    /// Platform mapping: Windows=piper_plus, macOS/Linux=piper_plus (resolved via .dylib/.so).
    /// </summary>
    internal static class PiperPlusNative
    {
#if UNITY_IOS && !UNITY_EDITOR
        private const string LibName = "__Internal";
#else
        private const string LibName = "piper_plus";
#endif

        // ===== Version =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr piper_plus_version();

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int piper_plus_api_version();

        // ===== Error =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr piper_plus_get_last_error();

        // ===== Lifecycle =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_create(
            ref PiperPlusConfig config,
            out IntPtr outEngine);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void piper_plus_free(IntPtr engine);

        // ===== Default options =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusSynthOptions piper_plus_default_options();

        // ===== One-shot synthesis =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_synthesize(
            IntPtr engine,
            IntPtr text,                    // const char* UTF-8
            ref PiperPlusSynthOptions opts,
            out IntPtr outSamples,          // float**
            out int outNumSamples,
            out int outSampleRate);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void piper_plus_free_audio(IntPtr samples);

        // ===== Query =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int piper_plus_sample_rate(IntPtr engine);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int piper_plus_num_speakers(IntPtr engine);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int piper_plus_num_languages(IntPtr engine);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int piper_plus_language_id(
            IntPtr engine,
            IntPtr languageName);          // const char* UTF-8

        // ===== Iterator pattern =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_synth_start(
            IntPtr engine,
            IntPtr text,                   // const char* UTF-8
            ref PiperPlusSynthOptions opts);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_synth_next(
            IntPtr engine,
            out PiperPlusAudioChunk outChunk);

        // ===== Streaming callback =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_synthesize_streaming(
            IntPtr engine,
            IntPtr text,
            ref PiperPlusSynthOptions opts,
            PiperPlusAudioCallback callback,
            IntPtr userData);

        // ===== Cancellable streaming =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_synthesize_streaming_ex(
            IntPtr engine,
            IntPtr text,
            ref PiperPlusSynthOptions opts,
            PiperPlusAudioCallbackEx callback,
            IntPtr userData);

        // ===== Custom dictionary =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_load_custom_dict(
            IntPtr engine,
            IntPtr dictPath);              // const char* UTF-8

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_clear_custom_dict(IntPtr engine);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_add_dict_word(
            IntPtr engine,
            IntPtr word,                   // const char* UTF-8
            IntPtr pronunciation,          // const char* UTF-8
            int priority);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int piper_plus_dict_entry_count(IntPtr engine);

        // ===== Phoneme timing =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_get_phoneme_timing(
            IntPtr engine,
            out PiperPlusTimingResult outTiming);

        // ===== G2P / Phonemization =====

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern PiperPlusStatus piper_plus_phonemize(
            IntPtr engine,
            IntPtr text,                   // const char* UTF-8
            IntPtr language,               // const char* UTF-8, NULL = auto-detect
            out PiperPlusPhonemeResult outResult);

        [DllImport(LibName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr piper_plus_available_languages(IntPtr engine);
    }

    /// <summary>
    /// Helper for UTF-8 string marshalling between managed and native code.
    /// </summary>
    internal static class Utf8Marshaller
    {
        /// <summary>
        /// Allocate a native UTF-8 string from a managed string.
        /// Returns IntPtr.Zero for null input.
        /// Caller must free the returned pointer with Marshal.FreeHGlobal.
        /// </summary>
        public static IntPtr StringToUtf8(string managed)
        {
            if (managed == null)
                return IntPtr.Zero;

            byte[] utf8 = System.Text.Encoding.UTF8.GetBytes(managed);
            IntPtr ptr = Marshal.AllocHGlobal(utf8.Length + 1);
            Marshal.Copy(utf8, 0, ptr, utf8.Length);
            Marshal.WriteByte(ptr, utf8.Length, 0); // NUL terminator
            return ptr;
        }

        /// <summary>
        /// Read a native UTF-8 string into a managed string.
        /// Returns null for IntPtr.Zero.
        /// Does NOT free the native pointer.
        /// </summary>
        public static string Utf8ToString(IntPtr native)
        {
            if (native == IntPtr.Zero)
                return null;

            // Find the NUL terminator to determine length
            int len = 0;
            while (Marshal.ReadByte(native, len) != 0)
                len++;

            if (len == 0)
                return string.Empty;

            byte[] utf8 = new byte[len];
            Marshal.Copy(native, utf8, 0, len);
            return System.Text.Encoding.UTF8.GetString(utf8);
        }
    }
}
