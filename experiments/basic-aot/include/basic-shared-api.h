#ifndef BASIC_SHARED_API_H
#define BASIC_SHARED_API_H

#include <stddef.h>

/* Call init before using exports that execute BASIC runtime operations. */
void basic_module_init(void);
void basic_module_fini(void);

/*
 * BASIC_UPPER takes a borrowed NUL-terminated byte string; NULL returns NULL.
 * The returned string is a separate malloc allocation owned by the caller and
 * remains valid across basic_module_fini() and dlclose(). Release it with
 * free() after dlclose(), or basic_string_free() while the DSO is loaded.
 * Wrappers explicitly declared pool-owned release the internal BASIC result
 * after copying; borrowed-result wrappers leave it untouched. Embedded NUL
 * bytes are not representable;
 * conversion follows the BASIC runtime's byte/locale behavior, not Unicode.
 */
char *BASIC_UPPER(const char *text);
char *BASIC_LITERAL(const char *text);
char *BASIC_ECHO(const char *text);
char *BASIC_LOCAL(const char *text);
char *BASIC_CONCAT(const char *left, const char *right);
char *BASIC_EMPTY(const char *text);
char *BASIC_BORROWED(const char *text);
void basic_string_free(char *text);

#endif
