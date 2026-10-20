# Series Matrix files — design note

GEO **Series Matrix** files (`GSE*_series_matrix.txt.gz`) bundle SOFT-style metadata headers with an optional expression table. This doc explains why GEOscouter does **not** use them as the primary scrape source.

---

## What a Series Matrix file contains

Three regions (example: `GSE285341`):

### 1. Series block (`!Series_*`)

Same family of fields as SOFT full-view:

- `!Series_title`, `!Series_summary`, `!Series_overall_design`
- Contact and institute fields
- `!Series_platform_id`, `!Series_sample_id`
- Often **one** series supplementary line, e.g. `GSE285341_RAW.tar`

### 2. Sample block (`!Sample_*`)

Repeated per GSM column:

- Sample title, organism, characteristics, protocols
- Multiple `!Sample_supplementary_file` lines per sample with **full per-sample filenames**

For spatial/Xenium studies this can list dozens of files per sample (`experiment.xenium.txt.gz`, `matrix.mtx.gz`, `transcripts.zarr.zip`, morphology images, etc.).

### 3. Expression table (`!series_matrix_table_begin` … `!series_matrix_table_end`)

Gene/feature matrix. Size varies:

- **Empty or trivial** for some spatial submissions (`!Sample_data_row_count "0"`)
- **Very large** for classic bulk RNA-seq or microarray series (tens to hundreds of MB)

---

## Comparison with GEOscouter's pipeline

| Aspect | Series Matrix header | GEOscouter (SOFT + XML + tar) |
|--------|----------------------|-------------------------------|
| Series metadata | Yes (`!Series_*`) | Yes (SOFT full-view) |
| Series supp files | Often only `*_RAW.tar` | Same from SOFT |
| Per-sample supp filenames | Yes (`!Sample_supplementary_file`) | Via XML custom list + tar expansion |
| Download size | Full file (header + matrix body) | Small HTTP responses only |
| Availability | Not all GSEs have a matrix | All public series accessions |

### Informative example (GSE285341)

- Series SOFT lists: `GSE285341_RAW.tar`
- Matrix header lists: per-GSM Xenium files (`*_experiment.xenium.txt.gz`, `*_matrix.mtx.gz`, …)

So for **some spatial datasets**, matrix headers are **richer at listing filenames** than series-level SOFT alone.

GEOscouter recovers similar filename sets without downloading matrix bodies:

1. Custom XML when SOFT shows `*_RAW.tar`
2. Remote tar member listing ([tar_expand.py](../../geoscouter/core/tar_expand.py))

---

## Why matrix files are not the default

1. **Bandwidth** — You must download (and usually decompress) the entire matrix file to read headers. For bulk RNA-seq this dwarfs the metadata size.
2. **Coverage** — Many modern submissions (scRNA-seq, spatial, proteomics) have no Series Matrix; supplementary files live only under `suppl/`.
3. **Redundancy** — Header fields duplicate SOFT full-view for series metadata; the app's goal is supplementary **filename comparison**, which SOFT+XML+tar already targets.
4. **Parsing cost** — Sample-level supplementary lines require aggregating across GSM columns into series-level rows for Jaccard similarity (GEOscouter's model is one table keyed by `Series`).

### When matrix headers would help

- Small or empty matrix bodies (some spatial series)
- You need sample-level supplementary URLs without tar/XML expansion
- You are building a **hybrid** tool that streams only until `!series_matrix_table_begin`

That hybrid is **not** implemented in GEOscouter today.

---

## Conclusion

Series Matrix files are a useful **reference** for what GEO stores (especially per-sample supplementary URLs on spatial studies), but they are **not a general replacement** for the current scrape pipeline:

- Usually **less efficient** (large downloads)
- **Not universally available**
- **Partially redundant** with SOFT full-view + XML + tar expansion already in [pipeline.py](../../geoscouter/core/pipeline.py)

---

## Related

- [pipeline/02_web_scraping.md](../pipeline/02_web_scraping.md) — current scrape flow
- [visualization/README.md](../visualization/README.md) — how filenames are used in networks
