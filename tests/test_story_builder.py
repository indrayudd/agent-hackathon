"""Tests for story builder plot curation."""
import pytest
from src.agent.knowledge_graph import KnowledgeGraph, KnowledgeNode


def _make_kg_with_investigation():
    """Create a KG with one investigation that has plot metadata."""
    kg = KnowledgeGraph()
    nid = kg.add_investigation(
        hypothesis_id="h1",
        hypothesis_title="CO bursts are heteroskedastic",
        finding="Variance increases 2.4x in high-CO regime (Levene p < 10^-56).",
        evidence_cells=["h1_cell_1", "h1_cell_2", "h1_cell_3"],
        plot_cells=["h1_cell_2", "h1_cell_3"],
        confidence=0.85,
        sub_findings=[],
        columns=["CO(GT)", "PT08.S1(CO)"],
        analysis_type="hypothesis_investigation",
    )
    # Simulate plot metadata stored by eda_agent
    node = kg.nodes[nid]
    node.metadata["plot_images"] = [
        {"cell_id": "h1_cell_2", "image_png": "base64data1"},
        {"cell_id": "h1_cell_3", "image_png": "base64data2"},
    ]
    node.metadata["cell_sources"] = {
        "h1_cell_1": "print(df['CO(GT)'].describe())",
        "h1_cell_2": "plt.scatter(df['CO(GT)'], df['PT08.S1(CO)'])\nplt.title('CO vs Sensor')\nplt.show()",
        "h1_cell_3": "plt.hist(residuals, bins=30)\nplt.title('Residual Distribution')\nplt.show()",
    }
    node.metadata["cell_outputs"] = {
        "h1_cell_1": "count    9357\nmean     2.15\nstd      1.45",
        "h1_cell_2": "[plot generated]",
        "h1_cell_3": "Levene p=1.996e-56\n[plot generated]",
    }
    return kg


def test_get_story_sections_includes_plot_metadata():
    kg = _make_kg_with_investigation()
    sections = kg.get_story_sections()
    inv_sections = [s for s in sections if s["type"] == "investigation"]
    assert len(inv_sections) == 1
    sec = inv_sections[0]
    assert "plot_metadata" in sec
    assert len(sec["plot_metadata"]) == 2
    meta0 = sec["plot_metadata"][0]
    assert "cell_id" in meta0
    assert "cell_source" in meta0
    assert "cell_output" in meta0
