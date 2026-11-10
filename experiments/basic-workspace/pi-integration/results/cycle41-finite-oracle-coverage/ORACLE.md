# Independent oracle

Generated finite tables are calculated by the Cycle39 mathematical template evaluator in campaign tooling, outside Cycle20. The generator retains an explicit mathematical specification for each function and calculates every table row from that specification before writing the host-owned maintenance contract. It never reads MIR outputs to generate expectations. The contract digest is then bound by the verified continuation process.

The table is finite evidence, not a proof over all numeric inputs. Inputs are boundary-oriented, include each relevant threshold and adjacent values, and include deterministic interior values. All campaign values/results are finite and integer-valued for the generated programs (serialized JSON may display `0.0`). Negative values are used as inputs, but not as edited unary-minus literal nodes.

The v2/v3 equivalence fixture independently computes the same clamp and threshold results arithmetically, then runs both contracts against the same Cycle34 baseline and target set. The v3 mode also receives an intentionally wrong but well-formed table; preview rejects it as an oracle mismatch without mutation. Input rows reordered consistently retain the same mapping; table contract and continuation tampering tests confirm the contract bytes are trust-bound.
