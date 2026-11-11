# Failures and preserved bring-up observations

No genuine MIR execution mismatch was confirmed. During harness bring-up, an initial oracle draft compared floating numeric values against bit observations; this produced a false mismatch and was corrected by using explicit output bit patterns. The first reducer draft could leave a removed operation's dependent temporary uninitialized; the reducer was corrected to remove dependent operations as a closure, and the accepted reduction now regenerates a valid program. These harness failures are preserved here; neither is counted as a product finding.

The injected reducer discrepancies are documented separately and are not product findings.
