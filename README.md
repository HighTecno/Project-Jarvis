# Project Jarvis

An AI-powered coding and homelab assistant with tool-calling capabilities.

## Features

- 🤖 **LLM Provider Choice** - Run with Ollama or Google (Gemma models supported)
- 🛠️ **Tool System** - Filesystem, terminal, Docker, systemd integration
- 🧠 **Skill System** - Add reusable skill playbooks (Claude Code-style workflows)
- 🏠 **Homelab Management** - Manage Docker services, logs, and Tailscale
- 🔒 **Security** - Authentication, rate limiting, input validation
- 📊 **Observability** - Structured logging, metrics ready
- 🌐 **Web UI** - Clean chat interface with streaming responses
- 🐳 **Docker Ready** - Full containerization with docker-compose

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Ollama running locally (if using `LLM_PROVIDER=ollama`) or a Google API key (if using `LLM_PROVIDER=google`)
- Python 3.12+ (for local development)

### Installation

1. **Clone and configure:**
```bash
git clone https://github.com/HighTecno/Project-Jarvis.git
cd Project-Jarvis
cp .env.example .env
# Edit .env with your settings
```

2. **Start with Docker Compose:**
```bash
docker-compose up -d
# You might have to add the --build flag to the command above
```

3. **Get your API key:**
```bash
docker-compose logs jarvis | grep "API key:"
# Or check ~/.jarvis/api_keys.txt on the host
```

4. **Access the UI:**
```
http://localhost:8000/static/
```

Add your API key as a Bearer token in the UI settings.

## Configuration

### Environment Variables

See `.env.example` for all configuration options.

**Key Settings:**

- `AUTH_ENABLED` - Enable/disable authentication (default: true)
- `RATE_LIMIT_ENABLED` - Enable/disable rate limiting (default: true)
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `LLM_PROVIDER` - LLM backend to use (`ollama` or `google`)
- `OLLAMA_MODEL` - Which Ollama model to use (default: qwen2.5-coder:7b)
- `GOOGLE_API_KEY` - Required when using `LLM_PROVIDER=google`
- `GOOGLE_MODEL` - Google model name (default: gemma-4-26b-it)
- `SKILLS_ENABLED` - Enable/disable custom skills (default: true)
- `SKILLS_FILE` - JSON file storing custom skills (default: ~/.jarvis/skills.json)

### Authentication

Authentication is **enabled by default**. On first run, an API key is generated and stored in `~/.jarvis/api_keys.txt`.

**Add more API keys:**
```bash
echo "your-new-key-here" >> ~/.jarvis/api_keys.txt
```

**Disable auth** (not recommended for production):
```bash
export AUTH_ENABLED=false
```

### Rate Limiting

Default: 60 requests per 60-second window per client IP.

Configure in `.env`:
```bash
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```

## Development

### Local Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Run Locally

```bash
cd backend
python run.py
```

### Run Terminal UI (TUI)

```bash
cd backend
python run.py --tui --url http://127.0.0.1:8000
```

TUI highlights:
- Split chat/tool panes with focus switching
- Slash commands for session management (`/help`, `/status`, `/history`, `/savechat`, `/loadchat`, `/export`)
- Built-in follow-up suggestions and streaming telemetry

### Run Tests

```bash
cd backend
pytest tests/ -v
```

## API Endpoints

### `POST /query`
Synchronous query endpoint.

**Request:**
```json
{
  "prompt": "List files in /workspace",
  "history": []  // optional
}
```

**Response:**
```json
{
  "response": "Here are the files...",
  "rate_limit": {
    "remaining": 55,
    "reset_in": 42
  }
}
```

### `POST /stream`
Streaming query endpoint with SSE (Server-Sent Events).

**Events:**
- `thinking` - Agent is processing
- `tool_call` - Tool is being executed
- `tool_result` - Tool execution result
- `final` - Final response
- `error` - Error occurred

### `GET /health`
Health check endpoint.

## Security Features

✅ **Input Validation** - Pydantic schemas for all tool arguments  
✅ **Authentication** - API key-based auth with session tokens  
✅ **Rate Limiting** - Per-IP request throttling  
✅ **Safe Execution** - Dangerous command blocking in terminal  
✅ **Path Validation** - Prevent directory traversal attacks  
✅ **Audit Logging** - Structured JSON logs for all actions  

## Architecture

```
Project-Jarvis/
├── backend/
│   ├── agent/          # Agent loop & LLM interaction
│   ├── tools/          # Tool implementations
│   ├── tests/          # Test suite
│   ├── static/         # Web UI
│   ├── auth.py         # Authentication
│   ├── validation.py   # Input validation
│   ├── rate_limit.py   # Rate limiting
│   ├── logger.py       # Structured logging
│   ├── main.py         # FastAPI app
│   └── config.py       # Configuration
├── docker-compose.yaml
└── .env
```

## Homelab Integration

Jarvis can manage your homelab services via Docker and systemd.

**Available tools:**
- `homelab.docker_logs` - View service logs
- `homelab.docker_status` - Check service status
- `homelab.docker_restart` - Restart services
- `homelab.docker_list` - List all containers
- `homelab.systemd_status` - Check systemd units
- `homelab.systemd_logs` - View systemd logs

Services are expected at `/hostroot/root/<service-name>/` with their own `docker-compose.yaml`.

## Troubleshooting

### "Authentication failed"
Check that you're sending the API key as a Bearer token:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8000/health
```

### "Rate limit exceeded"
Wait for the window to reset or increase limits in `.env`:
```bash
RATE_LIMIT_REQUESTS=120
```

### "LLM timeout"
Increase timeout or disable it:
```bash
LLM_TIMEOUT_SECONDS=300
LLM_TIMEOUT_ENABLED=true
```

### Check logs
```bash
docker-compose logs -f jarvis
```

## Roadmap

- [ ] Multi-agent orchestration
- [ ] Plugin system
- [ ] RAG for long-term memory
- [ ] Enhanced homelab integrations (Proxmox, k8s)
- [ ] VS Code extension
- [ ] Fine-tuning on codebase

## Contributing

1. Fork the repo
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

MIT License - see LICENSE file for details

---

## Pentest Module (hackai integration)

Jarvis includes a pentesting capability powered by a Kali Linux sidecar container.

### Setup

1. Copy the pentest config template:
```bash
cp pentest_config.example.yaml /path/to/workspace/pentest_config.yaml
# Edit target_whitelist to match your lab scope
```

2. Start with the Kali sidecar:
```bash
docker-compose up -d
```

3. Install Kali tools (one-time):
```bash
docker exec kali apt-get update && apt-get install -y nmap nikto hydra sqlmap curl
```

### Available tools

| Tool | Description |
|------|-------------|
| `pentest.shell_exec` | Run recon/low-risk commands inside Kali |
| `pentest.shell_exec_confirmed` | Run high-risk commands (user must confirm first) |
| `pentest.search_cve` | Search NVD + OSV.dev for CVEs by keyword or CVE-ID |
| `pentest.save_finding` | Save a finding with automatic CVE enrichment |
| `pentest.list_findings` | List all findings in the current session |
| `pentest.summarize_session` | Full session summary with findings and command history |

### Scope enforcement

All commands are checked against `target_whitelist` in `pentest_config.yaml` before execution. Commands with a risk score ≥ `confirm_threshold` (default 7) are blocked and must be re-submitted via `pentest.shell_exec_confirmed`. Recon commands (`nmap`, `ping`, `dig`, etc.) are always unrestricted.

### Session logs

Markdown logs are written to `PENTEST_LOGS_DIR` (default `/workspace/pentest_logs/`) with one file per day.
