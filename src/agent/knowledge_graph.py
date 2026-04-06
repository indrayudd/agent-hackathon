"""Knowledge graph for accumulating EDA findings with evidence chains."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)


@dataclass
class KnowledgeNode:
    """A single node in the knowledge graph."""
    id: str
    type: str  # "fact", "hypothesis", "evidence", "conclusion"
    text: str
    phase: str = ""
    cell_ids: list[str] = field(default_factory=list)
    plot_cell_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    hypothesis_id: str | None = None
    children: list[str] = field(default_factory=list)  # child node IDs

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "phase": self.phase,
            "cell_ids": self.cell_ids,
            "plot_cell_ids": self.plot_cell_ids,
            "confidence": self.confidence,
            "hypothesis_id": self.hypothesis_id,
            "children": self.children,
        }


class KnowledgeGraph:
    """Accumulates findings from all phases and investigations."""

    def __init__(self):
        self.nodes: dict[str, KnowledgeNode] = {}
        self._counter = 0

    def _next_id(self, prefix: str = "n") -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def add_fact(self, text: str, phase: str, cell_id: str | None = None) -> str:
        """Add a data fact from the initial EDA pass."""
        nid = self._next_id("fact")
        self.nodes[nid] = KnowledgeNode(
            id=nid, type="fact", text=text, phase=phase,
            cell_ids=[cell_id] if cell_id else [],
        )
        return nid

    def add_investigation(
        self,
        hypothesis_id: str,
        hypothesis_title: str,
        finding: str,
        evidence_cells: list[str],
        plot_cells: list[str],
        confidence: float = 0.8,
        sub_findings: list[dict] | None = None,
    ) -> str:
        """Add results from a hypothesis investigation."""
        nid = self._next_id("inv")
        node = KnowledgeNode(
            id=nid, type="conclusion", text=finding,
            phase=f"Investigation: {hypothesis_title}",
            cell_ids=evidence_cells, plot_cell_ids=plot_cells,
            confidence=confidence, hypothesis_id=hypothesis_id,
        )

        # Add sub-findings as children
        if sub_findings:
            for sf in sub_findings:
                child_id = self._next_id("sub")
                self.nodes[child_id] = KnowledgeNode(
                    id=child_id, type="evidence", text=sf.get("finding", ""),
                    phase=node.phase,
                    cell_ids=sf.get("cell_ids", []),
                    plot_cell_ids=sf.get("plot_cells", []),
                    confidence=sf.get("confidence", 0.7),
                    hypothesis_id=hypothesis_id,
                )
                node.children.append(child_id)

        self.nodes[nid] = node
        return nid

    def get_story_sections(self) -> list[dict]:
        """Generate story sections from the knowledge graph."""
        # Group by phase
        phase_nodes: dict[str, list[KnowledgeNode]] = {}
        for node in self.nodes.values():
            phase_nodes.setdefault(node.phase, []).append(node)

        sections = []

        # First: initial EDA facts
        for phase in ["Data Loading", "Data Cleaning", "Univariate Analysis",
                       "Time Series", "Dynamics", "Correlations", "Train/Test Split"]:
            nodes = phase_nodes.get(phase, [])
            if not nodes:
                continue
            all_cells = []
            all_plots = []
            findings = []
            for n in nodes:
                findings.append(n.text)
                all_cells.extend(n.cell_ids)
                all_plots.extend(n.plot_cell_ids)
            sections.append({
                "phase": phase,
                "title": phase,
                "content": "\n".join(f"- {f}" for f in findings),
                "cell_ids": list(set(all_cells)),
                "plot_cell_ids": list(set(all_plots)),
                "type": "initial",
            })

        # Then: investigation conclusions
        investigations = [n for n in self.nodes.values() if n.type == "conclusion"]
        investigations.sort(key=lambda n: n.confidence, reverse=True)

        for inv in investigations:
            children_text = []
            child_cells = []
            child_plots = []
            for child_id in inv.children:
                child = self.nodes.get(child_id)
                if child:
                    children_text.append(f"  - {child.text}")
                    child_cells.extend(child.cell_ids)
                    child_plots.extend(child.plot_cell_ids)

            content = inv.text
            if children_text:
                content += "\n\nSupporting evidence:\n" + "\n".join(children_text)

            sections.append({
                "phase": inv.phase,
                "title": inv.phase.replace("Investigation: ", ""),
                "content": content,
                "cell_ids": list(set(inv.cell_ids + child_cells)),
                "plot_cell_ids": list(set(inv.plot_cell_ids + child_plots)),
                "confidence": inv.confidence,
                "type": "investigation",
            })

        return sections

    def get_top_conclusions(self, n: int = 5) -> list[str]:
        """Get the top N conclusions by confidence for the executive summary."""
        conclusions = [
            node for node in self.nodes.values()
            if node.type == "conclusion"
        ]
        conclusions.sort(key=lambda n: n.confidence, reverse=True)
        return [c.text for c in conclusions[:n]]

    def to_dict(self) -> dict:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeGraph:
        kg = cls()
        for nid, nd in data.get("nodes", {}).items():
            kg.nodes[nid] = KnowledgeNode(**nd)
            kg._counter = max(kg._counter, int(nid.split("_")[-1]) if "_" in nid else 0)
        return kg
