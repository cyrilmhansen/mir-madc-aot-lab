/* Parse historical BASIC MIR text with the MADC-integrated MIR and emit ELF ET_REL. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"
#include "mir-debug.h"

#include <stdio.h>
#include <elf.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

static char *read_all(const char *path) {
  FILE *f = fopen(path, "rb");
  long n;
  char *buf;
  if (!f || fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET)) {
    if (f) fclose(f);
    return NULL;
  }
  buf = malloc((size_t)n + 1);
  if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
    free(buf);
    fclose(f);
    return NULL;
  }
  fclose(f);
  buf[n] = '\0';
  return buf;
}

/* The historical MIR writer appends lref declarations after their function,
   while the maintained MIR reader requires referenced data items to be known
   before parsing the function body. Move only those declarations before the
   first function; their function-local label names remain unchanged. */
static char *move_lrefs_before_functions(const char *input) {
  size_t n = strlen(input), first_func = n;
  char *out = malloc(n + 1);
  char *lrefs = malloc(n + 1);
  if (out == NULL || lrefs == NULL) { free(out); free(lrefs); return NULL; }
  size_t lused = 0, opos = 0;
  for (size_t start = 0; start < n;) {
    size_t end = start;
    while (end < n && input[end] != '\n') end++;
    if (end < n) end++;
    size_t len = end - start;
    if (memmem(input + start, len, ":\tlref\t", 7) != NULL) {
      memcpy(lrefs + lused, input + start, len);
      lused += len;
    }
    start = end;
  }
  for (size_t start = 0; start < n;) {
    size_t end = start;
    while (end < n && input[end] != '\n') end++;
    if (end < n) end++;
    size_t len = end - start;
    const char *line = input + start;
    int is_lref = memmem(line, len, ":\tlref\t", 7) != NULL;
    int is_func = memmem(line, len, ":\tfunc\t", 7) != NULL;
    if (!is_lref) {
      if (is_func && first_func == n) {
        first_func = opos;
        memcpy(out + opos, lrefs, lused);
        opos += lused;
      }
      memcpy(out + opos, line, len);
      opos += len;
    }
    start = end;
  }
  if (first_func == n) {
    memcpy(out + opos, lrefs, lused);
    opos += lused;
  }
  out[opos] = '\0';
  free(lrefs);
  return out;
}

typedef struct {
  MIR_item_t item;
  MIR_item_binding_t binding;
} import_binding_t;

/* MIR_link normally rejects an unresolved strong import because it expects a
   runnable module. For object emission, temporarily mark imports weak so link
   leaves them unresolved. The original binding is retained for restoring ELF
   symbol strength after MIR object capture. */
static import_binding_t *defer_import_resolution(MIR_context_t ctx, size_t *count_out) {
  MIR_module_t module;
  MIR_item_t item;
  size_t count = 0, index = 0;
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_import_item) count++;
  *count_out = count;
  import_binding_t *imports = count ? calloc(count, sizeof(*imports)) : NULL;
  if (count && !imports) return NULL;
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_import_item) {
        imports[index++] = (import_binding_t){item, (MIR_item_binding_t)item->binding};
        if (item->binding == MIR_ITEM_BIND_GLOBAL)
          MIR_item_set_binding(ctx, item, MIR_ITEM_BIND_WEAK);
      }
  return imports;
}

static void restore_import_bindings(MIR_context_t ctx, import_binding_t *imports,
                                    size_t import_count) {
  for (size_t i = 0; i < import_count; i++)
    MIR_item_set_binding(ctx, imports[i].item, imports[i].binding);
}

/* MIR_link only accepts unresolved imports when they are weak. The MIR object
   writer records that temporary state in ELF. Restore the declared binding in
   the finished ET_REL symbol table: strong imports remain undefined and the
   system linker will still reject a missing symbol. */
