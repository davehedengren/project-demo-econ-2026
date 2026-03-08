"""
Build the SQLite database from raw BLS XML, OEWS Excel, and O*NET text files.

Run this once to create data/career_data.db, then the server uses only the .db file.

Usage:
    python build_db.py
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Reuse existing parsers for the XML
from src.data_loader import load_occupations

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "career_data.db"


def create_tables(conn: sqlite3.Connection):
    """Create all tables and indexes."""
    conn.executescript("""
        DROP TABLE IF EXISTS occupations;
        DROP TABLE IF EXISTS occupation_soc_codes;
        DROP TABLE IF EXISTS similar_occupations;
        DROP TABLE IF EXISTS state_wages;
        DROP TABLE IF EXISTS onet_skills;
        DROP TABLE IF EXISTS onet_knowledge;
        DROP TABLE IF EXISTS onet_interests;
        DROP TABLE IF EXISTS onet_occupations;

        CREATE TABLE occupations (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT,
            median_pay_annual INTEGER,
            median_pay_hourly REAL,
            entry_level_education TEXT,
            work_experience TEXT,
            on_the_job_training TEXT,
            number_of_jobs INTEGER,
            employment_outlook TEXT,
            employment_outlook_value INTEGER,
            employment_openings INTEGER,
            what_they_do TEXT,
            work_environment TEXT,
            how_to_become_one TEXT,
            job_outlook_details TEXT,
            url TEXT
        );

        CREATE TABLE occupation_soc_codes (
            occupation_code TEXT NOT NULL,
            soc_code TEXT NOT NULL,
            PRIMARY KEY (occupation_code, soc_code)
        );

        CREATE TABLE similar_occupations (
            occupation_code TEXT NOT NULL,
            similar_title TEXT,
            similar_code TEXT,
            education TEXT,
            salary TEXT
        );

        CREATE TABLE state_wages (
            soc_code TEXT NOT NULL,
            state TEXT NOT NULL,
            occupation_title TEXT,
            employment INTEGER,
            median_annual INTEGER,
            median_hourly REAL,
            mean_annual INTEGER,
            pct10_annual INTEGER,
            pct25_annual INTEGER,
            pct75_annual INTEGER,
            pct90_annual INTEGER,
            location_quotient REAL,
            jobs_per_1000 REAL,
            PRIMARY KEY (soc_code, state)
        );

        CREATE TABLE onet_skills (
            onet_soc_code TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            importance REAL,
            PRIMARY KEY (onet_soc_code, skill_name)
        );

        CREATE TABLE onet_knowledge (
            onet_soc_code TEXT NOT NULL,
            area_name TEXT NOT NULL,
            importance REAL,
            PRIMARY KEY (onet_soc_code, area_name)
        );

        CREATE TABLE onet_interests (
            onet_soc_code TEXT NOT NULL,
            interest_name TEXT NOT NULL,
            score REAL,
            PRIMARY KEY (onet_soc_code, interest_name)
        );

        CREATE TABLE onet_occupations (
            onet_soc_code TEXT PRIMARY KEY,
            soc6 TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT
        );

        -- Indexes for fast lookups
        CREATE INDEX idx_occ_category ON occupations(category);
        CREATE INDEX idx_occ_education ON occupations(entry_level_education);
        CREATE INDEX idx_occ_outlook ON occupations(employment_outlook);
        CREATE INDEX idx_soc_soc_code ON occupation_soc_codes(soc_code);
        CREATE INDEX idx_state_soc ON state_wages(soc_code);
        CREATE INDEX idx_state_state ON state_wages(state);
        CREATE INDEX idx_onet_skills_name ON onet_skills(skill_name);
        CREATE INDEX idx_onet_knowledge_name ON onet_knowledge(area_name);
        CREATE INDEX idx_onet_interests_name ON onet_interests(interest_name);
        CREATE INDEX idx_onet_occ_soc6 ON onet_occupations(soc6);
    """)


def load_bls_occupations(conn: sqlite3.Connection):
    """Load BLS Occupational Outlook Handbook XML data."""
    xml_path = DATA_DIR / "xml-compilation.xml"
    if not xml_path.exists():
        print(f"  WARNING: {xml_path} not found, skipping BLS occupations")
        return

    print(f"  Loading {xml_path}...")
    occupations = load_occupations(str(xml_path))
    print(f"  Parsed {len(occupations)} occupations")

    # Insert occupations
    for occ in occupations:
        conn.execute("""
            INSERT INTO occupations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            occ.code, occ.title, occ.description, occ.category,
            occ.median_pay_annual, occ.median_pay_hourly,
            occ.entry_level_education, occ.work_experience, occ.on_the_job_training,
            occ.number_of_jobs, occ.employment_outlook, occ.employment_outlook_value,
            occ.employment_openings,
            occ.what_they_do, occ.work_environment, occ.how_to_become_one,
            occ.job_outlook_details, occ.url,
        ))

        # SOC codes
        for soc in occ.soc_codes:
            conn.execute(
                "INSERT OR IGNORE INTO occupation_soc_codes VALUES (?,?)",
                (occ.code, soc),
            )

        # Similar occupations
        for title, sim_code, education, salary in occ.similar_occupations:
            conn.execute(
                "INSERT INTO similar_occupations VALUES (?,?,?,?,?)",
                (occ.code, title, sim_code, education, salary),
            )

    conn.commit()
    print(f"  Inserted {len(occupations)} occupations")


