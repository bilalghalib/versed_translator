# Public-Domain English Translations — Seed List

> ## ⚠️ VERIFICATION PASS — 2026-08-14 (READ THIS BEFORE USING THE TABLE BELOW)
>
> The table further down was compiled by **WebSearch only**; its URLs were never fetched. A verification pass has now fetched all 16. **Several entries pointed at the wrong edition, and two are not public domain at all.** The table below is preserved as the original compilation record — **this block is authoritative where they disagree.**
>
> ### DROP — rights failures (do NOT use)
>
> - **#13 Mishkat al-Masabih.** The archive.org text is **not** Matthews' bare 1809 translation. Its title page reads *"TRANSLATED BY Capt. A. N. MATTHEWS / REVISED AND EDITED, WITH NOTES, BY F. K. KHAN DURRANI"*, publisher Tabligh Literature Company Lahore, stamped **"(All Rights Reserved)"**. Durrani (d. 1962) wove modernist editorial introductions into the body. It is also a part-issue fragment. **Not PD, not complete, not the claimed edition.**
> - **#14 Rehatsek, *Sirat Rasul Allah*.** Guillaume confusion is *cleared* (zero hits for Guillaume/Oxford/Wüstenfeld) — but the text is the **1964 Folio Society edition: Michael Edwardes' abridgement of Rehatsek**, and says so in its own preface. Edwardes' linking passages and bracketed glosses are woven into the running prose and cannot be mechanically stripped; first published 1964 in the UK, so URAA risk applies. **There is no public-domain English translation of the Sira at all** — Rehatsek's was the first ever and was not printed until 1964. The only PD Western-language option is Weil's German (1864).
> - **#12 Lane, *Arabian Society*** — PD is fine, but **confirmed not a translation of a work** (essays *about* the Nights). Drop as an alignment pair; keep only for genre colour.
>
> ### CORRECTED URLs — the doc's link is the wrong edition
>
> | # | Problem with the doc's URL | Use instead |
> |---|---|---|
> | 1 Baladhuri | 1968 AMS reprint, `access-restricted-item: true`, djvu.txt returns **HTTP 401** | v1 `originsofislamic01albauoft_djvu.txt` (974K) + v2 `originsoftheisla032520mbp_djvu.txt` (524K). ⚠️ `originsofislamic02albauoft` is **mislabeled** — a second copy of vol 1, not Murgotten |
> | 7 Hariri | **vol II only** ("CONTAINING THE LAST TWENTY-FOUR") | `the-assembly-of-al-hariri-all-50` → `The Assembly of Al Hariri All 50_djvu.txt` (654K) — all 50, headers FIRST→FIFTIETH verified, and **notes-free** (no philological apparatus to strip) |
> | 8 Ibn Tufayl | the **1929 Fulton-revised Stokes edition** — precisely what the doc's own note says to avoid | **Gutenberg** `https://www.gutenberg.org/cache/epub/16831/pg16831.txt` (279K) — the 1708 Ockley, human-proofread, **zero OCR noise** |
> | 15 Palmer Qur'an | **Part I only** (suras 1–16). The doc's secondary UMich URL is **SBE vol 14, *Sacred Laws of the Aryas*** — a different book entirely | `qurn01palm_djvu.txt` (784K) + `qurn02palm_djvu.txt` (677K) |
> | 16 Blunt | no archive.org item exists for the 1903 edition | `poeticalworksofw02blunuoft_djvu.txt`, odes at byte offsets **87,303–171,163**. MARC confirms Lady Anne translated, W.S. Blunt versified. ⚠️ `moallakat0000unse` is **Jones's 1782**, not Blunt |
> | 2 Ibn Khallikan | doc's Google scan is noisy but usable | Prefer GWU HighRes `HighRes_3288201929395{3,6,7}9_djvu.txt` (1.8–1.9M each) — markedly cleaner. Avoid the 1961/1970 reprints (`biographicaldict0001macg`, `ibnkhallikansbio0001ibnk`) — restricted |
> | 10 Lyall | scan is the **1930 reprint, not 1885**, carrying a new 1930 publishers' foreword | Usable only with that foreword excluded; OCR is poor regardless (`Chiistian monastoiy`) |
>
> ### RANKED for benchmark passage alignment (D1e option d)
>
> 1. **al-Hariri, *Assemblies* (all 50)** — adab/maqama. Complete, 50 discrete self-contained units, notes-free stream. Fills the highest-value empty genre. **Best overall.**
> 2. **Ibn Khallikan, *Biographical Dictionary*** — biography. Per-entry structure is the gold standard for 1:1/1:N validation; complete 4 vols; cleanest long-form text in the list (~7.8M chars).
> 3. **Ockley, *Hayy ibn Yaqzan*** — philosophy. Only human-proofread, zero-OCR-noise text found. Small (279K) but flawless — ideal **clean control set**.
> 4. **Baladhuri, *Origins of the Islamic State*** — history. Complete across the two replacement URLs; chapter-structured; needs footnote/running-header stripping.
> 5. **Blunt, *Seven Golden Odes*** — poetry. All seven odes, good OCR, structurally faithful line-for-line to the Arabic bayt.
> 6. **Knatchbull, *Kalila and Dimna*** — adab/fables. Complete, direct from Arabic, good OCR, headed fable units.
> 7. **Palmer, *Qur'an*** — scripture. Not a missing genre, but sura/verse headers are the strongest structural anchors in the list.
> 8. **Hamilton, *Antar*** — poetry/epic. All 4 vols (better than the doc claims) but continuous narrative + quote-mark OCR damage.
>
> **Deprioritize:** Lyall (poor OCR), Lee's Ibn Battuta (pages dominated by Persian/Arabic footnote garbage), Mas'udi (vol 1 only, inline Arabic mangled to noise), Ghazali (short condensation, indirect chain), Keith-Falconer (Syriac recension, not direct Arabic).
>
> ### ⚠️ GAP THIS LIST CANNOT CLOSE
>
> **Zero tafsir sources.** None of the 16 addresses tafsir, so D1e option (d) **cannot** close the tafsir hole from this list alone. Tafsir needs a separate sourcing decision.

