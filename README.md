# GEOscouter

GEOscouter helps you profile and compare public datasets on [GEO](https://www.ncbi.nlm.nih.gov/geo/) from an exported `gds_result.txt` search.

## Use the deployed app

**[Open GEOscouter on Streamlit Cloud →](https://geoscouter.streamlit.app/)**

No local setup required — upload your GEO `gds_result.txt` and run the pipeline in the browser.

## Full documentation

See [doc/README.md](doc/README.md) for the pipeline guide, filtering, visualization, and design notes (Series Matrix files, GEO DataSets vs GEOscouter).

Hackathon provenance (KIDS25 Team 17): [archive/KIDS25-Team17/PROVENANCE.md](archive/KIDS25-Team17/PROVENANCE.md).

## Sync with GitHub

Before editing or running the app, check that your local folder matches GitHub. Add this alias to `~/.zshrc` (once):

```bash
alias geoscoutersync='cd /Users/mmarcao/Documents/GEOscouter_v3 && git fetch origin && git status -sb'
```

Reload your shell (`source ~/.zshrc`), then whenever you return to the project run:

```bash
geoscoutersync
```

Example output:

```text
## dev...origin/dev              # in sync — safe to work
## dev...origin/dev [behind 2]   # run git pull before editing
## dev...origin/dev [ahead 1]    # run git push when ready
```

Work on branch **`dev`** (see [Push to GitHub](#push-to-github)).

## Run locally

### First-time setup

```bash
cd path/to/GEOscouter_v3
git checkout dev
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Launch the app

```bash
cd path/to/GEOscouter_v3
source .venv/bin/activate
streamlit run streamlit_app.py
```

Open the URL Streamlit prints (usually **http://localhost:8501**).

If port 8501 is busy or does not load (e.g. Cursor port forwarding), use another port:

```bash
streamlit run streamlit_app.py --server.port 8503 --server.address 127.0.0.1
```

Then open **http://127.0.0.1:8503**.

### Stop the app

Press `Ctrl+C` in the terminal where Streamlit is running.

### Using the app

1. Run a search on [GEO DataSets](https://www.ncbi.nlm.nih.gov/gds/), export **gds_result.txt**
2. Upload the file → **Run pipeline** (scrapes GEO; results are cached)
3. **Filter** by platform, sample count, and optional sample metadata **before** plotting
4. Visualize, build a GSE comparison list, export CSV/Excel

In step 3, define a **supervised file-structure signature** from training GSE(s) or by typing expected file types (e.g. `transcripts.parquet.gz`), then score other series by rule coverage. Step 4 can bulk-add GSEs matching that signature.

Example input: `data/input/gds_result.txt`

After code changes, use **Delete all cached outputs** in the app (or delete cached CSVs) and re-run the pipeline.

**Supplementary `.tar` files:** After the **(custom)** listing step, any remaining filenames ending in `.tar`, `.tar.gz`, or `.tgz` are opened remotely and their inner filenames are written to `geo_webscrap.csv` (the archive name itself is omitted). If expansion fails, the tar filename is kept.

### Optional: Selenium (local only)

Most series work without Chrome. Selenium is only a fallback if the **(custom)** supplementary file list cannot be loaded via HTTP. To enable it locally:

```bash
pip install selenium
# Chrome must be installed
```

## Project layout

```
geoscouter/          # reusable library (pipeline, filters, plots)
streamlit_app.py     # Streamlit UI entry point
data/input/          # example gds_result.txt
legacy/app/          # previous monolithic scripts (reference)
```

## Deploy on Streamlit Community Cloud

The public app is live at **[https://geoscouter.streamlit.app/](https://geoscouter.streamlit.app/)** (deployed from the `dev` branch).

To redeploy or fork your own instance:

1. Push the `dev` branch to GitHub (see below)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. New app → repository `Mmaycon/GEOscouter`, branch **`dev`**
4. Main file path: **`streamlit_app.py`**
5. Deploy

No Chrome/Selenium is required on Streamlit Cloud; supplementary files are fetched via HTTP (including **(custom)** file lists for `*_RAW.tar` archives, and remote tar expansion for any remaining `.tar` entries).

## Push to GitHub

From the project root, on branch `dev`:

```bash
git add README.md geoscouter/ streamlit_app.py requirements.txt pyproject.toml .streamlit/ .gitignore
git status
git commit -m "Improve pipeline: SuperSeries filter, custom RAW.tar file lists, local run docs"
git push origin dev
```

## License

MIT — see [LICENSE](LICENSE).
