# XGuard

XGuard is an enterprise maker-checker application for preparing, reviewing, and safely executing infrastructure changes. It combines a FastAPI backend, a Flask UI, AI-assisted clarification and code generation, ServiceNow import, and SSH/WinRM execution.

## Workflow

Create or import work package → answer automatically generated clarification questions → generate implementation and rollback content → submit for review → approve for execution or return for rework → execute → complete or roll back.

There is no separate validation page. Required AI questions are answered while editing the work package, before final code generation.

## Requirements

- Python 3.12 or 3.13
- Network access to the configured AI and ServiceNow instances
- Network access to target hosts for SSH or WinRM execution

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create `config.ini` in the project root. The application supplies local defaults, but production credentials and secret keys must be configured explicitly.

```ini
[application]
APP_NAME = XGuard
APP_VERSION = 1.0.0
DEBUG = false

[api]
API_PREFIX = /api/v1
CORS_ORIGINS = http://localhost:5000

[database]
DATABASE_URL = sqlite:///./makerchecker.db

[flask]
FLASK_SECRET_KEY = replace-me
FLASK_HOST = 0.0.0.0
FLASK_PORT = 5000

[fastapi]
FASTAPI_HOST = 127.0.0.1
FASTAPI_PORT = 8000

[ai]
GROQ_API_KEY = replace-me
BASE_URL = https://api.groq.com/openai/v1
MODEL = llama-3.3-70b-versatile
TIMEOUT_SECONDS = 60

[servicenow]
SERVICENOW_ENABLED = false
SERVICENOW_INSTANCE = https://your-instance.service-now.com
SERVICENOW_USERNAME = replace-me
SERVICENOW_PASSWORD = replace-me
SERVICENOW_INCIDENT_TABLE = incident
SERVICENOW_CHANGE_TABLE = change_request
SERVICENOW_REQUEST_TABLE = sc_request

[ssh]
DEFAULT_SSH_PORT = 22
SSH_TIMEOUT = 30

[winrm]
DEFAULT_WINRM_PORT = 5985
WINRM_TRANSPORT = ntlm
WINRM_TIMEOUT = 30

[logging]
LOG_LEVEL = INFO
LOG_FORMAT = json
LOG_FILE = logs/makerchecker.log
```

Do not commit real passwords, API keys, or production secret keys.

## Run

Start the API and UI in separate terminals:

```powershell
.\venv\Scripts\Activate.ps1
python run_api.py
```

```powershell
.\venv\Scripts\Activate.ps1
python run_web.py
```

Before the first login, create the five initial users once through the API:

```powershell
$body = @{ users = @(@{
    username = "admin"
    email = "admin@xguard.local"
    password = "Choose-A-Strong-Password"
    full_name = "XGuard Administrator"
    role = "admin"
    department = "Platform Operations"
    is_active = $true
}) } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/users/seed" -ContentType "application/json" -Body $body
```

Submit up to five users with your own passwords. Suggested roles are `admin`, `maker`, `checker`, `executor`, and `auditor`; they initially have the same access to all XGuard features. The seed endpoint returns `409` and cannot change accounts after the first user exists.

- UI: http://localhost:5000
- API: http://localhost:8000
- Interactive API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Login: http://localhost:5000/login

## Project structure

```text
app/
  api/v1/       FastAPI endpoints
  core/         configuration and database setup
  models/       SQLAlchemy models and workflow enums
  schemas/      request/response schemas
  services/     business logic and integrations
  web/          Flask routes, templates, and static assets
docs/API.md     maintained API reference and examples
run_api.py      API entry point
run_web.py      UI entry point
```

See [docs/API.md](docs/API.md) for the supported API surface and Postman examples.

## Safety

Remote execution is restricted to reviewer-approved work packages. Command results are stored by the API, and a package can be completed only after recorded commands succeed. Use least-privilege target accounts and keep XGuard inside the appropriate management network.

AI token usage is accumulated on each work package after successful AI calls. The dashboard reports tokens actually used during the current UTC calendar month across all work packages.
