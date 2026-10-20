# How to run it
# conda activate {your env}
# cd /where/your/code/is
# streamlit run streamlite_GEOscouter_v2.py
# input: upload gds_result.txt via the UI (works locally as well)

# env: 'merged env ...'

# Top of your main app file (before other imports) - helpful friendly error if bs4 missing
try:
    from bs4 import BeautifulSoup
except Exception as e:
    import streamlit as st
    st.set_page_config(layout="wide")
    st.title("GEOscouter - Dependency error")
    st.error(
        "Missing Python package: beautifulsoup4 (bs4). "
        "Streamlit cannot import `bs4`. \n\n"
        "Fix: add `beautifulsoup4` to your requirements.txt at the repo root, commit, push, then redeploy.\n\n"
        f"Original import error: {e}"
    )
    # Stop further execution so logs are clear
    raise

import streamlit as st
import pandas as pd
import os
import re
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import seaborn as sns
import networkx as nx
import numpy as np
from adjustText import adjust_text
from itertools import combinations
import GEOparse
import logging
import plotly.express as px
import plotly.graph_objects as go 
import textwrap
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO)

# --- Selenium optional import ---
SELENIUM_AVAILABLE = True
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.options import Options
except Exception:
    SELENIUM_AVAILABLE = False

# --- Part 1: Pipeline Functions ---
@st.cache_data
def wrap_text_for_plotly(text, width=30):
    """Wraps text with HTML line breaks for Plotly tooltips."""
    if not isinstance(text, str):
        return ""
    return "<br>".join(textwrap.wrap(text, width=width))

# --- Helper function Excel sheet names ---
def sanitize_sheet_name(name: str, used: set) -> str:
    # Excel sheet name rules
    name = str(name) if pd.notna(name) and str(name).strip() else "NA"
    bad = r'[:\\/?*\[\]]'
    safe = re.sub(bad, "_", name)
    safe = safe[:31] or "NA"
    base = safe
    i = 1
    while safe in used:
        suffix = f"_{i}"
        safe = (base[:31-len(suffix)] + suffix) if len(base) + len(suffix) > 31 else base + suffix
        i += 1
    used.add(safe)
    return safe

# Selenium driver creation (local only)
def get_headless_driver():
    """Configures and returns a headless Selenium driver (LOCAL only)."""
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium is not available in this environment.")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )
    return webdriver.Chrome(options=chrome_options)

# New helper: parse (custom) links without Selenium
def parse_custom_supp_files(custom_href: str, base_url: str, data: dict):
    """
    Fetch the '(custom)' supplementary file listing using requests (no Selenium),
    parse the table rows, and return a list of row dictionaries.
    """
    custom_url = urljoin(base_url, custom_href)

    r = requests.get(custom_url, timeout=30)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")

    supp_data = []

    # Each file row usually has a checkbox in the first column.
    for row in s.select("table tr"):
        cb = row.select_one("input[type='checkbox']")
        if not cb:
            continue

        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        # On GEO "(custom)" pages, column 0 is often checkbox, column 1 is filename
        # Filename may be a link (<a>), so prefer link text if present.
        filename_td = tds[1]
        a = filename_td.find("a")
        file_name = (a.get_text(strip=True) if a else filename_td.get_text(strip=True))

        if not file_name or file_name.lower() == "(all files)":
            continue

        # Usually size is in the next column
        size = tds[2].get_text(strip=True)

        # "File type/resource" is often later (sometimes last column)
        file_type_resource = ""
        if len(tds) >= 5:
            file_type_resource = tds[4].get_text(strip=True)
        elif len(tds) >= 4:
            file_type_resource = tds[3].get_text(strip=True)

        # Optional: keep your old "file_type" logic, but it's less reliable than GEO's column
        parts = file_name.split(".")
        file_type = parts[1] if len(parts) > 1 else "unknown"

        row_dict = data.copy()
        row_dict.update({
            "Supplementary file": file_name,
            "Size": size,
            "File type/resource": file_type_resource or file_type,
        })
        supp_data.append(row_dict)

    return supp_data

def supplementary_files_from_soft(soft_text: str):
    """
    Extract supplementary file URLs from SOFT text and return filenames + URLs.
    """
    files = []
    for line in soft_text.splitlines():
        if line.startswith("!Series_supplementary_file"):
            # format: !Series_supplementary_file = <url>
            parts = line.split("=", 1)
            if len(parts) != 2:
                continue
            url = parts[1].strip()
            if not url:
                continue
            filename = url.rstrip("/").split("/")[-1]
            if filename:
                files.append((filename, url))
    return files

def _is_ncbi_blocked(text: str) -> bool:
    lowered = text.lower()
    return "recaptcha" in lowered or "challengepage" in lowered

