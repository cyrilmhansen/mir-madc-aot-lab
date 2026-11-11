# Upstream-ready note: `mir.h` is not self-contained under strict C11

**Status:** reproduced locally; no issue filed and no upstream source changed.

**Affected file:** `madc/third_party/mir/mir.h`, declaration around line 896.

The header declares a function parameter of type `va_list` but does not include `<stdarg.h>`. A translation unit that directly includes `mir.h` under strict C11 fails unless its includer happened to include `<stdarg.h>` first.

Minimal reproducer (`experiments/mir-api-coverage/header-probe.c`):

```c
#include "mir.h"
int main(void) { return 0; }
```

Commands:

```sh
cc -std=c11 -fsyntax-only -I madc/third_party/mir experiments/mir-api-coverage/header-probe.c
clang -std=c11 -fsyntax-only -I madc/third_party/mir experiments/mir-api-coverage/header-probe.c
```

GCC 16.2.1 diagnostic: `mir.h:896:65: error: unknown type name 'va_list'`, with its note that `va_list` is defined in `<stdarg.h>`. Clang 23.1.4 reports the same unknown type at line 896. Both commands pass with `-include stdarg.h`.

Likely minimal header correction for upstream consideration: include `<stdarg.h>` before the declaration uses `va_list`. This record is not a patch proposal or external report. Full compiler commands/diagnostics are preserved in `header-probes.json`.
