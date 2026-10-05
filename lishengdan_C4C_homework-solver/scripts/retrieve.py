#!/usr/bin/env python3
"""
T-box Retrieval: Find the best solver template for a classified problem.

Given a concept ID from the classifier, walks the T-box graph to find
the most appropriate solver template. Implements the priority chain:
  exact match > parent concept > sibling concept > no match (oracle)

This module is the bridge between classification (which concept?)
and execution (which solver?). In a full KSTAR implementation,
this would query the KSTAR DB for validated skills.

Usage:
    from retrieve import TBoxRetriever
    retriever = TBoxRetriever("domain_skills/calculus_limits.yaml")
    solver_info = retriever.retrieve(concept_id, solver_id, features)
"""

import yaml
from pathlib import Path
from typing import Optional

try:
    from bootstrap import SKILL_ROOT
except ImportError:
    SKILL_ROOT = Path(__file__).resolve().parent.parent


class TBoxRetriever:
    """
    Retrieve solver templates from the T-box concept graph.

    In the full architecture, this would implement kstar-retrieval with
    confidence scoring and lifecycle-aware ranking. The starter kit
    version does priority-based lookup.
    """

    def __init__(self, tbox_path: str = None):
        """Load T-box from YAML file."""
        if tbox_path is None:
            tbox_path = SKILL_ROOT / "domain_skills" / "calculus_limits.yaml"

        self.tbox_path = Path(tbox_path)
        self.concepts = {}
        self.solution_methods = {}
        self.edges = []

        if self.tbox_path.exists():
            self._load(self.tbox_path)

    def _load(self, path: Path):
        """Parse the T-box YAML."""
        with open(path, "r", encoding="utf-8") as f:
            tbox = yaml.safe_load(f)

        for concept in tbox.get("concepts", []):
            self.concepts[concept["id"]] = concept

        for method in tbox.get("solution_methods", []):
            self.solution_methods[method["id"]] = method

        self.edges = tbox.get("edges", []) if "edges" in tbox else []

        # Build concept → solver index from solution_methods
        self._concept_solvers = {}
        for method in self.solution_methods.values():
            cid = method.get("concept")
            if cid:
                if cid not in self._concept_solvers:
                    self._concept_solvers[cid] = []
                self._concept_solvers[cid].append(method)

    def retrieve(
        self,
        concept_id: Optional[str],
        solver_id: Optional[str],
        features: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Retrieve the best solver for a classified problem.

        Args:
            concept_id: from classifier (which concept?)
            solver_id: from classifier (which solver?, may be None)
            features: problem features (for applies_when matching)

        Returns:
            Solver method dict or None (invoke oracle)
        """
        # 1. Direct solver match (classifier already identified the solver)
        if solver_id and solver_id in self.solution_methods:
            return self.solution_methods[solver_id]

        # 2. Find solvers for the concept
        if concept_id and concept_id in self._concept_solvers:
            solvers = self._concept_solvers[concept_id]
            if len(solvers) == 1:
                return solvers[0]
            # Multiple solvers for this concept — pick based on features
            if features:
                return self._rank_solvers(solvers, features)
            return solvers[0]

        # 3. Walk up to parent concept (via prerequisites)
        if concept_id and concept_id in self.concepts:
            concept = self.concepts[concept_id]
            for prereq_id in concept.get("prerequisites", []):
                if prereq_id in self._concept_solvers:
                    return self._concept_solvers[prereq_id][0]

        # 4. No solver found — this is the oracle invocation signal
        return None

    def get_solver_info(self, solver_id: str) -> Optional[dict]:
        """Get full info about a solver method."""
        return self.solution_methods.get(solver_id)

    def get_concept_info(self, concept_id: str) -> Optional[dict]:
        """Get full info about a concept."""
        return self.concepts.get(concept_id)

    def get_validation_rules(self, concept_id: str) -> list:
        """Get validation rules for a concept (if defined in T-box)."""
        # In the current T-box format, validation rules are in a top-level section
        # This is a placeholder for the full implementation
        return []

    def _rank_solvers(self, solvers: list, features: dict) -> dict:
        """
        Rank multiple solvers for the same concept.

        Uses applies_when field as a simple text match against features.
        In the full implementation, this would use confidence scoring
        from the KSTAR DB.
        """
        text_lower = features.get("text_lower", "")

        for solver in solvers:
            applies = solver.get("applies_when", "").lower()
            # Check if the applies_when keywords match
            if applies and any(word in text_lower for word in applies.split()):
                return solver

        return solvers[0]  # Default to first


def describe_retrieval(concept_id, solver_id, retriever: TBoxRetriever) -> str:
    """
    Human-readable description of what was retrieved.
    Useful for verbose pipeline output.
    """
    parts = []

    if concept_id:
        concept = retriever.get_concept_info(concept_id)
        if concept:
            parts.append(f"Concept: {concept['name']}")

    if solver_id:
        solver = retriever.get_solver_info(solver_id)
        if solver:
            parts.append(f"Solver: {solver['name']} ({solver.get('tool', 'unknown')})")

    if not parts:
        parts.append("No T-box match — oracle invocation needed")

    return " | ".join(parts)
