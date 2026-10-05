#!/usr/bin/env python3
"""
T-box Classifier: Map problems to concept nodes.

Loads the domain skill YAML (T-box) and uses its classification rules
to map each parsed problem to concept node(s). Classification is
priority-ordered: higher priority rules are checked first.

This replaces the hard-coded classify_problem() in parse_problems.py.

Usage:
    from classify import TBoxClassifier
    classifier = TBoxClassifier("domain_skills/calculus_limits.yaml")
    concept_id, solver_id = classifier.classify(problem)
"""

import re
import yaml
from pathlib import Path
from typing import Optional

try:
    from bootstrap import SKILL_ROOT
except ImportError:
    # Fallback if bootstrap not on path (e.g., running classify.py directly)
    SKILL_ROOT = Path(__file__).resolve().parent.parent


class TBoxClassifier:
    """
    Classify problems against T-box classification rules.

    The T-box YAML defines priority-ordered rules. Each rule has:
      - priority: int (higher = checked first)
      - pattern: dict of feature conditions
      - maps_to: concept node ID (or null)
      - solver: solver template ID (or null)
    """

    def __init__(self, tbox_path: str = None):
        """Load T-box from YAML file."""
        if tbox_path is None:
            # Default: look for calculus_limits.yaml relative to skill root
            tbox_path = SKILL_ROOT / "domain_skills" / "calculus_limits.yaml"

        self.tbox_path = Path(tbox_path)
        self.tbox = {}
        self.rules = []
        self.concepts = {}
        self.solution_methods = {}

        if self.tbox_path.exists():
            self._load(self.tbox_path)

    def _load(self, path: Path):
        """Parse the T-box YAML."""
        with open(path, "r", encoding="utf-8") as f:
            self.tbox = yaml.safe_load(f)

        # Index concepts by ID
        for concept in self.tbox.get("concepts", []):
            self.concepts[concept["id"]] = concept

        # Index solution methods by ID
        for method in self.tbox.get("solution_methods", []):
            self.solution_methods[method["id"]] = method

        # Load and sort classification rules by priority (descending)
        self.rules = sorted(
            self.tbox.get("classification_rules", []),
            key=lambda r: r.get("priority", 0),
            reverse=True,
        )

    def classify(self, problem: dict) -> tuple:
        """
        Classify a problem against T-box rules.

        Args:
            problem: dict with keys: text, math_expressions, sub_problems

        Returns:
            (concept_id, solver_id) — or (None, None) if no rule matches
        """
        # Extract features from the problem
        features = self._extract_features(problem)

        # Walk rules in priority order
        for rule in self.rules:
            if self._rule_matches(rule, features):
                return (rule.get("maps_to"), rule.get("solver"))

        return (None, None)

    def classify_with_reason(self, problem: dict) -> dict:
        """
        Classify and return full match info.

        Returns:
            {
                "concept_id": str or None,
                "solver_id": str or None,
                "priority": int,
                "reason": str,
                "features": dict
            }
        """
        features = self._extract_features(problem)

        for rule in self.rules:
            if self._rule_matches(rule, features):
                return {
                    "concept_id": rule.get("maps_to"),
                    "solver_id": rule.get("solver"),
                    "priority": rule.get("priority", 0),
                    "reason": rule.get("reason", f"Matched rule at priority {rule.get('priority')}"),
                    "features": features,
                }

        return {
            "concept_id": None,
            "solver_id": None,
            "priority": 0,
            "reason": "No classification rule matched",
            "features": features,
        }

    def get_concept(self, concept_id: str) -> Optional[dict]:
        """Look up a concept by ID."""
        return self.concepts.get(concept_id)

    def get_solver_method(self, solver_id: str) -> Optional[dict]:
        """Look up a solution method by ID."""
        return self.solution_methods.get(solver_id)

    # ──────────────────────────────────────────────
    # Feature extraction
    # ──────────────────────────────────────────────

    def _extract_features(self, problem: dict) -> dict:
        """
        Extract classifiable features from a problem.

        Features are the "observation layer" — what the classifier can see
        about the problem before choosing a concept node.
        """
        text = problem.get("text", "")
        math_exprs = problem.get("math_expressions", [])
        subs = problem.get("sub_problems", [])

        # Combine main text + sub-problem text for keyword matching
        all_text = text
        for sub in subs:
            all_text += " " + sub.get("text", "")

        text_lower = all_text.lower()
        latex_strs = [e.get("latex", "") for e in math_exprs]
        sub_latex = []
        for sub in subs:
            sub_latex.extend(e.get("latex", "") for e in sub.get("math_expressions", []))

        return {
            "text_lower": text_lower,
            "text_raw": text,
            "latex_strs": latex_strs,
            "sub_latex": sub_latex,
            "all_latex": latex_strs + sub_latex,
            "has_function_definition": self._has_function_definition(text, math_exprs),
            "has_abstract_function": self._has_abstract_function(math_exprs + [
                e for sub in subs for e in sub.get("math_expressions", [])
            ]),
            "has_limit_expression": self._has_limit_expression(latex_strs + sub_latex),
            "has_sub_problems": len(subs) > 0,
            "sub_count": len(subs),
        }

    def _has_function_definition(self, text: str, math_exprs: list) -> bool:
        """Check if the problem defines a concrete function like f(x) = x² or y = 2x."""
        for expr_info in math_exprs:
            latex_str = expr_info.get("latex", "")
            # f(x) = expr
            if re.match(r"f\s*\(\s*x\s*\)\s*=\s*.+", latex_str):
                return True
            # y = expr (with actual expression, not just "y = f(x)")
            m = re.match(r"y\s*=\s*(.+)", latex_str)
            if m and not re.search(r"[fgh]\s*\(", m.group(1)):
                return True
        return False

    def _has_abstract_function(self, math_exprs: list) -> bool:
        """Check for abstract function symbols like f(x), g(x)."""
        for expr_info in math_exprs:
            latex_str = expr_info.get("latex", "") if isinstance(expr_info, dict) else ""
            if re.search(r"[fgh]\s*\([a-z]\)", latex_str):
                return True
        return False

    def _has_limit_expression(self, latex_strs: list) -> bool:
        """Check if any expression contains \\lim."""
        for ls in latex_strs:
            if "\\lim" in ls or "lim_" in ls:
                return True
        return False

    # ──────────────────────────────────────────────
    # Rule matching
    # ──────────────────────────────────────────────

    def _rule_matches(self, rule: dict, features: dict) -> bool:
        """Check if a classification rule matches the extracted features."""
        pattern = rule.get("pattern", {})

        for condition_key, condition_value in pattern.items():
            if not self._check_condition(condition_key, condition_value, features):
                return False

        return True

    def _check_condition(self, key: str, value, features: dict) -> bool:
        """Evaluate a single condition against features."""

        if key == "text_contains":
            # value is a list of strings — at least one must appear in text
            text_lower = features["text_lower"]
            return any(kw.lower() in text_lower for kw in value)

        elif key == "has_function_definition":
            return features["has_function_definition"] == value

        elif key == "has_abstract_function":
            return features["has_abstract_function"] == value

        elif key == "has_limit_expression":
            return features["has_limit_expression"] == value

        elif key == "has_sub_problems":
            return features["has_sub_problems"] == value

        else:
            # Unknown condition — don't match (safe default)
            return False


