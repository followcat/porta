# Porta

Porta is a single-node control plane for SSH local port forwards (`ssh -L`). It provides a web UI and REST API for managing tunnel definitions, encrypting SSH credentials, supervising `ssh` subprocesses, and tracking runtime state, retries, events, and audit history.

This repository targets operators who need to manage a set of stable SSH forwards without depending on shell history, ad-hoc `autossh` sessions, or handwritten systemd units.

## Highlights

- Centralized tunnel inventory with start, stop, restart, and probe actions
- Password and private-key credential storage with AES-256-GCM encryption
- Background supervisor loop with health checks, backoff, and retry handling
- FastAPI JSON API under `/api/v1`
- Server-rendered admin UI built with Jinja2, HTMX, and Alpine.js
- Event and audit trails for operational debugging

## Tech Stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- MySQL 8+
- Jinja2 + HTMX + Alpine.js

## What Porta Manages

A tunnel in Porta maps directly to an SSH local forward:

```bash
ssh -N -L <bind_address>:<local_port>:<remote_host>:<remote_port> -p <ssh_port> <username>@<ssh_host>
```

Example:

```bash
ssh -N -L 0.0.0.0:24786:127.0.0.1:8086 -p 3008 developer@bigdata.intl-alphaleader.cn
```

Porta stores this as:

- `ssh_host`: `bigdata.intl-alphaleader.cn`
- `ssh_port`: `3008`
- `bind_address`: `0.0.0.0`
- `local_port`: `24786`
- `remote_host`: `127.0.0.1`
- `remote_port`: `8086`

## Architecture

The application uses a layered structure:

```text
API routes -> Services -> Repositories -> SQLAlchemy models -> MySQL
```

Key runtime components:

- `app/services/credential_service.py`: encrypt/decrypt SSH credentials
- `app/services/ssh_command_builder.py`: build safe `ssh` / `sshpass` argv lists
- `app/supervisor/manager.py`: background reconciliation loop
- `app/supervisor/worker.py`: per-tunnel process lifecycle and state transitions
- `app/web/`: admin UI templates and static assets

## Requirements

- Python `3.12+`
- MySQL `8+`
- OpenSSH client available on the host
- `sshpass` installed if you plan to use password-based SSH authentication

## Quick Start

1. Create and activate a virtual environment.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Copy the example environment file.

```bash
cp .env.example .env
```

4. Edit `.env` and set at least:

- `SECRET_KEY`
- `PORTA_MASTER_KEY`
- `MYSQL_DSN`

5. Initialize the database schema.

```bash
./scripts/init_db.sh
```

6. Create the first admin user.

```bash
python scripts/create_admin.py --username admin
```

7. Start the development server.

```bash
./scripts/dev.sh
```

Then open `http://127.0.0.1:8000/login`.

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Session signing key for the admin UI |
| `PORTA_MASTER_KEY` | Master encryption key for sensitive credential fields |
| `PORTA_MASTER_KEY_VERSION` | Key version marker stored with encrypted payloads |
| `MYSQL_DSN` | SQLAlchemy connection string for MySQL |
| `SSH_BIN` | Path to the system `ssh` executable |
| `SSHPASS_BIN` | Path to `sshpass` for password auth mode |
| `SUPERVISOR_LOOP_SECONDS` | Interval for the background reconciliation loop |
| `TUNNEL_STARTUP_GRACE_SECONDS` | Minimum initial startup wait used by the supervisor |
| `SESSION_COOKIE_NAME` | Cookie name for authenticated admin sessions |
| `AUTO_CREATE_TABLES` | Development helper; normally keep `false` and use Alembic |

See `.env.example` for defaults.

## API Overview

Base prefix: `/api/v1`

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET/POST /api/v1/credentials`
- `GET/PUT/DELETE /api/v1/credentials/{id}`
- `GET/POST /api/v1/tunnels`
- `GET/PUT/DELETE /api/v1/tunnels/{id}`
- `POST /api/v1/tunnels/{id}/start`
- `POST /api/v1/tunnels/{id}/stop`
- `POST /api/v1/tunnels/{id}/restart`
- `POST /api/v1/tunnels/{id}/probe`
- `GET /api/v1/tunnels/{id}/events`
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/audit`

## Development

Run the full test suite:

```bash
pytest
```

Create a new database migration:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Security Notes

- Porta never stores SSH passwords, passphrases, or private keys in plaintext.
- Password-based SSH is supported for compatibility, but key-based authentication is preferred.
- Using `0.0.0.0` as `bind_address` exposes the local forward to the network. Use it only when shared access is intended.

## Current Scope

This repository is intentionally focused on the single-node deployment model:

- Supported: local forwards (`ssh -L`)
- Not yet supported: reverse tunnels, SOCKS proxy mode, multi-agent deployment, HA coordination

## License

No license file is included yet. Choose and add a license before publishing the repository publicly if you want others to reuse the code.