static int restore_elf_import_bindings(MIR_context_t ctx, void *object, size_t object_size,
                                       const import_binding_t *imports,
                                       size_t import_count) {
  Elf64_Ehdr *eh;
  Elf64_Shdr *sh, *symtab = NULL, *strtab;
  if (object_size < sizeof(Elf64_Ehdr)) return -1;
  eh = object;
  if (memcmp(eh->e_ident, ELFMAG, SELFMAG) != 0 || eh->e_ident[EI_CLASS] != ELFCLASS64
      || eh->e_ident[EI_DATA] != ELFDATA2LSB || eh->e_shentsize != sizeof(Elf64_Shdr)
      || eh->e_shoff > object_size || eh->e_shnum > (object_size - eh->e_shoff) / sizeof(Elf64_Shdr))
    return -1;
  sh = (Elf64_Shdr *)((char *)object + eh->e_shoff);
  for (size_t i = 0; i < eh->e_shnum; i++)
    if (sh[i].sh_type == SHT_SYMTAB) { symtab = &sh[i]; break; }
  if (symtab == NULL || symtab->sh_link >= eh->e_shnum
      || symtab->sh_offset > object_size || symtab->sh_size > object_size - symtab->sh_offset
      || symtab->sh_entsize != sizeof(Elf64_Sym))
    return -1;
  strtab = &sh[symtab->sh_link];
  if (strtab->sh_offset > object_size || strtab->sh_size > object_size - strtab->sh_offset)
    return -1;
  Elf64_Sym *syms = (Elf64_Sym *)((char *)object + symtab->sh_offset);
  const char *names = (char *)object + strtab->sh_offset;
  size_t nsyms = symtab->sh_size / sizeof(*syms);
  for (size_t i = 0; i < import_count; i++) {
    if (imports[i].binding != MIR_ITEM_BIND_GLOBAL) continue;
    const char *name = MIR_item_name(ctx, imports[i].item);
    if (name == NULL) return -1;
    for (size_t j = 0; j < nsyms; j++) {
      if (syms[j].st_shndx != SHN_UNDEF || syms[j].st_name >= strtab->sh_size) continue;
      const char *symname = names + syms[j].st_name;
      if (memchr(symname, '\0', strtab->sh_size - syms[j].st_name) == NULL) return -1;
      if (strcmp(symname, name) == 0) {
        syms[j].st_info = ELF64_ST_INFO(STB_GLOBAL, ELF64_ST_TYPE(syms[j].st_info));
      }
    }
    /* MIR_gen may omit imports that are never referenced by emitted code. */
  }
  return 0;
}

static int valid_mir_identifier(const char *name) {
  if (name == NULL || !(isalpha((unsigned char)*name) || *name == '_' || *name == '$')) return 0;
  for (name++; *name; name++)
    if (!(isalnum((unsigned char)*name) || *name == '_' || *name == '$')) return 0;
  return 1;
}

static int text_defines_func(const char *text, const char *name) {
  size_t n = strlen(name);
  for (const char *line = text; *line;) {
    const char *end = strchr(line, '\n');
    size_t len = end ? (size_t)(end - line) : strlen(line);
    if (len > n + 6 && memcmp(line, name, n) == 0 && line[n] == ':'
        && memmem(line + n + 1, len - n - 1, "func", 4) != NULL)
      return 1;
    if (end == NULL) break;
    line = end + 1;
  }
  return 0;
}

static int validate_function_exports(MIR_context_t ctx, MIR_module_t module,
                                     char **exports, size_t n_exports, int enforce_c_abi) {
  for (size_t e = 0; e < n_exports; e++) {
    MIR_item_t found = NULL;
    for (MIR_item_t item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item
          && strcmp(MIR_item_name(ctx, item), exports[e]) == 0) { found = item; break; }
    if (found == NULL) {
      fprintf(stderr, "requested export is not a defined function: %s\n", exports[e]);
      return -1;
    }
    if (!enforce_c_abi) continue;
    MIR_func_t func = found->u.func;
    if (func->vararg_p || VARR_LENGTH(MIR_var_t, func->vars) < func->nargs) {
      fprintf(stderr, "unsupported signature for export %s\n", exports[e]);
      return -1;
    }
    for (size_t i = 0; i < func->nargs; i++) {
      MIR_type_t type = VARR_GET(MIR_var_t, func->vars, i).type;
      if (type != MIR_T_D && type != MIR_T_P) {
        fprintf(stderr, "unsupported argument type in export %s\n", exports[e]);
        return -1;
      }
    }
    if (func->nres > 1 || (func->nres == 1 && func->res_types[0] != MIR_T_D
                           && func->res_types[0] != MIR_T_P)) {
      fprintf(stderr, "unsupported result type in export %s\n", exports[e]);
      return -1;
    }
    fprintf(stderr, "export %s: %s(", exports[e],
            func->nres == 0 ? "void" : func->res_types[0] == MIR_T_D ? "double" : "char *");
    for (size_t i = 0; i < func->nargs; i++) {
      if (i) fputs(", ", stderr);
      fputs(VARR_GET(MIR_var_t, func->vars, i).type == MIR_T_D ? "double" : "char *", stderr);
    }
    fputs(")\n", stderr);
  }
  return 0;
}

static char *add_export_directives(const char *text, char **exports, size_t n_exports,
                                   size_t *size_out) {
  char *end_module = NULL;
  size_t directives_size = 0;
  for (size_t i = 0; i < n_exports; i++) directives_size += strlen(exports[i]) + sizeof("\texport\t\n") - 1;
  for (char *p = (char *)text; (p = strstr(p, "endmodule")) != NULL; p++) end_module = p;
  if (end_module == NULL) return NULL;
  size_t n = strlen(text);
  char *result = malloc(n + directives_size + 1);
  if (result == NULL) return NULL;
  size_t prefix = (size_t)(end_module - text), at = 0;
  memcpy(result, text, prefix); at += prefix;
  for (size_t i = 0; i < n_exports; i++) {
    int written = sprintf(result + at, "\texport\t%s\n", exports[i]);
    at += (size_t)written;
  }
  strcpy(result + at, end_module);
  *size_out = at + strlen(end_module);
  return result;
}

