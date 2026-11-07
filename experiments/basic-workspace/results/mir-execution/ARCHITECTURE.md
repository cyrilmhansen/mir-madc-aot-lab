# Structured Workspace → MIR execution: design boundary

## Decision before implementation

The canonical `Document.tokens` list remains the only editable BASIC source.
The existing token IDs, token-to-symbol bindings, function scopes and current
revision are the inputs to a derived immutable projection. Projection parsing
walks those tokens directly; it does not call `render_document`, `lex`, or the
historical BASIC parser. It recognizes only numeric `FUNCTION` bodies made of
assignments and arithmetic/function-call expressions. Anything outside that
subset is an explicit diagnostic.

The projection contains opaque function/variable identities plus typed
constants, variable references, arithmetic nodes, resolved numeric calls and
assignment statements. It is tied to `(document_id, revision)` and discarded
after the request. It is a compilation view, not a second editable syntax
tree.

A small native worker will receive a length-checked binary encoding of this
projection over stdin. The worker uses the public MIR C API to create function
prototypes, forward function items, MIR functions, double-precision registers,
instructions and call edges. It loads the resulting MIR module and executes
one requested function using either `MIR_interp_arr` or a generated native
function pointer. The worker process is terminated after the request; it owns
and releases the MIR context and generated code. A Python subprocess timeout
limits nontermination for JIT calls and contains worker faults. No BASIC, MIR,
object or program executable is written by this path.

The native worker itself is a rebuildable project utility. Its build output is
under the experiment's ignored `native/build/` directory and is not an output
of compiling a BASIC program.

## Historical frontend and behavior reference

The historical `basicc.c` provides the semantic reference but is not imported
as a parser library: it shares global `g_ctx`, `g_func`, `g_vars`, parser
vectors, arena-backed nodes and runtime state. Pulling it into an isolated
module would be a broader refactor. Its numeric default is `double`; its
`gen_program` initializes newly discovered variables to zero, which the
projection must preserve. The historical interpreter and JIT can be exercised
as downstream reference consumers using temporary BASIC driver files only in
the validation harness. Such files are not read by the new execution path.

## MIR API evidence

The pinned MADC MIR headers expose `MIR_new_module`, `MIR_new_proto_arr`,
`MIR_new_forward`, `MIR_new_func_arr`, `MIR_new_func_reg`, `MIR_new_insn_arr`,
`MIR_new_ret_insn`, `MIR_finish_func`, `MIR_finish_module`, `MIR_load_module`,
`MIR_link`, `MIR_interp_arr`, `MIR_gen_init`, `MIR_gen`, `MIR_gen_finish` and
`MIR_finish`. `MIR_T_D` and `MIR_DADD` / `MIR_DSUB` / `MIR_DMUL` / `MIR_DDIV`
are the selected numeric representation and operations. Internal calls use a
prototype plus a reference to a forward/defined function item, following the
historical BASIC compiler's two-pass declaration pattern.

## Constraints

- Initial subset: complete numeric `FUNCTION` declarations; double constants,
  scoped numeric variables/parameters, `+ - * /`, parentheses, unary signs,
  assignments, and resolved numeric function calls.
- Function call graphs may be recursive in the MIR program, but execution is
  always isolated in a worker with a deadline. No external imports are
  accepted.
- Strings, `SUB`, `DEF FN`, arrays, branches/loops, global main-program
  statements, builtins and incomplete/ambiguous functions are rejected.
- There is no compiled MIR cache in this first vertical slice. Each execution
  gets a fresh MIR context in a short-lived worker, so a failed edit preserves
  the old revision naturally and a committed revision can never hit stale
  generated code. Projection construction and MIR build costs are measured
  separately where possible.
- Interpreter and JIT results are doubles. Tests compare finite results with a
  stated floating-point tolerance and exact status/identity/revision behavior.
