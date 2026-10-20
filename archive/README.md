# Archived repositories

## KIDS25-Team17 (St. Jude biohackathon)

The directory [`KIDS25-Team17/`](KIDS25-Team17/) is a full mirror of the hackathon codebase:

**https://github.com/stjude-biohackathon/KIDS25-Team17**

Canonical ongoing development lives in this repository (`Mmaycon/GEOscouter`) at the repo root (`geoscouter/`, `streamlit_app.py`).

See [`KIDS25-Team17/PROVENANCE.md`](KIDS25-Team17/PROVENANCE.md) for contributor attribution and import notes.

To inspect original commit authors after the subtree import:

```bash
MERGE=$(git log --grep='git-subtree-dir: archive/KIDS25-Team17' -1 --format=%H)
git log "${MERGE}^2" --oneline
```
