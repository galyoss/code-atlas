"""The checks a review pass runs.

v1 registers IDOR only. A later vulnerability is a new check added here.
The runner does not change.
"""

from __future__ import annotations

from review.idor import IDOR


def registered_checks() -> tuple:
    return (IDOR,)
