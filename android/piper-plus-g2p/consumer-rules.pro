# Consumer ProGuard rules for piper-plus-g2p (Android G2P AAR).
# These rules are merged into the consuming app's R8 configuration.

# Keep all Kotlin public API surfaces.
-keep class com.piperplus.g2p.** { *; }
-keepclasseswithmembers class com.piperplus.g2p.** { native <methods>; }

# Keep our exception class for reflection-friendly error messages.
-keep class com.piperplus.g2p.PiperPlusG2pException { *; }
