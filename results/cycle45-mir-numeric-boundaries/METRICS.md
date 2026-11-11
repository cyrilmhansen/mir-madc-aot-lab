# Metrics

- Unique opcode names added: 18 new names (10 conversions + 8 overflow; EXT8, UEXT8, I2D, F2D were already in the Cycle44 set)
- Cumulative unique opcode-name coverage: 56/248, assuming Cycle44 baseline 38/248
- Conversion observations: 238
- Overflow result/flag observations: 208
- Total interpreter/JIT independent comparisons: 446
- Fresh text replay: 446
- Fresh binary replay: 446
- Native ELF object: 12 independent C client checks passed
- Genuine MIR discrepancies: 0
- Structural injected reducer checks: 2/2 reduced
- Production runtime changes: 0
