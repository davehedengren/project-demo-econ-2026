"""
SQLite-backed store for BLS occupation data with search and filter capabilities.
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class OccupationSummary:
    """Lightweight occupation summary for search results."""
    code: str
    title: str
    description: str
    category: str
    median_pay_annual: Optional[int]
    entry_level_education: str
    employment_outlook: str


class OccupationStore:
    """SQLite-backed store for BLS occupation data."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Cache lightweight metadata
        self._count = self._conn.execute("SELECT COUNT(*) FROM occupations").fetchone()[0]
        self._categories = {r[0] for r in self._conn.execute(
            "SELECT DISTINCT category FROM occupations WHERE category != ''"
        ).fetchall()}
        self._education_levels = {r[0] for r in self._conn.execute(
            "SELECT DISTINCT entry_level_education FROM occupations WHERE entry_level_education != ''"
        ).fetchall()}
        self._outlook_categories = {r[0] for r in self._conn.execute(
            "SELECT DISTINCT employment_outlook FROM occupations WHERE employment_outlook != ''"
        ).fetchall()}

    @property
    def count(self) -> int:
        return self._count

    @property
    def category_count(self) -> int:
        return len(self._categories)

    @property
    def categories(self) -> set[str]:
        return self._categories

    @property
    def education_levels(self) -> set[str]:
        return self._education_levels

    @property
    def outlook_categories(self) -> set[str]:
        return self._outlook_categories

    def get_all_for_api(self) -> list[dict]:
        """Get all occupations with fields needed for the /api/occupations endpoint."""
        rows = self._conn.execute("""
            SELECT code, title, description, category, median_pay_annual,
                   entry_level_education, employment_outlook, employment_outlook_value,
                   number_of_jobs, employment_openings, url
            FROM occupations
            ORDER BY COALESCE(number_of_jobs, 0) DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_by_code(self, code: str) -> Optional[dict]:
        """Get occupation by its code. Returns a dict with all fields."""
        row = self._conn.execute(
            "SELECT * FROM occupations WHERE code = ?", (code,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["soc_codes"] = self.get_soc_codes(code)
        return result

    def search(self, query: str, limit: int = 10) -> list[OccupationSummary]:
        """Search occupations by keyword with relevance scoring."""
        query_lower = query.lower()
        query_words = query_lower.split()

        # Fetch only the columns needed for scoring
        rows = self._conn.execute("""
            SELECT code, title, description, category, median_pay_annual,
                   entry_level_education, employment_outlook, what_they_do
            FROM occupations
        """).fetchall()

        results = []
        for row in rows:
            title_lower = (row["title"] or "").lower()
            desc_lower = (row["description"] or "").lower()
            what_lower = (row["what_they_do"] or "").lower()

            score = 0
            if query_lower == title_lower:
                score += 100
            elif query_lower in title_lower:
                score += 50

            for word in query_words:
                if word in title_lower:
                    score += 20
                if word in desc_lower:
                    score += 10
                if word in what_lower:
                    score += 5

            if score > 0:
                results.append((score, OccupationSummary(
                    code=row["code"],
                    title=row["title"],
                    description=row["description"],
                    category=row["category"],
                    median_pay_annual=row["median_pay_annual"],
                    entry_level_education=row["entry_level_education"],
                    employment_outlook=row["employment_outlook"],
                )))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def filter(
        self,
        categories: Optional[list[str]] = None,
        min_salary: Optional[int] = None,
        max_salary: Optional[int] = None,
        education_levels: Optional[list[str]] = None,
        outlook: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[OccupationSummary]:
        """Filter occupations by criteria using SQL."""
        conditions = []
        params = []

        if categories:
            placeholders = ",".join("?" * len(categories))
            conditions.append(f"category IN ({placeholders})")
            params.extend(categories)

        if min_salary is not None:
            conditions.append("median_pay_annual >= ?")
            params.append(min_salary)

        if max_salary is not None:
            conditions.append("median_pay_annual <= ?")
            params.append(max_salary)

        if education_levels:
            edu_conditions = []
            for edu in education_levels:
                edu_conditions.append("LOWER(entry_level_education) LIKE ?")
                params.append(f"%{edu.lower()}%")
            conditions.append(f"({' OR '.join(edu_conditions)})")

        if outlook:
            out_conditions = []
            for out in outlook:
                out_conditions.append("LOWER(employment_outlook) LIKE ?")
                params.append(f"%{out.lower()}%")
            conditions.append(f"({' OR '.join(out_conditions)})")

        where = " AND ".join(conditions) if conditions else "1=1"

        rows = self._conn.execute(f"""
            SELECT code, title, description, category, median_pay_annual,
                   entry_level_education, employment_outlook
            FROM occupations
            WHERE {where}
            LIMIT ?
        """, params + [limit]).fetchall()

        return [OccupationSummary(
            code=r["code"], title=r["title"], description=r["description"],
            category=r["category"], median_pay_annual=r["median_pay_annual"],
            entry_level_education=r["entry_level_education"],
            employment_outlook=r["employment_outlook"],
        ) for r in rows]

    def get_details(self, code: str) -> Optional[dict]:
        """Get full occupation details as a dictionary."""
        row = self._conn.execute(
            "SELECT * FROM occupations WHERE code = ?", (code,)
        ).fetchone()
        if not row:
            return None

        result = dict(row)
        result["soc_codes"] = self.get_soc_codes(code)

        # Truncate long text fields for LLM context
        for field, max_len in [("what_they_do", 2000), ("work_environment", 1000),
                                ("how_to_become_one", 1500), ("job_outlook_details", 1000)]:
            if result.get(field):
                result[field] = result[field][:max_len]

        return result

    def get_similar(self, code: str) -> list[dict]:
        """Get similar occupations for a given code."""
        rows = self._conn.execute("""
            SELECT similar_title as title, similar_code as code, education, salary
            FROM similar_occupations
            WHERE occupation_code = ?
        """, (code,)).fetchall()
        return [dict(r) for r in rows]

    def get_soc_codes(self, code: str) -> list[str]:
        """Get SOC codes for an occupation."""
        rows = self._conn.execute(
            "SELECT soc_code FROM occupation_soc_codes WHERE occupation_code = ?",
            (code,),
        ).fetchall()
        return [r[0] for r in rows]

    def get_by_soc_code(self, soc_code: str) -> Optional[dict]:
        """Get BLS occupation matching a SOC code."""
        row = self._conn.execute("""
            SELECT o.code, o.title, o.median_pay_annual
            FROM occupations o
            JOIN occupation_soc_codes s ON o.code = s.occupation_code
            WHERE s.soc_code = ?
            LIMIT 1
        """, (soc_code,)).fetchone()
        return dict(row) if row else None

    def get_stats(self) -> dict:
        """Get statistics about the loaded data."""
        return {
            "total_occupations": self._count,
            "categories": sorted(self._categories),
            "category_count": len(self._categories),
            "education_levels": sorted(self._education_levels),
            "outlook_categories": sorted(self._outlook_categories),
        }
