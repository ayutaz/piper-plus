#ifndef LIBRARY_PATH_H_
#define LIBRARY_PATH_H_

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Get the directory containing the piper-plus shared library.
 * Uses dladdr (Unix) or GetModuleHandleEx (Windows).
 *
 * @param buf    Output buffer for the directory path
 * @param size   Buffer size in bytes
 * @return 0 on success, -1 on failure
 */
int piper_plus_get_library_dir(char *buf, int size);

#ifdef __cplusplus
}
#endif

#endif /* LIBRARY_PATH_H_ */
