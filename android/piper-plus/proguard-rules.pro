# Keep JNI native methods from being removed or renamed by R8/ProGuard.
-keepclasseswithmembernames class com.piperplus.PiperPlusNative {
    native <methods>;
}

# Keep the companion object factory used via reflection in some DI setups.
-keep class com.piperplus.PiperPlus$Companion { *; }
