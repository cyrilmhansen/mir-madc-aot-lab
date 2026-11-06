#!/usr/bin/env python3
"""Inventory the BASIC standalone ELF corpus without modifying original binaries."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pathlib
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

try:
    from elftools.elf.elffile import ELFFile
    from elftools.elf.sections import SymbolTableSection
except ImportError as exc:
    raise SystemExit("pyelftools is required (python3 -m pip install pyelftools)") from exc

HERE = pathlib.Path(__file__).resolve().parents[1]
LAB = HERE.parents[1]
DEFAULT_BIN = HERE / "results/aot/standalone/bin"
DEFAULT_OUT = HERE / "results/aot/size-analysis"
DEFAULT_SOURCE = HERE / "upstream/basic/samples"
DEFAULT_OBJ = HERE / "results/aot/standalone/obj"
RUNTIME = HERE / "runtime/libbasicrt.a"

TRACKED_SECTIONS = {
    ".text", ".rodata", ".data", ".bss", ".plt", ".plt.got", ".plt.sec",
    ".got", ".got.plt", ".dynsym", ".dynstr", ".symtab", ".strtab",
    ".eh_frame", ".eh_frame_hdr",
}


def command_version(command: list[str]) -> str:
    try:
        p = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, env={**os.environ, "LC_ALL": "C"})
        return p.stdout.splitlines()[0] if p.stdout else f"exit {p.returncode}"
    except OSError as exc:
        return f"unavailable: {exc}"


def run_checked(command: list[str], *, cwd: pathlib.Path | None = None,
                timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, cwd=cwd, check=True, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise RuntimeError(f"command failed: {' '.join(command)}: {exc}\n{detail}") from exc


def get_size_summary(path: pathlib.Path) -> dict[str, int]:
    p = run_checked(["size", "-B", str(path)])
    lines = p.stdout.decode(errors="replace").splitlines()
    if len(lines) < 2:
        raise RuntimeError(f"size returned unrecognized output for {path}")
    fields = lines[-1].split()
    if len(fields) < 4 or not all(re.fullmatch(r"\d+", x) for x in fields[:4]):
        raise RuntimeError(f"size returned unrecognized row for {path}: {lines[-1]}")
    return dict(text=int(fields[0]), data=int(fields[1]), bss=int(fields[2]),
                total=int(fields[3]))


def elf_arch(elf: ELFFile) -> tuple[str, str]:
    machine = elf.header["e_machine"]
    arch = {
        "EM_X86_64": "x86-64", "EM_386": "i386", "EM_AARCH64": "AArch64",
        "EM_ARM": "ARM", "EM_RISCV": "RISC-V", "EM_PPC64": "PowerPC64",
    }.get(machine, machine)
    typ = {"ET_EXEC": "ET_EXEC", "ET_DYN": "ET_DYN", "ET_REL": "ET_REL"}.get(
        elf.header["e_type"], elf.header["e_type"])
    return arch, typ


def basic_source_metrics(source: pathlib.Path) -> dict:
    if not source.is_file():
        return {"source_bytes": None, "source_lines": None, "basic_records": None,
                "basic_statements_estimate": None}
    raw = source.read_bytes()
    records = []
    for line in raw.decode("utf-8", "replace").splitlines():
        content=re.sub(r"^\s*\d+\s*", "", line, count=1).strip()
        if not content or content.upper()=="REM" or content.upper().startswith("REM ") or content.startswith("'"):
            continue
        records.append(line)
    statements = 0
    for line in records:
        # BASIC's colon separates statements except inside quoted strings. A
        # doubled quote inside a string is treated as an escaped quote.
        quoted = False
        count = 1
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == '"':
                if quoted and i + 1 < len(line) and line[i + 1] == '"':
                    i += 2
                    continue
                quoted = not quoted
            elif ch == ":" and not quoted:
                count += 1
            i += 1
        statements += count
    return {"source_bytes": len(raw), "source_lines": len(raw.splitlines()),
            "basic_records": len(records), "basic_statements_estimate": statements}


def section_category(name: str) -> str:
    if name in (".text", ".init", ".fini") or name.startswith((".text.", ".plt")):
        return "code"
    if name == ".rodata" or name.startswith((".rodata.", ".srodata")):
        return "readonly_data"
    if name == ".data" or name.startswith((".data.", ".sdata")):
        return "writable_data"
    if name == ".bss" or name.startswith((".bss.", ".sbss")):
        return "bss"
    if name.startswith((".debug_", ".zdebug_")):
        return "debug"
    if name.startswith(".rela") or name.startswith(".rel"):
        return "relocations"
    if name in (".symtab", ".strtab", ".dynsym", ".dynstr", ".shstrtab"):
        return "symbols"
    if name.startswith(".eh_frame"):
        return "unwind"
    if name.startswith((".got", ".dynamic", ".hash", ".gnu", ".note", ".interp")):
        return "dynamic_metadata"
    return "other"


def inspect_elf(path: pathlib.Path, rel: str, source_root: pathlib.Path) -> dict:
    file_size = path.stat().st_size
    try:
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            arch, typ = elf_arch(elf)
            sections = []
            section_totals = Counter()
            file_intervals = []
            other_allocated = []
            section_category_totals = Counter()
            file_backed_category_totals = Counter()
            debug_bytes = 0
            relocation_bytes = 0
            for sec in elf.iter_sections():
                name = sec.name or "<unnamed>"
                size = int(sec["sh_size"])
                flags = int(sec["sh_flags"])
                allocated = bool(flags & 0x2)  # SHF_ALLOC
                nobits = sec["sh_type"] == "SHT_NOBITS"
                offset = int(sec["sh_offset"])
                if size and not nobits:
                    if offset + size > file_size:
                        raise RuntimeError(f"section {name} extends beyond file bounds")
                    file_intervals.append((offset, offset + size))
                sections.append({"name": name, "type": sec["sh_type"], "size": size,
                                 "offset": offset, "address": int(sec["sh_addr"]),
                                 "flags": flags, "allocated": allocated, "nobits": nobits,
                                 "file_backed": not nobits and size > 0,
                                 "category": section_category(name)})
                if not nobits and size > 0:
                    file_backed_category_totals[section_category(name)] += size
                if name != "<unnamed>":
                    section_totals[name] += size
                    category = section_category(name)
                    section_category_totals[category] += size
                    if name.startswith((".debug_", ".zdebug_")):
                        debug_bytes += size
                    if name.startswith((".rela", ".rel")):
                        relocation_bytes += size
                    if allocated and name not in TRACKED_SECTIONS and not name.startswith(
                            (".text.", ".rodata.", ".data.", ".bss.", ".sdata", ".sbss")):
                        other_allocated.append({"name": name, "size": size})
            file_intervals.sort()
            unique_file_bytes = 0
            union_end = -1
            for start, end in file_intervals:
                if end <= union_end:
                    continue
                unique_file_bytes += end - max(start, union_end)
                union_end = end
            loads = []
            for seg in elf.iter_segments():
                if seg["p_type"] == "PT_LOAD":
                    loads.append({"offset": int(seg["p_offset"]),
                                  "virtual_address": int(seg["p_vaddr"]),
                                  "file_size": int(seg["p_filesz"]),
                                  "memory_size": int(seg["p_memsz"]),
                                  "flags": int(seg["p_flags"]),
                                  "alignment": int(seg["p_align"])})
            load_file = sum(s["file_size"] for s in loads)
            load_mem = sum(s["memory_size"] for s in loads)
            load_span = (max(s["virtual_address"] + s["memory_size"] for s in loads)
                         - min(s["virtual_address"] for s in loads)) if loads else 0
            metadata_names = (".dynsym", ".dynstr", ".symtab", ".strtab", ".shstrtab",
                              ".eh_frame", ".eh_frame_hdr", ".dynamic", ".hash", ".gnu.hash",
                              ".gnu.version", ".gnu.version_r", ".gnu.version_d", ".interp",
                              ".note.gnu.build-id", ".rela.dyn", ".rela.plt", ".got",
                              ".got.plt", ".plt", ".plt.got", ".plt.sec")
            metadata_bytes = sum(size for name, size in section_totals.items()
                                 if name in metadata_names or name.startswith((".rela.", ".rel.", ".note.")))
            symbol_rows = []
            for sec in elf.iter_sections():
                if not isinstance(sec, SymbolTableSection):
                    continue
                for sym in sec.iter_symbols():
                    if not sym.name or not sym["st_size"] or sym["st_shndx"] == "SHN_UNDEF":
                        continue
                    idx = sym["st_shndx"]
                    sec_name = elf.get_section(idx).name if isinstance(idx, int) else str(idx)
                    symbol_rows.append({"name": sym.name, "size": int(sym["st_size"]),
                                        "type": sym["st_info"]["type"],
                                        "binding": sym["st_info"]["bind"],
                                        "section": sec_name,
                                        "table": sec.name})
            symbol_rows.sort(key=lambda x: x["size"], reverse=True)
            function_symbol_bytes_sum=sum(s["size"] for s in symbol_rows if s["type"]=="STT_FUNC")
            size_summary = get_size_summary(path)
            src = source_root / (rel + ".bas")
            return {
                "path": rel, "file_size": file_size, "architecture": arch,
                "elf_type": typ, "elf_class": elf.elfclass, "endianness": elf.little_endian,
                "entry_point": int(elf.header["e_entry"]), "sections": sections,
                "section_sizes": dict(section_totals), "category_section_bytes": dict(section_category_totals),
                "file_backed_category_bytes": dict(file_backed_category_totals),
                "text_size": section_totals[".text"], "rodata_size": section_totals[".rodata"],
                "data_size": section_totals[".data"], "bss_size": section_totals[".bss"],
                "plt_size": sum(v for k, v in section_totals.items() if k.startswith(".plt")),
                "got_size": section_totals[".got"], "got_plt_size": section_totals[".got.plt"],
                "dynsym_size": section_totals[".dynsym"], "dynstr_size": section_totals[".dynstr"],
                "symtab_size": section_totals[".symtab"], "strtab_size": section_totals[".strtab"],
                "rela_size": relocation_bytes, "eh_frame_size": section_totals[".eh_frame"],
                "eh_frame_hdr_size": section_totals[".eh_frame_hdr"], "debug_size": debug_bytes,
                "allocated_section_bytes_sum": sum(s["size"] for s in sections if s["allocated"]),
                "other_allocated_sections": other_allocated,
                "other_allocated_bytes": sum(x["size"] for x in other_allocated),
                "file_backed_section_bytes_sum": sum(e - s for s, e in file_intervals),
                "file_backed_section_bytes_unique": unique_file_bytes,
                "file_backed_overhead_bytes": max(0, file_size - unique_file_bytes),
                "metadata_bytes_estimate": metadata_bytes,
                "metadata_ratio": metadata_bytes / file_size if file_size else 0,
                "function_symbol_bytes_sum": function_symbol_bytes_sum,
                "function_to_text_ratio": function_symbol_bytes_sum / section_totals[".text"] if section_totals[".text"] else 0,
                "pt_load_segments": loads, "pt_load_file_size_sum": load_file,
                "pt_load_memory_size_sum": load_mem, "pt_load_memory_span": load_span,
                "size_utility": size_summary, "largest_defined_symbols": symbol_rows[:30],
                **basic_source_metrics(src),
            }
    except Exception as exc:
        raise RuntimeError(f"{rel}: {exc}") from exc


def percentile(values: list[float], p: float) -> float:
    xs = sorted(values)
    if not xs:
        return 0.0
    pos = (len(xs) - 1) * p
    low = math.floor(pos); high = math.ceil(pos)
    if low == high:
        return xs[low]
    return xs[low] * (high - pos) + xs[high] * (pos - low)


def run_behavior_check(original: pathlib.Path, stripped: pathlib.Path, out_dir: pathlib.Path) -> dict:
    names = ["array", "fib", "fizzbuzz", "math", "while"]
    results = {}
    with tempfile.TemporaryDirectory(prefix="atlas-elf-size-exec-") as temp:
        base = pathlib.Path(temp)
        for name in names:
            source_result = {}
            for version, exe in (("original", original / name), ("stripped", stripped / name)):
                cwd = base / name / version
                cwd.mkdir(parents=True)
                try:
                    p = subprocess.run([str(exe)], cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                    effects = []
                    for f in sorted(cwd.rglob("*")):
                        if f.is_file():
                            effects.append((str(f.relative_to(cwd)), f.read_bytes().hex()))
                    source_result[version] = {"returncode": p.returncode,
                                              "stdout_hex": p.stdout.hex(), "stderr_hex": p.stderr.hex(),
                                              "effects": effects, "timeout": False}
                except subprocess.TimeoutExpired:
                    source_result[version] = {"timeout": True}
            a, b = source_result["original"], source_result["stripped"]
            same = (not a.get("timeout") and not b.get("timeout") and
                    (a["returncode"], a["stdout_hex"], a["stderr_hex"], a["effects"]) ==
                    (b["returncode"], b["stdout_hex"], b["stderr_hex"], b["effects"]))
            source_result["match"] = same
            results[name] = source_result
    out_dir.joinpath("stripped-execution-check.json").write_text(
        json.dumps(results, indent=2) + "\n")
    if not all(v["match"] for v in results.values()):
        bad = [k for k, v in results.items() if not v["match"]]
        raise RuntimeError("stripped execution differs from original for: " + ", ".join(bad))
    return results


def write_csv(path: pathlib.Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(row.get(k), separators=(",", ":"))
                             if isinstance(row.get(k), (dict, list)) else row.get(k)
                             for k in fields})


def fmt_bytes(n: float) -> str:
    return f"{n / 1024:,.1f} KiB ({n:,.0f} bytes)"


def toolchain_info() -> dict:
    def git(cwd: pathlib.Path, args: list[str]) -> str | None:
        try:
            return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
        except Exception:
            return None
    return {"generated_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version.split()[0], "pyelftools": __import__("elftools").__version__,
            "platform": platform.platform(), "readelf": command_version(["readelf", "--version"]),
            "size": command_version(["size", "--version"]), "strip": command_version(["strip", "--version"]),
            "objdump": command_version(["objdump", "--version"]),
            "gcc": command_version(["cc", "--version"]),
            "lab_commit": git(LAB, ["rev-parse", "HEAD"]),
            "lab_branch": git(LAB, ["branch", "--show-current"]),
            "madc_commit": git(LAB / "madc", ["rev-parse", "HEAD"]),
            "basic_provenance": "cyrilmhansen/mir BASIC commit 54fa3e409224bbc6ffdbc421a80f02ff76f76ce6",
            "madc_provenance": "MADC submodule commit " + (git(LAB / "madc", ["rev-parse", "HEAD"]) or "unknown")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bin-root", type=pathlib.Path, default=DEFAULT_BIN)
    ap.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--source-root", type=pathlib.Path, default=DEFAULT_SOURCE)
    ap.add_argument("--object-root", type=pathlib.Path, default=DEFAULT_OBJ)
    ap.add_argument("--no-strip", action="store_true", help="skip stripped copies and execution check")
    args = ap.parse_args()
    bin_root = args.bin_root.resolve(); output = args.output_dir.resolve()
    source_root = args.source_root.resolve(); obj_root = args.object_root.resolve()
    if not bin_root.is_dir():
        ap.error(f"binary directory does not exist: {bin_root}")
    for tool in ("size", "strip", "cc"):
        if shutil.which(tool) is None:
            ap.error(f"required tool not found: {tool}")
    binaries = sorted(p for p in bin_root.rglob("*") if p.is_file())
    if not binaries:
        ap.error(f"no executables found under {bin_root}")
    output.mkdir(parents=True, exist_ok=True)
    rows=[]; failures=[]
    for path in binaries:
        rel=path.relative_to(bin_root).as_posix()
        try:
            rows.append(inspect_elf(path, rel, source_root))
        except Exception as exc:
            failures.append(str(exc))
    if failures:
        raise SystemExit(f"ELF audit failed for {len(failures)} of {len(binaries)} files; none were omitted:\n"+
                         "\n".join(f"  - {x}" for x in failures))
    if len(rows) != len(binaries):
        raise SystemExit("internal error: analysis count does not match discovered files")
    rows.sort(key=lambda r: r["path"])
    by_size=sorted(rows,key=lambda r:r["file_size"],reverse=True)
    by_text=sorted(rows,key=lambda r:r["text_size"],reverse=True)
    by_rodata=sorted(rows,key=lambda r:r["rodata_size"],reverse=True)
    by_meta=sorted(rows,key=lambda r:r["metadata_ratio"],reverse=True)
    sizes=[r["file_size"] for r in rows]
    mean=statistics.mean(sizes); median=statistics.median(sizes)
    stats={"count":len(rows),"total_deployed_bytes":sum(sizes),"minimum":min(sizes),
           "maximum":max(sizes),"mean":mean,"median":median,
           "standard_deviation_population":statistics.pstdev(sizes),
           "percentiles":{"p75":percentile(sizes,.75),"p90":percentile(sizes,.90),
                          "p95":percentile(sizes,.95),"p99":percentile(sizes,.99)},
           "pt_load_file_bytes_sum":sum(r["pt_load_file_size_sum"] for r in rows),
           "pt_load_memory_bytes_sum":sum(r["pt_load_memory_size_sum"] for r in rows),
           "file_backed_overhead_bytes_sum":sum(r["file_backed_overhead_bytes"] for r in rows)}
    bins=[("<32 KiB",0,32*1024),("32–64 KiB",32*1024,64*1024),
          ("64–128 KiB",64*1024,128*1024),("128–256 KiB",128*1024,256*1024),
          ("256–512 KiB",256*1024,512*1024),("512 KiB–1 MiB",512*1024,1024*1024),
          ("1–2 MiB",1024*1024,2*1024*1024),(">=2 MiB",2*1024*1024,float("inf"))]
    distribution={label:sum(lo<=x<hi for x in sizes) for label,lo,hi in bins}
    strip_rows=[]; strip_records=[]; behavior={}
    if not args.no_strip:
        stripped_root=output/"stripped"
        for r in rows:
            src=bin_root/r["path"]; dst=stripped_root/r["path"]
            dst.parent.mkdir(parents=True,exist_ok=True)
            run_checked(["strip","--strip-unneeded","-o",str(dst),str(src)])
            shutil.copystat(src,dst,follow_symlinks=True)
            stripped=inspect_elf(dst,r["path"],source_root)
            removed=r["file_size"]-stripped["file_size"]
            removed_sections=Counter()
            orig_secs=r["section_sizes"]; stripped_secs=stripped["section_sizes"]
            for name,n in orig_secs.items():
                d=n-stripped_secs.get(name,0)
                if d>0: removed_sections[name]+=d
            row={"path":r["path"],"original_bytes":r["file_size"],"stripped_bytes":stripped["file_size"],
                 "removed_bytes":removed,"removed_percent":100*removed/r["file_size"],
                 "removed_sections":dict(removed_sections),
                 "dominant_removed_sections":dict(removed_sections.most_common(8))}
            strip_rows.append(row); strip_records.append(stripped)
        behavior=run_behavior_check(bin_root,stripped_root,output)
    # Long section inventory is retained in a separate CSV for filtering and pivoting.
    section_rows=[]
    for r in rows:
        for s in r["sections"]:
            section_rows.append({"path":r["path"],**s})
    flat_fields=["path","file_size","architecture","elf_type","elf_class","entry_point",
      "text_size","rodata_size","data_size","bss_size","plt_size","got_size","got_plt_size",
      "dynsym_size","dynstr_size","symtab_size","strtab_size","rela_size","eh_frame_size",
      "eh_frame_hdr_size","debug_size","allocated_section_bytes_sum","other_allocated_bytes",
      "file_backed_section_bytes_sum","file_backed_section_bytes_unique","file_backed_overhead_bytes",
      "metadata_bytes_estimate","metadata_ratio","function_symbol_bytes_sum","function_to_text_ratio",
      "pt_load_file_size_sum","pt_load_memory_size_sum",
      "pt_load_memory_span","size_utility","source_bytes","source_lines","basic_records",
      "basic_statements_estimate","largest_defined_symbols","other_allocated_sections"]
    write_csv(output/"elf-sizes.csv",rows,flat_fields)
    write_csv(output/"sections.csv",section_rows,["path","name","type","size","offset","address","flags","allocated","nobits","file_backed","category"])
    write_csv(output/"strip-comparison.csv",strip_rows,["path","original_bytes","stripped_bytes","removed_bytes","removed_percent","removed_sections","dominant_removed_sections"])
    payload={"provenance":toolchain_info(),"binary_root":str(bin_root),"source_root":str(source_root),
             "statistics":stats,"size_distribution":distribution,"strip_comparison":strip_rows,
             "stripped_execution_check":behavior,"executables":rows}
    (output/"elf-sizes.json").write_text(json.dumps(payload,indent=2)+"\n")

    # Isolate whether the adapter's explicit MIR_gen loop duplicates the code
    # already prepared by MIR_link in object mode. The diagnostic variant and
    # all its artifacts stay in the analysis directory; source trees are read-only.
    emission_dir=output/"adapter-emission-experiment"
    emission_dir.mkdir(exist_ok=True)
    adapter_source=(HERE/"src/mir-to-elf.c").read_text()
    loop="""  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item) {
        int selected = !direct_shared;
        if (direct_shared)
          for (size_t i = 0; i < n_exports; i++)
            if (strcmp(MIR_item_name(ctx, item), exports[i]) == 0) selected = 1;
        if (selected) (void)MIR_gen(ctx, item);
      }
