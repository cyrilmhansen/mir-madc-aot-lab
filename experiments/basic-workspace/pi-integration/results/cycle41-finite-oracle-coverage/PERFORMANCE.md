# Performance

Confirmatory v2/v3 comparison on `Linux-7.3.0-rc6-2-cachyos-rc-x86_64-with-glibc2.44` with Python 3.14.8. Each cell is the median in ms from five fresh gateways; raw samples, min and max are in `benchmark-confirmatory-final/benchmark.json` and the uncontented replication `benchmark-confirmatory-replication-final/benchmark.json`. The 2x threshold was registered before the benchmark. Function count 2, three authorized targets, dependency depth 1.

| Inputs | Measure | v2 median | v3 median | v3/v2 |
|---:|---|---:|---:|---:|
| 16 | Schema validation / parse | 0.0083 | 0.0232 | 2.81x |
| 16 | Expected result lookup | 0.1240 | 0.0178 | 0.14x |
| 16 | Preview | 171.2920 | 172.1945 | 1.01x |
| 16 | Commit revalidation | 172.0284 | 169.3154 | 0.98x |
| 16 | MIR observation loop | 155.2817 | 156.6321 | 1.01x |
| 16 | Final validate + replay | 323.2413 | 326.8051 | 1.01x |
| 32 | Schema validation / parse | 0.0112 | 0.0445 | 3.96x |
| 32 | Expected result lookup | 0.2446 | 0.0238 | 0.10x |
| 32 | Preview | 314.8357 | 327.7402 | 1.04x |
| 32 | Commit revalidation | 329.3023 | 326.9640 | 0.99x |
| 32 | MIR observation loop | 313.4139 | 313.0585 | 1.00x |
| 32 | Final validate + replay | 636.4885 | 639.0036 | 1.00x |
| 64 | Schema validation / parse | 0.0083 | 0.0702 | 8.47x |
| 64 | Expected result lookup | 0.4879 | 0.0516 | 0.11x |
| 64 | Preview | 637.8698 | 634.1604 | 0.99x |
| 64 | Commit revalidation | 647.8555 | 635.2976 | 0.98x |
| 64 | MIR observation loop | 624.0660 | 620.8845 | 0.99x |
| 64 | Final validate + replay | 1257.2621 | 1255.2868 | 1.00x |

The table lookup was lower-latency than formula-oracle evaluation. Schema/table validation itself was 2.5–8.5x the formula-contract parse median across two uncontented five-sample runs at 16, 32 and 64 inputs. This relative increase repeated; its absolute median remained below 0.08 ms per contract, reaching about 0.07 ms at 64 inputs. It reflects validating every input and result cell. Preview, commit, MIR observation and full validation/replay stayed between 0.98x and 1.04x across modes in both runs, with MIR execution dominating. The per-contract parse overhead is a confirmed microbenchmark cost but was not material to end-to-end validation latency. Total validation time increased roughly with the number of input/function executions. This isolated comparison does not measure scaling in function count; generated workflows cover two to three functions. A first benchmark attempt that omitted the historical baseline corpus is retained in `benchmark-confirmatory/`; `benchmark-confirmatory-final/` and `benchmark-confirmatory-replication-final/` include the complete legacy attestation corpus.

## Observed ranges

Each entry reports median `[min,max]` milliseconds from five repetitions; no sample was dropped. Full per-sample values and environment are in each linked JSON result.

