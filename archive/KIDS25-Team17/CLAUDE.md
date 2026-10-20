# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GEOscouter is a Streamlit-based tool for profiling and curating public datasets from the Gene Expression Omnibus (GEO). It helps researchers quickly identify promising datasets, assess file format complexity, and budget for data analysis projects.

## Environment Setup

This project uses conda for package management. Create the environment using:

```bash
conda env create -f app/app_v1/biohack25_clean.yml
conda activate biohack25
```

The environment includes key dependencies:
- Python 3.10.18
- streamlit 1.50.0
- pandas, numpy, scipy for data manipulation
- scanpy, anndata for single-cell analysis
- plotly, matplotlib, seaborn for visualization
- GEOparse for metadata extraction
- selenium, beautifulsoup4 for web scraping

## Running the Application

The main application is a Streamlit app located at `app/app_v1/streamlite_app.py`.

To run the application:

```bash
streamlit run app/app_v1/streamlite_app.py
```

**Required setup before running:**
1. Create a folder containing the input file `gds_result.txt` (list of GEO dataset IDs)
2. When the app starts, provide the path to this folder in the UI
3. The app will cache results in `geo_webscrap.csv` to avoid re-scraping

## Application Architecture

The Streamlit app has a multi-stage workflow organized into 7 main sections:

### 1. Data Scraping Pipeline (`run_geo_pipeline`)
- Parses GEO series IDs (GSE) from `gds_result.txt`
- Groups series into clusters based on ID proximity
- Web scrapes NCBI GEO pages for metadata:
  - Title, summary, design, contact information
  - Platform information (GPL IDs)
  - Sample counts (GSM IDs)
  - Supplementary file details (name, size, type)
- Results cached to `geo_webscrap.csv`

### 2. Visualization Functions
- **Dataset Snapshot** (`dataset_snapshot`): Bar plots of total size, sample counts, and file type diversity per series
- **File Complexity** (`file_per_smp_complexity`): Interactive scatter plot showing relationship between file count and sample count
- **File Similarity Network** (`file_ext_network`): Network graph visualizing series similarity based on supplementary file extensions

### 3. Filtering System
Multi-stage filtering approach:
- **Restrictive parameters**: Filter by platform (GPL) and sample count range
- **Additive selection**: Build a list of GSEs by similarity threshold or manual entry
- **Combined filtering**: Apply all criteria simultaneously

### 4. Metadata Extraction (`get_gse_metadata`)
- Uses GEOparse library to download SOFT files
- Extracts detailed sample-level metadata (GSM)
- Processes characteristics fields into structured columns
- Downloads to `metadata/geo_soft_files/` directory
- Results cached per GSE

### 5-7. Metadata Analysis
- Browse metadata by GSE
- Keyword search across all metadata fields
- Export filtered metadata to Excel with one sheet per GSE

## Key Design Patterns

### Caching Strategy
The app uses two caching mechanisms:
1. **Streamlit cache** (`@st.cache_data`): Caches function results in memory during the session
2. **File cache**: Saves intermediate results (CSV files) to avoid re-running expensive operations

### Session State Management
All major data structures are stored in `st.session_state`:
- `df_combined`: Full scraped dataset
- `summary_df`: Aggregated statistics per series
- `gse_selection_list`: User-selected GSE IDs
- `gse_df_filtered`: Filtered dataset
- `list_of_metadata_dfs`: List of DataFrames, one per GSE
- `metadata_search_results`: Results from keyword search

### Excel Export Pattern
Uses `sanitize_sheet_name()` helper to ensure Excel-compatible sheet names:
- Removes invalid characters: `:\/?\*[]`
- Limits to 31 characters
- Handles duplicates by appending numeric suffixes
- Tracks used names to prevent collisions

## File Structure

```
app/app_v1/
├── streamlite_app.py         # Main Streamlit application
├── biohack25_clean.yml        # Conda environment specification
├── gds_result.txt             # Input file (user-provided)
├── geo_webscrap.csv           # Cached scraping results
├── filtered_geo_webscrap.csv  # Cached filtered results
├── metadata_GSE.xlsx          # Exported metadata (all)
├── metadata_filtered_by_word.xlsx  # Exported metadata (filtered)
└── metadata/
    └── geo_soft_files/        # Downloaded SOFT files (*.soft.gz)

others/
├── GEO_webscraping_v1.ipynb   # Development notebook (v1)
└── GEO_webscraping_v2.ipynb   # Development notebook (v2)
```

## Important Notes

- The app expects `gds_result.txt` to contain GSE identifiers in the format `GSE######`
- Web scraping can be slow; cached files prevent re-scraping on subsequent runs
- Network visualizations use Jaccard similarity on file extension suffixes (last 30% of filename)
- Metadata extraction uses NCBI's GEO FTP service via GEOparse
- All visualizations use Plotly for interactivity except Dataset Snapshot which uses matplotlib/seaborn