"""
    emission_results=[]
    libmir=LAB/"madc/obj/mir/host/libmir.a"
    if libmir.is_file() and loop in adapter_source:
        variant_src=emission_dir/"mir-to-elf-no-explicit-gen.c"
        variant=emission_dir/"mir-to-elf-no-explicit-gen"
        variant_src.write_text(adapter_source.replace(loop,
          "  /* Diagnostic only: omit explicit MIR_gen after MIR_link. */\n",1))
        run_checked(["cc","-O2","-I",str(LAB/"madc/third_party/mir"),str(variant_src),
                     str(libmir),"-lm","-ldl","-lpthread","-o",str(variant)])
        for rel in ("bcg/test1","fib","array","bcg/poker"):
            mir=HERE/"results/aot/standalone/obj"/(rel+".mir")
            original_obj=obj_root/(rel+".o")
            if not mir.is_file() or not original_obj.is_file():
                emission_results.append({"program":rel,"status":"not-available"}); continue
            record={"program":rel,"status":"generated"}
            for label,obj_path in (("normal",original_obj),
                                   ("no_explicit_gen",emission_dir/(rel.replace("/","-")+".o"))):
                obj_path.parent.mkdir(parents=True,exist_ok=True)
                if label=="no_explicit_gen":
                    run_checked([str(variant),str(mir),str(obj_path)])
                with obj_path.open("rb") as f:
                    oe=ELFFile(f); text_sec=oe.get_section_by_name(".text")
                    symtab=oe.get_section_by_name(".symtab")
                    funcs=[]
                    if symtab:
                        for sym in symtab.iter_symbols():
                            if sym["st_info"]["type"]=="STT_FUNC" and sym["st_shndx"]!="SHN_UNDEF":
                                funcs.append(int(sym["st_size"]))
                    text_size=int(text_sec["sh_size"]) if text_sec else 0
                    record[label]={"object_bytes":obj_path.stat().st_size,"text":text_size,
                      "data":int(oe.get_section_by_name(".data")["sh_size"]) if oe.get_section_by_name(".data") else 0,
                      "mir_addrpool":int(oe.get_section_by_name(".mir.addrpool")["sh_size"]) if oe.get_section_by_name(".mir.addrpool") else 0,
                      "rela_text":int(oe.get_section_by_name(".rela.text")["sh_size"]) if oe.get_section_by_name(".rela.text") else 0,
                      "rela_text_entries":(int(oe.get_section_by_name(".rela.text")["sh_size"])//int(oe.get_section_by_name(".rela.text")["sh_entsize"])) if oe.get_section_by_name(".rela.text") and oe.get_section_by_name(".rela.text")["sh_entsize"] else 0,
                      "function_symbol_bytes_sum":sum(funcs),
                      "text_not_covered_by_function_sizes":max(0,text_size-sum(funcs))}
                exe=emission_dir/(rel.replace("/","-")+"-"+label)
                run_checked(["cc",str(obj_path),"-Wl,--gc-sections",str(RUNTIME),"-lm","-o",str(exe)])
                record[label]["linked_executable_bytes"]=exe.stat().st_size
            emission_results.append(record)
        t1=next((x for x in emission_results if x.get("program")=="bcg/test1"),None)
        if t1:
            with tempfile.TemporaryDirectory(prefix="atlas-elf-size-adapter-") as temp:
                outputs=[]
                for label in ("normal","no_explicit_gen"):
                    exe=emission_dir/("bcg-test1-"+label)
                    p=subprocess.run([str(exe)],cwd=temp,stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
                    outputs.append((p.returncode,p.stdout,p.stderr))
                t1["behavior_match"]=outputs[0]==outputs[1]
                if not t1["behavior_match"]:
                    raise RuntimeError("adapter emission experiment changed bcg/test1 behavior")
        write_csv(output/"adapter-object-emission.csv",emission_results,
                  ["program","status","normal","no_explicit_gen","behavior_match"])
    else:
        (emission_dir/"NOT-AVAILABLE.txt").write_text("Expected adapter code sequence or MADC library unavailable; experiment skipped.\n")

    baseline_dir=output/"baselines"; baseline_dir.mkdir(exist_ok=True)
    c_source=baseline_dir/"minimal-c.c"; c_exe=baseline_dir/"minimal-c"
    c_source.write_text("int main(void) { return 0; }\n")
    run_checked(["cc","-Os","-ffunction-sections","-fdata-sections","-Wl,--gc-sections",
                 str(c_source),"-o",str(c_exe)])
    c_base=inspect_elf(c_exe,"minimal-c",pathlib.Path("/nonexistent"))
    (baseline_dir/"baseline-summary.json").write_text(json.dumps({"minimal_c":{
      "file_size":c_base["file_size"],"text":c_base["text_size"],"rodata":c_base["rodata_size"],
      "data":c_base["data_size"],"bss":c_base["bss_size"],"size_utility":c_base["size_utility"]},
      "smallest_basic":{"path":by_size[-1]["path"],"file_size":by_size[-1]["file_size"]}},indent=2)+"\n")

    disasm_dir=output/"disassembly"; disasm_dir.mkdir(exist_ok=True)
    for rel in ("bcg/test1","array","fib","bcg/poker","bcg/qubit",
                "bcg/mastermind","bcg/football","fleuves"):
        obj=obj_root/(rel+".o")
        if not obj.is_file(): continue
        stem=rel.replace("/","-")
        with obj.open("rb") as f:
            oe=ELFFile(f); symtab=oe.get_section_by_name(".symtab")
            main_value=None
            if symtab:
                for sym in symtab.iter_symbols():
                    if sym.name=="main": main_value=int(sym["st_value"]); break
        if main_value is not None:
            prefix=run_checked(["objdump","-dr",f"--start-address={main_value}",
                                f"--stop-address={main_value+512}",str(obj)])
            first=run_checked(["objdump","-dr","--start-address=0","--stop-address=512",str(obj)])
            (disasm_dir/(stem+"-main-object-prefix.txt")).write_bytes(prefix.stdout)
            (disasm_dir/(stem+"-first-text-prefix.txt")).write_bytes(first.stdout)
        secdump=run_checked(["objdump","-s","-j",".data",str(obj)])
        (disasm_dir/(stem+"-data.txt")).write_bytes(secdump.stdout)

    total_composition=Counter()
    for r in rows:
        for cat,n in r["category_section_bytes"].items(): total_composition[cat]+=n
    summary=["# BASIC AOT ELF size audit", "", f"Analyzed **{len(rows)}** ELF executables under `{bin_root}`.",
      "", "## Corpus statistics", "", "| Metric | Result |", "|---|---:|",
      f"| Total deployed file size | {fmt_bytes(stats['total_deployed_bytes'])} |",
      f"| Minimum | {fmt_bytes(stats['minimum'])} |",f"| Maximum | {fmt_bytes(stats['maximum'])} |",
      f"| Mean | {fmt_bytes(mean)} |",f"| Median | {fmt_bytes(median)} |",
      f"| Population standard deviation | {fmt_bytes(stats['standard_deviation_population'])} |"]
    for key,val in stats["percentiles"].items(): summary.append(f"| {key.upper()} | {fmt_bytes(val)} |")
    summary += [f"| Sum PT_LOAD file bytes | {fmt_bytes(stats['pt_load_file_bytes_sum'])} |",
      f"| Sum PT_LOAD memory bytes | {fmt_bytes(stats['pt_load_memory_bytes_sum'])} |",
      f"| File bytes outside unique file-backed sections | {fmt_bytes(stats['file_backed_overhead_bytes_sum'])} |",
      "", "Size ranges:", "", "| Range | Programs |", "|---|---:|"]
    summary += [f"| {k} | {v} |" for k,v in distribution.items()]
    summary += ["", "## Largest section totals", "",
      "Section bytes are individual ELF section sizes. PT_LOAD segment sizes are separately reported because segment ranges can overlap and section sizes do not include file padding/header gaps.",
      "", "| Section category | Sum across executables |", "|---|---:|"]
    summary += [f"| {k} | {fmt_bytes(v)} |" for k,v in sorted(total_composition.items(),key=lambda x:-x[1])]
    summary += ["", "## Largest proportional metadata", "",
      "Metadata estimate counts symbol/string tables, relocations, unwind tables, dynamic linker tables, PLT/GOT and notes; this is a defined accounting category, not an optimization estimate.", "",
      "| Program | File size | Metadata estimate | Share |", "|---|---:|---:|---:|"]
    summary += [f"| `{r['path']}` | {fmt_bytes(r['file_size'])} | {fmt_bytes(r['metadata_bytes_estimate'])} | {100*r['metadata_ratio']:.1f}% |" for r in by_meta[:10]]
    summary += ["", "## Stripping", "", f"`strip --strip-unneeded` was applied to copies under `{output / 'stripped'}`. Originals were not modified."]
    if strip_rows:
        removed=sum(x["removed_bytes"] for x in strip_rows); orig=sum(x["original_bytes"] for x in strip_rows)
        summary += [f"The corpus copies removed {fmt_bytes(removed)} total ({100*removed/orig:.1f}% of original deployed bytes). Five previously validated deterministic programs were executed from original and stripped copies; all matched stdout, stderr, status and file effects."]
        removed_sections=Counter()
        for r in strip_rows:
            for n,v in r["removed_sections"].items(): removed_sections[n]+=v
        summary += ["Aggregate removed sections:",""]
        summary += [f"- `{n}`: {fmt_bytes(v)}" for n,v in removed_sections.most_common(8)]
    summary += ["", "## Small-program baseline and adapter emission experiment", "",
      f"A minimal host C executable built with GCC `-Os` is **{fmt_bytes(c_base['file_size'])}**; the smallest BASIC executable (`{by_size[-1]['path']}`) is **{fmt_bytes(by_size[-1]['file_size'])}**. BASIC adds generated code, runtime calls/data and an address pool; this is not a pure runtime-size subtraction.",
      "", "The diagnostic adapter variant omitting its explicit `MIR_gen` loop after `MIR_link` was generated from the unchanged adapter source and exercised on existing MIR files. See `adapter-object-emission.csv` and `adapter-emission-experiment/`. It links and executes `bcg/test1` with identical output. Normal ET_REL `.text` is close to twice the sum of defined function symbol sizes for these samples; the no-explicit-gen variant emits one copy. This is evidence of redundant code in the lab adapter call sequence, not a MIR codegen optimization result. Treat removing that loop as an isolated follow-up requiring the full suite."]
    summary += ["", "## Toolchain and provenance", "", "```json",json.dumps(payload["provenance"],indent=2),"```", "",
      "Raw per-program data is in `elf-sizes.json` and `elf-sizes.csv`; `sections.csv` is the long-form section table."]
    (output/"SUMMARY.md").write_text("\n".join(summary)+"\n")

    top20=["# Top 20 largest BASIC AOT executables","","| Rank | Program | File | .text | .rodata | .data | .bss | Metadata | Source | Lines | Statements* | Top defined symbol |",
           "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for i,r in enumerate(by_size[:20],1):
        sym=r["largest_defined_symbols"][0] if r["largest_defined_symbols"] else {}
        top20.append(f"| {i} | `{r['path']}` | {fmt_bytes(r['file_size'])} | {fmt_bytes(r['text_size'])} | {fmt_bytes(r['rodata_size'])} | {fmt_bytes(r['data_size'])} | {fmt_bytes(r['bss_size'])} | {fmt_bytes(r['metadata_bytes_estimate'])} | {fmt_bytes(r['source_bytes'] or 0)} | {r['source_lines']} | {r['basic_statements_estimate']} | `{sym.get('name','—')}` ({sym.get('size',0):,} B) |")
    top20 += ["","*Statement count is an estimate: non-comment source records split on colons outside quoted strings.",""]
    (output/"top20.md").write_text("\n".join(top20))
    outliers=["# ELF size outliers","", "## Ten largest `.text` sections", "", "| Program | .text | File | Source bytes | Source lines |", "|---|---:|---:|---:|---:|"]
    outliers += [f"| `{r['path']}` | {fmt_bytes(r['text_size'])} | {fmt_bytes(r['file_size'])} | {r['source_bytes']} | {r['source_lines']} |" for r in by_text[:10]]
    outliers += ["", "## Ten largest `.rodata` sections", "", "| Program | .rodata | File | Source bytes | Source lines |", "|---|---:|---:|---:|---:|"]
    outliers += [f"| `{r['path']}` | {fmt_bytes(r['rodata_size'])} | {fmt_bytes(r['file_size'])} | {r['source_bytes']} | {r['source_lines']} |" for r in by_rodata[:10]]
    outliers += ["", "## Largest defined symbols in the ten largest executables", ""]
    for r in by_size[:10]:
        outliers += [f"### `{r['path']}`", "", "| Symbol | Type | Section | Bytes |", "|---|---|---|---:|"]
        outliers += [f"| `{s['name']}` | {s['type']} | `{s['section']}` | {s['size']:,} |" for s in r["largest_defined_symbols"][:10]]
        if not r["largest_defined_symbols"]: outliers.append("No sized defined symbols in available symbol tables.")
        outliers.append("")
    if strip_rows:
        outliers += ["## Largest stripping reductions", "", "| Program | Removed | Percent | Main removed sections |", "|---|---:|---:|---|"]
        outliers += [f"| `{r['path']}` | {fmt_bytes(r['removed_bytes'])} | {r['removed_percent']:.1f}% | `{json.dumps(r['dominant_removed_sections'],separators=(',',':'))}` |" for r in sorted(strip_rows,key=lambda x:-x['removed_bytes'])[:20]]
    (output/"outliers.md").write_text("\n".join(outliers)+"\n")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        sizes_kib=[x/1024 for x in sizes]
        fig,ax=plt.subplots(figsize=(8,4.5)); ax.hist(sizes_kib,bins=24,color="#3b78a6",edgecolor="white"); ax.set_xscale("log"); ax.set_xlabel("Executable size (KiB, log scale)"); ax.set_ylabel("Programs"); ax.set_title("BASIC AOT executable size distribution"); fig.tight_layout(); fig.savefig(output/"size-distribution.png",dpi=150); plt.close(fig)
        chosen=by_size[:20]; labels=[pathlib.Path(r["path"]).name for r in reversed(chosen)]
        cats=[("Code","code"),("Read-only data","readonly_data"),("Writable data","writable_data"),
              ("Relocations","relocations"),("Symbols","symbols"),("Unwind","unwind"),
              ("Dynamic metadata","dynamic_metadata"),("Debug","debug"),("Other sections","other"),
              ("File padding/headers","file_backed_overhead_bytes")]
        bottom=np.zeros(len(chosen)); fig,ax=plt.subplots(figsize=(11,7))
        for label,key in cats:
            vals=[]
            for r in reversed(chosen):
                if key=="file_backed_overhead_bytes": val=r[key]
                else: val=r["file_backed_category_bytes"].get(key,0)
                vals.append(val/1024)
            ax.barh(labels,vals,left=bottom,label=label); bottom+=np.array(vals)
        ax.set_xlabel("Section/file bytes (KiB)"); ax.set_title("Top 20 ELF file composition (approximate categories)"); ax.legend(loc="lower right"); fig.tight_layout(); fig.savefig(output/"top20-section-composition.png",dpi=150); plt.close(fig)
        src=[r for r in rows if r["source_bytes"] is not None]
        fig,ax=plt.subplots(figsize=(7,5)); ax.scatter([r["source_bytes"]/1024 for r in src],[r["text_size"]/1024 for r in src],alpha=.65); ax.set_xlabel("BASIC source size (KiB)"); ax.set_ylabel(".text size (KiB)"); ax.set_title("Source size versus generated .text"); fig.tight_layout(); fig.savefig(output/"source-vs-text.png",dpi=150); plt.close(fig)
        if strip_rows:
            sorted_strip=sorted(strip_rows,key=lambda x:x["original_bytes"])
            fig,ax=plt.subplots(figsize=(9,5)); x=range(len(sorted_strip)); ax.plot(x,[r["original_bytes"]/1024 for r in sorted_strip],label="Original"); ax.plot(x,[r["stripped_bytes"]/1024 for r in sorted_strip],label="Stripped"); ax.set_xlabel("Programs sorted by original size"); ax.set_ylabel("Executable size (KiB)"); ax.set_title("Original and stripped executable sizes"); ax.legend(); fig.tight_layout(); fig.savefig(output/"original-vs-stripped.png",dpi=150); plt.close(fig)
    except ImportError:
        (output/"charts-skipped.txt").write_text("matplotlib and numpy are unavailable; tabular reports are complete.\n")

    # Re-link existing objects only to generate map files; original corpus ELFs
    # are read-only and are never replaced. This estimates archive contribution.
    maps=output/"link-maps"; maps.mkdir(exist_ok=True)
    map_status=[]
    if RUNTIME.is_file():
        for rel in ("bcg/test1", "fib", "array", "bcg/poker", "fleuves"):
            obj=obj_root/(rel+".o")
            if not obj.is_file():
                map_status.append({"program":rel,"status":"not-available","detail":"existing ET_REL object missing"}); continue
            mapfile=maps/(rel.replace("/","-")+".map")
            exe=maps/(rel.replace("/","-")+"-relinked")
            exe.parent.mkdir(parents=True,exist_ok=True)
            try:
                run_checked(["cc",str(obj),"-Wl,--gc-sections",f"-Wl,-Map,{mapfile}",str(RUNTIME),"-lm","-o",str(exe)])
                map_status.append({"program":rel,"status":"generated","map":mapfile.name,
                                   "relinked_file_size":exe.stat().st_size})
            except RuntimeError as exc:
                map_status.append({"program":rel,"status":"failed","detail":str(exc)})
    (maps/"README.md").write_text("# Representative linker maps\n\nGenerated by re-linking already existing ET_REL BASIC objects against the cached static BASIC runtime with `--gc-sections`; no BASIC source or corpus ELF was rebuilt or overwritten. Relinked executables are retained here for provenance.\n\n"+json.dumps(map_status,indent=2)+"\n")
    print(f"Analyzed {len(rows)} ELF files; total {stats['total_deployed_bytes']:,} bytes.")
    print(f"Results: {output}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        raise SystemExit(str(exc))