# ──────────────────────────────────────────────
# Backward-compatible type mapping
# ──────────────────────────────────────────────
# Maps (concept_id, solver_id) to the legacy type strings
# used by solve.py's SOLVERS dict. This bridge lets us
# incrementally adopt the T-box without rewriting all solvers.

SOLVER_TYPE_MAP = {
    "ed_notation_solver": "epsilon_delta",
    "ed_computation_solver": "epsilon_delta",  # solve.py auto-detects function def
    "horizontal_tangent_solver": "tangent",
    "tangent_at_point_solver": "tangent",
    "limit_direct_computation": "limit",
    "limit_dne_proof": "limit",
    "limit_squeeze": "limit",
    "conceptual_limit_definitions": "conceptual",
    "conceptual_tangent_questions": "conceptual",
    "lhopital_solver": "limit",
    "newton_method_solver": "calculation",
    "implicit_diff_solver": "calculation",
    "critical_points_solver": "calculation",
}

# For problems with no concept match
CONCEPT_TYPE_MAP = {
    "epsilon_delta_notation": "epsilon_delta",
    "epsilon_delta_computation": "epsilon_delta",
    "horizontal_tangent": "tangent",
    "tangent_line": "tangent",
    "limit_definition": "limit",
    "limit_existence": "limit",
    "one_sided_limit": "limit",
    "squeeze_theorem": "limit",
    "continuity": "conceptual",
    "infinity_limit": "limit",
    "lhopital_rule": "limit",
    "discontinuity_types": "conceptual",
    "intermediate_value_theorem": "conceptual",
    "growth_hierarchy": "conceptual",
    "limit_algebraic_strategies": "limit",
    "epsilon_delta_nonlinear": "epsilon_delta",
    "newton_method": "calculation",
    "implicit_differentiation": "calculation",
    "critical_number": "calculation",
}


def classify_to_legacy_type(problem: dict, classifier: TBoxClassifier = None) -> str:
    """
    Classify a problem and return the legacy type string for solve.py.

    This is the bridge function: T-box classification → legacy solver routing.
    """
    if classifier is None:
        classifier = TBoxClassifier()

    concept_id, solver_id = classifier.classify(problem)

    # Try solver mapping first (more specific)
    if solver_id and solver_id in SOLVER_TYPE_MAP:
        return SOLVER_TYPE_MAP[solver_id]

    # Then concept mapping
    if concept_id and concept_id in CONCEPT_TYPE_MAP:
        return CONCEPT_TYPE_MAP[concept_id]

    # Fallback: no match → conceptual (will try template or return unsolved)
    if concept_id is None and solver_id is None:
        return "conceptual"

    return "calculation"
