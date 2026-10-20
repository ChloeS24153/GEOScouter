# Provenance — KIDS25 Team 17 hackathon codebase

This tree is an archived copy of the **St. Jude Biohackathon 2025** team repository:

- **Original URL:** https://github.com/stjude-biohackathon/KIDS25-Team17
- **Import location:** `archive/KIDS25-Team17/` in [Mmaycon/GEOscouter](https://github.com/Mmaycon/GEOscouter)
- **Import method:** `git subtree add` (full file tree; hackathon git history is linked via the subtree merge commit on `main`)

## Canonical software today

The maintained GEOscouter application and library are at the **repository root**:

- Python package: `geoscouter/`
- Streamlit UI: `streamlit_app.py`
- Tests: `tests/`

This archive is for **historical reference and authorship traceability**, not for day-to-day installs.

## Human contributors (hackathon repository)

Based on the original GitHub repository and commit history:

| Contributor | Notes |
|-------------|--------|
| Maycon Marção ([@Mmaycon](https://github.com/Mmaycon)) | Primary development |
| Yutian Liu ([@Margery0011](https://github.com/Margery0011)) | README and project diagram updates |
| Renato Umeton ([@renato-umeton](https://github.com/renato-umeton)) | Documentation (e.g. CLAUDE.md via PR) |
| Jared Andrews ([@j-andrews7](https://github.com/j-andrews7)) | Commits on team repo |
| Luke Zhang ([@lukezhang-811](https://github.com/lukezhang-811)) | Commits on team repo |
| Felipe | Streamlit app work (see commit `fcbb0da` message on hackathon history) |

Co-authorship on future papers should be agreed explicitly with each person; this file documents **code provenance**, not a final author list.

## Development tools

**Cursor** and other AI assistants may have been used for editing in the successor repo. They are **not** co-authors, copyright holders, or listed contributors unless a human explicitly adopts that policy.

## Viewing pre-import commits

After subtree import, hackathon commits are reachable through the merge commit’s second parent (example on current `main`):

```bash
MERGE=$(git log --grep='git-subtree-dir: archive/KIDS25-Team17' -1 --format=%H)
git log "${MERGE}^2" --format='%h %an <%ae> %s'
```
