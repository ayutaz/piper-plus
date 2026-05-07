package com.piperplus.g2p

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * L1: lightweight reflection-only checks against [PiperPlusG2pNative].
 *
 * The JNI methods cannot be invoked in pure JVM (`UnsatisfiedLinkError` —
 * no `libpiper_plus_g2p_jni.so` on the test classpath), so this test only
 * verifies the **shape** of the bridge: that every external method the
 * Kotlin wrapper relies on is declared with the right signature.
 *
 * If any of these names or signatures change, [PiperPlusG2p] will fail to
 * link at runtime. Catching it at L1 prevents a Pixel 6 emulator round-trip
 * just to discover a typo.
 */
class PiperPlusG2pNativeTest {

    @Test
    fun `expected external methods are declared`() {
        val klass: Class<*> = PiperPlusG2pNative::class.java
        val methods = klass.declaredMethods.associateBy { it.name }

        val expected = setOf(
            "nativeCreate",
            "nativeFree",
            "nativePhonemize",
            "nativeAvailableLanguages",
            "nativeLoadCustomDict",
            "nativeSetZhEnDispatch",
            "nativeIsZhEnDispatchEnabled",
            "nativeVersion",
        )
        val missing = expected - methods.keys
        assertEquals("missing native bridge methods: $missing", emptySet<String>(), missing)
    }

    @Test
    fun `nativePhonemize returns String array`() {
        val m = PiperPlusG2pNative::class.java.getDeclaredMethod(
            "nativePhonemize",
            Long::class.javaPrimitiveType,
            String::class.java,
            String::class.java,
        )
        // The JNI side returns String[3]; downstream code indexes into it
        // (triple[0], [1], [2]) so this must remain an array.
        assertEquals(Array<String>::class.java, m.returnType)
    }

    @Test
    fun `nativeFree takes a single long handle`() {
        val m = PiperPlusG2pNative::class.java.getDeclaredMethod(
            "nativeFree",
            Long::class.javaPrimitiveType,
        )
        assertEquals(Void.TYPE, m.returnType)
    }
}
