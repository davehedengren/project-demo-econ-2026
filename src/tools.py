"""
Claude tool definitions and execution for the career counselor chatbot.
"""

import json
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

from .occupation_store import OccupationStore
from .onet_data import OnetStore
from .state_data import StateDataStore


def load_tool_definitions(store: OccupationStore, onet_store: Optional[OnetStore] = None) -> list[dict]:
    """Load tool definitions from Jinja2 template."""
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("tools.j2")

    stats = store.get_stats()

    rendered = template.render(
        categories=stats["categories"],
        education_levels=stats["education_levels"],
        outlook_categories=stats["outlook_categories"],
        skill_names=onet_store.get_all_skill_names() if onet_store else [],
    )

    return json.loads(rendered)


def execute_tool(
    store: OccupationStore,
    state_store: StateDataStore,
    tool_name: str,
    tool_input: dict[str, Any],
    onet_store: Optional[OnetStore] = None,
) -> str:
    """Execute a tool and return the result as a string."""

    if tool_name == "search_occupations":
        query = tool_input.get("query", "")
        results = store.search(query, limit=10)

        if not results:
            return f"No occupations found matching '{query}'. Try different keywords."

        output = f"Found {len(results)} occupations matching '{query}':\n\n"
        for r in results:
            salary_str = f"${r.median_pay_annual:,}/year" if r.median_pay_annual else "Salary varies"
            output += f"**{r.title}** (code: {r.code})\n"
            output += f"  {r.description}\n"
            output += f"  Education: {r.entry_level_education} | {salary_str} | Outlook: {r.employment_outlook}\n\n"

        return output

    elif tool_name == "filter_occupations":
        categories = tool_input.get("categories")
        min_salary = tool_input.get("min_salary")
        max_salary = tool_input.get("max_salary")
        education_levels = tool_input.get("education_levels")
        outlook = tool_input.get("outlook")

        results = store.filter(
            categories=categories,
            min_salary=min_salary,
            max_salary=max_salary,
            education_levels=education_levels,
            outlook=outlook,
            limit=20,
        )

        if not results:
            return "No occupations found matching those criteria. Try adjusting your filters."

        # Build filter description
        filter_desc = []
        if categories:
            filter_desc.append(f"categories: {', '.join(categories)}")
        if min_salary:
            filter_desc.append(f"min salary: ${min_salary:,}")
        if max_salary:
            filter_desc.append(f"max salary: ${max_salary:,}")
        if education_levels:
            filter_desc.append(f"education: {', '.join(education_levels)}")
        if outlook:
            filter_desc.append(f"outlook: {', '.join(outlook)}")

        output = f"Found {len(results)} occupations"
        if filter_desc:
            output += f" with {'; '.join(filter_desc)}"
        output += ":\n\n"

        for r in results:
            salary_str = f"${r.median_pay_annual:,}/year" if r.median_pay_annual else "Salary varies"
            output += f"**{r.title}** (code: {r.code})\n"
            output += f"  {r.description}\n"
            output += f"  Education: {r.entry_level_education} | {salary_str} | Outlook: {r.employment_outlook}\n\n"

        return output

    elif tool_name == "get_occupation_details":
        code = tool_input.get("code", "")
        details = store.get_details(code)

        if not details:
            return f"Occupation with code '{code}' not found."

        output = f"# {details['title']}\n\n"
        output += f"**Code:** {details['code']}\n"
        output += f"**Category:** {details['category']}\n"
        output += f"**SOC Codes:** {', '.join(details['soc_codes'])}\n\n"

        output += "## Quick Facts (National)\n"
        if details['median_pay_annual']:
            output += f"- **Median Annual Salary:** ${details['median_pay_annual']:,}\n"
        if details['median_pay_hourly']:
            output += f"- **Median Hourly Wage:** ${details['median_pay_hourly']:.2f}\n"
        output += f"- **Entry-Level Education:** {details['entry_level_education']}\n"
        output += f"- **Work Experience Required:** {details['work_experience']}\n"
        output += f"- **On-the-Job Training:** {details['on_the_job_training']}\n"
        if details['number_of_jobs']:
            output += f"- **Number of Jobs (2024):** {details['number_of_jobs']:,}\n"
        output += f"- **Job Outlook (2024-2034):** {details['employment_outlook']}\n"
        if details['employment_openings']:
            output += f"- **Projected Openings:** {details['employment_openings']:,} per year\n"
        output += "\n"

        if details['what_they_do']:
            output += f"## What They Do\n{details['what_they_do']}\n\n"

        if details['how_to_become_one']:
            output += f"## How to Become One\n{details['how_to_become_one']}\n\n"

        if details['work_environment']:
            output += f"## Work Environment\n{details['work_environment']}\n\n"

        if details['job_outlook_details']:
            output += f"## Job Outlook\n{details['job_outlook_details']}\n\n"

        return output

    elif tool_name == "get_similar_occupations":
        code = tool_input.get("code", "")
        similar = store.get_similar(code)

        if not similar:
            occ = store.get_by_code(code)
            if not occ:
                return f"Occupation with code '{code}' not found."
            return f"No similar occupations found for {occ['title']}."

        occ = store.get_by_code(code)
        output = f"Similar occupations to **{occ['title']}**:\n\n"

        for s in similar:
            output += f"**{s['title']}**\n"
            output += f"  Education: {s['education']} | Salary: {s['salary']}\n\n"

        return output

    elif tool_name == "get_state_data":
        code = tool_input.get("code", "")
        state = tool_input.get("state", "")

        # Get SOC codes for this occupation
        soc_codes = store.get_soc_codes(code)
        if not soc_codes:
            return f"Occupation with code '{code}' not found."

        occ = store.get_by_code(code)
        national_median = occ["median_pay_annual"] if occ else None

        # Try each SOC code until we find data
        state_data = None
        for soc in soc_codes:
            state_data = state_store.get_state_data(soc, state)
            if state_data:
                break

        if not state_data:
            # Try to find the state
            found_state = state_store.find_state(state)
            if found_state:
                return f"No data found for '{occ['title']}' in {found_state}. This occupation may not be tracked separately in this state."
            return f"State '{state}' not found. Please use full state name (e.g., 'California', 'New York')."

        output = f"# {occ['title']} in {state_data['state']}\n\n"
        output += "## Employment & Wages\n"

        if state_data['employment']:
            output += f"- **Jobs in {state_data['state']}:** {state_data['employment']:,}\n"

        if state_data['median_annual']:
            output += f"- **Median Salary ({state_data['state']}):** ${state_data['median_annual']:,}/year\n"
            if national_median:
                diff = state_data['median_annual'] - national_median
                pct = (diff / national_median) * 100
                comparison = "higher" if diff > 0 else "lower"
                output += f"- **vs National Median (${national_median:,}):** ${abs(diff):,} {comparison} ({abs(pct):.1f}%)\n"

        if state_data['location_quotient']:
            lq = state_data['location_quotient']
            if lq > 1.0:
                lq_desc = f"Jobs are {lq:.2f}x more concentrated here than nationally"
            else:
                lq_desc = f"Jobs are {lq:.2f}x less concentrated here than nationally"
            output += f"- **Location Quotient:** {lq:.2f} ({lq_desc})\n"

        output += "\n## Salary Range in " + state_data['state'] + "\n"
        if state_data['pct10_annual']:
            output += f"- 10th percentile: ${state_data['pct10_annual']:,}\n"
        if state_data['pct25_annual']:
            output += f"- 25th percentile: ${state_data['pct25_annual']:,}\n"
        if state_data['median_annual']:
            output += f"- 50th percentile (median): ${state_data['median_annual']:,}\n"
        if state_data['pct75_annual']:
            output += f"- 75th percentile: ${state_data['pct75_annual']:,}\n"
        if state_data['pct90_annual']:
            output += f"- 90th percentile: ${state_data['pct90_annual']:,}\n"

        return output

    elif tool_name == "compare_states":
        code = tool_input.get("code", "")
        states = tool_input.get("states", [])

        soc_codes = store.get_soc_codes(code)
        if not soc_codes:
            return f"Occupation with code '{code}' not found."

        occ = store.get_by_code(code)
        national_median = occ['median_pay_annual'] if occ else None

        # Get data for each state
        results = []
        for state in states:
            for soc in soc_codes:
                data = state_store.get_state_data(soc, state)
                if data:
                    results.append(data)
                    break

        if not results:
            return f"No state data found for '{occ['title']}' in the specified states."

        output = f"# {occ['title']} - State Comparison\n\n"
        if national_median:
            output += f"**National Median:** ${national_median:,}/year\n\n"

        output += "| State | Jobs | Median Salary | vs National | Location Quotient |\n"
        output += "|-------|------|---------------|-------------|-------------------|\n"

        for data in results:
            jobs = f"{data['employment']:,}" if data['employment'] else "N/A"
            salary = f"${data['median_annual']:,}" if data['median_annual'] else "N/A"

            if data['median_annual'] and national_median:
                diff = data['median_annual'] - national_median
                vs_nat = f"+${diff:,}" if diff >= 0 else f"-${abs(diff):,}"
            else:
                vs_nat = "N/A"

            lq = f"{data['location_quotient']:.2f}" if data['location_quotient'] else "N/A"

            output += f"| {data['state']} | {jobs} | {salary} | {vs_nat} | {lq} |\n"

        return output

    elif tool_name == "get_top_states":
        code = tool_input.get("code", "")
        limit = tool_input.get("limit", 10)

        soc_codes = store.get_soc_codes(code)
        if not soc_codes:
            return f"Occupation with code '{code}' not found."

        occ = store.get_by_code(code)

        # Get data for first matching SOC code
        all_states = []
        for soc in soc_codes:
            all_states = state_store.get_occupation_by_state(soc)
            if all_states:
                break

        if not all_states:
            return f"No state data found for '{occ['title']}'."

        output = f"# Top States for {occ['title']}\n\n"
        output += "States ranked by total employment:\n\n"

        output += "| Rank | State | Jobs | Median Salary | Location Quotient |\n"
        output += "|------|-------|------|---------------|-------------------|\n"

        for i, data in enumerate(all_states[:limit], 1):
            jobs = f"{data['employment']:,}" if data['employment'] else "N/A"
            salary = f"${data['median_annual']:,}" if data['median_annual'] else "N/A"
            lq = f"{data['location_quotient']:.2f}" if data['location_quotient'] else "N/A"

            output += f"| {i} | {data['state']} | {jobs} | {salary} | {lq} |\n"

        return output

    # --- O*NET-powered tools ---

    elif tool_name == "get_occupation_skills":
        if not onet_store:
            return "Skills data is not available."

        code = tool_input.get("code", "")
        soc_codes = store.get_soc_codes(code)
        occ = store.get_by_code(code)
        if not occ:
            return f"Occupation with code '{code}' not found."

        skills = onet_store.get_skills(soc_codes, top_n=10)
        knowledge = onet_store.get_knowledge(soc_codes, top_n=8)

        if not skills and not knowledge:
            return f"No skills data found for '{occ['title']}'. This occupation may not have a detailed O*NET profile."

        output = f"# Skills & Knowledge for {occ['title']}\n\n"

        if skills:
            output += "## Top Skills (by importance, scale 1-5)\n"
            for s in skills:
                bar = "█" * int(s["importance"]) + "░" * (5 - int(s["importance"]))
                output += f"- **{s['skill']}**: {s['importance']:.1f} {bar}\n"
            output += "\n"

        if knowledge:
            output += "## Key Knowledge Areas (by importance, scale 1-5)\n"
            for k in knowledge:
                bar = "█" * int(k["importance"]) + "░" * (5 - int(k["importance"]))
                output += f"- **{k['area']}**: {k['importance']:.1f} {bar}\n"

        return output

    elif tool_name == "get_occupation_interests":
        if not onet_store:
            return "Interests data is not available."

        code = tool_input.get("code", "")
        soc_codes = store.get_soc_codes(code)
        occ = store.get_by_code(code)
        if not occ:
            return f"Occupation with code '{code}' not found."

        interests = onet_store.get_interests(soc_codes)
        if not interests:
            return f"No interest profile found for '{occ['title']}'."

        output = f"# Interest Profile for {occ['title']}\n\n"
        output += "Holland Code personality types (scale 1-7, higher = stronger fit):\n\n"

        for i in interests:
            bar = "█" * round(i["score"]) + "░" * (7 - round(i["score"]))
            output += f"- **{i['interest']}** ({i['score']:.1f}): {i['description']} {bar}\n"

        # Identify top type
        top = interests[0]
        output += f"\n**Primary type: {top['interest']}** — This career most aligns with people who enjoy {top['description'].lower()}.\n"

        return output

    elif tool_name == "find_careers_by_skills":
        if not onet_store:
            return "Skills data is not available."

        skill_names = tool_input.get("skills", [])
        if not skill_names:
            return "Please specify at least one skill to search for."

        results = onet_store.find_by_skills(skill_names, top_n=15)
        if not results:
            return f"No occupations found emphasizing skills: {', '.join(skill_names)}. Check spelling — available skills include: {', '.join(onet_store.get_all_skill_names()[:10])}..."

        output = f"# Careers Matching Skills: {', '.join(skill_names)}\n\n"
        output += "Occupations ranked by how much they value these skills:\n\n"

        # Try to enrich with BLS data
        for r in results:
            bls_occ = store.get_by_soc_code(r["soc_code"])
            salary_str = ""
            if bls_occ and bls_occ["median_pay_annual"]:
                salary_str = f" | ${bls_occ['median_pay_annual']:,}/yr"

            output += f"**{r['title']}** (SOC: {r['soc_code']}{salary_str})\n"

        return output

    elif tool_name == "find_careers_by_interests":
        if not onet_store:
            return "Interests data is not available."

        profile = {
            "Realistic": tool_input.get("realistic", 1),
            "Investigative": tool_input.get("investigative", 1),
            "Artistic": tool_input.get("artistic", 1),
            "Social": tool_input.get("social", 1),
            "Enterprising": tool_input.get("enterprising", 1),
            "Conventional": tool_input.get("conventional", 1),
        }

        results = onet_store.find_by_interests(profile, top_n=15)
        if not results:
            return "No matching occupations found for that interest profile."

        # Build profile summary
        top_interests = sorted(profile.items(), key=lambda x: x[1], reverse=True)[:3]
        profile_desc = ", ".join(f"{name} ({val})" for name, val in top_interests)

        output = f"# Careers Matching Interest Profile\n\n"
        output += f"**Top interests:** {profile_desc}\n\n"
        output += "Best-matching occupations:\n\n"

        for r in results:
            bls_occ = store.get_by_soc_code(r["soc_code"])
            salary_str = ""
            if bls_occ and bls_occ["median_pay_annual"]:
                salary_str = f" | ${bls_occ['median_pay_annual']:,}/yr"

            output += f"**{r['title']}** (SOC: {r['soc_code']}{salary_str})\n"

        return output

    else:
        return f"Unknown tool: {tool_name}"
