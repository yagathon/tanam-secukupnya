# G1 benchmark — dev set — gemini-3.5-flash

45 labeled notes (synthetic, Bahasa/Sundanese WhatsApp style), received 2026-10-12.

| Measure | Result |
|---|---|
| Kind correct (signals / harvest issue / none) | 45/45 (100%) |
| Field-level accuracy (all scored fields) | 244/246 (99%) |
| False alarms on noise notes | 0/11 |
| Extra signals not in the label | 0 |
| Errors | 0 |
| Median latency | 7.8 s |
| Avg tokens in / out | 2852 / 106 |

| Field | Correct |
|---|---|
| harvest_issue/cause | 12/12 (100%) |
| harvest_issue/crop | 12/12 (100%) |
| harvest_issue/delay | 12/12 (100%) |
| harvest_issue/farmer | 12/12 (100%) |
| harvest_issue/magnitude | 12/12 (100%) |
| harvest_issue/period | 11/12 (92%) |
| signals/cause | 29/29 (100%) |
| signals/crop | 29/29 (100%) |
| signals/direction | 29/29 (100%) |
| signals/magnitude | 29/29 (100%) |
| signals/period | 28/29 (97%) |
| signals/scope | 29/29 (100%) |

## Misses (2)

- **n19** `Kak, 2 minggu ke depan pakcoy +15% ya, ada event makan siang kantor deket resto` — expected signals, got signals; wrong: s0.period
- **h11** `Ulat grayak nyerang pakcoy, sudah 2 bedeng habis dari 6 yang mau panen` — expected harvest_issue, got harvest_issue; wrong: period
