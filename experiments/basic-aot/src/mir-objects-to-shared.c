/* Merge MADC/MIR ET_REL inputs and emit an ELF ET_DYN without a system linker. */
#define _GNU_SOURCE
#include "mir-debug.h"

#include <elf.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

typedef struct {
  unsigned char *data;
  size_t size;
} file_t;

static file_t read_file(const char *path) {
  file_t f = {0};
  FILE *in = fopen(path, "rb");
  long n;
  if (in == NULL || fseek(in, 0, SEEK_END) != 0 || (n = ftell(in)) < 0
      || fseek(in, 0, SEEK_SET) != 0) {
    if (in) fclose(in);
    return f;
  }
  f.data = malloc((size_t)n ? (size_t)n : 1);
  if (f.data == NULL || fread(f.data, 1, (size_t)n, in) != (size_t)n) {
    free(f.data);
    f.data = NULL;
    fclose(in);
    return f;
  }
  fclose(in);
  f.size = (size_t)n;
  return f;
}

static int valid_elf64(const unsigned char *data, size_t size, Elf64_Ehdr **eh_out,
                       Elf64_Phdr **ph_out) {
  if (size < sizeof(Elf64_Ehdr)) return 0;
  Elf64_Ehdr *eh = (Elf64_Ehdr *)data;
  if (memcmp(eh->e_ident, ELFMAG, SELFMAG) || eh->e_ident[EI_CLASS] != ELFCLASS64
      || eh->e_ident[EI_DATA] != ELFDATA2LSB || eh->e_phentsize != sizeof(Elf64_Phdr)
      || eh->e_phoff > size || eh->e_phnum > (size - eh->e_phoff) / sizeof(Elf64_Phdr))
    return 0;
  *eh_out = eh;
  *ph_out = (Elf64_Phdr *)(data + eh->e_phoff);
  return 1;
}

/* Direct MIR ELF images have identity p_offset/p_vaddr layout. */
static int patch_image(unsigned char *data, size_t size, char **hidden, size_t n_hidden,
                       char **required, size_t n_required) {
  Elf64_Ehdr *eh;
  Elf64_Phdr *ph;
  Elf64_Dyn *dyn = NULL;
  size_t dyn_size = 0;
  if (!valid_elf64(data, size, &eh, &ph) || eh->e_type != ET_DYN) return -1;
  for (size_t i = 0; i < eh->e_phnum; i++)
    if (ph[i].p_type == PT_DYNAMIC) {
      if (ph[i].p_offset > size || ph[i].p_filesz > size - ph[i].p_offset) return -1;
      dyn = (Elf64_Dyn *)(data + ph[i].p_offset);
      dyn_size = ph[i].p_filesz / sizeof(*dyn);
      break;
    }
  if (dyn == NULL) return -1;
  uint64_t sym_vaddr = 0, str_vaddr = 0, str_size = 0, sym_ent = 0;
  for (size_t i = 0; i < dyn_size && dyn[i].d_tag != DT_NULL; i++) {
    if (dyn[i].d_tag == DT_SYMTAB) sym_vaddr = dyn[i].d_un.d_ptr;
    if (dyn[i].d_tag == DT_STRTAB) str_vaddr = dyn[i].d_un.d_ptr;
    if (dyn[i].d_tag == DT_STRSZ) str_size = dyn[i].d_un.d_val;
    if (dyn[i].d_tag == DT_SYMENT) sym_ent = dyn[i].d_un.d_val;
  }
  uint64_t nchain = 0;
  for (size_t i = 0; i < dyn_size && dyn[i].d_tag != DT_NULL; i++)
    if (dyn[i].d_tag == DT_HASH) {
      uint64_t off = dyn[i].d_un.d_ptr;
      if (off > size || 2 * sizeof(uint32_t) > size - off) return -1;
      nchain = ((uint32_t *)(data + off))[1];
      break;
    }
  if (sym_ent != sizeof(Elf64_Sym) || sym_vaddr > size || str_vaddr > size
      || str_size > size - str_vaddr || nchain == 0
      || nchain > (size - sym_vaddr) / sizeof(Elf64_Sym))
    return -1;
  Elf64_Sym *syms = (Elf64_Sym *)(data + sym_vaddr);
  const char *strs = (const char *)(data + str_vaddr);
  unsigned char *required_seen = calloc(n_required ? n_required : 1, 1);
  unsigned char *hidden_seen = calloc(n_hidden ? n_hidden : 1, 1);
  if (required_seen == NULL || hidden_seen == NULL) {
    free(required_seen); free(hidden_seen); return -1;
  }
  for (uint64_t i = 1; i < nchain; i++) {
    if (syms[i].st_name >= str_size
        || memchr(strs + syms[i].st_name, '\0', str_size - syms[i].st_name) == NULL)
      goto fail;
    const char *name = strs + syms[i].st_name;
    for (size_t j = 0; j < n_hidden; j++)
      if (strcmp(name, hidden[j]) == 0) {
        if (syms[i].st_shndx == SHN_UNDEF) goto fail;
        syms[i].st_other = (syms[i].st_other & ~0x3) | STV_HIDDEN;
        hidden_seen[j] = 1;
      }
    for (size_t j = 0; j < n_required; j++)
      if (strcmp(name, required[j]) == 0) {
        if (syms[i].st_shndx != SHN_UNDEF
            || ELF64_ST_BIND(syms[i].st_info) != STB_GLOBAL)
          goto fail;
        required_seen[j] = 1;
      }
  }
  for (size_t i = 0; i < n_hidden; i++) if (!hidden_seen[i]) {
    fprintf(stderr, "requested hidden symbol not present in .dynsym: %s\n", hidden[i]);
    goto fail;
  }
  for (size_t i = 0; i < n_required; i++) if (!required_seen[i]) {
    fprintf(stderr, "required strong undefined dynamic symbol not present: %s\n", required[i]);
    goto fail;
  }
  free(required_seen); free(hidden_seen);
  return 0;
fail:
  free(required_seen); free(hidden_seen);
  return -1;
}

