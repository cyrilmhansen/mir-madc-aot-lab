# libmpdec 4.0.1 `mpd_qnew()` root-cause investigation

## Finding

The first semantic loss is in MADC's C parser/CIR construction, before c2mir,
MIR linking/inlining, or native code generation. The `-DASM` libmpdec build uses
GNU extended inline assembly in `_mpd_mul_words()` (`typearith.h:206`): the
`mulq` template defines the `h` and `l` outputs. MADC does not implement
non-empty GNU asm templates. Its `Program::skip_gnu_asm_statement()` in
`madc/src/parser.cpp` parses the operands, then lowers their evaluation to a
comma expression; the template is discarded and output constraints are not
emulated. Thus the source's `h` and `l` definitions are absent from CIR.

The MIR emitted from that CIR confirms the consequence:

```mir
_mpd_mul_words: func u64:U0_hi, u64:U0_lo, u64:U0_a, u64:U0_b
  local i64:U0_h, i64:U0_l
  mov u64:(U0_hi):L, U0_h
  mov u64:(U0_lo):L, U0_l
  ret
```

`U0_h` and `U0_l` are read without definitions. That is the first point where
the intended C/asm computation has been lost. GCC's and Clang's outputs for the
same source are correct. The inliner is not the root cause: inlining propagates
the undefined overflow flag into `mpd_qnew_size`, where its native code happens
to test `RSI`; disabling only MIR inlining changes that code and argument
passing, but the allocation still fails because `_mpd_mul_words` remains
undefined.

The standalone `c2m` frontend rejects the same input with `non-empty asm
statements are not implemented` and `asm output operands are not implemented`.
This comparison separates MADC's parser behavior from c2mir and MIR: MADC's
front end discards semantics that c2mir itself refuses to compile.

No MADC code change is claimed. Implementing GNU extended asm is outside a
minimal correction; silently treating a non-empty asm template as an empty
template is the limitation demonstrated here. A supported libmpdec C fallback
(`-DANSI -DHAVE_UINT128_T`, with `CONFIG_64`) does produce a valid allocation,
but is only a configuration control, not a fix for the `-DASM` miscompile.

## Reproduction

The Cycle 4 baseline was MADC `f541a7a54624869e29b01f2f30b174bc0329eea5`,
on the Linux x86-64 hardware-backed host recorded in
`results/linux-x86_64/environment.json`. The checkout is containerized but
`systemd-detect-virt --vm` reports `none`; it is not QEMU CPU emulation.

The original library failure was reproduced with:

```sh
scripts/repro-linux-mpdecimal-qnew.sh
```

It prints `mpd_qnew=NULL` and exits 2. The fresh Cycle 4 copy of the exact
script and its output are in `results/linux-x86_64/logs/cycle4-mpdecimal-qnew-*`.
The script's output directory was isolated so the previously modified Cycle 3
logs were not overwritten. The build options for `mpalloc.c` were the existing
ones: `-c -O2 -std=c99 -DCONFIG_64 -DASM -DNDEBUG -fPIC -I <libmpdec>`.

The 26-line independent case is `src/clients/mpdecimal_inline_asm_min.c`. The
test command is:

```sh
scripts/test-linux-madc-inline-asm-min.sh
```

The script is a regression test that intentionally fails on this baseline:
GCC and Clang print `high=0`; a GCC-linked MADC AOT object at `-O2` prints an
uninitialized value and exits 1. MADC JIT prints an uninitialized value at
each of `-O0`, `-O1`, and `-O2`. The raw outputs and statuses are the
`cycle4-inline-asm-*` logs under `results/linux-x86_64/logs/`.

## CIR, MIR, and machine-code evidence

Using the same `-O2 -std=c99 -DCONFIG_64 -DASM -DNDEBUG -fPIC` options and
the same libmpdec include directory:

```sh
madc/bin/madc --dump-cir -O2 -std=c99 -DCONFIG_64 -DASM -DNDEBUG -fPIC \
  -I vendor/mpdecimal-4.0.1-c-only/libmpdec \
  vendor/mpdecimal-4.0.1-c-only/libmpdec/mpalloc.c
madc/bin/madc --dump-cir-checked -O2 -std=c99 -DCONFIG_64 -DASM -DNDEBUG -fPIC \
  -I vendor/mpdecimal-4.0.1-c-only/libmpdec \
  vendor/mpdecimal-4.0.1-c-only/libmpdec/mpalloc.c
root=$PWD
(cd "$root/vendor/mpdecimal-4.0.1-c-only/libmpdec" && \
  MADC_DUMP_MIR=1 "$root/madc/bin/madc" -c -O2 -std=c99 -DCONFIG_64 -DASM \
    -DNDEBUG -fPIC -I "$root/vendor/mpdecimal-4.0.1-c-only/libmpdec" \
    -o "$root/results/linux-x86_64/artifacts/cycle4-mpdecimal/mpalloc-rawmir.o" \
    mpalloc.c)
```

Both CIR dumps contain `_mpd_mul_words`'s local declarations and assignments
from `h`/`l` to `*hi`/`*lo`, but no asm operation. In the pre-check CIR, the
asm statement is represented only by a comma expression evaluating `high`,
`low`, `a`, and `b`. The post-check CIR preserves that omission. `--dump-cir`
then exits 1 because this source-only JIT invocation has unresolved library
imports; its dump is produced before that error. `--dump-cir-checked` exits 0
after dumping and stopping. The CLI dump flags are wired to the JIT path, not
the `-c` AOT call; `MADC_DUMP_MIR=1` is the existing AOT MIR hook.

