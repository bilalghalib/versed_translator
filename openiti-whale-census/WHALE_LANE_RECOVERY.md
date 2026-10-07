# Whale lane recovery notes

One-time routing lane (Aug 2026). Not a generalized migration system.

## Existing 23 whales (Nautilus coordinator → Descent export)

**What we did:** For each book in `wayway_existing_whales.csv`, pending rows were
flipped to `archived` (not a new `delegated` status). `claim()` only selects
`pending`, so Fish on Nautilus cannot pick these up. Rows were exported to
Descent as `.jsonl.zst` with `status='pending'` for Wayway ingest.

**Receipt:** `whale-lane/manifests/existing_whales_delegation_receipt.jsonl`

**If export must be redone for a book:**

1. Confirm no active leases: `status='leased' AND lease_expires_at > now()`
2. Only re-export if rows are still `archived` with a known `updated_at` from
   the first flip — do not bulk-unarchive without checking completed rows.
3. To restore Nautilus claimability (emergency only): flip `archived` →
   `pending` for that `book_uri` where no local audio exists yet. Never delete
   coordinator rows.

## M2_NEW lane (183 books, never ingested to Nautilus)

Ledgers copy Hikma → Descent under `whale-lane/ledgers/books/`. M2 prepares
spool files under `whale-lane/prepared/`. These books are listed in
`nautilus_ingest_exclusion.txt` — remainder ingest must pass `--exclude` before
resume.

## Do not

- Rerun CATT (diacritics already in ledgers)
- Global `GROUP BY book_uri` on the 52 GB Nautilus coordinator
- Repoint Fish workers until Wayway fork coordinator is verified
- Touch `REVIEW` books (Nuwayri, MasalikAbsar, BadaicSanaic)