int main(int argc, char **argv) {
  const char *output = NULL, *runpath = NULL;
  char *needed[32], *hidden[256], *required[256], *inputs[64];
  size_t n_needed = 0, n_hidden = 0, n_required = 0, n_inputs = 0;
  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "--needed") == 0 && i + 1 < argc) {
      if (n_needed == sizeof(needed) / sizeof(needed[0])) return 2;
      needed[n_needed++] = argv[++i];
    } else if (strcmp(argv[i], "--runpath") == 0 && i + 1 < argc) {
      runpath = argv[++i];
    } else if (strcmp(argv[i], "--hide") == 0 && i + 1 < argc) {
      if (n_hidden == sizeof(hidden) / sizeof(hidden[0])) return 2;
      hidden[n_hidden++] = argv[++i];
    } else if (strcmp(argv[i], "--require") == 0 && i + 1 < argc) {
      if (n_required == sizeof(required) / sizeof(required[0])) return 2;
      required[n_required++] = argv[++i];
    } else if (output == NULL) output = argv[i];
    else if (n_inputs < sizeof(inputs) / sizeof(inputs[0])) inputs[n_inputs++] = argv[i];
    else return 2;
  }
  if (output == NULL || n_inputs == 0 || n_needed == 0) {
    fprintf(stderr, "usage: %s [--needed SONAME] [--runpath PATH] [--hide SYMBOL] "
                    "[--require IMPORT] output.so input.o...\n", argv[0]);
    return 2;
  }
  MIR_object_t obj = MIR_object_create();
  if (obj == NULL) { fputs("MIR_object_create failed\n", stderr); return 1; }
  int rc = 1;
  for (size_t i = 0; i < n_inputs; i++) {
    file_t f = read_file(inputs[i]);
    char err[512] = {0};
    if (f.data == NULL || MIR_object_read(obj, f.data, f.size, err, sizeof err) != 0) {
      fprintf(stderr, "MIR_object_read(%s): %s\n", inputs[i],
              err[0] ? err : "could not read input");
      free(f.data);
      goto done;
    }
    free(f.data);
  }
  for (size_t i = 0; i < n_required; i++) {
    int found = 0;
    for (size_t j = 0;; j++) {
      const char *name = MIR_object_undef_name(obj, j);
      if (name == NULL) break;
      if (strcmp(name, required[i]) == 0) {
        found = 1;
        if (MIR_object_undef_weak_p(obj, j)) {
          fprintf(stderr, "required import is weak in input objects: %s\n", required[i]);
          goto done;
        }
      }
    }
    if (!found) {
      fprintf(stderr, "required import is not undefined in input objects: %s\n", required[i]);
      goto done;
    }
  }
  struct MIR_object_exec_params params = {0};
  params.shared_p = 1;
  params.needed = (const char *const *)needed;
  params.n_needed = n_needed;
  params.runpath = runpath;
  void *image = NULL;
  size_t image_size = 0;
  if (MIR_object_emit_executable(obj, &params, &image, &image_size) != 0 || image == NULL) {
    fputs("MIR_object_emit_executable(shared) failed\n", stderr);
    free(image);
    goto done;
  }
  if (patch_image(image, image_size, hidden, n_hidden, required, n_required) != 0) {
    fputs("failed to enforce requested dynamic-symbol visibility/import strength\n", stderr);
    free(image);
    goto done;
  }
  FILE *out = fopen(output, "wb");
  int write_ok = out != NULL && fwrite(image, 1, image_size, out) == image_size;
  int close_rc = out != NULL ? fclose(out) : 0;
  if (!write_ok || close_rc != 0) {
    perror(output);
    free(image);
    goto done;
  }
  chmod(output, 0755);
  fprintf(stderr, "wrote %zu-byte MIR-linked ET_DYN from %zu MIR ET_REL inputs\n",
          image_size, n_inputs);
  free(image);
  rc = 0;
done:
  MIR_object_destroy(obj);
  return rc;
}
