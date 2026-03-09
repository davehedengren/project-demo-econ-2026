"""
Generate rich Markdown profile files for each occupation by combining
BLS Occupational Outlook Handbook data with O*NET skills/interests data.

These profiles give the LLM deep, readable context about each career —
much richer than truncated SQL snippets.

Usage:
    python build_profiles.py
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "career_data.db"
PROFILES_DIR = DATA_DIR / "profiles"


def get_onet_skills(conn: sqlite3.Connection, soc_codes: list[str], top_n: int = 10) -> list[dict]:
    """Get top skills for an occupation from O*NET."""
    if not soc_codes:
        return []
    # Find O*NET codes matching these SOC codes
    placeholders = ",".join("?" * len(soc_codes))
    onet_codes = [r[0] for r in conn.execute(
        f"SELECT onet_soc_code FROM onet_occupations WHERE soc6 IN ({placeholders})",
        soc_codes,
    ).fetchall()]
    if not onet_codes:
        return []
    ph = ",".join("?" * len(onet_codes))
    rows = conn.execute(f"""
        SELECT skill_name, ROUND(AVG(importance), 2) as importance
        FROM onet_skills WHERE onet_soc_code IN ({ph})
        GROUP BY skill_name ORDER BY importance DESC LIMIT ?
    """, onet_codes + [top_n]).fetchall()
    return [{"skill": r[0], "importance": r[1]} for r in rows]


def get_onet_knowledge(conn: sqlite3.Connection, soc_codes: list[str], top_n: int = 8) -> list[dict]:
    """Get top knowledge areas for an occupation from O*NET."""
    if not soc_codes:
        return []
    placeholders = ",".join("?" * len(soc_codes))
    onet_codes = [r[0] for r in conn.execute(
        f"SELECT onet_soc_code FROM onet_occupations WHERE soc6 IN ({placeholders})",
        soc_codes,
    ).fetchall()]
    if not onet_codes:
        return []
    ph = ",".join("?" * len(onet_codes))
    rows = conn.execute(f"""
        SELECT area_name, ROUND(AVG(importance), 2) as importance
        FROM onet_knowledge WHERE onet_soc_code IN ({ph})
        GROUP BY area_name ORDER BY importance DESC LIMIT ?
    """, onet_codes + [top_n]).fetchall()
    return [{"area": r[0], "importance": r[1]} for r in rows]


def get_onet_interests(conn: sqlite3.Connection, soc_codes: list[str]) -> list[dict]:
    """Get Holland Code interest profile from O*NET."""
    if not soc_codes:
        return []
    placeholders = ",".join("?" * len(soc_codes))
    onet_codes = [r[0] for r in conn.execute(
        f"SELECT onet_soc_code FROM onet_occupations WHERE soc6 IN ({placeholders})",
        soc_codes,
    ).fetchall()]
    if not onet_codes:
        return []
    ph = ",".join("?" * len(onet_codes))
    rows = conn.execute(f"""
        SELECT interest_name, ROUND(AVG(score), 2) as score
        FROM onet_interests WHERE onet_soc_code IN ({ph})
        GROUP BY interest_name ORDER BY score DESC
    """, onet_codes).fetchall()
    return [{"interest": r[0], "score": r[1]} for r in rows]


def get_similar_occupations(conn: sqlite3.Connection, code: str) -> list[dict]:
    """Get similar occupations from BLS data."""
    rows = conn.execute("""
        SELECT similar_title, education, salary FROM similar_occupations
        WHERE occupation_code = ?
    """, (code,)).fetchall()
    return [{"title": r[0], "education": r[1], "salary": r[2]} for r in rows]


def build_profile(conn: sqlite3.Connection, occ: dict) -> str:
    """Build a rich Markdown profile for a single occupation."""
    code = occ["code"]

    # Get SOC codes for O*NET lookup
    soc_codes = [r[0] for r in conn.execute(
        "SELECT soc_code FROM occupation_soc_codes WHERE occupation_code = ?",
        (code,),
    ).fetchall()]

    skills = get_onet_skills(conn, soc_codes)
    knowledge = get_onet_knowledge(conn, soc_codes)
    interests = get_onet_interests(conn, soc_codes)
    similar = get_similar_occupations(conn, code)

    lines = []

    # Header
    lines.append(f"# {occ['title']}")
    lines.append("")
    lines.append(f"**Code:** {code}  ")
    lines.append(f"**Category:** {occ['category']}  ")
    if soc_codes:
        lines.append(f"**SOC Codes:** {', '.join(soc_codes)}  ")
    lines.append("")

    # Description
    if occ["description"]:
        lines.append(f"> {occ['description']}")
        lines.append("")

    # Quick Facts
    lines.append("## Quick Facts")
    lines.append("")
    if occ["median_pay_annual"]:
        lines.append(f"- **Median Annual Salary:** ${occ['median_pay_annual']:,}")
    if occ["median_pay_hourly"]:
        lines.append(f"- **Median Hourly Wage:** ${occ['median_pay_hourly']:.2f}")
    lines.append(f"- **Entry-Level Education:** {occ['entry_level_education']}")
    if occ["work_experience"] and occ["work_experience"] != "None":
        lines.append(f"- **Work Experience Required:** {occ['work_experience']}")
    if occ["on_the_job_training"] and occ["on_the_job_training"] != "None":
        lines.append(f"- **On-the-Job Training:** {occ['on_the_job_training']}")
    if occ["number_of_jobs"]:
        lines.append(f"- **Number of Jobs (2024):** {occ['number_of_jobs']:,}")
    if occ["employment_outlook"]:
        lines.append(f"- **Job Outlook (2024-2034):** {occ['employment_outlook']}")
    if occ["employment_openings"]:
        lines.append(f"- **Projected Annual Openings:** {occ['employment_openings']:,}")
    lines.append("")

    # What They Do
    if occ["what_they_do"]:
        lines.append("## What They Do")
        lines.append("")
        lines.append(occ["what_they_do"])
        lines.append("")

    # How to Become One
    if occ["how_to_become_one"]:
        lines.append("## How to Become One")
        lines.append("")
        lines.append(occ["how_to_become_one"])
        lines.append("")

    # Work Environment
    if occ["work_environment"]:
        lines.append("## Work Environment")
        lines.append("")
        lines.append(occ["work_environment"])
        lines.append("")

    # Job Outlook
    if occ["job_outlook_details"]:
        lines.append("## Job Outlook")
        lines.append("")
        lines.append(occ["job_outlook_details"])
        lines.append("")

    # O*NET Skills
    if skills:
        lines.append("## Key Skills (O*NET)")
        lines.append("")
        lines.append("Skills ranked by importance (scale 1-5):")
        lines.append("")
        for s in skills:
            bar = "█" * int(s["importance"]) + "░" * (5 - int(s["importance"]))
            lines.append(f"- **{s['skill']}**: {s['importance']:.1f} {bar}")
        lines.append("")

    # O*NET Knowledge Areas
    if knowledge:
        lines.append("## Key Knowledge Areas (O*NET)")
        lines.append("")
        for k in knowledge:
            bar = "█" * int(k["importance"]) + "░" * (5 - int(k["importance"]))
            lines.append(f"- **{k['area']}**: {k['importance']:.1f} {bar}")
        lines.append("")

    # Holland Code Interest Profile
    if interests:
        lines.append("## Personality Fit (Holland Code)")
        lines.append("")
        holland_desc = {
            "Realistic": "Hands-on, practical work with tools, machines, plants, or animals",
            "Investigative": "Research, analysis, and solving complex problems",
            "Artistic": "Creative expression, design, and working with ideas",
            "Social": "Helping, teaching, counseling, and working with people",
            "Enterprising": "Leading, persuading, and managing business activities",
            "Conventional": "Organizing, managing data, and following procedures",
        }
        for i in interests:
            desc = holland_desc.get(i["interest"], "")
            bar = "█" * round(i["score"]) + "░" * (7 - round(i["score"]))
            lines.append(f"- **{i['interest']}** ({i['score']:.1f}/7): {desc} {bar}")
        top = interests[0]
        lines.append("")
        lines.append(f"**Primary type: {top['interest']}** — Best suited for people who enjoy {holland_desc.get(top['interest'], '').lower()}.")
        lines.append("")

    # Similar Occupations
    if similar:
        lines.append("## Similar Occupations")
        lines.append("")
        for s in similar:
            parts = [f"**{s['title']}**"]
            if s["education"]:
                parts.append(f"Education: {s['education']}")
            if s["salary"]:
                parts.append(f"Salary: {s['salary']}")
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    return "\n".join(lines)


def main():
    print(f"Building occupation profiles from {DB_PATH}")

    if not DB_PATH.exists():
        print("ERROR: career_data.db not found. Run build_db.py first.")
        return

    # Create profiles directory
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Fetch all occupations
    occupations = conn.execute("SELECT * FROM occupations ORDER BY title").fetchall()
    print(f"Found {len(occupations)} occupations")

    count = 0
    for occ in occupations:
        occ_dict = dict(occ)
        profile = build_profile(conn, occ_dict)

        # Use code as filename (safe for filesystem)
        filename = f"{occ_dict['code']}.md"
        filepath = PROFILES_DIR / filename
        filepath.write_text(profile, encoding="utf-8")
        count += 1

    conn.close()

    print(f"\nGenerated {count} occupation profiles in {PROFILES_DIR}/")
    print(f"Total size: {sum(f.stat().st_size for f in PROFILES_DIR.glob('*.md')) / (1024*1024):.1f} MB")


if __name__ == "__main__":
    main()
