# Career Counselor Chatbot

A Flask-based career counselor chatbot that uses Anthropic's Claude API and BLS/O*NET occupation data to help users explore career options.

## GitHub Repository
https://github.com/davehedengren/project-demo-econ-2026

## Architecture
- **Backend**: Python/Flask web app (`src/main.py`)
- **AI**: Anthropic Claude API via `src/chatbot.py` with tool use for occupation lookups
- **Data**: SQLite database (`data/career_data.db`) containing BLS occupation data, state wage data, and O*NET skills/knowledge/interests
- **Frontend**: Inline HTML template in `src/main.py` with chat interface and career explorer panel

## Key Files
- `src/main.py` - Flask app, HTML template, routes
- `src/chatbot.py` - Claude-based chatbot with tool-calling
- `src/occupation_store.py` - Occupation data access layer
- `src/state_data.py` - State-level wage data
- `src/onet_data.py` - O*NET skills/knowledge/interests data
- `src/tools.py` - Tool definitions for chatbot
- `data/career_data.db` - SQLite database (built via `build_db.py`)

## Environment
- **Secret**: `ANTHROPIC_API_KEY` (required for chat functionality)
- **Dev**: Flask dev server on port 5000
- **Production**: Gunicorn on port 5000, autoscale deployment target
- **Data loading**: Lazy-loaded on first request (not at startup) to ensure fast healthcheck responses

## Deployment Notes
- Deployment uses gunicorn with `--timeout=120 --workers=2`
- `/health` endpoint returns 200 immediately (no data loading)
- Data stores are lazy-loaded via `_ensure_data_loaded()` on first real request
