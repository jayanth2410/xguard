# Maker-Checker Enterprise Workflow Platform

A comprehensive platform for managing IT changes with AI-assisted creation, human review, dynamic validation, and controlled execution.

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   TRIGGER   │────▶│  AI MAKER   │────▶│   HUMAN     │────▶│ VALIDATION  │
│ (ServiceNow)│     │             │     │   CHECKER   │     │   AGENT     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                                                                    ▼
                                                            ┌─────────────┐
                                                            │  EXECUTOR   │
                                                            └─────────────┘
```

### Components

1. **AI Maker** - Intelligent agents that:
   - Analyze requirements and context
   - Generate code, scripts, and commands
   - Create implementation procedures
   - Perform change impact analysis (RAG: Red/Amber/Green)

2. **Human Checker** - Expert review gate for:
   - Code review and security scanning
   - Impact assessment
   - Execution control level approval (Automated/Manual)
   - Approve, reject, or request rework

3. **Validation Agent** - Dynamic context-aware validation:
   - Questions based on change type (Network, Server, Database, Cloud, etc.)
   - Interactive Q&A (not just yes/no)
   - Pre-execution confirmation
   - All questions must be answered before execution

4. **Executor** - Controlled change execution:
   - JIT (Just-In-Time) verification
   - Click-to-move execution
   - Real-time output capture
   - Automatic rollback on failure

## Change Types Supported

| Type | Examples | Validation Focus |
|------|----------|------------------|
| Network | Firewall, Router, Switch | Device hostname, ports, VLANs, NOC coordination |
| Server | VM, OS, Patching | Hostname, reboot requirements, affected services |
| Database | Schema, Config, Backup | Database details, tables, recovery options |
| Cloud | AWS, Azure, GCP | Account, region, resources, IAM |
| Application | Deploy, Config, Restart | Version, deployment strategy, health checks |
| Security | IAM, Cert, Firewall Rule | Security scope, approvals, audit trail |
| Container | K8s Pods, Deploy, Scale | Cluster, namespace, replicas |
| Monitoring | Alerts, Dashboards | System, alerts affected, on-call notification |

## Tech Stack

- **Backend API**: FastAPI (Python)
- **Web UI**: Flask with Tailwind CSS and Alpine.js
- **Database**: PostgreSQL with SQLAlchemy
- **Task Queue**: Celery with Redis
- **AI/LLM**: OpenAI/Anthropic integration ready

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL
- Redis (optional, for async tasks)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd MakerChecker
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

5. Initialize the database:
```bash
# Create PostgreSQL database
createdb makerchecker

# Tables are created automatically on first run
```

### Running the Application

**Start the API server (FastAPI):**
```bash
python run_api.py
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

**Start the Web UI (Flask):**
```bash
python run_web.py
# Web UI available at http://localhost:5000
```

## API Endpoints

### Work Packages
- `POST /api/v1/work-packages/` - Create work package
- `GET /api/v1/work-packages/` - List work packages
- `GET /api/v1/work-packages/{id}` - Get work package
- `PUT /api/v1/work-packages/{id}` - Update work package
- `POST /api/v1/work-packages/{id}/submit` - Submit for review
- `POST /api/v1/work-packages/{id}/generate` - Generate implementation with AI

### Reviews
- `GET /api/v1/reviews/pending` - Get pending reviews
- `POST /api/v1/reviews/{id}/start` - Start review
- `POST /api/v1/reviews/submit` - Submit review decision

### Validation
- `POST /api/v1/validation/session` - Create validation session
- `GET /api/v1/validation/session/{id}` - Get session details
- `GET /api/v1/validation/session/{id}/questions` - Get questions
- `POST /api/v1/validation/session/{id}/respond` - Submit response
- `GET /api/v1/validation/questions/{change_type}` - Get questions for change type

### Execution
- `POST /api/v1/execution/start` - Start execution
- `GET /api/v1/execution/{id}/status` - Get execution status
- `POST /api/v1/execution/{id}/complete` - Mark as complete

### Workflow
- `GET /api/v1/workflow/status/{id}` - Get workflow status
- `GET /api/v1/workflow/dashboard` - Get dashboard summary
- `GET /api/v1/workflow/audit/{id}` - Get audit trail

## Project Structure

```
MakerChecker/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── work_packages.py
│   │       ├── reviews.py
│   │       ├── validation.py
│   │       ├── execution.py
│   │       └── workflow.py
│   ├── core/
│   │   ├── config.py           # Settings
│   │   ├── database.py         # Database setup
│   │   └── validation_questions.py  # Dynamic questions
│   ├── models/
│   │   ├── database.py         # SQLAlchemy models
│   │   └── enums.py            # Enumerations
│   ├── schemas/                # Pydantic schemas
│   ├── services/
│   │   ├── maker_service.py
│   │   ├── checker_service.py
│   │   ├── validation_service.py
│   │   ├── execution_service.py
│   │   ├── audit_service.py
│   │   └── workflow_service.py
│   └── web/
│       ├── __init__.py         # Flask application
│       ├── routes.py
│       └── templates/          # HTML templates
├── requirements.txt
├── run_api.py                  # Run FastAPI
├── run_web.py                  # Run Flask
└── .env.example
```

## Workflow States

```
DRAFT → PENDING_REVIEW → IN_REVIEW → APPROVED → PENDING_VALIDATION
                              ↓                        ↓
                         REJECTED              VALIDATION_IN_PROGRESS
                              ↓                        ↓
                    REWORK_REQUIRED ←────────── VALIDATION_FAILED
                                                       ↓
                                                  VALIDATED
                                                       ↓
                                              PENDING_EXECUTION
                                                       ↓
                                                  EXECUTING
                                                       ↓
                                    ┌─────────────────┴─────────────────┐
                                    ↓                                   ↓
                               EXECUTED                          EXECUTION_FAILED
                                    ↓                                   ↓
                               COMPLETED                          ROLLED_BACK
```

## License

MIT License
