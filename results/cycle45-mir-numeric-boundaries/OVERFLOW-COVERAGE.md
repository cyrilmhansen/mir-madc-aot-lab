# Overflow coverage

Eight opcode names executed. For each, 13 operand pairs exercised an overflow-flag branch and the arithmetic result (208 observations total). The independent oracle uses wide integer arithmetic and explicit low-32 signed interpretation. Cases include ordinary values, signed limits, high-bit patterns, signed overflow and unsigned multiply overflow. BO observes signed overflow; UBO observes unsigned multiply overflow. ADDO/SUBO's unsigned flag was audited but not separately branched in this bounded harness.
