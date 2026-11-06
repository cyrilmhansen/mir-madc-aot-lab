/* Run a basicc -r MIR module twice in one process through the historical JIT. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"
#include "basic_runtime.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

extern void basic_print(basic_num_t);
extern void basic_print_str(const char *);
extern basic_num_t basic_read(void);
extern char *basic_read_str(void);
extern void basic_restore(void);
extern void basic_enable_line_tracking(basic_num_t);
extern void basic_set_line(basic_num_t);

static void *resolve(const char *name) {
#define RESOLVE(n, fn) if (strcmp(name, n) == 0) return (void *)(uintptr_t)&fn
  RESOLVE("basic_data_init", basic_data_init);
  RESOLVE("basic_data_add_num", basic_data_add_num);
  RESOLVE("basic_data_add_str", basic_data_add_str);
  RESOLVE("basic_data_fini", basic_data_fini);
  RESOLVE("basic_read", basic_read);
  RESOLVE("basic_read_str", basic_read_str);
  RESOLVE("basic_restore", basic_restore);
  RESOLVE("basic_print", basic_print);
  RESOLVE("basic_print_str", basic_print_str);
  RESOLVE("basic_enable_line_tracking", basic_enable_line_tracking);
  RESOLVE("basic_set_line", basic_set_line);
#undef RESOLVE
  /* The compiler declares unused runtime imports in every module. */
  return (void *)(uintptr_t)&basic_data_init;
}

int main(int argc, char **argv) {
  MIR_context_t ctx;
  MIR_module_t module;
  MIR_item_t item, main_item = NULL;
  FILE *input;
  int64_t (*entry)(void);
  if (argc != 2) return 2;
  ctx = MIR_init();
  input = fopen(argv[1], "rb");
  if (!input) { perror(argv[1]); return 2; }
  MIR_read(ctx, input);
  fclose(input);
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module)) {
    MIR_load_module(ctx, module);
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item && !strcmp(MIR_item_name(ctx, item), "main"))
        main_item = item;
  }
  if (!main_item) return 3;
  MIR_gen_init(ctx);
  MIR_link(ctx, MIR_set_gen_interface, resolve);
  entry = (int64_t (*)(void))MIR_gen(ctx, main_item);
  (void)entry();
  (void)entry();
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return 0;
}
