import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from geoscouter.core.similarity import (
    SIGNATURE_NODE,
    SUPERVISED_SIMILARITY_HELP,
    applied_signature_rules_table,
    calculate_similarity_edges,
    score_supervised_candidates,
    supervised_comparison_table_from_rules,
)


def supervised_file_similarity_network(
    df: pd.DataFrame,
    training_gses: list[str],
    rules: list[dict],
    signature_mode: str = "training_gse",
    edge_threshold: float = 0.2,
):
    st.subheader("Supervised file structure similarity network")
    with st.expander("How is the signature calculated?", expanded=False):
        st.markdown(SUPERVISED_SIMILARITY_HELP)

    series_files, _, _ = calculate_similarity_edges(df)
    training, candidate_scores = score_supervised_candidates(
        series_files, training_gses, rules
    )

    if signature_mode == "training_gse" and not training:
        st.warning("Select at least one training GSE present in the active dataset.")
        return

    if not rules:
        st.warning(
            "No signature rules are enabled. Include at least one pattern in the table above."
        )
        return

    edge_threshold = st.slider(
        "Minimum similarity for edge to signature",
        0.0,
        1.0,
        edge_threshold,
        0.05,
        help="GSEs at or above this score are linked to the signature (viridis). "
        "Below threshold: gray, no edge.",
    )

    linked = sorted(
        [(gse, score) for gse, score in candidate_scores.items() if score >= edge_threshold],
        key=lambda x: x[1],
        reverse=True,
    )
    unlinked = sorted(
        [(gse, score) for gse, score in candidate_scores.items() if score < edge_threshold],
        key=lambda x: x[1],
        reverse=True,
    )

    node_info_df = df.drop_duplicates(subset="Series").set_index("Series")

    tar_mask = df["TAR file"] == True
    tar_gses = set(df.loc[tar_mask, "Series"].dropna())


    pos: dict[str, tuple[float, float]] = {SIGNATURE_NODE: (0.0, 0.0)}

    training_list = sorted(training)
    for i, gse in enumerate(training_list):
        angle = 2 * math.pi * i / max(len(training_list), 1)
        pos[gse] = (0.22 * math.cos(angle), 0.22 * math.sin(angle))

    for i, (gse, score) in enumerate(linked):
        angle = 2 * math.pi * i / max(len(linked), 1)
        radius = 0.42 + 0.38 * (1.0 - score)
        pos[gse] = (radius * math.cos(angle), radius * math.sin(angle))

    for i, (gse, _score) in enumerate(unlinked):
        angle = 2 * math.pi * i / max(len(unlinked), 1)
        pos[gse] = (0.95 * math.cos(angle), 0.95 * math.sin(angle))

    def _node_hover(node: str, score: float | None = None) -> str:
        if node == SIGNATURE_NODE:
            training_line = (
                f"Training GSEs: {len(training)}<br>"
                if signature_mode == "training_gse"
                else "Manual file-type signature<br>"
            )
            return (
                f"<b>{SIGNATURE_NODE}</b><br>"
                f"{training_line}"
                f"Active rules: {len(rules)}<br>"
                f"Linked candidates: {len(linked)}"
            )
        is_training = node in training
        role = "<br><b>Training example</b>" if is_training else ""
        score_line = (
            f"<br>Similarity: {score:.3f}" if score is not None else ""
        )
        linked_line = (
            "<br>Linked to signature"
            if score is not None and score >= edge_threshold
            else "<br>Below threshold (no edge)"
            if score is not None
            else ""
        )
        if node in node_info_df.index:
            info = node_info_df.loc[node]
            title_val = info.get("Title", "N/A")
            title_str = "N/A" if pd.isna(title_val) else str(title_val)
            assay_val = info.get("Platform_labels") or info.get("Study_type") or "N/A"
            return (
                f"<b>{node}</b>{role}{score_line}{linked_line}<br>"
                f"Title: {title_str[:80]}<br>"
                f"Assay: {assay_val}<br>Samples: {info.get('Samples', 'N/A')}"
            )
        return f"<b>{node}</b>{role}{score_line}{linked_line}"

    edge_traces = []

    for gse in training_list:
        x0, y0 = pos[SIGNATURE_NODE]
        x1, y1 = pos[gse]
        edge_traces.append(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(width=2, color="rgba(52, 152, 219, 0.55)", dash="dot"),
                hoverinfo="text",
                hovertext=f"Training example: {gse}",
                showlegend=False,
            )
        )

    for gse, weight in linked:
        x0, y0 = pos[SIGNATURE_NODE]
        x1, y1 = pos[gse]
        width = 1.5 + 5 * weight
        edge_traces.append(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(
                    width=width,
                    color=px.colors.sample_colorscale("viridis", weight)[0],
                ),
                hoverinfo="text",
                hovertext=f"Similarity to signature: {weight:.3f}",
                showlegend=False,
            )
        )

    def _scatter_nodes(nodes, size, color, line, text_labels=None, hovers=None):
        if not nodes:
            return None
        labels = text_labels or nodes
        hovertext = hovers or [_node_hover(n) for n in nodes]
        label_colors = ["red" if node in tar_gses else "black"
                       for node in nodes]
        return go.Scatter(
            x=[pos[n][0] for n in nodes],
            y=[pos[n][1] for n in nodes],
            mode="markers+text",
            hoverinfo="text",
            text=labels,
            textposition="top center",
            hovertext=hovertext,
            marker=dict(size=size, color=color, line=line),
            textfont = dict(color = label_colors)
        )

    def _scatter_nodes_viridis(nodes, scores, size, line):
        if not nodes:
            return None
        colors = [px.colors.sample_colorscale("viridis", scores[n])[0] for n in nodes]
        hovers = [_node_hover(n, scores[n]) for n in nodes]
        label_colors = ["red" if node in tar_gses else "black"
                        for node in nodes]
        return go.Scatter(
            x=[pos[n][0] for n in nodes],
            y=[pos[n][1] for n in nodes],
            mode="markers+text",
            hoverinfo="text",
            text=nodes,
            textposition="top center",
            hovertext=hovers,
            marker=dict(size=size, color=colors, line=line),
            textfont = dict(color = label_colors)
        )

    linked_nodes = [gse for gse, _ in linked]
    unlinked_nodes = [gse for gse, _ in unlinked]
    linked_score_map = dict(linked)
    unlinked_score_map = dict(unlinked)

    node_traces = [
        t
        for t in [
            _scatter_nodes(
                unlinked_nodes,
                12,
                "#b0b8c4",
                dict(width=1.5, color="#ffffff"),
                hovers=[_node_hover(n, unlinked_score_map[n]) for n in unlinked_nodes],
            ),
            _scatter_nodes_viridis(
                linked_nodes,
                linked_score_map,
                16,
                dict(width=2, color="#ffffff"),
            ),
            _scatter_nodes(
                training_list,
                18,
                "#3498db",
                dict(width=2, color="#1f618d"),
            ),
            _scatter_nodes(
                [SIGNATURE_NODE],
                24,
                "#d4a017",
                dict(width=3, color="#8b6914"),
                text_labels=["Signature"],
            ),
        ]
        if t is not None
    ]

    data = edge_traces + node_traces
    data.append(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            marker=dict(
                colorscale="viridis",
                cmin=0,
                cmax=1,
                showscale=True,
                colorbar=dict(thickness=15, title="Signature similarity"),
            ),
            hoverinfo="none",
        )
    )

    if signature_mode == "manual":
        title = (
            f"Manual signature ({len(rules)} rules, {len(linked)} linked / "
            f"{len(unlinked)} below threshold)"
        )
        legend_training = None
    else:
        title = (
            f"Supervised similarity from {len(training)} training GSE(s) "
            f"({len(rules)} rules, {len(linked)} linked / "
            f"{len(unlinked)} below threshold)"
        )
        legend_training = dict(
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            text="Blue dotted: training GSEs",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            font=dict(size=11, color="#2980b9"),
        )

    annotations = [
        a
        for a in [
            legend_training,
            dict(
                x=0.02,
                y=0.94 if legend_training else 0.98,
                xref="paper",
                yref="paper",
                text="Viridis: linked to signature (similarity gradient)",
                showarrow=False,
                xanchor="left",
                yanchor="top",
                font=dict(size=11, color="#440154"),
            ),
            dict(
                x=0.02,
                y=0.90 if legend_training else 0.94,
                xref="paper",
                yref="paper",
                text="Gray: shown but below edge threshold",
                showarrow=False,
                xanchor="left",
                yanchor="top",
                font=dict(size=11, color="#6b7280"),
            ),
            dict(
                x=0.02,
                y=0.86 if legend_training else 0.90,
                xref="paper",
                yref="paper",
                text="Red: GSE has tar files",
                showarrow=False,
                xanchor="left",
                yanchor="top",
                font=dict(size=11, color="red")
            )
        ]
        if a is not None
    ]

    fig = go.Figure(
        data=data,
        layout=go.Layout(
            title=title,
            showlegend=False,
            hovermode="closest",
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            annotations=annotations,
        ),
    )
    fig.update_layout(height=700)
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Applied signature rules")
    st.dataframe(applied_signature_rules_table(rules), width="stretch", hide_index=True)

    st.markdown("#### Comparison to signature")
    comparison_df = supervised_comparison_table_from_rules(
        series_files, list(training), rules
    )
    st.dataframe(
        comparison_df,
        column_config={
            "GEO link": st.column_config.LinkColumn(
                "GSE",
                display_text=r"acc=(GSE\d+)",
            ),
            "GSE": None,
        },
        width="stretch",
        hide_index=True,
    )
