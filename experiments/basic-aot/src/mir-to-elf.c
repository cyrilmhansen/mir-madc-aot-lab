/* Parse historical BASIC MIR text with the MADC-integrated MIR and emit ELF ET_REL. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"

#include <stdio.h>
#include <elf.h>
#include <stdlib.h>
#include <string.h>

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

int main(int argc, char **argv) {
  MIR_context_t ctx;
  MIR_module_t module;
  MIR_item_t item;
  char *text;
  char *end_module;
  char *exported_text;
  void *object = NULL;
  size_t object_size = 0;
  size_t import_count = 0;
  import_binding_t *imports = NULL;
  FILE *out;
  int rc = 1;
  if (argc != 3) {
    fprintf(stderr, "usage: %s input.mir output.o\n", argv[0]);
    return 2;
  }
  text = read_all(argv[1]);
  if (!text) {
    perror(argv[1]);
    return 2;
  }
  /* basicc does not mark its generated main function exported. Add it while
     the MIR parser is still in the module, as required by MIR syntax. */
  end_module = NULL;
  for (char *p = text; (p = strstr(p, "endmodule")) != NULL; p++)
    end_module = p;
  if (end_module == NULL) {
    fprintf(stderr, "input has no endmodule\n");
    free(text);
    return 2;
  }
  exported_text = malloc(strlen(text) + sizeof("\texport\tmain\n"));
  if (!exported_text) {
    free(text);
    return 2;
  }
  size_t prefix = (size_t)(end_module - text);
  memcpy(exported_text, text, prefix);
  memcpy(exported_text + prefix, "\texport\tmain\n", sizeof("\texport\tmain\n") - 1);
  strcpy(exported_text + prefix + sizeof("\texport\tmain\n") - 1, end_module);
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
    MIR_load_module(ctx, module);
  }
  MIR_gen_init(ctx);
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
      if (item->item_type == MIR_func_item) (void)MIR_gen(ctx, item);
  if (MIR_gen_object_emit(ctx, &object, &object_size) != 0 || !object) {
    fprintf(stderr, "MIR_gen_object_emit failed\n");
    goto done;
  }
  if (restore_elf_import_bindings(ctx, object, object_size, imports, import_count) != 0) {
    fprintf(stderr, "failed to restore strong ELF import bindings\n");
    goto done;
  }
  out = fopen(argv[2], "wb");
  if (!out) {
    perror(argv[2]);
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
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return rc;
}
