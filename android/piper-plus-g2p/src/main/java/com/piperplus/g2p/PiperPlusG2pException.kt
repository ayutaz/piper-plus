package com.piperplus.g2p

/**
 * Thrown when the underlying piper-plus G2P C API returns an error.
 *
 * The `message` carries the error string returned by
 * `piper_plus_get_last_error()` at the time the exception was thrown.
 * The optional `cause` lets callers chain a triggering exception
 * (e.g. an IOException from DictionaryDownloader) so stack traces
 * preserve the original failure.
 */
class PiperPlusG2pException(
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause)
