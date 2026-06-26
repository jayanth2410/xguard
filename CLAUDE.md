# Claude Code Configuration

## Project context
- Python project: Maker-Checker Enterprise Workflow Platform
- Backend: FastAPI
- Web UI: Flask
- Database: SQLAlchemy
- Entry points: `run_api.py`, `run_web.py`

## Working rules
- Prefer small, targeted edits.
- Preserve existing structure and style.
- Use `config.ini` for application settings.
- Avoid hardcoding secrets; keep credentials out of source control.
- Validate changes after editing when possible.

## Repo-specific notes
- FastAPI app is in `app/main.py`.
- Shared config is in `app/core/config.py`.
- Service logic is in `app/services/`.
- Web templates are in `app/web/templates/`.

## Common run commands
- API: `python run_api.py`
- Web UI: `python run_web.py`
