# Opcode contracts

| Opcode family | Contract used | Status |
|---|---|---|
| EXT8/16/32 | Sign-extend low 8/16/32 bits into I64 | Executed |
| UEXT8/16/32 | Zero-extend low 8/16/32 bits into I64 | Executed |
| I2F/I2D | Signed I64 to F/D | Executed |
| UI2F/UI2D | Unsigned I64 bit pattern to F/D | Executed |
| F2I/D2I | Truncate finite in-range F/D toward zero to I64 | Executed; nonfinite/out-of-range excluded |
| F2D/D2F | Precision conversion | Executed |
| ADDO/SUBO/MULO | I64 result with signed overflow condition | Executed; ADDO/SUBO also expose unsigned flag, not exercised here |
| ADDOS/SUBOS/MULOS | Low-32 operation, signed overflow condition | Executed; compare low 32 result bits |
| UMULO/UMULOS | Unsigned overflow condition for 64/32-bit multiplication | Executed |
| LD conversion forms | Canonicalized to D because MIR_LD_IS_D=1 | Not distinct from D; no long-double claim |

Overflow opcodes use a subsequent BO or UBO branch to observe the signed or unsigned overflow state. The arithmetic result is separately returned and compared.