def _fetch_soft_text(gse_id: str) -> str:
    soft_url = (
        f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
        f"?acc={gse_id}&targ=self&form=text&view=full"
    )
    response = requests.get(soft_url, timeout=30)
    response.raise_for_status()
    return response.text

def _parse_metadata_from_soft(soft_text: str) -> dict:
    field_map = {
        "title": "Title",
        "summary": "Summary",
        "overall_design": "Overall design",
        "contact_name": "Contact name",
        "contact_email": "E-mail(s)",
        "contact_phone": "Phone",
        "contact_institute": "Organization name",
        "contact_department": "Department",
        "contact_laboratory": "Lab",
        "contact_city": "City",
        "contact_state": "State/province",
        "contact_country": "Country",
    }
    data = {}
    for line in soft_text.splitlines():
        if not line.startswith("!Series_"):
            continue
        key, value = line.split("=", 1)
        soft_key = key.replace("!Series_", "").strip()
        if soft_key not in field_map:
            continue
        parsed = value.strip()
        if soft_key == "contact_name":
            parsed = parsed.replace(",,", " ").strip()
        data[field_map[soft_key]] = parsed
    return data

def _bytes_to_geo_size(size_bytes: str) -> str:
    try:
        nbytes = int(size_bytes)
    except (TypeError, ValueError):
        return ""
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:.1f} Gb"
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024 ** 2:.1f} Mb"
    if nbytes >= 1024:
        return f"{nbytes / 1024:.1f} Kb"
    return f"{nbytes} b"

def _fetch_custom_supp_files_xml(gse_id: str, data: dict) -> list[dict]:
    xml_url = f"https://www.ncbi.nlm.nih.gov/geo/download/?format=xml&acc={gse_id}"
    try:
        response = requests.get(xml_url, timeout=45)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as e:
        logging.warning(f"Custom XML file list failed for {gse_id}: {e}")
        return []

    rows = []
    for file_el in root.findall("file"):
        file_name = (file_el.text or "").strip()
        if not file_name:
            continue
        row_dict = data.copy()
        row_dict.update({
            "Supplementary file": file_name,
            "Size": _bytes_to_geo_size(file_el.get("size", "")),
            "File type/resource": file_name.rsplit(".", 1)[-1] if "." in file_name else "unknown",
        })
        rows.append(row_dict)
    return rows

# Main GSE processing - driver is optional
def process_gse(gse_id, driver=None, super_series=None):
    if not super_series:
        super_series = gse_id

    url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse_id}"
    soft_text = _fetch_soft_text(gse_id)
    soft_blocked = _is_ncbi_blocked(soft_text)

    html_response = requests.get(url, timeout=30)
    html_blocked = _is_ncbi_blocked(html_response.text)
    soup = BeautifulSoup(html_response.text, "html.parser") if not html_blocked else None

    desired_fields = [
        "Title", "Summary", "Overall design", "Contact name", "E-mail(s)",
        "Phone", "Organization name", "Department", "Lab", "City",
        "State/province", "Country"
    ]

    data = _parse_metadata_from_soft(soft_text) if not soft_blocked else {}
    if not data and soup is not None:
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) == 2:
                label = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                if label in desired_fields:
                    data[label] = value

    platforms = set(re.findall(r"(GPL\d+)", soft_text if not soft_blocked else ""))
    samples = set(re.findall(r"(GSM\d+)", soft_text if not soft_blocked else ""))

    data.update({
        "Platforms": ", ".join(sorted(platforms)),
        "Samples": len(samples),
        "Series": gse_id,
        "SuperSeries": super_series,
    })

    supp_data = []

    soft_supp_files = supplementary_files_from_soft(soft_text) if not soft_blocked else []
    soft_names = [name for name, _ in soft_supp_files]
    needs_custom_xml = (
        not soft_supp_files
        or any(name.upper().endswith("_RAW.TAR") or name.upper().endswith("RAW.TAR") for name in soft_names)
    )

    if needs_custom_xml:
        xml_rows = _fetch_custom_supp_files_xml(gse_id, data)
        if xml_rows:
            supp_data = xml_rows

    if not supp_data and soft_supp_files:
        for file_name, file_url in soft_supp_files:
            parts = file_name.split(".")
            file_type = parts[1] if len(parts) > 1 else "unknown"

            row_dict = data.copy()
            row_dict.update({
                "Supplementary file": file_name,
                "Size": "",
                "File type/resource": file_type,
                "Supplementary URL": file_url,
            })
            supp_data.append(row_dict)

    # Case 1: '(custom)' link - requests-first approach (HTML only when not blocked)
    custom_link_tag = soup.find("a", string="(custom)") if soup is not None else None
    if custom_link_tag and not supp_data:
        try:
            href = custom_link_tag.get("href")
            if href:
                parsed = parse_custom_supp_files(href, url, data)
                if parsed:
                    supp_data.extend(parsed)
                else:
                    logging.warning(f"(custom) page returned no parsed files for {gse_id}; will fallback.")
            else:
                logging.warning(f"(custom) link has no href for {gse_id}; will fallback.")

            if not supp_data and driver is not None and SELENIUM_AVAILABLE:
                driver.get(url)
                wait = WebDriverWait(driver, 7)

                custom_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "(custom)")))
                custom_link.click()

                wait.until(EC.presence_of_all_elements_located(
                    (By.XPATH, "//table//tr[td/input[@type='checkbox']]")
                ))
                rows = driver.find_elements(By.XPATH, "//table//tr[td/input[@type='checkbox']]")

                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        file_name = cells[0].text.strip()
                        if file_name.lower() == "(all files)":
                            continue

                        size = cells[1].text.strip()
                        parts = file_name.split('.')
                        file_type = parts[1] if len(parts) > 1 else "unknown"

                        row_dict = data.copy()
                        row_dict.update({
                            "Supplementary file": file_name,
                            "Size": size,
                            "File type/resource": file_type,
                        })
                        supp_data.append(row_dict)

        except Exception as e:
            logging.warning(f"Error processing custom link for {gse_id}: {e}")

    # Case 2: standard HTML parsing fallback
    if not supp_data and soup is not None:
        tables = soup.find_all('table')
        supp_table = None
        for table in tables[::-1]:
            header_row = table.find('tr')
            if not header_row:
                continue
            headers = [
                cell.get_text(strip=True)
                for cell in header_row.find_all(['td', 'th'])
            ]
            if "Supplementary file" in headers:
                supp_table = table
                break

        if supp_table:
            for row in supp_table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    row_dict = data.copy()
                    row_dict.update({
                        "Supplementary file": cells[0].get_text(strip=True),
                        "Size": cells[1].get_text(strip=True),
                        "File type/resource": cells[3].get_text(strip=True),
                    })
                    supp_data.append(row_dict)

    if not supp_data:
        supp_data.append(data)

    return supp_data


