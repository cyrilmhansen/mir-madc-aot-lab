# Signature coverage

The frozen confirmatory matrix contains 48 distinct ordered argument-type sequences. Five deterministic input seeds per shape produce 240 confirmatory function observations. Four separately labelled exploratory mixed-spill shapes add 20 observations, for 260 total. This count measures shape and value observations separately; it is not an opcode count.

Types exercised: I64, U64, I32, U32, P, F and D. Shapes cover zero, one, two, four through ten arguments. The all-I64 arity 7–10 and all-D arity 9–10 signatures cross their respective register classes. Mixed exploratory cases include 8 GP + 2 SSE, 2 GP + 8 SSE, and near-boundary variants. `generated-signatures.json` records the argument sequence, ABI class, assigned register/stack location, return type/location, family and confirmatory/exploratory tier.

Every matrix function weights each argument differently and checks that all positions contribute. Integer reference inputs avoid overflow. Floating inputs are exact binary fractions and outputs are compared exactly. Narrow type identity functions test sign/zero extension through exact C prototypes.

This is a stratified scalar signature matrix, not all permutations of the type set. There are no aggregate, long-double, vector, variadic or cross-target signatures.
