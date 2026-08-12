# Versed Benchmark v0.1-DRAFT -- assembly stats

Seed: `20260812`

- draft_test: **1111** items (target ~1200)
- dev_bakeoff: **139** items (target 150)

Sources: ATHAR native **test** split only (train rows never eligible); all of LK Hadith. hadith-json excluded entirely (rights_status=INDEX_ONLY_NO_REDISTRIBUTION -- English side never ships).

Attribution finding: ATHAR's parquet files carry only `(arabic, english)` columns -- no per-row work/author/genre metadata exists in the source data (verified against both train and test parquet schemas), so ATHAR rows are grouped under `ATHAR_UNKNOWN_ATTRIBUTION`. LK Hadith carries a real per-row collection field (`work_id`: AbuDaud/Bukhari/IbnMaja/Muslim/Nesai/Tirmizi) which is used as the attribution axis for that source.

## By length band

| band | available | target draft_test | actual draft_test | shortfall | target dev_bakeoff | actual dev_bakeoff | shortfall |
|---|---|---|---|---|---|---|---|
| 30-80 | 23695 | 400 | 400 | 0 | 50 | 50 | 0 |
| 100-250 | 5015 | 400 | 400 | 0 | 50 | 50 | 0 |
| 250-600 | 350 | 400 | 311 | 89 | 50 | 39 | 11 |

## By length band x attribution group

| band | attribution | available | draft_test | dev_bakeoff |
|---|---|---|---|---|
| 30-80 | ATHAR_UNKNOWN_ATTRIBUTION | 237 | 4 | 0 |
| 30-80 | AbuDaud | 3618 | 61 | 8 |
| 30-80 | Bukhari | 5029 | 85 | 11 |
| 30-80 | IbnMaja | 3578 | 60 | 8 |
| 30-80 | Muslim | 4921 | 83 | 10 |
| 30-80 | Nesai | 4412 | 75 | 9 |
| 30-80 | Tirmizi | 1900 | 32 | 4 |
| 100-250 | ATHAR_UNKNOWN_ATTRIBUTION | 1 | 0 | 0 |
| 100-250 | AbuDaud | 714 | 57 | 7 |
| 100-250 | Bukhari | 1124 | 90 | 11 |
| 100-250 | IbnMaja | 367 | 29 | 4 |
| 100-250 | Muslim | 925 | 74 | 9 |
| 100-250 | Nesai | 555 | 44 | 6 |
| 100-250 | Tirmizi | 1329 | 106 | 13 |
| 250-600 | AbuDaud | 44 | 39 | 5 |
| 250-600 | Bukhari | 94 | 84 | 10 |
| 250-600 | IbnMaja | 14 | 12 | 2 |
| 250-600 | Muslim | 95 | 84 | 11 |
| 250-600 | Nesai | 28 | 25 | 3 |
| 250-600 | Tirmizi | 75 | 67 | 8 |

## By source

| source | draft_test | dev_bakeoff |
|---|---|---|
| athar | 4 | 0 |
| lk_hadith | 1107 | 139 |
