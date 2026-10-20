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

def run_geo_pipeline(dir_base):
    gds_file_path = os.path.join(dir_base, "gds_result.txt")
    if not os.path.exists(gds_file_path):
        st.error(f"Input file not found: {gds_file_path}.")
        return None
    with open(gds_file_path, 'r', encoding='utf-8') as f: text = f.read()
    gse_ids = sorted(set(re.findall(r'GSE(\d+)\b', text)), key=int)
    clusters, current_cluster, prev_num = [], [], None
    cluster_index = 1
    for gse_num_str in gse_ids:
        gse_num = int(gse_num_str)
        if prev_num is None: current_cluster = [gse_num]
        elif gse_num - prev_num <= 10: current_cluster.append(gse_num)
        else:
            clusters.append((cluster_index, current_cluster))
            cluster_index += 1
            current_cluster = [gse_num]
        prev_num = gse_num
    if current_cluster: clusters.append((cluster_index, current_cluster))
    gse_to_cluster = {val: cid for cid, gse_list in clusters for val in gse_list}
    data = [{"GSE": f"GSE{gns}", "Cluster": f"Cluster{gse_to_cluster.get(int(gns), None)}"} for gns in gse_ids]
    df = pd.DataFrame(data).drop_duplicates(subset=['GSE']).reset_index(drop=True)
    def process_gse(gse_id):
        url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse_id}"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        data = {}
        rows = soup.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                label = cols[0].get_text(strip=True)
                if label in ["Title", "Summary", "Overall design", "Contact name", "E-mail(s)", "Phone", "Organization name", "Department", "Lab", "City", "State/province", "Country"]:
                    data[label] = cols[1].get_text(strip=True)
        soft_url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse_id}&format=soft"
        soft_response = requests.get(soft_url)
        data["Platforms"] = ", ".join(sorted(set(re.findall(r"(GPL\d+)", soft_response.text))))
        data["Samples"] = len(set(re.findall(r"(GSM\d+)", soft_response.text)))
        data["Series"] = gse_id
        supp_data = []
        tables = soup.find_all('table')
        supp_table_found = False
        for table in tables[::-1]:
             headers = [cell.get_text(strip=True) for cell in table.find_all(['td', 'th'])]
             if "Supplementary file" in headers and "Size" in headers:
                supp_table_found = True
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        row_dict = data.copy()
                        row_dict.update({"Supplementary file": cells[0].get_text(strip=True), "Size": cells[1].get_text(strip=True), "File type/resource": cells[3].get_text(strip=True)})
                        supp_data.append(row_dict)
                break
        if not supp_table_found: supp_data.append(data)
        return supp_data
    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    gse_list = df['GSE']
    for i, gse in enumerate(gse_list):
        status_text.text(f"Scraping {gse} ({i+1}/{len(gse_list)})...")
        all_data.extend(process_gse(gse))
        progress_bar.progress((i + 1) / len(gse_list))
    status_text.success("Web scraping complete!")
    return pd.DataFrame(all_data)

# --- Part 2: Visualization Functions ---
def dataset_snapshot(df):
    st.subheader("Dataset Snapshot")
    df = df.copy()
    def size_to_mb(size_str):
        if pd.isnull(size_str): return 0
        try:
            num, unit = str(size_str).strip().split()
            num = float(num)
            if 'gb' in unit.lower(): return num * 1024
            if 'mb' in unit.lower(): return num
            if 'kb' in unit.lower(): return num / 1024
            return num / (1024 * 1024)
        except: return 0
    df['Size_MB'] = df['Size'].apply(size_to_mb)
    df['Filetype_unzipped'] = df['File type/resource'].str.replace('.gz', '', regex=False)
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
        # size='total_size_mb',
        hover_name='Series',
        hover_data=['Hover_Title', 'Platforms', 'num_samples', 'total_size_mb'],
        title='Unique Supplementary Files vs Samples per Series (Hover for Details)'
    )
    fig.update_traces(
        hovertemplate="<br>".join([
            "<b>%{hovertext}</b>", # This is the 'Series' name
            "Title: %{customdata[0]}", # This points to 'Hover_Title'
            "Platforms: %{customdata[1]}", # This points to 'Platforms'
           # "num_samples: %{customdata[2]}", # This points to 'num_samples'
           # "total_size_mb: %{customdata[2]}" # This points to 'total_size_mb' and formats it
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
dir_base = st.text_input("Enter the path to the folder containing 'gds_result.txt':")

if st.button("Run Pipeline", type="primary"):
    if dir_base and os.path.isdir(dir_base):
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
                st.success(f"Pipeline finished! Results are ready and saved to {cache_file_path} for future runs.")
    else:
        st.error("Please provide a valid directory path.")

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
                else:
                    st.error("Cannot export. Ensure data is loaded and a search has been performed.")
