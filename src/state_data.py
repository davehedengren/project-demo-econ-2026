"""
State-level employment and wage data from BLS OEWS.
"""

from pathlib import Path
from typing import Optional

import pandas as pd


class StateDataStore:
    """Store for state-level employment and wage data."""

    def __init__(self, xlsx_path: str):
        self.df = pd.read_excel(xlsx_path)
        # Filter to state-level data only (AREA_TYPE == 2)
        self.states_df = self.df[self.df['AREA_TYPE'] == 2].copy()

        # Get list of valid states
        self.states = sorted(self.states_df['AREA_TITLE'].unique().tolist())

        # Build SOC code index for fast lookup
        self._by_soc: dict[str, pd.DataFrame] = {}
        for soc in self.states_df['OCC_CODE'].unique():
            self._by_soc[soc] = self.states_df[self.states_df['OCC_CODE'] == soc]

    def get_state_data(self, soc_code: str, state: str) -> Optional[dict]:
        """Get employment and wage data for a specific occupation in a state."""
        if soc_code not in self._by_soc:
            return None

        df = self._by_soc[soc_code]
        state_row = df[df['AREA_TITLE'].str.lower() == state.lower()]

        if state_row.empty:
            return None

        row = state_row.iloc[0]

        return {
            "state": row['AREA_TITLE'],
            "occupation": row['OCC_TITLE'],
            "soc_code": soc_code,
            "employment": self._safe_int(row.get('TOT_EMP')),
            "median_annual": self._safe_int(row.get('A_MEDIAN')),
            "median_hourly": self._safe_float(row.get('H_MEDIAN')),
            "mean_annual": self._safe_int(row.get('A_MEAN')),
            "pct10_annual": self._safe_int(row.get('A_PCT10')),
            "pct25_annual": self._safe_int(row.get('A_PCT25')),
            "pct75_annual": self._safe_int(row.get('A_PCT75')),
            "pct90_annual": self._safe_int(row.get('A_PCT90')),
            "location_quotient": self._safe_float(row.get('LOC_QUOTIENT')),
            "jobs_per_1000": self._safe_float(row.get('JOBS_1000')),
        }

    def get_occupation_by_state(self, soc_code: str) -> list[dict]:
        """Get data for an occupation across all states, sorted by employment."""
        if soc_code not in self._by_soc:
            return []

        df = self._by_soc[soc_code]
        results = []

        for _, row in df.iterrows():
            emp = self._safe_int(row.get('TOT_EMP'))
            if emp is None:
                continue
            results.append({
                "state": row['AREA_TITLE'],
                "employment": emp,
                "median_annual": self._safe_int(row.get('A_MEDIAN')),
                "location_quotient": self._safe_float(row.get('LOC_QUOTIENT')),
            })

        # Sort by employment descending
        results.sort(key=lambda x: x['employment'] or 0, reverse=True)
        return results

    def compare_states(self, soc_code: str, states: list[str]) -> list[dict]:
        """Compare an occupation across multiple specified states."""
        results = []
        for state in states:
            data = self.get_state_data(soc_code, state)
            if data:
                results.append(data)
        return results

    def find_state(self, query: str) -> Optional[str]:
        """Find a state by partial name match."""
        query_lower = query.lower()
        for state in self.states:
            if query_lower in state.lower():
                return state
        return None

    def _safe_int(self, val) -> Optional[int]:
        """Safely convert to int, handling NaN and special values."""
        if pd.isna(val):
            return None
        try:
            if isinstance(val, str):
                val = val.replace(',', '').replace('*', '').replace('#', '')
                if not val or val == '**':
                    return None
            return int(float(val))
        except (ValueError, TypeError):
            return None

    def _safe_float(self, val) -> Optional[float]:
        """Safely convert to float, handling NaN and special values."""
        if pd.isna(val):
            return None
        try:
            if isinstance(val, str):
                val = val.replace(',', '').replace('*', '').replace('#', '')
                if not val or val == '**':
                    return None
            return round(float(val), 2)
        except (ValueError, TypeError):
            return None


def load_state_data(xlsx_path: str | Path | None = None) -> StateDataStore:
    """Load state data from xlsx file."""
    if xlsx_path is None:
        xlsx_path = Path(__file__).parent.parent / "data" / "state_M2024_dl.xlsx"
    return StateDataStore(str(xlsx_path))
