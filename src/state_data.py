"""
SQLite-backed state-level employment and wage data from BLS OEWS.
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


class StateDataStore:
    """SQLite-backed store for state-level employment and wage data."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Cache state list
        self._states = [r[0] for r in self._conn.execute(
            "SELECT DISTINCT state FROM state_wages ORDER BY state"
        ).fetchall()]

    @property
    def states(self) -> list[str]:
        return self._states

    def get_state_data(self, soc_code: str, state: str) -> Optional[dict]:
        """Get employment and wage data for a specific occupation in a state."""
        row = self._conn.execute("""
            SELECT state, occupation_title as occupation, soc_code,
                   employment, median_annual, median_hourly, mean_annual,
                   pct10_annual, pct25_annual, pct75_annual, pct90_annual,
                   location_quotient, jobs_per_1000
            FROM state_wages
            WHERE soc_code = ? AND LOWER(state) = LOWER(?)
        """, (soc_code, state)).fetchone()

        return dict(row) if row else None

    def get_occupation_by_state(self, soc_code: str) -> list[dict]:
        """Get data for an occupation across all states, sorted by employment."""
        rows = self._conn.execute("""
            SELECT state, employment, median_annual, location_quotient
            FROM state_wages
            WHERE soc_code = ? AND employment IS NOT NULL
            ORDER BY employment DESC
        """, (soc_code,)).fetchall()

        return [dict(r) for r in rows]

    def find_state(self, query: str) -> Optional[str]:
        """Find a state by partial name match."""
        query_lower = query.lower()
        for state in self._states:
            if query_lower in state.lower():
                return state
        return None


def load_state_data(db_path: str) -> StateDataStore:
    """Load state data from SQLite database."""
    return StateDataStore(db_path)