int main(int argc, char **argv) {
  MIR_context_t ctx;
  MIR_module_t module;
  MIR_item_t item;
  char *text;
  char *exported_text;
  char *exports[128];
  size_t n_exports = 0;
  int direct_shared = 0, explicit_exports = 0;
  void *object = NULL;
  size_t object_size = 0;
  size_t import_count = 0;
  import_binding_t *imports = NULL;
  int gen_initialized = 0;
  FILE *out;
  int rc = 1;
  const char *input_path = NULL, *output_path = NULL;
  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "--export") == 0) {
      if (++i >= argc || n_exports == sizeof(exports) / sizeof(exports[0])
          || !valid_mir_identifier(argv[i])) {
        fprintf(stderr, "--export requires a valid MIR function name\n");
        return 2;
      }
      explicit_exports = 1;
      for (size_t j = 0; j < n_exports; j++)
        if (strcmp(exports[j], argv[i]) == 0) {
          fprintf(stderr, "duplicate export: %s\n", argv[i]);
          return 2;
        }
      exports[n_exports++] = argv[i];
    } else if (strcmp(argv[i], "--direct-shared") == 0) {
      direct_shared = 1;
    } else if (input_path == NULL) input_path = argv[i];
    else if (output_path == NULL) output_path = argv[i];
    else {
      fprintf(stderr, "unexpected argument: %s\n", argv[i]);
      return 2;
    }
  }
  if (input_path == NULL || output_path == NULL || (direct_shared && !explicit_exports)) {
    fprintf(stderr, "usage: %s [--export NAME ...] [--direct-shared] input.mir output\n", argv[0]);
    return 2;
  }
  if (!explicit_exports) exports[n_exports++] = "main";
  text = read_all(input_path);
  if (!text) {
    perror(input_path);
    return 2;
  }
  for (size_t i = 0; i < n_exports; i++) {
    if (!text_defines_func(text, exports[i])) {
      fprintf(stderr, "requested export is not defined in MIR input: %s\n", exports[i]);
      free(text);
      return 2;
    }
  }
  size_t exported_size;
  exported_text = add_export_directives(text, exports, n_exports, &exported_size);
  if (!exported_text) {
    fprintf(stderr, "MIR input has no endmodule or export allocation failed\n");
    free(text);
    return 2;
  }
  (void)exported_size;
  free(text);
  char *ordered_text = move_lrefs_before_functions(exported_text);
  free(exported_text);
  if (ordered_text == NULL) {
    fprintf(stderr, "out of memory while ordering MIR lref declarations\n");
    return 2;
  }
  ctx = MIR_init();
  MIR_scan_string(ctx, ordered_text);
  free(ordered_text);
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module)) {
    if (validate_function_exports(ctx, module, exports, n_exports, explicit_exports) != 0)
      goto done;
    MIR_load_module(ctx, module);
  }
  MIR_gen_init(ctx);
  gen_initialized = 1;
  MIR_gen_set_object_mode(ctx, 1);
  imports = defer_import_resolution(ctx, &import_count);
  if (imports == NULL && import_count != 0) {
    fprintf(stderr, "out of memory while deferring object imports\n");
    goto done;
  }
  MIR_link(ctx, MIR_set_gen_interface, NULL);
  restore_import_bindings(ctx, imports, import_count);
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
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
  if (direct_shared) {
    struct MIR_object_exec_params params = {0};
    static const char *const needed[] = {"libc.so.6", "libm.so.6"};
    params.shared_p = 1;
    params.needed = needed;
    params.n_needed = sizeof(needed) / sizeof(needed[0]);
    if (MIR_gen_object_emit_executable(ctx, &params, &object, &object_size) != 0 || !object) {
      fprintf(stderr, "MIR_gen_object_emit_executable(shared) failed\n");
      goto done;
    }
  } else {
    if (MIR_gen_object_emit(ctx, &object, &object_size) != 0 || !object) {
      fprintf(stderr, "MIR_gen_object_emit failed\n");
      goto done;
    }
    if (restore_elf_import_bindings(ctx, object, object_size, imports, import_count) != 0) {
      fprintf(stderr, "failed to restore strong ELF import bindings\n");
      goto done;
    }
  }
  out = fopen(output_path, "wb");
  if (!out) {
    perror(output_path);
    goto done;
  }
  if (fwrite(object, 1, object_size, out) != object_size || fclose(out) != 0) {
    perror(argv[2]);
    goto done;
  }
  fprintf(stderr, "wrote %zu-byte ELF object\n", object_size);
  rc = 0;
done:
  free(imports);
  free(object);
  if (gen_initialized) MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return rc;
}