def run_geo_pipeline(dir_base, proximity_window=10):
    gds_file_path = os.path.join(dir_base, "gds_result.txt")
    if not os.path.exists(gds_file_path):
        st.error(f"Input file not found: {gds_file_path}.")
        return None

    # Step 1: read file
    with open(gds_file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Step 2: extract numeric GSE IDs
    gse_ids = re.findall(r'GSE(\d+)\b', text)
    gse_ids = sorted(set(gse_ids), key=int)

    # Step 3: cluster by numeric proximity
    clusters = []
    cluster_index = 0
    current_cluster = []
    prev_num = None

    for gse_num_str in gse_ids:
        gse_num = int(gse_num_str)
        if prev_num is None:
            current_cluster = [gse_num]
            cluster_index = 1
        else:
            if gse_num - prev_num <= proximity_window:
                current_cluster.append(gse_num)
            else:
                clusters.append((cluster_index, current_cluster))
                cluster_index += 1
                current_cluster = [gse_num]
        prev_num = gse_num

    if current_cluster:
        clusters.append((cluster_index, current_cluster))

    # Step 4: mapping
    gse_to_cluster = {}
    for cluster_id, gse_list in clusters:
        for val in gse_list:
            gse_to_cluster[val] = cluster_id

    # Step 5: build DataFrame with GSE + Cluster
    data = []
    for gse_num_str in gse_ids:
        gse_num = int(gse_num_str)
        cluster_id = gse_to_cluster.get(gse_num, None)
        gse_code = f"GSE{gse_num_str}"
        data.append({"GSE": gse_code, "Cluster": f"Cluster{cluster_id}"})

    df = pd.DataFrame(data).drop_duplicates(subset=['GSE']).reset_index(drop=True)

    # Optional: save clustering CSV
    gds_processed_path = os.path.join(dir_base, "gds_processed.csv")
    df.to_csv(gds_processed_path, index=False)

    # 1. Selenium optional initialization
    driver = None
    if SELENIUM_AVAILABLE:
        try:
            driver = get_headless_driver()
        except Exception as e:
            logging.warning(f"Selenium driver not available; continuing without Selenium. Details: {e}")
            driver = None

    all_data = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        gse_list = df['GSE']
        total = len(gse_list)

        for i, gse in enumerate(gse_list):
            status_text.text(f"Scraping {gse} ({i+1}/{total})...")
            # pass optional driver (None on Cloud)
            all_data.extend(process_gse(gse, driver))
            progress_bar.progress((i + 1) / total)

        status_text.success("Web scraping complete!")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    df_combined = pd.DataFrame(all_data)

    # cache combined CSV as before
    combined_path = os.path.join(dir_base, "geo_webscrap.csv")
    df_combined.to_csv(combined_path, index=False)

    return df_combined


def normalize_scrape_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["Platforms", "Series", "Samples"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["Platforms"] = (
        df["Platforms"]
        .fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    df["Samples"] = pd.to_numeric(df["Samples"], errors="coerce").fillna(0).astype(int)
    df["Series"] = df["Series"].fillna("").astype(str).str.strip().str.upper()
    return df

# --- Part 2: Visualization Functions ---
def dataset_snapshot(df):
    st.subheader("Dataset Snapshot")
    df = df.copy()
    def size_to_mb(size_str):
        if pd.isnull(size_str): return 0
        try:
            # Accept formats like "1.2 MB", "34 KB", "0.5 GB"
            num, unit = str(size_str).strip().split()
            num = float(num)
            if 'gb' in unit.lower(): return num * 1024
            if 'mb' in unit.lower(): return num
            if 'kb' in unit.lower(): return num / 1024
            return num / (1024 * 1024)
        except:
            return 0
    df['Size_MB'] = df.get('Size', pd.Series([None]*len(df))).apply(size_to_mb)
    df['Filetype_unzipped'] = df.get('File type/resource', pd.Series(['']*len(df))).str.replace('.gz', '', regex=False)
    summary = df.groupby('Series').agg(
        total_size_mb=('Size_MB', 'sum'),
        num_samples=('Samples', 'first'),
        num_file_types=('Filetype_unzipped', 'nunique'),
        num_files=('Supplementary file', 'nunique'),
        Platforms=('Platforms', 'first'),
        Title=('Title', 'first')
    ).reset_index()
    def platform_group(p_str):
        if pd.isnull(p_str): return 'Unknown'
        return 'Multiple Platforms' if ',' in str(p_str) else str(p_str)
    summary['Platform_Group'] = summary['Platforms'].apply(platform_group)

    summary['Hover_Title'] = summary['Title'].apply(wrap_text_for_plotly)

    for y_col, title, ylabel in [
        ('total_size_mb', 'Total Size per Series', 'Total Size (MB)'),
        ('num_samples', 'Samples per Series', 'Number of Samples'),
        ('num_file_types', 'File Types per Series', 'Number of File Types')]:
        fig, ax = plt.subplots(figsize=(18, 8))
        sns.barplot(data=summary, x='Series', y=y_col, hue='Platform_Group', ax=ax, palette='Set2')
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        plt.xticks(rotation=90)
        plt.legend(title='Platform_Group', bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.tight_layout()
        st.pyplot(fig)
    return summary


def file_per_smp_complexity(summary_df):
    st.subheader("File vs. Sample Complexity")
    fig = px.scatter(
        summary_df,
        x='num_files',
        y='num_samples',
        color='Platform_Group',
        hover_name='Series',
        hover_data=['Hover_Title', 'Platforms', 'num_samples', 'total_size_mb'],
        title='Unique Supplementary Files vs Samples per Series (Hover for Details)'
    )
    fig.update_traces(
        hovertemplate="<br>".join([
            "<b>%{hovertext}</b>", # This is the 'Series' name
            "Title: %{customdata[0]}", # This points to 'Hover_Title'
            "Platforms: %{customdata[1]}", # This points to 'Platforms'
        ])
    )
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)
    

def file_ext_network(df):
    st.subheader("File Extension Similarity Network")
    series_files, edges, G = calculate_similarity_edges(df)
    
    if not G.nodes:
        st.warning("Not enough data to create a network graph.")
        return

    pos = nx.spring_layout(G, seed=42, k=2.5)

    # --- Create Traces for Plotly ---
    edge_traces = []
    all_weights = [d['weight'] for _, _, d in G.edges(data=True)]
    
    # Create a list of Scatter traces, one for each edge, to apply color
    for edge in G.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        weight = edge[2]['weight']
        
        color = px.colors.sample_colorscale('viridis', weight)[0]

        edge_traces.append(go.Scatter(
            x=[x0, x1], y=[y0, y1],
            mode='lines',
            line=dict(width=2.5, color=color),
            hoverinfo='text',
            hovertext=f'Similarity: {weight:.3f}'
        ))
            
    # Create Nodes Trace
    node_x, node_y, node_text, node_hover_text = [], [], [], []
    node_info_df = df.drop_duplicates(subset='Series').set_index('Series')
    
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        
        if node in node_info_df.index:
            info = node_info_df.loc[node]
            hover_text = (
                f"<b>{node}</b><br>"
                f"Title: {info.get('Title', 'N/A')[:50]}...<br>"
                f"Platforms: {info.get('Platforms', 'N/A')}<br>"
                f"Samples: {info.get('Samples', 'N/A')}"
            )
            node_hover_text.append(hover_text)
        else:
            node_hover_text.append(f"<b>{node}</b>")

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        hoverinfo='text',
        text=node_text,
        textposition="top center",
        hovertext=node_hover_text,
        marker=dict(
            showscale=True,
            colorscale='viridis', 
            size=15,
            colorbar=dict(
                thickness=15,
                title='Node Connections (Degree)',
                xanchor='left',
                x=0, 
            ),
            line_width=2))
    
    node_adjacencies = [len(adj[1]) for adj in G.adjacency()]
    node_trace.marker.color = node_adjacencies

    # Create a DUMMY trace for the edge color bar
    if all_weights:
        colorbar_trace = go.Scatter(
            x=[None], y=[None],
            mode='markers',
            marker=dict(
                colorscale='viridis',
                cmin=0,
                cmax=1,
                showscale=True,
                colorbar=dict(
                    thickness=15,
                    title='Edge Similarity Score'
                )
            ),
            hoverinfo='none'
        )
        data = edge_traces + [node_trace, colorbar_trace]
    else:
        data = edge_traces + [node_trace]

    # Create the Figure
    fig = go.Figure(data=data,
                 layout=go.Layout(
                    title=dict(
                        text='<br>Series Network by Supplementary File Similarity',
                        font=dict(size=16)
                    ),
                    showlegend=False,
                    hovermode='closest',
                    margin=dict(b=20,l=5,r=5,t=40),
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                    )
    
    fig.update_layout(height=800)
    st.plotly_chart(fig, use_container_width=True)

# --- Helper function to calculate similarity ---
def calculate_similarity_edges(df):
    def last_pct_str(s, pct=0.3):
        if pd.isnull(s): return ''
        return str(s)[-max(1, int(len(str(s)) * pct)):]
    series_files = df.groupby('Series')['Supplementary file'].apply(lambda files: set(last_pct_str(f) for f in files))
    edges = [(s1, s2, len(series_files[s1] & series_files[s2]) / len(series_files[s1] | series_files[s2]))
             for s1, s2 in combinations(series_files.index, 2) if len(series_files[s1] | series_files[s2]) > 0]
    G = nx.Graph()
    G.add_nodes_from(series_files.index)
    G.add_weighted_edges_from(e for e in edges if e[2] > 0)
    return series_files, edges, G

# --- Part 3: Metadata Functions ---
@st.cache_data
def get_gse_metadata(df_filtered, metadata_dir):
    list_of_gse_dataframes = []
    gse_ids_to_process = df_filtered['Series'].unique()
    progress_bar = st.progress(0)
    status_text = st.empty()
    for i, gse_id in enumerate(gse_ids_to_process):
        status_text.text(f"Getting metadata for {gse_id} ({i+1}/{len(gse_ids_to_process)})...")
        try:
            gse = GEOparse.get_GEO(geo=gse_id, destdir=os.path.join(metadata_dir, "geo_soft_files"))
            all_samples_data = []
            for gsm_name, gsm_obj in gse.gsms.items():
                processed_metadata = {'gsm_id': gsm_name}
                for key, value in gsm_obj.metadata.items():
                    processed_metadata[key] = value[0] if isinstance(value, list) and len(value) > 0 else value
                if 'characteristics_ch1' in gsm_obj.metadata:
                    for characteristic in gsm_obj.metadata['characteristics_ch1']:
                        parts = characteristic.split(':', 1)
                        if len(parts) == 2:
                            processed_metadata[parts[0].strip()] = parts[1].strip()
                all_samples_data.append(processed_metadata)
            metadata_df = pd.DataFrame(all_samples_data)
            metadata_df['gse_id'] = gse_id
            list_of_gse_dataframes.append(metadata_df)
        except Exception as e:
            st.warning(f"Failed to get metadata for {gse_id}. Error: {e}")
        progress_bar.progress((i + 1) / len(gse_ids_to_process))
    status_text.success("Metadata extraction complete!")
    return list_of_gse_dataframes

# --- Streamlit App ---
st.set_page_config(layout="wide")
st.title("GEOscouter - Curating datasets from GEO 🧬")

# Initialize session state
st.session_state.setdefault('df_combined', None)
st.session_state.setdefault('summary_df', None)
st.session_state.setdefault('gse_selection_list', [])
st.session_state.setdefault('gse_df_filtered', None)
st.session_state.setdefault('list_of_metadata_dfs', None)
st.session_state.setdefault('metadata_search_results', None)

# --- Main Pipeline Execution ---
st.header("1. Run Data Scraping")
uploaded_gds = st.file_uploader("Upload gds_result.txt", type=["txt"])
# Working directory (Cloud-safe): /tmp/geoscouter
WORK_DIR = Path(tempfile.gettempdir()) / "geoscouter"
WORK_DIR.mkdir(parents=True, exist_ok=True)

dir_base = str(WORK_DIR)  # keep the rest of your pipeline code unchanged

# --- Manual cache cleanup button ---
if st.button("🗑 Delete cached geo_webscrap.csv"):
    cache_path = os.path.join(dir_base, "geo_webscrap.csv")
    if os.path.exists(cache_path):
        os.remove(cache_path)
        st.success("Cached geo_webscrap.csv deleted. Next run will scrape fresh data.")
    else:
        st.info("No cached geo_webscrap.csv found.")
        
if st.button("Run Pipeline", type="primary"):
    if uploaded_gds is None:
        st.error("Please upload gds_result.txt first.")
    else:
        # Save uploaded file into WORK_DIR as gds_result.txt (so run_geo_pipeline can find it)
        gds_path = Path(dir_base) / "gds_result.txt"
        gds_path.write_bytes(uploaded_gds.getvalue())

        cache_file_path = os.path.join(dir_base, "geo_webscrap.csv")
        if os.path.exists(cache_file_path):
            st.info(f"Loading data from existing file: {cache_file_path}")
            st.session_state.df_combined = pd.read_csv(cache_file_path)
            st.success("Cached data loaded successfully!")
        else:
            st.info("Cached file not found. Running the full web scraping pipeline...")
            df_result = run_geo_pipeline(dir_base)
            if df_result is not None:
                st.session_state.df_combined = df_result
                st.session_state.df_combined.to_csv(cache_file_path, index=False)
                st.success(f"Pipeline finished! Results saved to {cache_file_path}")

# --- Debug: Inspect Raw Output Files ---
if dir_base and os.path.isdir(dir_base):
    st.header("🔎 Debug: Inspect Pipeline Output Files")

    gds_path = os.path.join(dir_base, "gds_processed.csv")
    geo_path = os.path.join(dir_base, "geo_webscrap.csv")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("gds_processed.csv")
        if os.path.exists(gds_path):
            try:
                df_gds = pd.read_csv(gds_path)
                st.write("Shape:", df_gds.shape)
                st.dataframe(df_gds.head(20))
                with st.expander("Download gds_processed.csv"):
                    st.write(f"Path: {gds_path}")
                    st.download_button("Download gds_processed.csv", data=open(gds_path, "rb"), file_name="gds_processed.csv")
            except Exception as e:
                st.error(f"Failed to read gds_processed.csv: {e}")
        else:
            st.info("gds_processed.csv not found yet.")

    with col_b:
        st.subheader("geo_webscrap.csv")
        if os.path.exists(geo_path):
            try:
                df_geo = pd.read_csv(geo_path)
                st.write("Shape:", df_geo.shape)
                st.dataframe(df_geo.head(20))
                with st.expander("Download geo_webscrap.csv"):
                    st.write(f"Path: {geo_path}")
                    st.download_button("Download geo_webscrap.csv", data=open(geo_path, "rb"), file_name="geo_webscrap.csv")
            except Exception as e:
                st.error(f"Failed to read geo_webscrap.csv: {e}")
        else:
            st.info("geo_webscrap.csv not found yet.")

# --- Unfiltered Visualization Section ---
if st.session_state.df_combined is not None:
    st.header("2. Visualize Datasets")
    if st.button("Generate Dataset Snapshot Plots"):
        st.session_state.summary_df = dataset_snapshot(st.session_state.df_combined)
    if st.button("Generate File Complexity Plot"):
        if 'summary_df' not in st.session_state or st.session_state.summary_df is None:
            st.session_state.summary_df = dataset_snapshot(st.session_state.df_combined)
        file_per_smp_complexity(st.session_state.summary_df)
    if st.button("Generate File Similarity Network"):
        file_ext_network(st.session_state.df_combined)

# --- Filtering Section ---
if st.session_state.df_combined is not None:
    st.header("3. Selecting specific GSEs")
    with st.container(border=True):
        st.subheader("Step 1: Selecting Restrictive Parameters (Optional)")
        col1_filter, col2_filter = st.columns(2)
        with col1_filter:
            platforms_series = st.session_state.df_combined['Platforms'].dropna().str.split(', ')
            all_platforms = sorted(list(set([p for sublist in platforms_series for p in sublist])))
            selected_platforms = st.multiselect("Filter by Platform(s):", options=all_platforms, help="Leave empty to include all.")
        with col2_filter:
            st.write("**Filter by Sample Count Range:**")
            min_samples = st.number_input("Minimum samples (>=):", min_value=0, value=0, step=10, help="Set to 0 to disable.")
            max_samples = st.number_input("Maximum samples (<=):", min_value=0, value=0, step=10, help="Set to 0 to disable.")

        st.subheader("Step 2: Build Additional GSE Selection List (Optional)")
        col1_add, col2_add = st.columns(2)
        with col1_add:
            st.write("**Method 1: Add by Similarity**")
            sim_threshold = st.number_input("Similarity >=", min_value=0.0, max_value=1.0, value=0.8, step=0.05)
            if st.button("Add by Similarity"):
                _, edges, _ = calculate_similarity_edges(st.session_state.df_combined)
                added_gses = {s for e in edges if e[2] >= sim_threshold for s in e[:2]}
                st.session_state.gse_selection_list.extend(list(added_gses))
                st.success(f"Added {len(added_gses)} GSEs to the selection list.")
        with col2_add:
            st.write("**Method 2: Manually Add**")
            manual_gse = st.text_input("GSE ID:", key="manual_gse_input")
            if st.button("Add GSE"):
                if manual_gse:
                    st.session_state.gse_selection_list.append(manual_gse.strip().upper())
                    st.rerun()

        st.divider()
        
        unique_selection_count = len(set(st.session_state.gse_selection_list))
        st.write(f"**Additive Selection List:** {unique_selection_count} unique GSEs selected.")
        if st.button("Reset Selection List"):
            st.session_state.gse_selection_list = []
            st.rerun()

        st.subheader("Step 3: Apply All Filters")
        if st.button("Filter GSE Selected", type="primary"):
            df_to_filter = st.session_state.df_combined.copy()
            unique_samples_df = df_to_filter.drop_duplicates(subset=['Series'])
            if selected_platforms:
                platform_regex = '|'.join(selected_platforms)
                df_to_filter = df_to_filter[df_to_filter['Platforms'].str.contains(platform_regex, na=False)]
            
            gses_passing_samples = set(df_to_filter['Series'].unique())
            if min_samples > 0:
                gses_passing_samples.intersection_update(unique_samples_df.query(f'Samples >= {min_samples}')['Series'])
            if max_samples > 0:
                gses_passing_samples.intersection_update(unique_samples_df.query(f'Samples <= {max_samples}')['Series'])
            df_to_filter = df_to_filter[df_to_filter['Series'].isin(gses_passing_samples)]
            
            if st.session_state.gse_selection_list:
                unique_gses_to_keep = set(st.session_state.gse_selection_list)
                df_to_filter = df_to_filter[df_to_filter['Series'].isin(unique_gses_to_keep)]
            
            st.session_state.gse_df_filtered = df_to_filter
            final_gse_count = len(st.session_state.gse_df_filtered['Series'].unique())
            st.success(f"Filtered DataFrame created with {final_gse_count} unique GSEs.")

# --- Filtered Visualization and Export Section ---
if st.session_state.gse_df_filtered is not None:
    st.header("4. Analyze Selected GSEs")
    
    if st.button("Make Plots from Selected GSEs"):
        with st.spinner("Generating filtered plots..."):
            if not st.session_state.gse_df_filtered.empty:
                filtered_summary = dataset_snapshot(st.session_state.gse_df_filtered)
                file_per_smp_complexity(filtered_summary)
                file_ext_network(st.session_state.gse_df_filtered)
            else:
                st.warning("The filtered DataFrame is empty. No plots to generate.")

    if st.button("Extract the data"):
        if dir_base:
            output_csv_path = os.path.join(dir_base, "filtered_geo_webscrap.csv")
            st.session_state.gse_df_filtered.to_csv(output_csv_path, index=False)
            st.success(f"Filtered data saved successfully to: {output_csv_path}")
        else:
            st.error("Please provide the initial directory path in Step 1 to save the file.")

# --- Metadata Analysis Section ---
st.title("5. Metadata Analysis")
if st.button("Get GSE Metadata"):
    df_to_process = None
    if st.session_state.gse_df_filtered is not None:
        df_to_process = st.session_state.gse_df_filtered
        st.info("Using the FILTERED GSE list for metadata extraction.")
    elif st.session_state.df_combined is not None:
        df_to_process = st.session_state.df_combined
        st.info("Using the FULL GSE list for metadata extraction.")
    
    if df_to_process is not None and dir_base:
        metadata_dir = os.path.join(dir_base, "metadata")
        os.makedirs(metadata_dir, exist_ok=True)
        st.session_state.list_of_metadata_dfs = get_gse_metadata(df_to_process, metadata_dir)
    else:
        st.warning("Please run the main pipeline first by providing a directory path.")

if st.session_state.list_of_metadata_dfs:
    with st.container(border=True):
        st.header("Explore GSEs Metadata")
        gse_options = [df['gse_id'].iloc[0] for df in st.session_state.list_of_metadata_dfs]
        selected_gse = st.selectbox("Select a GSE to view:", options=gse_options, key="raw_gse_select")
        for df in st.session_state.list_of_metadata_dfs:
            if df['gse_id'].iloc[0] == selected_gse:
                st.dataframe(df)
                break
        
        if st.button("Extract Metadata to Excel"):
            if dir_base:
                excel_out_path = os.path.join(dir_base, "metadata_GSE.xlsx")
                used_names = set()
                with pd.ExcelWriter(excel_out_path, engine="xlsxwriter") as writer:
                    for df in st.session_state.list_of_metadata_dfs:
                        gse_id = df['gse_id'].iloc[0]
                        sheet_name = sanitize_sheet_name(gse_id, used_names)
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                st.success(f"Metadata successfully exported to: {excel_out_path}")
            else:
                st.error("Please provide the initial directory path in Step 1 to save the Excel file.")

    with st.container(border=True):
        st.header("6. Search Key Words and Visualize Metadata")
        keyword = st.text_input("Enter keyword to search:", key="keyword_search")
        if st.button("Search Metadata"):
            if keyword:
                found_gses, found_gsms, gsm_counts_per_gse = set(), set(), {}
                for df in st.session_state.list_of_metadata_dfs:
                    mask = df.apply(lambda col: col.astype(str).str.contains(keyword, case=False, na=False))
                    if mask.values.any():
                        gse_id = df['gse_id'].iloc[0]
                        matching_gsms = df.loc[mask.any(axis=1), 'gsm_id'].tolist()
                        found_gses.add(gse_id)
                        found_gsms.update(matching_gsms)
                        gsm_counts_per_gse[gse_id] = len(matching_gsms)
                st.session_state.metadata_search_results = {'gse_vector': sorted(list(found_gses)), 'gsm_vector': sorted(list(found_gsms)), 'counts': gsm_counts_per_gse, 'keyword': keyword}
            else:
                st.warning("Please enter a keyword.")
        if st.session_state.metadata_search_results:
            res = st.session_state.metadata_search_results
            st.info(f"Found '{res['keyword']}' in **{len(res['gse_vector'])}** GSEs and **{len(res['gsm_vector'])}** GSMs.")
            plot_df = pd.DataFrame(list(res['counts'].items()), columns=['GSE', 'GSM Count']).sort_values('GSM Count', ascending=False)
            fig = px.bar(plot_df, x='GSE', y='GSM Count', title=f"Matched GSMs per GSE for '{res['keyword']}'")
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("Show/Hide Found GSE/GSM Names"):
                st.dataframe({"Found GSEs": res['gse_vector'], "Found GSMs": pd.Series(res['gsm_vector'])})
    
    with st.container(border=True):
        st.header("7. Explore Filtered Metadata")
        if st.session_state.metadata_search_results:
            res = st.session_state.metadata_search_results
            if not res['gse_vector']:
                st.write("No matching GSEs to display.")
            else:
                selected_filtered_gse = st.selectbox("Select a filtered GSE to view:", options=res['gse_vector'], key="filtered_gse_select")
                for df in st.session_state.list_of_metadata_dfs:
                    if df['gse_id'].iloc[0] == selected_filtered_gse:
                        filtered_subset = df[df['gsm_id'].isin(res['gsm_vector'])].copy()
                        st.dataframe(filtered_subset)
                        break

            st.header("Export Filtered Metadata")
            if st.button("Extract metadata filtered to excel"):
                if dir_base and st.session_state.list_of_metadata_dfs and st.session_state.metadata_search_results:
                    excel_out_path = os.path.join(dir_base, "metadata_filtered_by_word.xlsx")
                    
                    list_of_filtered_dfs = []
                    res = st.session_state.metadata_search_results
                    gses_to_include = res['gse_vector']
                    gsms_to_include = res['gsm_vector']

                    for df in st.session_state.list_of_metadata_dfs:
                        gse_id = df['gse_id'].iloc[0]
                        if gse_id in gses_to_include:
                            filtered_subset = df[df['gsm_id'].isin(gsms_to_include)].copy()
                            if not filtered_subset.empty:
                                list_of_filtered_dfs.append(filtered_subset)
                    
                    used_names = set()
                    with pd.ExcelWriter(excel_out_path, engine="xlsxwriter") as writer:
                        for filt_df in list_of_filtered_dfs:
                            gse_id = filt_df['gse_id'].iloc[0]
                            sheet_name = sanitize_sheet_name(gse_id, used_names)
                            filt_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    st.success(f"Filtered metadata successfully exported to: {excel_out_path}")
                
                    st.error("Cannot export. Ensure data is loaded and a search has been performed.")
