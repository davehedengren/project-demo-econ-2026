"""
In-memory store for occupation data with search and filter capabilities.
"""

from dataclasses import dataclass
from typing import Optional

from .data_loader import Occupation, load_occupations


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
    """In-memory store for BLS occupation data."""

    def __init__(self, xml_path: str):
        self.occupations: list[Occupation] = load_occupations(xml_path)
        self._by_code: dict[str, Occupation] = {occ.code: occ for occ in self.occupations}
        self._by_title_lower: dict[str, Occupation] = {occ.title.lower(): occ for occ in self.occupations}

        # Build indexes
        self.categories: set[str] = {occ.category for occ in self.occupations}
        self.education_levels: set[str] = {occ.entry_level_education for occ in self.occupations if occ.entry_level_education}
        self.outlook_categories: set[str] = {occ.employment_outlook for occ in self.occupations if occ.employment_outlook}

    @property
    def count(self) -> int:
        return len(self.occupations)

    @property
    def category_count(self) -> int:
        return len(self.categories)

    def get_by_code(self, code: str) -> Optional[Occupation]:
        """Get occupation by its code."""
        return self._by_code.get(code)

    def get_by_title(self, title: str) -> Optional[Occupation]:
        """Get occupation by exact title (case-insensitive)."""
        return self._by_title_lower.get(title.lower())

    def search(self, query: str, limit: int = 10) -> list[OccupationSummary]:
        """
        Search occupations by keyword in title and description.
        Returns ranked results.
        """
        query_lower = query.lower()
        query_words = query_lower.split()

        results = []
        for occ in self.occupations:
            title_lower = occ.title.lower()
            desc_lower = occ.description.lower()
            what_lower = occ.what_they_do.lower()

            # Score based on matches
            score = 0

            # Exact title match
            if query_lower == title_lower:
                score += 100

            # Title contains full query
            elif query_lower in title_lower:
                score += 50

            # Title contains query words
            for word in query_words:
                if word in title_lower:
                    score += 20

            # Description contains query
            if query_lower in desc_lower:
                score += 10

            # What they do contains query words
            for word in query_words:
                if word in what_lower:
                    score += 5

            if score > 0:
                results.append((score, occ))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)

        return [
            OccupationSummary(
                code=occ.code,
                title=occ.title,
                description=occ.description,
                category=occ.category,
                median_pay_annual=occ.median_pay_annual,
                entry_level_education=occ.entry_level_education,
                employment_outlook=occ.employment_outlook,
            )
            for _, occ in results[:limit]
        ]

    def filter(
        self,
        categories: Optional[list[str]] = None,
        min_salary: Optional[int] = None,
        max_salary: Optional[int] = None,
        education_levels: Optional[list[str]] = None,
        outlook: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[OccupationSummary]:
        """
        Filter occupations by multiple criteria.
        """
        results = []

        for occ in self.occupations:
            # Category filter
            if categories and occ.category not in categories:
                continue

            # Salary filter
            if min_salary and (occ.median_pay_annual is None or occ.median_pay_annual < min_salary):
                continue
            if max_salary and (occ.median_pay_annual is None or occ.median_pay_annual > max_salary):
                continue

            # Education filter (partial match)
            if education_levels:
                edu_match = False
                for edu in education_levels:
                    if edu.lower() in occ.entry_level_education.lower():
                        edu_match = True
                        break
                if not edu_match:
                    continue

            # Outlook filter (partial match)
            if outlook:
                outlook_match = False
                for out in outlook:
                    if out.lower() in occ.employment_outlook.lower():
                        outlook_match = True
                        break
                if not outlook_match:
                    continue

            results.append(OccupationSummary(
                code=occ.code,
                title=occ.title,
                description=occ.description,
                category=occ.category,
                median_pay_annual=occ.median_pay_annual,
                entry_level_education=occ.entry_level_education,
                employment_outlook=occ.employment_outlook,
            ))

            if len(results) >= limit:
                break

        return results

    def get_details(self, code: str) -> Optional[dict]:
        """Get full occupation details as a dictionary."""
        occ = self.get_by_code(code)
        if not occ:
            return None

        return {
            "code": occ.code,
            "title": occ.title,
            "description": occ.description,
            "category": occ.category,
            "soc_codes": occ.soc_codes,
            "median_pay_annual": occ.median_pay_annual,
            "median_pay_hourly": occ.median_pay_hourly,
            "entry_level_education": occ.entry_level_education,
            "work_experience": occ.work_experience,
            "on_the_job_training": occ.on_the_job_training,
            "number_of_jobs": occ.number_of_jobs,
            "employment_outlook": occ.employment_outlook,
            "employment_openings": occ.employment_openings,
            "what_they_do": occ.what_they_do[:2000] if occ.what_they_do else "",  # Truncate for context
            "work_environment": occ.work_environment[:1000] if occ.work_environment else "",
            "how_to_become_one": occ.how_to_become_one[:1500] if occ.how_to_become_one else "",
            "pay_details": occ.pay_details[:500] if occ.pay_details else "",
            "job_outlook_details": occ.job_outlook_details[:1000] if occ.job_outlook_details else "",
        }

    def get_similar(self, code: str) -> list[dict]:
        """Get similar occupations for a given occupation code."""
        occ = self.get_by_code(code)
        if not occ:
            return []

        return [
            {
                "title": title,
                "code": sim_code,
                "education": education,
                "salary": salary,
            }
            for title, sim_code, education, salary in occ.similar_occupations
        ]

    def get_soc_codes(self, code: str) -> list[str]:
        """Get SOC codes for an occupation."""
        occ = self.get_by_code(code)
        if not occ:
            return []
        return occ.soc_codes

    def get_stats(self) -> dict:
        """Get statistics about the loaded data."""
        return {
            "total_occupations": len(self.occupations),
            "categories": sorted(self.categories),
            "category_count": len(self.categories),
            "education_levels": sorted(self.education_levels),
            "outlook_categories": sorted(self.outlook_categories),
        }
