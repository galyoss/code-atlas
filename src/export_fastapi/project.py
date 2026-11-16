"""Repository plus the CPG and the Python source index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from export_fastapi.facts import Limits
from export_fastapi.overlay import Overlay
from export_fastapi.source_index import SourceIndex


@dataclass
class Project:
    repo: Path
    index: SourceIndex
    overlay: Overlay
    limits: Limits
