# Step 0 — `gds_result.txt` input

GEOscouter starts from a plain-text export of a [GEO DataSets](https://www.ncbi.nlm.nih.gov/gds/) search — not from the Entrez API directly.

**Source:** [geoscouter/core/gds_parse.py](../../geoscouter/core/gds_parse.py)

---

## When to use

- You have run a keyword or fielded search on GEO DataSets (e.g. `lung cancer AND Xenium`).
- You want to curate the resulting series list in GEOscouter (filter, compare supplementary files, visualize).

---

## How to obtain the file

1. Open [GEO DataSets](https://www.ncbi.nlm.nih.gov/gds/) and run your search.
2. Use the **Send to** menu → **File** → format **Text** (`.txt`).
3. Save as `gds_result.txt`.
4. Upload in the app (step 1) or place a copy at `WORK_DIR/gds_result.txt` for local testing.

Example in the repo: [data/input/gds_result.txt](../../data/input/gds_result.txt).

---

## File structure (expectations)

The parser splits the file on numbered entries:

```
1. Series title here [assay tag]
(Submitter supplied) Summary text...
Organism:	Mus musculus
Type:		Expression profiling by high throughput sequencing
Platform: GPL24247 4 Samples
Series		Accession: GSE237782	ID: 200237782

2. Next series ...
```

| Pattern | Used for |
|---------|----------|
| `^\d+\.\s` | Entry boundaries |
| `Series Accession: GSE\d+` | GSE ID extraction |
| `Type:` | `Study_type` per series |
| `Organism:` | Organism (metadata dict; not always written to scrape CSV) |
| Title `[tag]` or `(tag)` | `Assay_hint` when Type is generic (e.g. `Other`) |
| `This SuperSeries is composed` / `Platforms:` (plural) | SuperSeries parent — **excluded** from scrape list |

---

## What `gds_parse` produces

### `parse_gds_result(text)`

Returns:

- **`scrape_gses`** — subseries and standalone GSEs to scrape (SuperSeries parents dropped).
- **`excluded_superseries`** — parent accessions that were filtered out.

The UI shows an info message when SuperSeries parents are excluded.

### `parse_gds_series_metadata(text)`

Per-GSE dict with:

- `study_type` — from `Type:` line
- `organism` — from `Organism:` line
- `assay_hint` — bracket/paren tag from title

These feed `Study_type`, `Assay_hint`, and `Platform_labels` after scraping ([platforms.py](../../geoscouter/core/platforms.py)).

### `build_gds_processed_df(...)`

Clusters GSE numeric IDs by proximity (`proximity_window=10` by default) → `gds_processed.csv` with `GSE` and `Cluster` columns.

---

## SuperSeries handling

If a block is identified as a SuperSeries parent, it is **not** scraped. Subseries listed in the same export are scraped individually. This avoids duplicate rows and focuses on concrete downloadable series.

---

## Related

- [02_web_scraping.md](02_web_scraping.md) — what happens after upload
- [reference/geodatasets_api_vs_geoscouter.md](../reference/geodatasets_api_vs_geoscouter.md) — DataSets export vs programmatic API
