# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interactive career counselor chatbot that helps students decide on career paths using Bureau of Labor Statistics (BLS) Occupational Outlook Handbook data. Students share their academic background (courses enjoyed, grades, strengths/weaknesses) and receive personalized career guidance grounded in real labor market data.

## Architecture

- **LLM**: Anthropic Claude Opus 4.6 API (`claude-opus-4-6`)
- **Data storage**: Single SQLite database (`data/career_data.db`) built from BLS + O*NET raw files
- **Data sources**: BLS Occupational Outlook Handbook, OEWS state wages, O*NET skills/interests
- **Tool use**: Claude has 11 tools to query the database for accurate, grounded responses
- **Build step**: Run `python build_db.py` to rebuild the database from raw data files
- **Deployment**: Replit

## Data

### Occupational Data
`data/xml-compilation.xml` (~12MB) - BLS Occupational Outlook Handbook containing:
- 342 occupations across 25 categories
- Job titles, descriptions, and SOC codes
- National median pay (annual/hourly)
- Education and training requirements
- Employment projections (2024-2034)
- National job counts and growth rates
- Similar occupation relationships

### State-Level Data
`data/state_M2024_dl.xlsx` - OEWS May 2024 state employment/wage data:
- Employment counts by state for each occupation
- Median and mean wages by state
- Wage percentiles (10th, 25th, 75th, 90th)
- Location quotient (job concentration vs national)
- See `data/state_data_dictionary.txt` for field definitions

### O*NET Skills & Interests Data
`data/onet/` - O*NET 30.2 Database (downloaded, not checked into git):
- `Skills.txt` - 35 skills rated by importance for 894 occupations
- `Knowledge.txt` - 33 knowledge areas rated by importance
- `Interests.txt` - Holland Code (RIASEC) interest profiles
- `Occupation_Data.txt` - 1,016 O*NET occupation titles/descriptions
- `Abilities.txt` - Cognitive and physical abilities (available for future use)
- `Education_Training_Experience.txt` - Education requirements (available for future use)
- Mapped to BLS occupations via SOC codes

## Code Style

- **LLM Prompts**: Use Jinja2 templates (`.j2` files) in `src/templates/` for all LLM system prompts and tool definitions. This makes prompts easier to edit and version control separately from code.

## Environment

- `ANTHROPIC_API_KEY` - API key for Claude Opus 4.6 (stored in `.env`)

## Permissions

- `.env` file in root contains secrets and cannot be read by LLM coding tools
- Claude has permission to read all other files in this project folder
- Ask the user before accessing files outside this project directory
