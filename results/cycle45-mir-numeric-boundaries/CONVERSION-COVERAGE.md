# Conversion coverage

14 concrete conversion opcode names executed: six extension forms, four integer-to-float forms, two float-to-I64 forms and F2D/D2F. Each ran 17 deterministic observations (238 total). Values include narrow sign-bit boundaries, high-bit patterns, integer exactness boundaries, fractional truncation values, and finite in-range values near I64 limits. F2I/D2I out-of-range and nonfinite cases are excluded because C conversion behavior is undefined or target-specific there. Floating outputs are compared by exact representation bits on the recorded Linux x86-64 host. Signed zero is preserved as a bit-pattern observation where applicable.

No claim is made for distinct LD precision on this build. Conversion chains and converted conditional branches are not part of the executed corpus; those requested families remain open coverage.
