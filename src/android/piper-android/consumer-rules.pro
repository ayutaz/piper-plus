# Piper Android TTS - Consumer ProGuard Rules
# These rules are automatically applied to apps that depend on this library.

# Keep JNI native methods
-keepclasseswithmembers class com.github.ayousanz.piper.** {
    native <methods>;
}

# Keep public API classes
-keep public class com.github.ayousanz.piper.PiperTts { public *; }
-keep public class com.github.ayousanz.piper.PiperConfig { *; }
-keep public class com.github.ayousanz.piper.PiperAudio { *; }
-keep public class com.github.ayousanz.piper.PiperTtsService { public *; }

# Keep ONNX Runtime classes (uses reflection)
-keep class ai.onnxruntime.** { *; }
-dontwarn ai.onnxruntime.**
