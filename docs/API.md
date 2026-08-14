# XGuard API

Base URL: `http://localhost:8000/api/v1`

FastAPI also publishes live OpenAPI documentation at `http://localhost:8000/docs` and `http://localhost:8000/redoc`.

## Work packages

| Method | Path | Purpose |
|---|---|---|
| POST | `/work-packages/` | Create a work package |
| GET | `/work-packages/` | List packages; supports `status`, `change_type`, `ticket_id`, `page`, and `page_size` |
| GET | `/work-packages/{id}` | Get one package |
| PUT | `/work-packages/{id}` | Update editable package data |
| POST | `/work-packages/{id}/submit` | Submit generated package content for review |

Create example:

```json
{
  "ticket_id": "CHG0012345",
  "title": "Restart application service",
  "description": "Restart the service on the production application host.",
  "change_type": "server",
  "trigger_source": "manual",
  "execution_mode": "manual",
  "target_hosts": ["172.19.0.34"]
}
```

Updates use the same field names, but all fields are optional.

Work-package responses include `tokens_used`, the cumulative number of tokens reported by the AI provider for successful clarification and final-generation calls. The dashboard includes `tokens_used_this_month`, representing usage during the current UTC calendar month across all work packages.

## AI generation

| Method | Path | Purpose |
|---|---|---|
| POST | `/ai/generate-script` | Generate clarification questions or final implementation and rollback content |

Call the endpoint with package context. It generates final code immediately when the request is technically clear. If a required technical detail is genuinely missing, `ready_to_generate` is `false` and the response contains no more than three blocking `questions`; call it again with `question_responses`. Connection details and governance information are not clarification questions. The final result is persisted when `work_package_id` is provided.

```json
{
  "work_package_id": "72ca84ac-8c18-4ce3-bd08-03e7dfa0b6de",
  "change_type": "server",
  "title": "Restart application service",
  "description": "Restart the production service safely.",
  "target_hosts": ["172.19.0.34"],
  "platform": "linux",
  "question_responses": [
    {
      "question_id": "service_name",
      "question": "Which service should be restarted?",
      "answer": "nginx"
    }
  ]
}
```

## Reviews

| Method | Path | Purpose |
|---|---|---|
| GET | `/reviews/pending` | List packages waiting for review |
| POST | `/reviews/{work_package_id}/start?reviewer_id={uuid}` | Start a review |
| POST | `/reviews/submit?reviewer_id={uuid}` | Submit the review decision |
| GET | `/reviews/work-package/{work_package_id}` | Get review history |

Review submission example:

```json
{
  "work_package_id": "72ca84ac-8c18-4ce3-bd08-03e7dfa0b6de",
  "decision": "approved",
  "comments": "Approved for the maintenance window.",
  "code_review_notes": "Commands reviewed.",
  "rollback_review_notes": "Rollback is adequate.",
  "impact_review_notes": "Impact is acceptable.",
  "approved_execution_mode": "manual"
}
```

Valid decisions are `approved`, `rejected`, and `rework_required`.

## Execution

| Method | Path | Purpose |
|---|---|---|
| POST | `/execution/remote/test-connection` | Test SSH or WinRM connectivity |
| POST | `/execution/remote/execute` | Run one approved command and record its result |
| POST | `/execution/remote/execute-script` | Run an approved multiline script |
| POST | `/execution/{work_package_id}/complete` | Complete a successfully executed package |

Connection test example:

```json
{
  "host": "172.19.0.34",
  "port": 22,
  "username": "linuxadmin",
  "password": "replace-me",
  "private_key": "",
  "connection_type": "ssh"
}
```

Use `POST http://localhost:8000/api/v1/execution/remote/test-connection` in Postman with `Content-Type: application/json`. A private target IP is reachable only when XGuard is running inside, or connected to, that private network.

Single-command execution adds `work_package_id`, `command`, `timeout`, `is_rollback`, and `rollback_complete` to the connection fields. Normal execution requires reviewer approval. Rollback is allowed only after execution starts or fails.

When a work package has multiple target IPs, the Execution page tracks each target independently. The operator selects and executes one target at a time. If any target fails, further implementation execution is locked and full rollback runs sequentially against every configured target, including the failed target. Completion is enabled only after every target succeeds.

## Workflow and audit

| Method | Path | Purpose |
|---|---|---|
| GET | `/workflow/dashboard` | Dashboard counts and status summary |
| GET | `/workflow/audit/{work_package_id}` | Detailed package, review, execution-session, command, output, error, and rollback audit |
| GET | `/workflow/audit/{work_package_id}/timeline` | Package audit timeline |
| GET | `/workflow/audit/{work_package_id}/compliance` | Package compliance record |

Audit data is derived from `work_packages`, `reviews`, and `execution_records`.
Each recorded command includes its target host, complete command or script,
timestamp, exit code, standard output, standard error, success state, and whether
it was a rollback command.

## ServiceNow

| Method | Path | Purpose |
|---|---|---|
| GET | `/servicenow/test-connection` | Test configured ServiceNow access |
| GET | `/servicenow/lookup/{ticket_number}` | Find an exact New ticket across incidents, changes, and requests |
| GET | `/servicenow/ci-address/{ticket_number}` | Resolve the ticket's CI name, IP address, OS, and OS version from CMDB |
| GET | `/servicenow/incidents` | List incidents |
| GET | `/servicenow/incidents/pending` | List pending incidents |
| GET | `/servicenow/incidents/{number}` | Get incident details |
| GET | `/servicenow/changes` | List change requests |
| GET | `/servicenow/changes/pending` | List pending change requests |
| GET | `/servicenow/changes/{number}` | Get change details |
| GET | `/servicenow/requests` | List service requests |
| GET | `/servicenow/requests/{number}` | Get request details |
| POST | `/servicenow/import` | Import a record as a work package |

List endpoints accept `query`, `limit` (maximum 200), and `offset` where applicable. XGuard adds the New-state constraint directly to the ServiceNow encoded query before making the request: incidents use `state=1`, changes use `state=-5`, and service requests use `state=1`. Records in other states are not downloaded and filtered locally.

Import example:

```json
{
  "record_number": "INC0012345",
  "record_type": "incident",
  "change_type": "server"
}
```

`record_type` accepts `incident`, `change_request`, or `request`.

## Common responses

- `400` — invalid request or workflow action
- `404` — work package or external record not found
- `409` — action is not allowed from the current workflow status
- `422` — request body failed schema validation
- `502` — AI provider generation failed

Error bodies follow FastAPI's format:

```json
{
  "detail": "A clear description of the problem"
}
```

## Users and login

| Method | Path | Purpose |
|---|---|---|
| POST | `/users/seed` | Create the five initial users when the users table is empty |
| POST | `/users/login` | Verify an active user by username/email and password |

One-time seed request:

```json
{
  "users": [
    {
      "username": "admin",
      "email": "admin@xguard.local",
      "password": "Choose-A-Strong-Password",
      "full_name": "XGuard Administrator",
      "role": "admin",
      "department": "Platform Operations",
      "is_active": true
    }
  ]
}
```

Submit up to five users and assign each one its own password. Suggested roles are `admin`, `maker`, `checker`, `executor`, and `auditor`. Seeding is permanently rejected after any user exists. Login request:

```json
{
  "username": "admin",
  "password": "Choose-A-Strong-Temporary-Password"
}
```

The Flask UI creates its signed session only after this API verifies the credentials. Roles are recorded now, but all roles currently have access to every feature until authorization rules are configured.