The full CIR dumps are
`cycle4-mpalloc-dump-cir.stderr` and
`cycle4-mpalloc-dump-cir-checked.stderr`; raw pre-link MIR is
`cycle4-mpalloc-rawmir.stderr`. The key MIR function is near line 52 of that
file. Its first instructions only copy the uninitialized locals. The c2mir
comparison is captured in `cycle4-inline-asm-c2m.stderr`.

ELF structure/symbol/relocation inventories are in
`cycle4-mpalloc-sections.txt`, `cycle4-mpalloc-symbols.txt`, and
`cycle4-mpalloc-relocations.txt`; full disassembly is
`cycle4-mpalloc-object-disassembly.txt`. The object has `.text`, `.data`,
`.mir.addrpool`, `.rela.text`, `.rela.data`, `.rela.mir.addrpool`, and
`.rela.eh_frame`. `readelf` resolves the relevant address-pool entries to the
expected `malloc`, `mpd_mallocfunc`, and `mpd_qnew_size` symbols with zero
addends. `_mpd_mul_words` is local and defined in `.text`; its emitted body
reads `%r8/%r9` into the high/low outputs although the function has only four
x86-64 arguments, matching its undefined MIR locals. The GDB break at
`mpd_qnew_size+0x31` is in `cycle4-mpdecimal-qnew-gdb.txt`: `RDI=2`, `RSI` and
`RDX` are caller-stack addresses, and the next instruction is `test %rsi,%rsi`.

For the inlining-only experiment, temporary diagnostic hooks were added around
`CirJitSession::init_contexts()` and `load_and_link()` and then removed. They
provided `MADC_DISABLE_MIR_INLINING=1` and pre/post `MIR_link` snapshots; the
source checkout is clean afterward. A fresh process at `-O2` printed the
marker `[madc-diagnostic] MIR inlining disabled; opt=2`. The baseline
post-link snapshot expands `mpd_alloc` and its overflow helpers into
`mpd_qnew_size`; the no-inline snapshot retains the calls. With inlining
disabled, `mpd_qnew_size` now sets `RDI=1`, `RSI=48` before calling `mpd_alloc`
and tests the returned `RAX`, but the full reproducer still returns NULL.
The helper `_mpd_mul_words` has already lost its computation before either
linking mode.

The baseline machine code at `mpd_qnew_size+0x31` contains `test %rsi,%rsi`
before any allocator call. Its expected logical value is the overflow flag for
`1 * sizeof(mpd_t)`; that flag should be zero. The source asm is the only code
that writes the high/low product words used by `mul_size_t_overflow`, but those
writes are absent from CIR/MIR. Therefore `RSI` is not a misplaced ABI
argument: the `test` consumes an undefined overflow value. The MIR snapshots
are `cycle4-mpalloc-baseline.stderr`; baseline and no-inline machine code are
`cycle4-mpalloc-baseline-disassembly.txt` and
`cycle4-mpalloc-noinline-disassembly.txt`. Their objects are under
`results/linux-x86_64/artifacts/cycle4-mpdecimal/`. The Cycle 3 GDB trace with
entry registers is `cycle3-mpdecimal-qnew-gdb.txt`.

This establishes the first divergence as source-to-CIR lowering of unsupported
non-empty GNU asm. It eliminates MIR inlining, MIR argument lowering, ELF
relocations, and dynamic import resolution as the cause of this qnew failure.

## Allocation integrity control

`src/clients/mpdecimal_qnew_integrity_repro.c` checks initialized structure
fields, the data allocation and `mpd_del()` cleanup. It passes against GCC's
library and against a MADC `mpalloc.o` compiled with the supported ANSI
128-bit fallback:

```sh
madc -c -O2 -std=c99 -DCONFIG_64 -DANSI -DHAVE_UINT128_T -DNDEBUG -fPIC \
  -I vendor/mpdecimal-4.0.1-c-only/libmpdec -o mpalloc-ansi-u128.o mpalloc.c
```

Both print `flags=0 exp=0 digits=0 len=0 alloc=2 data=non-NULL` and exit 0.
The exact artifacts/logs are under `results/linux-x86_64/artifacts/cycle4-mpdecimal/`
and `results/linux-x86_64/logs/cycle4-qnew-integrity-*`. This does not validate
the other 14 library units or the official test matrix under that configuration.

## Validation and repository state

After removing the temporary MIR diagnostic hooks, the focused MADC tests pass:

| Test | Result |
|---|---:|
| `test_object_load` | 9/9 cases, 142/142 assertions |
| `test_native_shared` | 5/5 cases, 169/169 assertions |

There is no compiler fix, no MADC commit, no submodule pointer change, and no
claim that the original `-DASM` build works. MADC remains at baseline commit
`f541a7a54624869e29b01f2f30b174bc0329eea5` on
`experiment/mir-aot-correctness`. The Cycle 4 lab changes are recorded in the
lab repository; no push was performed. The Cycle 3 six `test_cir_freeze`
failures remain an independent baseline.
