# Audit and build provenance

- Root HEAD at start: `c57ffbbe7e08b80e51758f5ba8af582f9de24345`; branch `experiment/mir-aot-correctness-cycle3`.
- MADC submodule: `868847a76434058483bade03ead09ba6acb9d771`, clean; no checkout change, update, reset or rebuild was performed.
- Historical expected MADC pin: `f541a7a54624869e29b01f2f30b174bc0329eea5`.
- MIR subtree tree hash at current checkout: `a635f2d12959ceda27c31e6a440aa273e76ab9a0`. Cycle42 recorded this subtree as byte-identical to the historical pin.
- Current archive: `madc/obj/mir/host/libmir.a`, SHA-256 `a1e6f02f014b11796dadcc3628e369a3c0bb0039c604b6fe8b36c8a081f52bb8`. Its exact provenance from a clean build is not known; results are qualified to this archive and these headers.
- Headers: `mir.h` `00d834c862090a521d9d222bfebc6a3e74e7ff334666223ddce75ea9d66fe3a3`; `mir-gen.h` `c49715429dd4334dd9a57cae6b9bb14a124adc4a5052df07f171039addc4ae63`; `mir-debug.h` `079a1aaf71084eef60ce008d5328ee343f602e2df4b046352ac7c9a73a490c96`.
- Host: Linux x86-64, GCC `cc 16.2.1 20260810`, Clang `23.1.4`, GNU ld `2.47`, Python `3.14.8`.
- Primary flags: `-std=gnu11 -O2 -Wall -Wextra -Werror -I madc/third_party/mir`; links `libmir.a -lm -ldl -lpthread`. UBSan used `-O1 -g -fsanitize=undefined -fno-sanitize-recover=all`. The MIR header's `va_list` defect requires GNU mode or explicit `<stdarg.h>` preinclude for strict C11 probes.

Cycle42 API inventory was reused rather than regenerated from another MIR release. It found 181 declared names including inline helpers and 171 exported archive symbols; `MIR_get_global_item` was the non-inline declaration without an archive definition. The inventory records header declaration, archive export and current-target distinctions. Cycle43 exercised the public APIs listed in `ARCHITECTURE.md`.

The original Cycle42 353-case corpus was rerun against this exact available archive. Direct, text and binary streams each passed 353 rows and were byte-identical. This is a rerun, not a claim that the archive was rebuilt from the historical submodule pin.
