package com.piperplus

/**
 * Exception thrown when a piper-plus native operation fails.
 *
 * The [message] contains the error string from `piper_plus_get_last_error()`.
 */
class PiperPlusException(message: String) : RuntimeException(message)
