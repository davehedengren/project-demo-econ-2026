# Career Counselor Chatbot

Interactive career counselor that helps students explore careers using Bureau of Labor Statistics Occupational Outlook Handbook data.

## Features

- **342 occupations** across 25 career categories
- Search by keywords (interests, job types, subjects)
- Filter by education level, salary range, job outlook
- Detailed occupation profiles with salary, requirements, and outlook data
- Similar occupation recommendations
- State/area resource links for geographic job market research

## Setup

### 1. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-api-key-here
```

### 3. Run the chatbot

**Web interface (recommended):**
```bash
python -m src.main
```
Then open http://localhost:8080 in your browser.

**Command line interface:**
```bash
python -m src.main --cli
```

## Replit Deployment

1. Import the repository to Replit
2. Add `ANTHROPIC_API_KEY` to Secrets
3. Click Run - the `.replit` file is pre-configured

## Project Structure

```
├── data/
│   └── xml-compilation.xml   # BLS Occupational Outlook Handbook data
├── src/
│   ├── templates/
│   │   ├── system_prompt.j2  # Claude system prompt
│   │   └── tools.j2          # Tool definitions
│   ├── data_loader.py        # XML parsing
│   ├── occupation_store.py   # Search/filter store
│   ├── tools.py              # Tool execution
│   ├── chatbot.py            # Conversation orchestration
│   └── main.py               # Entry point (Flask + CLI)
├── requirements.txt
├── .replit
└── CLAUDE.md
```

## Tools Available to Claude

1. **search_occupations** - Keyword search in titles/descriptions
2. **filter_occupations** - Filter by category, salary, education, outlook
3. **get_occupation_details** - Full details for one occupation
4. **get_similar_occupations** - Related careers
5. **get_state_resources** - State-specific employment and wage data links

## Data Source

Bureau of Labor Statistics Occupational Outlook Handbook
- Employment projections: 2024-2034
- Wage data: May 2024
