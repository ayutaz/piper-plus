# Consumer ProGuard rules shipped inside the AAR.
# Applied automatically when an app depends on this library.

-keepclasseswithmembernames class com.piperplus.PiperPlusNative {
    native <methods>;
}

-keep class com.piperplus.PiperPlus { *; }
-keep class com.piperplus.PiperPlus$Companion { *; }
-keep class com.piperplus.PiperPlusException { *; }
