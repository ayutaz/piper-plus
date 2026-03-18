# Piper Android TTS - Consumer ProGuard Rules
# These rules are automatically applied to apps that depend on this library.

# Keep JNI native methods
-keepclasseswithmembers class com.github.ayousanz.piper.** {
    native <methods>;
}

# Keep NativeBridge (prevents obfuscation breaking JNI name mangling)
-keep class com.github.ayousanz.piper.internal.NativeBridge { *; }

# Keep public API classes
-keep public class com.github.ayousanz.piper.PiperTts { public *; }
-keep public class com.github.ayousanz.piper.PiperConfig { *; }
-keep public class com.github.ayousanz.piper.PiperAudio { *; }
-keep class com.github.ayousanz.piper.AudioPlayer { public *; }
-keep class com.github.ayousanz.piper.ModelManager { public *; }
-keep class com.github.ayousanz.piper.ModelManager$ModelInfo { public *; }

# Keep Android TTS service component
-keep class com.github.ayousanz.piper.PiperTtsService { *; }

# Keep ONNX Runtime classes (uses reflection)
-keep class ai.onnxruntime.** { *; }
-dontwarn ai.onnxruntime.**