| Run | Inputs | Measure | v2 median [min,max] ms | v3 median [min,max] ms |
|---|---:|---|---:|---:|
| run-1 | 16 | Contract/table validation | 0.0083 [0.0079,0.0114] | 0.0232 [0.0203,0.0264] |
| run-1 | 16 | Expected-row lookup | 0.1240 [0.1200,0.1288] | 0.0178 [0.0136,0.0695] |
| run-1 | 16 | Preview | 171.2920 [168.9927,173.1348] | 172.1945 [169.4029,172.5553] |
| run-1 | 16 | Commit revalidation | 172.0284 [169.4841,174.8149] | 169.3154 [166.9006,172.7698] |
| run-1 | 16 | MIR observation loop | 155.2817 [151.5150,158.5901] | 156.6321 [150.9930,161.0939] |
| run-1 | 16 | Final validation + replay | 323.2413 [320.0923,342.6876] | 326.8051 [323.6978,329.4597] |
| run-1 | 32 | Contract/table validation | 0.0112 [0.0064,0.0113] | 0.0445 [0.0379,0.0481] |
| run-1 | 32 | Expected-row lookup | 0.2446 [0.1315,0.2852] | 0.0238 [0.0214,0.0313] |
| run-1 | 32 | Preview | 314.8357 [295.7946,331.8045] | 327.7402 [322.5143,332.4787] |
| run-1 | 32 | Commit revalidation | 329.3023 [269.4869,338.8400] | 326.9640 [319.1887,336.7808] |
| run-1 | 32 | MIR observation loop | 313.4139 [275.0025,328.1732] | 313.0585 [301.6833,318.2659] |
| run-1 | 32 | Final validation + replay | 636.4885 [534.3850,636.7955] | 639.0036 [625.3052,677.6159] |
| run-1 | 64 | Contract/table validation | 0.0083 [0.0080,0.0117] | 0.0702 [0.0637,0.0887] |
| run-1 | 64 | Expected-row lookup | 0.4879 [0.4686,0.5591] | 0.0516 [0.0422,0.0773] |
| run-1 | 64 | Preview | 637.8698 [629.0065,659.1826] | 634.1604 [630.3084,658.8875] |
| run-1 | 64 | Commit revalidation | 647.8555 [637.0688,660.1726] | 635.2976 [628.9494,648.3566] |
| run-1 | 64 | MIR observation loop | 624.0660 [606.1804,633.4498] | 620.8845 [604.8524,625.9695] |
| run-1 | 64 | Final validation + replay | 1257.2621 [1242.0238,1275.2277] | 1255.2868 [1244.3544,1280.1808] |
| run-2 | 16 | Contract/table validation | 0.0083 [0.0077,0.0112] | 0.0207 [0.0204,0.0266] |
| run-2 | 16 | Expected-row lookup | 0.1332 [0.1217,0.1501] | 0.0171 [0.0133,0.0569] |
| run-2 | 16 | Preview | 170.8183 [170.2263,175.9605] | 175.8292 [169.4393,182.6078] |
| run-2 | 16 | Commit revalidation | 174.9602 [169.3292,178.0474] | 171.0053 [163.9613,174.1868] |
| run-2 | 16 | MIR observation loop | 157.1394 [153.1578,158.7478] | 158.8192 [156.2646,186.4578] |
| run-2 | 16 | Final validation + replay | 332.7442 [321.5696,334.8059] | 331.4309 [322.3032,335.8536] |
| run-2 | 32 | Contract/table validation | 0.0109 [0.0088,0.0112] | 0.0373 [0.0344,0.0487] |
| run-2 | 32 | Expected-row lookup | 0.2456 [0.2381,0.2698] | 0.0255 [0.0236,0.0320] |
| run-2 | 32 | Preview | 329.1565 [322.8166,340.0947] | 327.6590 [326.8209,348.8523] |
| run-2 | 32 | Commit revalidation | 329.0573 [327.7064,332.2905] | 329.2552 [325.6875,335.0636] |
| run-2 | 32 | MIR observation loop | 314.5158 [311.4471,318.1191] | 313.1418 [307.7224,318.0897] |
| run-2 | 32 | Final validation + replay | 641.4215 [633.8330,646.8194] | 638.7615 [633.1011,646.2902] |
| run-2 | 64 | Contract/table validation | 0.0111 [0.0081,0.0111] | 0.0695 [0.0632,0.0805] |
| run-2 | 64 | Expected-row lookup | 0.5082 [0.4700,0.5547] | 0.0501 [0.0440,0.0841] |
| run-2 | 64 | Preview | 651.4629 [633.4596,663.8415] | 645.4052 [637.8800,652.2233] |
| run-2 | 64 | Commit revalidation | 638.2678 [569.6602,657.0716] | 645.7394 [641.2522,656.3346] |
| run-2 | 64 | MIR observation loop | 627.6026 [624.3663,636.5325] | 633.1553 [623.1148,638.9041] |
| run-2 | 64 | Final validation + replay | 1272.3132 [1255.7346,1280.8145] | 1276.1352 [1255.6885,1319.2498] |
