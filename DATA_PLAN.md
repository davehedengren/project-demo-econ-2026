# Data Gathering Plan

Plan to enrich the career counselor chatbot with more detailed and diverse data sources.

## What We Have Now

| Data Source | Records | Key Fields |
|---|---|---|
| BLS OOH XML | 342 occupations, 25 categories | Title, description, pay, education, outlook, growth, similar occupations |
| OEWS State Excel | 37,609 rows, 50 states + DC, 854 SOC codes | Employment, median/mean wages, percentiles (10th-90th), location quotient |

## Phase 1: Unlock Data We Already Have (Low Effort)

The OEWS Excel file contains more data than we currently expose.

### 1.1 Metro Area (MSA) Data
The state Excel file includes metro-area records (AREA_TYPE != 2). Add a tool to look up occupation data by city/metro area, not just state.
- **Source**: Already in `data/state_M2024_dl.xlsx`
- **Work**: Filter for MSA records in `state_data.py`, add `get_metro_data` tool
- **Value**: Students can see salary/jobs for specific cities (e.g., "Software developers in Austin, TX")

### 1.2 Industry Breakdown by Occupation
The OEWS publishes a separate **industry-by-occupation** matrix showing which industries employ each occupation and at what pay.
- **Source**: [OEWS Industry Data](https://www.bls.gov/oes/tables.htm) — download the "nat3d" or "nat4d" industry file
- **Work**: New data file, new tool `get_industry_breakdown`
- **Value**: Answer "Where do accountants actually work?" → 19% accounting firms, 14% government, 10% finance...

## Phase 2: Add Skills & Education Detail (Medium Effort)

### 2.1 O*NET Skills & Knowledge Data
The O*NET database (Department of Labor) has detailed skill profiles for every occupation, mapped by SOC code.
- **Source**: [O*NET Database](https://www.onetcenter.org/database.html) — free CSV downloads
- **Key files**: `Skills.csv`, `Knowledge.csv`, `Abilities.csv`, `Work Activities.csv`, `Education, Training, and Experience.csv`
- **Work**: Load CSVs, join to occupations via SOC code, add tools like `get_skills_for_occupation` and `find_occupations_by_skill`
- **Value**: "What skills do I need?" / "I'm good at math — what careers match?" — this is a huge gap right now

### 2.2 O*NET Interests & Work Styles
O*NET also maps occupations to Holland Code interest types (Realistic, Investigative, Artistic, Social, Enterprising, Conventional).
- **Source**: `Interests.csv` from O*NET
- **Work**: Load and add a `match_by_interests` tool
- **Value**: Students can take a quick interest quiz and get matched careers

### 2.3 Typical Degree Fields
O*NET's `Education, Training, and Experience.csv` lists the most common degree fields for each occupation (e.g., "Computer Science" for software developers).
- **Source**: O*NET education data
- **Work**: New tool `get_degree_fields`
- **Value**: Directly answers "What should I major in?"

## Phase 3: Expand Career Coverage (Medium-High Effort)

### 3.1 Emerging & Niche Occupations
The BLS OOH covers 342 occupations but misses many emerging roles. O*NET has ~1,000 occupations with detailed profiles.
- **Source**: O*NET `Occupation Data.csv` — ~1,016 occupations
- **Work**: Supplement our 342 BLS occupations with O*NET-only occupations (title, description, skills, education). Won't have BLS outlook/pay data for all, but skills and education data would still be valuable.
- **Value**: Cover roles like "Data Scientist", "UX Designer", "Cloud Architect" that may not have standalone BLS entries

### 3.2 Apprenticeship & Alternative Pathways
Many students won't pursue a 4-year degree. Add data on apprenticeships and alternative credentials.
- **Source**: [DOL ApprenticeshipUSA](https://www.apprenticeship.gov/apprenticeship-data) and [CareerOneStop](https://www.careeronestop.org/) APIs
- **Work**: New data file mapping occupations to available apprenticeships, certifications, bootcamp pathways
- **Value**: "I don't want to go to college — what are my options for this career?"

### 3.3 Licensure & Certification Requirements
Some occupations require specific licenses or certifications.
- **Source**: O*NET `Certification and Licensure.csv`, plus parsing BLS "How to Become One" sections more carefully
- **Work**: Structured data extraction + new tool
- **Value**: "Do I need a license to be a physical therapist in California?"

## Phase 4: Real-Time & Advanced Data (High Effort)

### 4.1 Job Postings / Labor Market Signals
Add current job market data to complement BLS projections.
- **Source Options**:
  - [Lightcast (formerly EMSI)](https://lightcast.io/) — comprehensive but paid
  - [USA Jobs API](https://developer.usajobs.gov/) — free, government jobs only
  - [BLS JOLTS](https://www.bls.gov/jlt/) — Job Openings and Labor Turnover Survey (aggregate, not by occupation)
- **Work**: API integration, periodic refresh
- **Value**: "Are companies actually hiring for this right now?"

### 4.2 Demographic Workforce Data
Show representation in different occupations.
- **Source**: [BLS Current Population Survey](https://www.bls.gov/cps/cpsaat11.htm) — workforce demographics by occupation
- **Work**: New data file, new tool
- **Value**: "What does the workforce look like for this occupation?"

## Priority Recommendation

| Priority | Item | Effort | Impact |
|---|---|---|---|
| 1 | Metro area data (1.1) | Low | High — students care about cities, not just states |
| 2 | O*NET skills data (2.1) | Medium | Very High — biggest gap in current system |
| 3 | Industry breakdown (1.2) | Low-Medium | Medium — adds context to "where do they work" |
| 4 | O*NET interests (2.2) | Medium | High — enables interest-based matching |
| 5 | Degree fields (2.3) | Medium | High — directly answers "what should I major in" |
| 6 | Emerging occupations (3.1) | Medium | Medium — fills coverage gaps |
| 7 | Alternative pathways (3.2) | Medium-High | Medium — important for non-college students |
