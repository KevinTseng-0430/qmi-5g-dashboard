# Architecture

## Goals
1. Keep monitoring read-only.
2. Avoid continuous AT-port ownership.
3. Use QMI NAS/WDS for modem telemetry.
4. Use Linux sysfs for high-frequency throughput.
5. Decouple collection from presentation using a JSON state file.

## Polling cadence

```text
RX/TX counters              1 s
RSRP/RSRQ/SNR               2 s
registration/PLMN/RAT       5 s
IP/gateway/MTU              5 s
APN/profile                30 s
```
