# Pinned MIR API inventory

Generated from `madc/third_party/mir` and `madc/obj/mir/host/libmir.a`.

- Header function-like names inventoried: 181.
- MIR-prefixed archive exports: 171.
- Concrete opcode enumerators: 248.
- MIR type enum values: 18.

## Declared API names

| API | Header | Archive status |
|---|---|---|
| `MIR_FP_branch_code_p` | mir.h (inline) | header_inline |
| `MIR_abandon_module` | mir.h | exported |
| `MIR_add_alias_conflict` | mir.h | exported |
| `MIR_addr_code_p` | mir.h (inline) | header_inline |
| `MIR_alias` | mir.h | exported |
| `MIR_alias_conflict_p` | mir.h | exported |
| `MIR_alias_name` | mir.h | exported |
| `MIR_any_branch_code_p` | mir.h (inline) | header_inline |
| `MIR_append_insn` | mir.h | exported |
| `MIR_branch_code_p` | mir.h (inline) | header_inline |
| `MIR_call_code_p` | mir.h (inline) | header_inline |
| `MIR_change_module_ctx` | mir.h | exported |
| `MIR_copy_insn` | mir.h | exported |
| `MIR_debug_add_bitfield` | mir-debug.h | exported |
| `MIR_debug_add_enumerator` | mir-debug.h | exported |
| `MIR_debug_add_file` | mir-debug.h | exported |
| `MIR_debug_add_func` | mir-debug.h | exported |
| `MIR_debug_add_member` | mir-debug.h | exported |
| `MIR_debug_add_param_type` | mir-debug.h | exported |
| `MIR_debug_add_var` | mir-debug.h | exported |
| `MIR_debug_array_type` | mir-debug.h | exported |
| `MIR_debug_base_type` | mir-debug.h | exported |
| `MIR_debug_destroy` | mir-debug.h | exported |
| `MIR_debug_emit` | mir-debug.h | exported |
| `MIR_debug_enum_type` | mir-debug.h | exported |
| `MIR_debug_func_type` | mir-debug.h | exported |
| `MIR_debug_gdb_register` | mir-debug.h | exported |
| `MIR_debug_gdb_unregister` | mir-debug.h | exported |
| `MIR_debug_init` | mir-debug.h | exported |
| `MIR_debug_pointer_type` | mir-debug.h | exported |
| `MIR_debug_struct_type` | mir-debug.h | exported |
| `MIR_debug_typedef_type` | mir-debug.h | exported |
| `MIR_finish` | mir.h | exported |
| `MIR_finish_func` | mir.h | exported |
| `MIR_finish_module` | mir.h | exported |
| `MIR_func_debug_homes_only` | mir.h | exported |
| `MIR_func_debug_homes_only_p` | mir.h | exported |
| `MIR_gen` | mir-gen.h | exported |
| `MIR_gen_cfi_cie` | mir-gen.h | exported |
| `MIR_gen_finish` | mir-gen.h | exported |
| `MIR_gen_get_code` | mir-gen.h | exported |
| `MIR_gen_get_object` | mir-gen.h | exported |
| `MIR_gen_init` | mir-gen.h | exported |
| `MIR_gen_object_emit` | mir-gen.h | exported |
| `MIR_gen_object_emit_executable` | mir-gen.h | exported |
| `MIR_gen_object_prepare` | mir-gen.h | exported |
| `MIR_gen_set_debug_file` | mir-gen.h | exported |
| `MIR_gen_set_debug_level` | mir-gen.h | exported |
| `MIR_gen_set_object_mode` | mir-gen.h | exported |
| `MIR_gen_set_optimize_level` | mir-gen.h | exported |
| `MIR_get_alloc` | mir.h | exported |
| `MIR_get_error_func` | mir.h | exported |
| `MIR_get_func_redef_permission_p` | mir.h | exported |
| `MIR_get_global_item` | mir.h | declared_without_library_symbol |
| `MIR_get_inline_permission_p` | mir.h | exported |
| `MIR_get_item_func` | mir.h | exported |
| `MIR_get_module_list` | mir.h | exported |
| `MIR_get_spill_all_p` | mir.h | exported |
| `MIR_init` | mir.h (inline) | header_inline |
| `MIR_init2` | mir.h (inline) | header_inline |
| `MIR_insert_insn_after` | mir.h | exported |
| `MIR_insert_insn_before` | mir.h | exported |
| `MIR_insn_name` | mir.h | exported |
| `MIR_insn_nops` | mir.h | exported |
| `MIR_insn_op_mode` | mir.h | exported |
| `MIR_int_branch_code_p` | mir.h (inline) | header_inline |
| `MIR_interp` | mir.h | exported |
| `MIR_interp_arr` | mir.h | exported |
| `MIR_interp_arr_varg` | mir.h | exported |
| `MIR_item_align` | mir.h | exported |
| `MIR_item_name` | mir.h | exported |
| `MIR_item_set_align` | mir.h | exported |
| `MIR_item_set_binding` | mir.h | exported |
| `MIR_link` | mir.h | exported |
| `MIR_load_external` | mir.h | exported |
| `MIR_load_module` | mir.h | exported |
| `MIR_module_link_check` | mir.h | exported |
| `MIR_module_privatize_for_link` | mir.h | exported |
| `MIR_new_alias_mem_op` | mir.h | exported |
| `MIR_new_bss` | mir.h | exported |
| `MIR_new_call_insn` | mir.h | exported |
| `MIR_new_data` | mir.h | exported |
| `MIR_new_double_op` | mir.h | exported |
| `MIR_new_export` | mir.h | exported |
| `MIR_new_expr_data` | mir.h | exported |
| `MIR_new_float_op` | mir.h | exported |
| `MIR_new_forward` | mir.h | exported |
| `MIR_new_func` | mir.h | exported |
| `MIR_new_func_arr` | mir.h | exported |
| `MIR_new_func_reg` | mir.h | exported |
| `MIR_new_global_func_reg` | mir.h | exported |
| `MIR_new_import` | mir.h | exported |
| `MIR_new_insn` | mir.h | exported |
| `MIR_new_insn_arr` | mir.h | exported |
| `MIR_new_int_op` | mir.h | exported |
| `MIR_new_jcall_insn` | mir.h | exported |
| `MIR_new_label` | mir.h | exported |
| `MIR_new_label_op` | mir.h | exported |
| `MIR_new_ldouble_op` | mir.h | exported |
| `MIR_new_lref_data` | mir.h | exported |
| `MIR_new_mem_op` | mir.h | exported |
| `MIR_new_module` | mir.h | exported |
| `MIR_new_proto` | mir.h | exported |
| `MIR_new_proto_arr` | mir.h | exported |
| `MIR_new_ref_data` | mir.h | exported |
| `MIR_new_ref_op` | mir.h | exported |
| `MIR_new_reg_op` | mir.h | exported |
| `MIR_new_ret_insn` | mir.h | exported |
| `MIR_new_str_op` | mir.h | exported |
| `MIR_new_string_data` | mir.h | exported |
| `MIR_new_uint_op` | mir.h | exported |
| `MIR_new_unwind_region` | mir.h | exported |
| `MIR_new_vararg_func` | mir.h | exported |
| `MIR_new_vararg_func_arr` | mir.h | exported |
| `MIR_new_vararg_proto` | mir.h | exported |
| `MIR_new_vararg_proto_arr` | mir.h | exported |
| `MIR_object_add_init` | mir-debug.h | exported |
| `MIR_object_add_reloc` | mir-debug.h | exported |
| `MIR_object_add_symbol` | mir-debug.h | exported |
| `MIR_object_addrpool_append` | mir-debug.h | exported |
| `MIR_object_bss_reserve` | mir-debug.h | exported |
| `MIR_object_create` | mir-debug.h | exported |
| `MIR_object_data_append` | mir-debug.h | exported |
| `MIR_object_destroy` | mir-debug.h | exported |
| `MIR_object_emit` | mir-debug.h | exported |
| `MIR_object_emit_executable` | mir-debug.h | exported |
| `MIR_object_find_symbol` | mir-debug.h | exported |
| `MIR_object_load` | mir-debug.h | exported |
| `MIR_object_loaded_init_array` | mir-debug.h | exported |
| `MIR_object_loaded_sym` | mir-debug.h | exported |
| `MIR_object_loaded_unload` | mir-debug.h | exported |
| `MIR_object_read` | mir-debug.h | exported |
| `MIR_object_section_append` | mir-debug.h | exported |
| `MIR_object_section_bytes` | mir-debug.h | exported |
| `MIR_object_section_symbol` | mir-debug.h | exported |
| `MIR_object_set_debug` | mir-debug.h | exported |
| `MIR_object_symbol_define` | mir-debug.h | exported |
| `MIR_object_symbol_defined_p` | mir-debug.h | exported |
| `MIR_object_text_append` | mir-debug.h | exported |
| `MIR_object_undef_name` | mir-debug.h | exported |
| `MIR_object_undef_weak_p` | mir-debug.h | exported |
| `MIR_op_eq_p` | mir.h | exported |
| `MIR_op_hash_step` | mir.h | exported |
| `MIR_output` | mir.h | exported |
| `MIR_output_insn` | mir.h | exported |
| `MIR_output_item` | mir.h | exported |
| `MIR_output_module` | mir.h | exported |
| `MIR_output_op` | mir.h | exported |
| `MIR_output_str` | mir.h | exported |
| `MIR_overflow_insn_code_p` | mir.h (inline) | header_inline |
| `MIR_prepend_insn` | mir.h | exported |
| `MIR_read` | mir.h | exported |
| `MIR_read_with_func` | mir.h | exported |
| `MIR_reg` | mir.h | exported |
| `MIR_reg_debug_home_p` | mir.h | exported |
| `MIR_reg_frame_offset` | mir.h | exported |
| `MIR_reg_hard_reg_name` | mir.h | exported |
| `MIR_reg_name` | mir.h | exported |
| `MIR_reg_type` | mir.h | exported |
| `MIR_remove_insn` | mir.h | exported |
| `MIR_reverse_branch_code` | mir.h | exported |
| `MIR_scan_string` | mir.h | exported |
| `MIR_set_error_func` | mir.h | exported |
| `MIR_set_func_noinline` | mir.h | exported |
| `MIR_set_func_redef_permission` | mir.h | exported |
| `MIR_set_func_unwind_base` | mir.h | exported |
| `MIR_set_func_unwind_personality` | mir.h | exported |
| `MIR_set_gen_interface` | mir-gen.h | exported |
| `MIR_set_inline_permission` | mir.h | exported |
| `MIR_set_interp_interface` | mir.h | exported |
| `MIR_set_lazy_bb_gen_interface` | mir-gen.h | exported |
| `MIR_set_lazy_gen_interface` | mir-gen.h | exported |
| `MIR_set_reg_debug_home` | mir.h | exported |
| `MIR_set_source_loc` | mir.h | exported |
| `MIR_set_spill_all` | mir.h | exported |
| `MIR_set_unwind_region` | mir.h | exported |
| `MIR_type_str` | mir.h | exported |
| `MIR_write` | mir.h | exported |
| `MIR_write_module` | mir.h | exported |
| `MIR_write_module_with_func` | mir.h | exported |
| `MIR_write_with_func` | mir.h | exported |
