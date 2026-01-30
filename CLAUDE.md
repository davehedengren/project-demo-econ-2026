# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interactive career counselor chatbot that helps students decide on career paths using Bureau of Labor Statistics (BLS) Occupational Outlook Handbook data. Students share their academic background (courses enjoyed, grades, strengths/weaknesses) and receive personalized career guidance grounded in real labor market data.

## Architecture

- **LLM**: Anthropic Claude Opus 4.5 API (`claude-opus-4-5-20251101`)
- **Data source**: BLS Occupational Outlook Handbook XML
- **Tool use**: Claude has skills/tools to query the XML database for accurate, grounded responses
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

## Code Style

- **LLM Prompts**: Use Jinja2 templates (`.j2` files) in `src/templates/` for all LLM system prompts and tool definitions. This makes prompts easier to edit and version control separately from code.

## Environment

- `ANTHROPIC_API_KEY` - API key for Claude Opus 4.5 (stored in `.env`)

## Permissions

- `.env` file in root contains secrets and cannot be read by LLM coding tools
- Claude has permission to read all other files in this project folder
- Ask the user before accessing files outside this project directory
