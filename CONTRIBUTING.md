# Contributing to GEOscouter

Thank you for helping improve GEOscouter. This document covers the essentials; full project docs are in [README.md](README.md) and [doc/README.md](doc/README.md).

## Branch workflow (fork → feature branch → PR)

Contributors work from a **fork**. You do **not** need push access to `Mmaycon/GEOscouter`. The maintainer **reviews and merges**; do not push directly to the upstream repo.

| Repository | Role |
|------------|------|
| **`Mmaycon/GEOscouter`** (upstream) | Canonical project. Target branch for PRs: **`dev`**. **`main`** is release-only. |
| **Your fork** (`YOUR_USER/GEOscouter`) | Where you push feature branches. |

**Rules**

- Open pull requests **into `dev`** on `Mmaycon/GEOscouter` — **not** into `main`.
- One topic per PR (one feature, fix, or doc).
- Delete your feature branch on the fork after merge (optional but tidy).

### dev and main: integration vs release

GEOscouter uses two upstream branches on purpose:

- **`dev`** — integration branch. All community pull requests merge here. When your PR is merged, your work is part of the project.
- **`main`** — release branch. Maintainers merge **`dev` → `main`** when cutting a release. **`main`** is the stable line and GitHub’s **default branch** for this repository.

**GitHub Contributors / Insights graph** (the contributor list on the repo homepage) counts commits on the **default branch** (`main`), not on `dev` alone. So graph credit for this repo usually appears **after** your commits are included in a **`dev` → `main`** release merge—not the moment your PR lands on `dev`.

Before your first commit, set `git config user.email` to an email **verified on your GitHub account** (or your GitHub noreply address). Commits made with unlinked local emails are not attributed to your `@user` on GitHub.

After your commits reach **`main`**, the **Contributors graph** may take **some time** to refresh (often minutes to hours; longer after large history changes). Individual commit pages may show the correct author before Insights updates.

```mermaid
flowchart LR
  fork[Fork_and_feature_branch]
  prDev[PR_merged_to_dev]
  release[Maintainer_merges_dev_to_main]
  graph[GitHub_Contributors_graph_updates]
  fork --> prDev --> release --> graph
```

### First-time setup

1. On GitHub: **Fork** [Mmaycon/GEOscouter](https://github.com/Mmaycon/GEOscouter) to your account.
2. Clone **your fork** (replace `YOUR_USER`):

```bash
git clone https://github.com/YOUR_USER/GEOscouter.git
cd GEOscouter
git remote add upstream https://github.com/Mmaycon/GEOscouter.git
git fetch upstream
git checkout -b dev upstream/dev   # track upstream dev locally
```

3. See [dev and main: integration vs release](#dev-and-main-integration-vs-release) for git author email and how GitHub contributor credit works.

### Every contribution

```bash
git checkout dev
git pull upstream dev              # sync with Mmaycon/GEOscouter dev
git checkout -b feature/short-name # new branch from dev
# … edit, commit …
git push -u origin feature/short-name   # origin = your fork
```

3. On GitHub: **New pull request**
   - **base repository:** `Mmaycon/GEOscouter`, **base:** `dev`
   - **head repository:** `YOUR_USER/GEOscouter`, **compare:** `feature/short-name`
4. Fill in the PR template, link an issue if you have one (e.g. `Fixes #3`), and wait for CI **tests** + maintainer review.

If GitHub shows “compare across forks,” choose your fork as the head and **`dev`** as the base.

### Syncing when `dev` moves ahead

```bash
git checkout dev
git pull upstream dev
git checkout feature/short-name
git merge dev   # or: git rebase dev
git push origin feature/short-name
```

Use the **Update branch** button on the PR if GitHub offers it.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Example input: [data/input/gds_result.txt](data/input/gds_result.txt).

## Before you open a PR

Run the test suite (same checks as CI):

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

If you change behavior in `geoscouter/core/` or library code under `geoscouter/`, **add or update tests** in `tests/` when reasonable.

## Continuous integration

On every pull request to **`dev`**, GitHub Actions runs the **`tests`** workflow on Ubuntu: install dependencies, run the command above, then verify `import geoscouter` and `import streamlit_app`. See the [Actions tab](https://github.com/Mmaycon/GEOscouter/actions) for logs.

## After you open a PR

1. Wait for the **tests** check to finish (green is good).
2. A maintainer reviews the diff.
3. If merged, your changes land on **`dev`**. They reach **`main`** and the public Contributors graph when a maintainer merges **`dev` → `main`** (see [dev and main: integration vs release](#dev-and-main-integration-vs-release)).

Small fixes do not need a linked issue; larger work benefits from discussing first.

## Issues and ideas

Use the [issue chooser](https://github.com/Mmaycon/GEOscouter/issues/new/choose) (template **Ideas, bugs, or help**) or open a **blank issue**. Prefix the title with `[Step N]` if you know which part of the app — optional. A short paragraph is enough.

## Where to change code

| App step | Main modules |
|----------|----------------|
| 1 — Run data scraping | `geoscouter/core/pipeline.py`, `gds_parse.py`, `tar_expand.py` |
| 2 — Filter datasets | `geoscouter/core/filters.py`, `platforms.py` |
| 3 — Visualize datasets | `geoscouter/viz/`, `geoscouter/core/similarity.py` |
| 4 — Select GSEs | `streamlit_app.py`, `similarity.py` |
| 5 — Metadata & curation | `geoscouter/core/metadata.py`, `curation.py`, `filters.py` |

UI wiring lives in [streamlit_app.py](streamlit_app.py); prefer putting reusable logic in the `geoscouter` package.

## Proposing changes

- For **non-trivial** work, an issue first helps — but informal notes are welcome.
- Link an issue in your PR when you have one.
- Avoid unrelated refactors or large formatting-only diffs.

## Conduct and transparency

- Be respectful in issues and reviews.
- If AI tools generated a **substantial** part of your PR, say so in the PR description so maintainers can review carefully.

## Questions

Open an issue or tag [@Mmaycon](https://github.com/Mmaycon) on GitHub.
