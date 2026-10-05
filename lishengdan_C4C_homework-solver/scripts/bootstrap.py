#!/usr/bin/env python3
"""
Dependency bootstrap for the homework solver skill.

Auto-installs required Python packages if missing. Called at the top of
pipeline.py so the skill runs without a manual `pip install` step.

Also provides SKILL_ROOT — the absolute path to the skill's root directory,
used by all modules to resolve relative paths to domain_skills/, oracles/,
solver_templates/, etc.

Usage:
    from bootstrap import ensure_dependencies, SKILL_ROOT
"""

import subprocess
import sys
from pathlib import Path

# ── Skill root resolution ────────────────────────────────
# SKILL_ROOT = parent of scripts/ = the skill's top-level directory.
# All relative paths (domain_skills/, oracles/, solver_templates/)
# are resolved from here, regardless of where the user invokes
# the pipeline from.
SKILL_ROOT = Path(__file__).resolve().parent.parent

# ── Required packages ────────────────────────────────────
# (import_name, pip_name, min_version_or_None)
REQUIRED = [
    ("sympy", "sympy", "1.12"),
    ("yaml", "pyyaml", "6.0"),
]

# Optional packages — installed only if the user requests features
# that need them (PDF ingestion, OCR, etc.)
OPTIONAL = [
    ("pdfplumber", "pdfplumber", None),
    ("docx", "python-docx", None),
    ("PIL", "Pillow", None),
]


def _try_import(module_name: str) -> bool:
    """Check if a module is importable."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _install(pip_name: str, min_version: str = None):
    """Install a package via pip."""
    pkg = f"{pip_name}>={min_version}" if min_version else pip_name
    print(f"   📦 Installing {pkg}...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg,
             "--break-system-packages", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        # Retry without --break-system-packages (older pip)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except subprocess.CalledProcessError:
            return False


def ensure_dependencies(include_optional: bool = False):
    """
    Check and auto-install required packages.

    Called once at pipeline startup. Skips packages that are already
    installed. Returns list of packages that were installed.
    """
    installed = []
    missing = []

    for import_name, pip_name, min_ver in REQUIRED:
        if not _try_import(import_name):
            missing.append((import_name, pip_name, min_ver))

    if not missing:
        return installed  # Everything already available

    print("🔧 Auto-installing missing dependencies...")
    for import_name, pip_name, min_ver in missing:
        if _install(pip_name, min_ver):
            installed.append(pip_name)
            print(f"      ✅ {pip_name}")
        else:
            print(f"      ❌ Failed to install {pip_name}")
            print(f"         Please run: pip install {pip_name}")
            sys.exit(1)

    if include_optional:
        for import_name, pip_name, min_ver in OPTIONAL:
            if not _try_import(import_name):
                if _install(pip_name, min_ver):
                    installed.append(pip_name)

    return installed


def get_domain_skills_dir() -> Path:
    """Return absolute path to domain_skills/ directory."""
    return SKILL_ROOT / "domain_skills"


def get_solver_templates_dir() -> Path:
    """Return absolute path to solver_templates/ directory."""
    return SKILL_ROOT / "solver_templates"


def get_oracles_dir() -> Path:
    """Return absolute path to oracles/ directory."""
    return SKILL_ROOT / "oracles"


def get_references_dir() -> Path:
    """Return absolute path to references/ directory."""
    return SKILL_ROOT / "references"
