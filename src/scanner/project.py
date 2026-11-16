"""Repository plus the CPG and the Python source index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scanner.facts import Limits
from scanner.overlay import Overlay
from scanner.source_index import SourceIndex


@dataclass
class Project:
    repo: Path
    index: SourceIndex
    overlay: Overlay
    limits: Limits
