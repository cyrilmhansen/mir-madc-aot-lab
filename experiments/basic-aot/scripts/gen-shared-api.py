#!/usr/bin/env python3
"""Generate C adapters and an ELF export map for selected BASIC functions."""
import argparse
import json
import re
from pathlib import Path

PUBLIC = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MIR = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def parse_string_export(spec: str):
    if "=" not in spec or ":" not in spec:
        raise ValueError(f"expected PUBLIC=INTERNAL:ARGS[:pool|borrowed], got {spec!r}")
    public, target = spec.split("=", 1)
    parts = target.split(":")
    internal, encoded_args = parts[:2]
    ownership = parts[2] if len(parts) == 3 else "borrowed"
    if len(parts) > 3 or ownership not in ("pool", "borrowed"):
        raise ValueError(f"ownership must be pool or borrowed in {spec!r}")
    if not PUBLIC.fullmatch(public) or not MIR.fullmatch(internal):
        raise ValueError(f"invalid C or MIR identifier in {spec!r}")
    args = [] if encoded_args in ("", "void") else encoded_args.split(",")
    if len(args) > 5 or any(arg not in ("p", "d") for arg in args):
        raise ValueError(f"arguments must be up to five p (string) or d (double): {spec!r}")
    return public, internal, args, ownership


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--export", action="append", default=[])
    parser.add_argument("--string-export", action="append", default=[])
    parser.add_argument("--test-allocator", action="store_true")
    args = parser.parse_args()

    if not args.export and not args.string_export:
        parser.error("at least one selected export is required")
    if any(not PUBLIC.fullmatch(name) for name in args.export):
        parser.error("--export expects a C identifier")
    wrappers = [parse_string_export(spec) for spec in args.string_export]
    names = args.export + [w[0] for w in wrappers]
    if len(set(names)) != len(names):
        parser.error("duplicate public export")
    if len({w[1] for w in wrappers}) != len(wrappers):
        parser.error("duplicate internal BASIC function")

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    c_lines = [
        "#define _GNU_SOURCE",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "",
    ]
    if args.test_allocator:
        c_lines += ["int basic_shared_test_fail_alloc_once;", ""]
    header = [
        "#ifndef BASIC_SHARED_API_H",
        "#define BASIC_SHARED_API_H",
        "#include <stddef.h>",
        "",
        "/* Call basic_module_init() before invoking functions that use the BASIC runtime. */",
        "void basic_module_init(void);",
        "void basic_module_fini(void);",
    ]
    if wrappers:
        c_lines += ["/* Public results use malloc/free; pool disposal follows explicit annotations. */"]
        header += [
            "",
            "/*",
            " * String arguments are borrowed NUL-terminated byte strings. A NULL",
            " * argument returns NULL. Results are independent malloc() allocations",
            " * owned by the caller and may be released with free() after dlclose().",
        " * A :pool export frees its internal result after copying; a :borrowed",
        " * export leaves the internal result with BASIC until module fini.",
            " * Embedded NUL bytes are not representable; case conversion follows the",
            " * runtime's byte/locale behavior and does not promise Unicode handling.",
            " */",
            "void basic_string_free(char *text);",
        ]
        c_lines += ["void basic_string_free(char *text) { free(text); }", ""]

    if any(owner == "pool" for _, _, _, owner in wrappers):
        c_lines += ["extern void basic_free(char *);", ""]
    for index, (public, internal, arg_kinds, ownership) in enumerate(wrappers):
        params = ["const char *" + f"arg{i}" if kind == "p" else "double " + f"arg{i}"
                  for i, kind in enumerate(arg_kinds)]
        proto = ", ".join(params) or "void"
        call_args = ", ".join(f"arg{i}" for i in range(len(arg_kinds)))
        c_lines += [
            f'extern char *basic_internal_{index}({proto}) __asm__({json.dumps(internal)});',
            f"char *{public}({proto}) {{",
        ]
        for i, kind in enumerate(arg_kinds):
            if kind == "p":
                c_lines.append(f"  if (arg{i} == NULL) return NULL;")
        c_lines += [
            f"  char *internal_result = basic_internal_{index}({call_args});",
            "  if (internal_result == NULL) return NULL;",
            "  size_t length = strlen(internal_result);",
        ]
        if ownership == "pool":
            c_lines.append("  if (length == SIZE_MAX) { basic_free(internal_result); return NULL; }")
        else:
            c_lines.append("  if (length == SIZE_MAX) return NULL;")
        if args.test_allocator:
            c_lines += [
                "  if (basic_shared_test_fail_alloc_once) {",
                "    basic_shared_test_fail_alloc_once = 0;",
                ("    basic_free(internal_result);" if ownership == "pool" else "    (void)internal_result;"),
                "    return NULL;",
                "  }",
            ]
        c_lines += [
            "  char *copy = malloc(length + 1);",
            ("  if (copy == NULL) { basic_free(internal_result); return NULL; }"
             if ownership == "pool" else "  if (copy == NULL) return NULL;"),
            "  memcpy(copy, internal_result, length + 1);",
            ("  basic_free(internal_result);" if ownership == "pool" else "  (void)internal_result;"),
            "  return copy;",
            "}",
            "",
        ]
        header.append(f"char *{public}({proto});")

    if args.test_allocator:
        c_lines += [
            "void basic_shared_test_fail_next_alloc(void) { basic_shared_test_fail_alloc_once = 1; }",
            "",
        ]
    header += ["", "#endif /* BASIC_SHARED_API_H */", ""]

    (out / "basic-shared-api.c").write_text("\n".join(c_lines))
    (out / "basic-shared-api.h").write_text("\n".join(header))
    exports = list(names) + ["basic_module_init", "basic_module_fini"]
    if wrappers:
        exports.append("basic_string_free")
    if args.test_allocator:
        exports.append("basic_shared_test_fail_next_alloc")
    (out / "basic-shared-api.map").write_text(
        "{ global: " + "; ".join(exports) + "; local: *; };\n"
    )


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc))
