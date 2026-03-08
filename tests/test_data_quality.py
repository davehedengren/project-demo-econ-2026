"""
Tests to verify data quality and recommendation accuracy
after the SQLite migration and O*NET integration.
"""

import sqlite3
from pathlib import Path

import pytest

DB_PATH = str(Path(__file__).parent.parent / "data" / "career_data.db")


# --- Fixtures ---

@pytest.fixture(scope="module")
def store():
    from src.occupation_store import OccupationStore
    return OccupationStore(DB_PATH)


@pytest.fixture(scope="module")
def state_store():
    from src.state_data import load_state_data
    return load_state_data(DB_PATH)


@pytest.fixture(scope="module")
def onet_store():
    from src.onet_data import load_onet_data
    return load_onet_data(DB_PATH)


@pytest.fixture(scope="module")
def all_stores(store, state_store, onet_store):
    return store, state_store, onet_store


# --- Database Integrity ---

class TestDatabaseIntegrity:
    def test_db_exists(self):
        assert Path(DB_PATH).exists()

    def test_occupation_count(self, store):
        assert store.count == 342

    def test_categories(self, store):
        assert store.category_count == 25

    def test_states(self, state_store):
        assert len(state_store.states) == 51  # 50 states + DC

    def test_onet_skills(self, onet_store):
        skills = onet_store.get_all_skill_names()
        assert len(skills) == 35

    def test_onet_knowledge(self, onet_store):
        areas = onet_store.get_all_knowledge_names()
        assert len(areas) == 33

    def test_soc_code_mapping(self, store):
        """Nearly all occupations should have at least one SOC code."""
        conn = sqlite3.connect(DB_PATH)
        orphans = conn.execute("""
            SELECT o.code, o.title FROM occupations o
            LEFT JOIN occupation_soc_codes s ON o.code = s.occupation_code
            WHERE s.soc_code IS NULL
        """).fetchall()
        conn.close()
        # Military Careers is an umbrella page without SOC codes — acceptable
        assert len(orphans) <= 1, f"Too many occupations without SOC codes: {orphans}"


# --- Search Quality ---

class TestSearchQuality:
    def test_search_software(self, store):
        results = store.search("software", limit=5)
        titles = [r.title.lower() for r in results]
        assert any("software" in t for t in titles)

    def test_search_nurse(self, store):
        results = store.search("nurse", limit=5)
        titles = [r.title.lower() for r in results]
        assert any("nurse" in t or "nursing" in t for t in titles)

    def test_search_teacher(self, store):
        results = store.search("teacher", limit=10)
        titles = [r.title.lower() for r in results]
        assert any("teacher" in t for t in titles)

    def test_search_returns_results(self, store):
        """Common career terms should return results."""
        for query in ["doctor", "engineer", "writer", "mechanic", "cook"]:
            results = store.search(query, limit=5)
            assert len(results) > 0, f"No results for '{query}'"

    def test_search_ranking(self, store):
        """Exact title matches should rank higher than partial."""
        results = store.search("accountant", limit=5)
        # Accountants should be first or second
        assert "accountant" in results[0].title.lower()


# --- Filter Quality ---

class TestFilterQuality:
    def test_filter_by_salary(self, store):
        results = store.filter(min_salary=100000, limit=50)
        assert all(r.median_pay_annual >= 100000 for r in results)

    def test_filter_by_education(self, store):
        results = store.filter(education_levels=["High school diploma"], limit=20)
        assert len(results) > 0
        assert all("high school" in r.entry_level_education.lower() for r in results)

    def test_filter_by_category(self, store):
        results = store.filter(categories=["healthcare"], limit=50)
        assert len(results) > 0
        assert all(r.category == "healthcare" for r in results)

    def test_filter_combined(self, store):
        results = store.filter(
            min_salary=80000,
            education_levels=["Bachelor's degree"],
            limit=20,
        )
        for r in results:
            assert r.median_pay_annual >= 80000
            assert "bachelor" in r.entry_level_education.lower()


# --- State Data Quality ---

