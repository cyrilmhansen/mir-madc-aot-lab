# Audit

Initial root HEAD was the expected Cycle45 commit `62360fce496f3cf9745fc50aa4d84dd633c67920`. MADC remained at `868847a76434058483bade03ead09ba6acb9d771`; the MIR source subtree matches historical `f541a7a54624869e29b01f2f30b174bc0329eea5`. The Cycle44 isolated archive hash still matches Cycle45: `9ee503c7bedf7f490df5e097441474b9977cf5fd1c0b497f2297a926528a594a`. The checked-out system archive remains a different artifact. No MADC or MIR source was modified.

Cycle42–45 evidence remains route-specific. Cycle42 and Cycle45 emphasize interpreter/JIT plus persistence; Cycle43 adds CFG and memory; Cycle44 adds ABI, cross-module linking, shared libraries and selected object loader paths. These do not imply general AOT correctness beyond tested cases. Cycle46 combines those tested mechanisms in six dataflow-composite families.

`MIR_gen_set_optimize_level` accepts an unsigned value. Source defines level 0 as fast generation, 1 as register allocation plus combiner, 2 adding GVN/CCP (default), and >=3 as all optimization passes. Cycle46 executed levels 0–3.
