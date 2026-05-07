package com.piperplus.g2p

/**
 * Thrown when the underlying piper-plus G2P C API returns an error.
 *
 * The `message` carries the error string returned by
 * `piper_plus_get_last_error()` at the time the exception was thrown.
 */
class PiperPlusG2pException(message: String) : RuntimeException(message)