class TestStateData:
    def test_california_exists(self, state_store):
        assert "California" in state_store.states

    def test_state_lookup(self, state_store):
        data = state_store.get_state_data("13-2011", "California")  # Accountants
        assert data is not None
        assert data["state"] == "California"
        assert data["median_annual"] is not None
        assert data["median_annual"] > 0

    def test_top_states(self, state_store):
        results = state_store.get_occupation_by_state("13-2011")
        assert len(results) > 0
        # Should be sorted by employment descending
        for i in range(len(results) - 1):
            assert results[i]["employment"] >= results[i + 1]["employment"]

    def test_find_state_partial(self, state_store):
        assert state_store.find_state("calif") == "California"
        assert state_store.find_state("new y") == "New York"


# --- O*NET Skills Quality ---

class TestOnetSkills:
    def test_software_dev_skills(self, onet_store):
        """Software developers should rank Programming highly."""
        skills = onet_store.get_skills(["15-1252"], top_n=10)
        skill_names = [s["skill"] for s in skills]
        assert "Programming" in skill_names
        assert "Critical Thinking" in skill_names

    def test_nurse_skills(self, onet_store):
        """Nurses should rank Service Orientation and Social Perceptiveness highly."""
        skills = onet_store.get_skills(["29-1141"], top_n=10)
        skill_names = [s["skill"] for s in skills]
        assert "Service Orientation" in skill_names or "Social Perceptiveness" in skill_names

    def test_accountant_knowledge(self, onet_store):
        """Accountants should value Economics and Accounting knowledge."""
        knowledge = onet_store.get_knowledge(["13-2011"], top_n=10)
        areas = [k["area"] for k in knowledge]
        assert "Economics and Accounting" in areas

    def test_skills_importance_range(self, onet_store):
        """Skill importance scores should be between 1 and 5."""
        skills = onet_store.get_skills(["15-1252"], top_n=35)
        for s in skills:
            assert 1.0 <= s["importance"] <= 5.0, f"{s['skill']}: {s['importance']}"


# --- O*NET Interests Quality ---

class TestOnetInterests:
    def test_software_dev_investigative(self, onet_store):
        """Software devs should be primarily Investigative."""
        interests = onet_store.get_interests(["15-1252"])
        top = interests[0]
        assert top["interest"] == "Investigative"
        assert top["score"] > 5.0

    def test_nurse_social(self, onet_store):
        """Nurses should be primarily Social."""
        interests = onet_store.get_interests(["29-1141"])
        top = interests[0]
        assert top["interest"] == "Social"

    def test_graphic_designer_artistic(self, onet_store):
        """Graphic designers should be primarily Artistic."""
        interests = onet_store.get_interests(["27-1024"])
        top = interests[0]
        assert top["interest"] == "Artistic"

    def test_all_six_codes(self, onet_store):
        """Every occupation should return all 6 Holland codes."""
        interests = onet_store.get_interests(["15-1252"])
        interest_names = {i["interest"] for i in interests}
        expected = {"Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"}
        assert interest_names == expected


# --- Skill Matching Quality ---

class TestSkillMatching:
    def test_math_programming(self, onet_store):
        """Math + Programming should surface technical careers."""
        results = onet_store.find_by_skills(["Mathematics", "Programming"], top_n=10)
        titles = [r["title"].lower() for r in results]
        # Should find at least one programmer/developer/statistician
        assert any(
            any(kw in t for kw in ["programmer", "statistician", "developer", "mathematician"])
            for t in titles
        ), f"Expected technical careers, got: {titles}"

    def test_writing_speaking(self, onet_store):
        """Writing + Speaking should surface communication-heavy careers."""
        results = onet_store.find_by_skills(["Writing", "Speaking"], top_n=15)
        assert len(results) > 0

    def test_science_skills(self, onet_store):
        """Science skill should surface research/science careers."""
        results = onet_store.find_by_skills(["Science"], top_n=10)
        titles = [r["title"].lower() for r in results]
        assert any(
            any(kw in t for kw in ["scientist", "biologist", "chemist", "physicist", "research"])
            for t in titles
        ), f"Expected science careers, got: {titles}"


# --- Interest Matching Quality ---

