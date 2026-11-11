# External imports

Three C helpers are imported by MIR prototypes: an eight-I64 weighted checksum, an alternating I64/double checksum, and a pointer-plus-length buffer writer/checksum. Exact prototypes are used on both sides. `MIR_load_external` binds the JIT/interpreter external path; native object/shared paths resolve the same symbols from an independently compiled client executable exported with `-rdynamic`; the object loader uses an explicit resolver.

The pointer helper writes only eight bytes within an initialized region. Tests compare the entire buffer and both canary regions. Repeated calls use reset buffers. All expected values are computed independently in the C fixture/reference.

The missing-import object-loader control withholds `abi_c_mixed`; `MIR_object_load` rejects with an unresolved-symbol diagnostic and nonzero status. No variadic import was attempted.
