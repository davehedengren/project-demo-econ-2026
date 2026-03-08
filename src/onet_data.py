"""
SQLite-backed O*NET data for skills, knowledge, and interest matching.
Data source: O*NET 30.2 Database (U.S. Department of Labor)
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

# Holland Code descriptions for interest matching
HOLLAND_CODES = {
    "Realistic": "Hands-on, practical work with tools, machines, plants, or animals",
    "Investigative": "Research, analysis, and solving complex problems",
    "Artistic": "Creative expression, design, and working with ideas",
    "Social": "Helping, teaching, counseling, and working with people",
    "Enterprising": "Leading, persuading, and managing business activities",
    "Conventional": "Organizing, managing data, and following procedures",
}


class OnetStore:
    """SQLite-backed store for O*NET skills, knowledge, and interests."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Cache skill/knowledge names (small lists, used in tool definitions)
        self._skill_names = [r[0] for r in self._conn.execute(
            "SELECT DISTINCT skill_name FROM onet_skills ORDER BY skill_name"
        ).fetchall()]
        self._knowledge_names = [r[0] for r in self._conn.execute(
            "SELECT DISTINCT area_name FROM onet_knowledge ORDER BY area_name"
        ).fetchall()]

        count = self._conn.execute("SELECT COUNT(*) FROM onet_occupations").fetchone()[0]
        logger.info("O*NET store ready: %d occupations, %d skills, %d knowledge areas",
                     count, len(self._skill_names), len(self._knowledge_names))

    def _find_onet_codes(self, soc_codes: list[str]) -> list[str]:
        """Find O*NET codes matching BLS SOC codes."""
        if not soc_codes:
            return []
        placeholders = ",".join("?" * len(soc_codes))
        rows = self._conn.execute(f"""
            SELECT onet_soc_code FROM onet_occupations
            WHERE soc6 IN ({placeholders})
        """, soc_codes).fetchall()
        return [r[0] for r in rows]

    def get_skills(self, soc_codes: list[str], top_n: int = 10) -> list[dict]:
        """Get top skills for an occupation by importance."""
        onet_codes = self._find_onet_codes(soc_codes)
        if not onet_codes:
            return []

        placeholders = ",".join("?" * len(onet_codes))
        rows = self._conn.execute(f"""
            SELECT skill_name as skill, ROUND(AVG(importance), 2) as importance
            FROM onet_skills
            WHERE onet_soc_code IN ({placeholders})
            GROUP BY skill_name
            ORDER BY importance DESC
            LIMIT ?
        """, onet_codes + [top_n]).fetchall()

        return [dict(r) for r in rows]

    def get_knowledge(self, soc_codes: list[str], top_n: int = 10) -> list[dict]:
        """Get top knowledge areas for an occupation by importance."""
        onet_codes = self._find_onet_codes(soc_codes)
        if not onet_codes:
            return []

        placeholders = ",".join("?" * len(onet_codes))
        rows = self._conn.execute(f"""
            SELECT area_name as area, ROUND(AVG(importance), 2) as importance
            FROM onet_knowledge
            WHERE onet_soc_code IN ({placeholders})
            GROUP BY area_name
            ORDER BY importance DESC
            LIMIT ?
        """, onet_codes + [top_n]).fetchall()

        return [dict(r) for r in rows]

    def get_interests(self, soc_codes: list[str]) -> list[dict]:
        """Get Holland Code interest profile for an occupation."""
        onet_codes = self._find_onet_codes(soc_codes)
        if not onet_codes:
            return []

        placeholders = ",".join("?" * len(onet_codes))
        rows = self._conn.execute(f"""
            SELECT interest_name as interest, ROUND(AVG(score), 2) as score
            FROM onet_interests
            WHERE onet_soc_code IN ({placeholders})
            GROUP BY interest_name
            ORDER BY score DESC
        """, onet_codes).fetchall()

        return [{
            "interest": r["interest"],
            "score": r["score"],
            "description": HOLLAND_CODES.get(r["interest"], ""),
        } for r in rows]

    def find_by_skills(self, skill_names: list[str], top_n: int = 15) -> list[dict]:
        """Find occupations that most value the given skills."""
        if not skill_names:
            return []

        placeholders = ",".join("?" * len(skill_names))
        rows = self._conn.execute(f"""
            SELECT s.onet_soc_code, o.soc6 as soc_code, o.title,
                   ROUND(SUM(s.importance), 2) as match_score
            FROM onet_skills s
            JOIN onet_occupations o ON s.onet_soc_code = o.onet_soc_code
            WHERE LOWER(s.skill_name) IN ({','.join('LOWER(?)' for _ in skill_names)})
            GROUP BY s.onet_soc_code
            ORDER BY match_score DESC
            LIMIT ?
        """, skill_names + [top_n]).fetchall()

        return [dict(r) for r in rows]

    def find_by_interests(self, interest_profile: dict[str, float], top_n: int = 15) -> list[dict]:
        """
        Find occupations matching a Holland Code interest profile.
        interest_profile: e.g., {"Investigative": 7, "Social": 5}
        """
        if not interest_profile:
            return []

        # Build a weighted score query
        # For each occupation: SUM(user_weight * occupation_score) for each interest
        case_parts = []
        params = []
        for interest, weight in interest_profile.items():
            case_parts.append(f"CASE WHEN i.interest_name = ? THEN i.score * ? ELSE 0 END")
            params.extend([interest, weight])

        score_expr = " + ".join(case_parts)

        rows = self._conn.execute(f"""
            SELECT i.onet_soc_code, o.soc6 as soc_code, o.title,
                   ROUND(SUM({score_expr}), 1) as match_score
            FROM onet_interests i
            JOIN onet_occupations o ON i.onet_soc_code = o.onet_soc_code
            GROUP BY i.onet_soc_code
            ORDER BY match_score DESC
            LIMIT ?
        """, params + [top_n]).fetchall()

        return [dict(r) for r in rows]

    def get_all_skill_names(self) -> list[str]:
        return self._skill_names

    def get_all_knowledge_names(self) -> list[str]:
        return self._knowledge_names


def load_onet_data(db_path: str) -> OnetStore:
    """Load O*NET data from SQLite database."""
    return OnetStore(db_path)
