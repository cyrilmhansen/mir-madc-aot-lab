/* Minimal MIR API case: a reference to anonymous lref data cannot be printed. */
#include "mir.h"

#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
  if (argc > 1 && strcmp(argv[1], "read") == 0) {
    char text[32768];
    size_t n = fread(text, 1, sizeof(text) - 1, stdin);
    text[n] = '\0';
    MIR_context_t reader = MIR_init();
    MIR_scan_string(reader, text);
    puts("read-ok");
    MIR_finish(reader);
    return 0;
  }
  int named = argc > 1 && strcmp(argv[1], "named") == 0;
  MIR_context_t ctx = MIR_init();
  MIR_module_t module = MIR_new_module(ctx, "lref_test");
  MIR_item_t func = MIR_new_func(ctx, "test", 0, NULL, 0);
  MIR_label_t ret = MIR_new_label(ctx);
  MIR_item_t data = MIR_new_lref_data(ctx, named ? "return_addr_0" : NULL, ret, NULL, 0);
  MIR_reg_t value = MIR_new_func_reg(ctx, func->u.func, MIR_T_I64, "return_addr");
  MIR_append_insn(ctx, func,
                  MIR_new_insn(ctx, MIR_MOV, MIR_new_reg_op(ctx, value), MIR_new_ref_op(ctx, data)));
  MIR_append_insn(ctx, func, ret);
  MIR_append_insn(ctx, func, MIR_new_ret_insn(ctx, 0));
  MIR_finish_func(ctx);
  MIR_finish_module(ctx);
  fprintf(stderr, "lref item name: %s\n", MIR_item_name(ctx, data) ? MIR_item_name(ctx, data) : "(null)");
  MIR_output(ctx, stdout);
  MIR_finish(ctx);
  return 0;
}
