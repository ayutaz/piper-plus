# JNI から参照されるクラスは難読化しない
-keep class com.piperplus.PiperPlusNative { *; }
-keep class com.piperplus.PiperPlusException { *; }
