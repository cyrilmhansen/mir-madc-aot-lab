# Independent references

Each matrix function computes a weighted sum with distinct odd coefficients. Integer values are small and bounded so no signed overflow occurs. Floating arguments use exact binary fractions; the oracle applies explicit conversions for integer, float and double inputs and exact equality is used. Mixed outputs are double results with explicit integer-to-double conversion in both reference and MIR body.

The separately compiled C imports implement the checksum or pointer write directly and independently of MIR. The MIR implementation does not call an oracle to obtain expected values. Pointer expectations are calculated from the specified byte pattern; tests compare returned checksum, full buffer and canaries.

These finite inputs validate tested signatures and values, not every possible value. C and MIR share the platform's scalar ABI only where the client exercises the generated native code; interpreter calls are separately classified.