def safe_int(val) -> int | None:
    """Convert a value to int, handling NaN and special BLS markers."""
    if pd.isna(val):
        return None
    try:
        if isinstance(val, str):
            val = val.replace(",", "").replace("*", "").replace("#", "")
            if not val or val == "**":
                return None
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val) -> float | None:
    """Convert a value to float, handling NaN and special BLS markers."""
    if pd.isna(val):
        return None
    try:
        if isinstance(val, str):
            val = val.replace(",", "").replace("*", "").replace("#", "")
            if not val or val == "**":
                return None
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None


def load_state_wages(conn: sqlite3.Connection):
    """Load OEWS state-level employment and wage data."""
    xlsx_path = DATA_DIR / "state_M2024_dl.xlsx"
    if not xlsx_path.exists():
        print(f"  WARNING: {xlsx_path} not found, skipping state data")
        return

    print(f"  Loading {xlsx_path}...")
    df = pd.read_excel(xlsx_path)

    # Filter to state-level data only (AREA_TYPE == 2)
    states_df = df[df["AREA_TYPE"] == 2]
    print(f"  Found {len(states_df)} state-level records")

    rows = []
    for _, row in states_df.iterrows():
        rows.append((
            row["OCC_CODE"],
            row["AREA_TITLE"],
            row.get("OCC_TITLE", ""),
            safe_int(row.get("TOT_EMP")),
            safe_int(row.get("A_MEDIAN")),
            safe_float(row.get("H_MEDIAN")),
            safe_int(row.get("A_MEAN")),
            safe_int(row.get("A_PCT10")),
            safe_int(row.get("A_PCT25")),
            safe_int(row.get("A_PCT75")),
            safe_int(row.get("A_PCT90")),
            safe_float(row.get("LOC_QUOTIENT")),
            safe_float(row.get("JOBS_1000")),
        ))

    conn.executemany(
        "INSERT OR IGNORE INTO state_wages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    print(f"  Inserted {len(rows)} state wage records")


def load_onet_data(conn: sqlite3.Connection):
    """Load O*NET skills, knowledge, interests, and occupation data."""
    onet_dir = DATA_DIR / "onet"
    if not onet_dir.exists():
        print(f"  WARNING: {onet_dir} not found, skipping O*NET data")
        return

    # Skills
    skills_path = onet_dir / "Skills.txt"
    if skills_path.exists():
        print(f"  Loading {skills_path}...")
        df = pd.read_csv(skills_path, sep="\t")
        df = df[(df["Scale ID"] == "IM") & (df["Recommend Suppress"] != "Y")]
        rows = [(r["O*NET-SOC Code"], r["Element Name"], round(float(r["Data Value"]), 2))
                for _, r in df.iterrows()]
        conn.executemany("INSERT OR IGNORE INTO onet_skills VALUES (?,?,?)", rows)
        conn.commit()
        print(f"  Inserted {len(rows)} skill ratings")

    # Knowledge
    know_path = onet_dir / "Knowledge.txt"
    if know_path.exists():
        print(f"  Loading {know_path}...")
        df = pd.read_csv(know_path, sep="\t")
        df = df[(df["Scale ID"] == "IM") & (df["Recommend Suppress"] != "Y")]
        rows = [(r["O*NET-SOC Code"], r["Element Name"], round(float(r["Data Value"]), 2))
                for _, r in df.iterrows()]
        conn.executemany("INSERT OR IGNORE INTO onet_knowledge VALUES (?,?,?)", rows)
        conn.commit()
        print(f"  Inserted {len(rows)} knowledge ratings")

    # Interests
    int_path = onet_dir / "Interests.txt"
    if int_path.exists():
        print(f"  Loading {int_path}...")
        df = pd.read_csv(int_path, sep="\t")
        holland = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]
        df = df[(df["Scale ID"] == "OI") & (df["Element Name"].isin(holland))]
        rows = [(r["O*NET-SOC Code"], r["Element Name"], round(float(r["Data Value"]), 2))
                for _, r in df.iterrows()]
        conn.executemany("INSERT OR IGNORE INTO onet_interests VALUES (?,?,?)", rows)
        conn.commit()
        print(f"  Inserted {len(rows)} interest ratings")

    # Occupations
    occ_path = onet_dir / "Occupation_Data.txt"
    if occ_path.exists():
        print(f"  Loading {occ_path}...")
        df = pd.read_csv(occ_path, sep="\t")
        rows = [(r["O*NET-SOC Code"], r["O*NET-SOC Code"][:7], r["Title"], r["Description"])
                for _, r in df.iterrows()]
        conn.executemany("INSERT OR IGNORE INTO onet_occupations VALUES (?,?,?,?)", rows)
        conn.commit()
        print(f"  Inserted {len(rows)} O*NET occupations")


def main():
    print(f"Building career database at {DB_PATH}")
    print()

    # Remove old database if exists
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))

    print("Creating tables...")
    create_tables(conn)

    print("\nLoading BLS occupations...")
    load_bls_occupations(conn)

    print("\nLoading state wages...")
    load_state_wages(conn)

    print("\nLoading O*NET data...")
    load_onet_data(conn)

    # Print summary
    print("\n" + "=" * 50)
    print("Database build complete!")
    print()
    for table in ["occupations", "occupation_soc_codes", "similar_occupations",
                   "state_wages", "onet_skills", "onet_knowledge",
                   "onet_interests", "onet_occupations"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")

    db_size = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"\n  Database size: {db_size:.1f} MB")

    conn.close()


if __name__ == "__main__":
    main()
