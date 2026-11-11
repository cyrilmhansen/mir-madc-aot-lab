# Header self-containment issue

`mir.h` declares a public function taking `va_list` but does not include `<stdarg.h>` first.

Minimal reproducer:

```c
#include "mir.h"
int main(void) { return 0; }
```

Command: `gcc -std=c11 -I madc/third_party/mir -x c -fsyntax-only -`.

Diagnostic: `madc/third_party/mir/mir.h:896:65: error: unknown type name ‘va_list’`; GCC notes that `va_list` is defined by `<stdarg.h>`. Clang 23.1.4 reports the same unknown type at line 896. Preincluding `<stdarg.h>` makes both compilers accept the header under strict C11.

This is an existing public-header self-containment issue, not an ABI execution mismatch. The pinned header was not modified and no external issue was opened.