Companion to `corpus/pd_translations_seed.json`. Compiled 2026-08-12 for **C6 checkpoint 1** (rights inventory seed) and **C7 gold-work candidates** (alignment engine validation set) per `VERSED_TRANSLATION_ROADMAP.md`.

**Method:** WebSearch only (no WebFetch verification pass in this session — every `source_url` below is a URL that actually appeared in search results, never constructed from memory). No rights claim here is a legal opinion; **D6b** (EU/French IP counsel) still gates commercial use, and every "PD" rationale is a plausibility argument (translator death year and/or pre-1930 publication year), not a cleared determination. Entries the compiler was unsure about are marked `confidence: low` rather than asserted as safe — see the table.

16 entries, spanning **9 genres**: history (2), biography (1), adab/fables (3), adab/maqama (1), philosophy (2), travel (1), poetry (3), hadith (1), sira (1), scripture (1). *(Some entries carry a compound genre tag — counts above reflect primary genre.)*

---

## Table

| # | Work | Author | Translator (d.) | Pub. year | Genre | OpenITI URI (guess) | Confidence | Source seen |
|---|------|--------|------------------|-----------|-------|----------------------|------------|-------------|
| 1 | Futuh al-Buldan → *Origins of the Islamic State* | al-Baladhuri (d.892) | Hitti / Murgotten | 1916 / 1924 | history | `0279Baladhuri.FutuhBuldan` | **high** | [archive.org](https://archive.org/details/originsofislami00bala) |
| 2 | Wafayat al-A'yan → *Ibn Khallikan's Biographical Dictionary* | Ibn Khallikan (d.1282) | de Slane (d.1878) | 1842–1871 | biography | `0681IbnKhallikan.WafayatAcyan` | **high** | [archive.org](https://archive.org/details/ibnkhallikansbi00slangoog) |
| 3 | Muruj al-Dhahab → *Meadows of Gold* (vol.1 only) | al-Mas'udi (d.956) | Sprenger (d.1893) | 1841 | history | `0346Mascudi.MurujDhahab` | medium | [archive.org](https://archive.org/details/elmasdshistoric00unkngoog) |
| 4 | Kalila wa-Dimna → *Kalila and Dimna, or The Fables of Bidpai* | Ibn al-Muqaffa' (d.~757) | Knatchbull | 1819 | adab/fables | `0139IbnMuqaffac.KalilaWaDimna` | **high** | [archive.org](https://archive.org/details/kalilaanddimnao00almgoog) |
| 5 | Kalila wa-Dimna (Syriac branch) → *Kalilah and Dimnah* | Ibn al-Muqaffa' (indirect) | Keith-Falconer (d.1887) | 1885 | adab/fables | `0139IbnMuqaffac.KalilaWaDimna` | medium | [archive.org](https://archive.org/details/kalila-dimna) |
| 6 | Rihla → *The Travels of Ibn Batuta* (abridged) | Ibn Battuta (d.1368/9) | Samuel Lee (d.1852) | 1829 | travel | `0779IbnBattuta.Rihla` | **high** | [archive.org](https://archive.org/details/b28406084) |
| 7 | Maqamat al-Hariri → *The Assemblies of Al-Hariri* | al-Hariri (d.1122) | Chenery (d.1884) / Steingass (d.1903) | 1867 / 1898 | adab/maqama | `0516IbnCaliHariri.Maqamat` | **high** | [archive.org](https://archive.org/stream/assembliesofalha015555mbp/assembliesofalha015555mbp_djvu.txt) |
| 8 | Hayy ibn Yaqzan → *The History of Hayy Ibn Yaqzan* | Ibn Tufayl (d.1185) | Simon Ockley (d.1720) | 1708 | philosophy | `0581IbnTufayl.HayyIbnYaqzan` | **high** | [archive.org](https://archive.org/details/historyofhayyibn00ibnu) |
| 9 | Kimiya-yi Sa'adat → *The Alchemy of Happiness* | al-Ghazali (d.1111) | Claud Field (d.1941) | 1910 | philosophy | `0505Ghazali.KimiyaSacada` | medium | [archive.org](https://archive.org/details/alchemyofhappine00algh) |
| 10 | (anthology) → *Translations of Ancient Arabian Poetry* | various | Lyall (d.1920) | 1885 | poetry | *(none — anthology)* | **high** | [archive.org](https://archive.org/details/in.ernet.dli.2015.50391) |
| 11 | Sirat 'Antar (part) → *Antar, a Bedoueen Romance* | anonymous | Terrick Hamilton | 1819–1820 | poetry/epic | `0800Anonymous.SiratCantara` | medium | [archive.org](https://archive.org/details/antar-romance-hamilton) |
| 12 | (Lane's notes on) Alf Layla wa-Layla → *Arabian Society in the Middle Ages* | E.W. Lane (d.1876) | Lane (posthumous) | 1883 | adab/social hist. | `0700Anonymous.AlfLaylaWaLayla` | low | [archive.org](https://archive.org/details/arabiansocietyin00laneuoft) |
| 13 | Mishkat al-Masabih → *Mishkat-ul-Masabih* | al-Khatib al-Tabrizi (compiler) | Capt. A.N. Matthews | 1809–1810 | hadith | `0741KhatibTabrizi.MishkatMasabih` | medium | [archive.org](https://archive.org/stream/MishkatAlMasabihhadith/mishkat+al-masabih+(hadith)_djvu.txt) |
| 14 | Sirat Rasul Allah → *The Life of Muhammad* | Ibn Ishaq/Ibn Hisham | Edward Rehatsek (d.1891) | unclear (pre-1891 / 1898) | sira | `0151IbnIshaq.Sira` | low | [archive.org](https://archive.org/stream/Sirat-lifeOfMuhammadBy-ibnIshaq/SiratIbnIahaqInEnglish_djvu.txt) |
| 15 | al-Qur'an → *The Qur'an* (Sacred Books of the East) | — | E.H. Palmer (d.1882) | 1880 | scripture | `0001Quran.Mushaf` | **high** | [archive.org](https://archive.org/details/qurn00unkngoog) |
| 16 | al-Mu'allaqat → *The Seven Golden Odes of Pagan Arabia* | 7 pre-Islamic poets | W.S. Blunt (d.1922) | 1903 | poetry | `0486IbnAhmadZuzani.SharhMucallaqat` (approx.) | low | [HathiTrust catalog](https://catalog.hathitrust.org/Record/001229726) |

---

## The 3 strongest candidates for early alignment work (C7)

Selection criteria: **complete** translation of the whole work, a **clean digital text** (not just a scan), and the underlying Arabic work **present in the OpenITI priority list**.

1. **al-Baladhuri, *Origins of the Islamic State* (Hitti/Murgotten, 1916–1924)** — `0279Baladhuri.FutuhBuldan`. Both volumes together cover the full *Futuh al-Buldan*; Hitti's is a careful, literal scholarly translation with a full OCR text stream on archive.org, making segment-to-segment alignment tractable. High confidence on PD status.
2. **Ibn Khallikan, *Biographical Dictionary* (de Slane, 1842–1871)** — `0681IbnKhallikan.WafayatAcyan`. The four-volume translation is complete, entry-structured (each biography is a natural alignment unit — a gift for 1:1/1:N link validation), and independently multiply-digitized (Google Books scans + at least two archive.org copies), which helps cross-check OCR quality.
3. **al-Hariri, *Assemblies* (Chenery 1867 + Steingass 1898)** — `0516IbnCaliHariri.Maqamat`. The two volumes jointly translate all 50 maqamat, giving a complete, stylistically demanding (rhymed prose) test of the alignment engine's handling of adab genre — a useful genre counterweight to the two history candidates above. Full text stream confirmed on archive.org.

*Close 4th, worth keeping in view:* Knatchbull's 1819 **Kalila and Dimna** (`0139IbnMuqaffac.KalilaWaDimna`) — complete, directly from Arabic, high confidence, but the fable-per-fable structure is less battle-tested for alignment than the entry-structured Ibn Khallikan text.

## Entries where a source URL could not be firmly confirmed

- **#16, al-Mu'allaqat / Blunt's *Seven Golden Odes* (1903)** — only a HathiTrust *catalog record* was directly observed in search results; no full-view/OCR text URL for this specific edition was confirmed. Booksellers and a Blunt-biography stream on archive.org referenced it, but none was an exact full-text link for the 1903 Golden Odes edition itself. Needs a follow-up WebFetch/archive.org search pass before use.
- **#14, Rehatsek's *Sirat Rasul Allah*** — a text was found and its URL recorded, but the underlying publication history (translated pre-1891, presented to the Royal Asiatic Society 1898, apparently first printed as an abridgement only in 1964) is murky enough that the digitized text's actual provenance needs verification before treating it as confirmed-PD source material. Do not confuse with A. Guillaume's 1955 translation of the same work, which is **not** public domain and must be excluded.
- **#12, Lane's *Arabian Society in the Middle Ages*** — URL confirmed and clearly PD, but flagged separately: this is Lane's own compiled notes/essays *about* the 1001 Nights, not a direct translation of one work, so it's marked low confidence for use as a C7 alignment pair even though its PD status itself is solid.

## Standing caveats carried from the roadmap

- Nothing here has been checked against **D6c** (hadith-json/Sunnah.com material is index-only, never ships/trains) except to note that #13 (Matthews' 1809 Mishkat) is an independently-sourced 19th-century PD text, not Sunnah.com content — but the specific digitized copy found may be a later re-edited reprint and should be checked before use.
- All "PD" rationales in this list rest on translator-death-year and/or pre-1930-publication-year heuristics per the roadmap's own framing; none of this constitutes cleared legal sign-off, and **D6b** (EU/French counsel) still gates commercial exploitation.
- This list deliberately excludes translations that are clearly *not* PD-eligible even though they are the modern standard editions for their works — e.g. A. Guillaume's 1955 *Sirat Rasul Allah*, H.A.R. Gibb's Hakluyt Society *Ibn Battuta* (1958+), James Robson's *Mishkat al-Masabih*, and Franz Rosenthal's *Muqaddimah* (1958) — flagging these by name so a future pass doesn't accidentally reach for them.
