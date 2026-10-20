# GEO DataSets vs GEOscouter

GEOscouter **consumes** a GEO DataSets text export. It does not replace NCBI search APIs or the GEO website for discovery.

---

## Roles

| Aspect | GEO DataSets (NCBI) | GEOscouter |
|--------|---------------------|------------|
| **Purpose** | Search and index public GEO records | Curate a search export; compare **supplementary file layouts**; filter and visualize |
| **Primary input** | Web UI queries or Entrez/eUtils programmatic search | Uploaded `gds_result.txt` |
| **Primary output** | Accession lists, record metadata in NCBI formats | `geo_webscrap.csv`, filtered tables, similarity networks, Excel exports |
| **Supplementary files** | Listed per record; no bulk cross-series comparison | **Core feature**: Jaccard / supervised filename matching across many GSEs |
| **Sample-level metadata** | Per-record pages, SOFT, or matrix downloads | Optional GSM tables via GEOparse in-app (step 2) |
| **Expression data** | Series Matrix, processed matrices, RAW archives | Not loaded — filenames and series metadata only |

---

## Typical workflow

```mermaid
flowchart LR
  search["GEO DataSets search"]
  export["Export gds_result.txt"]
  geoScouter["GEOscouter pipeline"]
  curated["Filtered GSE list + similarity views"]

  search --> export --> geoScouter --> curated
```

1. **Discovery** — use [GEO DataSets](https://www.ncbi.nlm.nih.gov/gds/) (or Entrez `gds` database via [eUtils](https://www.ncbi.nlm.nih.gov/home/develop/api/)) to find candidate series.
2. **Export** — save results as `gds_result.txt` (see [pipeline/01_gds_input.md](../pipeline/01_gds_input.md)).
3. **Curation** — GEOscouter scrapes supplementary file names, filters by platform/assay/samples, and builds comparison networks.

GEOscouter is **downstream** of DataSets search, not a substitute for it.

---

## APIs and what GEOscouter uses

### GEO DataSets / Entrez (not called directly by GEOscouter)

- **eSearch / eSummary / eFetch** on `db=gds` — programmatic search and retrieval of DataSets records.
- Useful for: building accession lists, scheduled searches, integrating with pipelines before GEOscouter.
- Requires: API key recommended for high volume; Entrez usage policies apply.

GEOscouter does **not** query `gds` at runtime. It only parses the text file you export from the website.

### GEO accession endpoints (used by GEOscouter scrape)

| Endpoint | Role in GEOscouter |
|----------|-------------------|
| `acc.cgi?...&targ=self&form=text&view=full` | Series SOFT metadata + supplementary URLs |
| `geo/download/?format=xml&acc=GSE...` | Per-file list when SOFT shows `*_RAW.tar` |
| `geo/download/?acc=...&format=file&file=...` | Tar streaming for member expansion |
| HTML / Selenium | Fallback only when not blocked |

Optional GSM fetch uses **GEOparse** (`get_GEO`), which downloads SOFT family files per series.

---

## When to use which tool

| Goal | Use |
|------|-----|
| Find studies by keyword, organism, platform | GEO DataSets UI or Entrez `gds` API |
| Compare supplementary **file naming patterns** across many GSEs from one search | GEOscouter |
| Filter by GPL, sample count, assay type from a DataSets export | GEOscouter |
| Download expression matrices for analysis | GEO Series Matrix, supplementary files, or SRA — not GEOscouter |
| Programmatic metadata for one GSE | eUtils, GEOparse, or SOFT/MINiML |
| Reproducible curation notebook with networks and Excel handoff | GEOscouter after DataSets export |

---

## Limitations

- **GEOscouter** depends on NCBI availability and scrape endpoints (see [pipeline/02_web_scraping.md](../pipeline/02_web_scraping.md) troubleshooting).
- **DataSets export** reflects your search at export time; it is not a live API subscription.
- **Neither** replaces reading the original paper or GEO submission for experimental design details.

---

## Related

- [pipeline/01_gds_input.md](../pipeline/01_gds_input.md) — `gds_result.txt` format
- [reference/series_matrix_files.md](series_matrix_files.md) — Series Matrix as an alternative metadata source
- [doc/README.md](../README.md) — full app pipeline