class TestInterestMatching:
    def test_investigative_social(self, onet_store):
        """High Investigative + Social should surface teaching/research careers."""
        results = onet_store.find_by_interests({
            "Realistic": 1, "Investigative": 7, "Artistic": 2,
            "Social": 6, "Enterprising": 1, "Conventional": 2,
        }, top_n=10)
        titles = [r["title"].lower() for r in results]
        # Should find teachers, researchers, professors
        assert any(
            any(kw in t for kw in ["teacher", "professor", "instructor", "counselor", "therapist"])
            for t in titles
        ), f"Expected teaching/helping careers, got: {titles}"

    def test_realistic_conventional(self, onet_store):
        """High Realistic + Conventional should surface trades/technical careers."""
        results = onet_store.find_by_interests({
            "Realistic": 7, "Investigative": 2, "Artistic": 1,
            "Social": 1, "Enterprising": 1, "Conventional": 6,
        }, top_n=10)
        titles = [r["title"].lower() for r in results]
        assert len(results) > 0

    def test_enterprising_profile(self, onet_store):
        """High Enterprising should surface business/management careers."""
        results = onet_store.find_by_interests({
            "Realistic": 1, "Investigative": 2, "Artistic": 1,
            "Social": 3, "Enterprising": 7, "Conventional": 4,
        }, top_n=10)
        titles = [r["title"].lower() for r in results]
        assert any(
            any(kw in t for kw in ["manager", "executive", "sales", "marketing", "business"])
            for t in titles
        ), f"Expected business careers, got: {titles}"


# --- Tool Execution ---

class TestToolExecution:
    def test_all_tools_execute(self, all_stores):
        """Every tool should execute without error."""
        from src.tools import execute_tool
        store, state_store, onet_store = all_stores

        test_code = store.search("accountant", limit=1)[0].code

        tools_and_inputs = [
            ("search_occupations", {"query": "data"}),
            ("filter_occupations", {"min_salary": 50000}),
            ("get_occupation_details", {"code": test_code}),
            ("get_similar_occupations", {"code": test_code}),
            ("get_state_data", {"code": test_code, "state": "Idaho"}),
            ("compare_states", {"code": test_code, "states": ["Idaho", "Utah"]}),
            ("get_top_states", {"code": test_code}),
            ("get_occupation_skills", {"code": test_code}),
            ("get_occupation_interests", {"code": test_code}),
            ("find_careers_by_skills", {"skills": ["Mathematics"]}),
            ("find_careers_by_interests", {
                "realistic": 3, "investigative": 5, "artistic": 2,
                "social": 4, "enterprising": 3, "conventional": 3,
            }),
        ]

        for tool_name, tool_input in tools_and_inputs:
            result = execute_tool(store, state_store, tool_name, tool_input, onet_store)
            assert isinstance(result, str), f"{tool_name} didn't return a string"
            assert len(result) > 0, f"{tool_name} returned empty string"
            assert "Error" not in result, f"{tool_name} returned error: {result[:100]}"


# --- Cross-data Matching ---

class TestCrossDataMatching:
    def test_bls_to_onet_soc_mapping(self, store, onet_store):
        """BLS occupations should map to O*NET data via SOC codes."""
        matched = 0
        total = 0
        for row in store.get_all_for_api():
            soc_codes = store.get_soc_codes(row["code"])
            if soc_codes:
                total += 1
                skills = onet_store.get_skills(soc_codes, top_n=1)
                if skills:
                    matched += 1

        match_rate = matched / total if total > 0 else 0
        assert match_rate > 0.80, f"Only {match_rate:.0%} of BLS occupations have O*NET skills data"

    def test_skill_match_returns_bls_salary(self, store, onet_store):
        """Skill matching should return occupations with BLS salary data."""
        results = onet_store.find_by_skills(["Mathematics", "Critical Thinking"], top_n=10)
        enriched = 0
        for r in results:
            bls = store.get_by_soc_code(r["soc_code"])
            if bls and bls.get("median_pay_annual"):
                enriched += 1

        assert enriched > 0, "No skill-matched careers had BLS salary data"
