/* Parse historical BASIC MIR text with the MADC-integrated MIR and emit ELF ET_REL. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"

#include <stdio.h>
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

/* Object capture records unresolved imports as ELF relocations. */
static void *unresolved_import(const char *name) {
  (void)name;
  return (void *)1;
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
  ctx = MIR_init();
  MIR_scan_string(ctx, exported_text);
  free(exported_text);
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module)) {
    MIR_load_module(ctx, module);
  }
  MIR_gen_init(ctx);
  MIR_gen_set_object_mode(ctx, 1);
  MIR_link(ctx, MIR_set_gen_interface, unresolved_import);
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item) (void)MIR_gen(ctx, item);
  if (MIR_gen_object_emit(ctx, &object, &object_size) != 0 || !object) {
    fprintf(stderr, "MIR_gen_object_emit failed\n");
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
  free(object);
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return rc;
}
