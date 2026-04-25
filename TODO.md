# Project Jarvis - Roadmap

## ✅ Phase 9: UX + Prompt Overhaul (COMPLETE)

- [x] **TUI quality overhaul**
  - Upgraded terminal UI with richer status telemetry (elapsed time, counters, auth state)
  - Added better split-pane rendering with wrapped lines and improved scrolling ergonomics
  - Added robust slash-command workflow: session reset, focus switching, history cap, save/load/export, search
  - Added keyboard quality-of-life shortcuts (clear, toggle tools, clear input)

- [x] **System prompt overhaul**
  - Rebuilt prompt around strict execution standards and tool discipline
  - Added explicit coding/debugging quality bars for root-cause fixes and safe operations
  - Improved safety and homelab rules while preserving strict JSON tool-call protocol

- [x] **Test + docs refresh**
  - Extended TUI and prompt tests for new behavior contracts
  - Updated root/backend docs for new TUI capabilities and runtime prompt architecture

---

## ✅ Phase 1: Foundation (COMPLETE)

- [x] Authentication system (API keys + sessions)
- [x] Input validation (Pydantic schemas)
- [x] Rate limiting (per-IP throttling)
- [x] Structured logging (JSON format)
- [x] Error handling throughout
- [x] Test suite foundation
- [x] Core tool ecosystem (filesystem, terminal, Docker, systemd)
- [x] Comprehensive documentation

---

## ✅ Phase 2: Critical Fixes (COMPLETE)

These bugs could cause data loss or crashes in production.

- [x] **Fix thread safety race condition**
  - Wrap `_append_exchange()` in `agent/core.py` with `_HISTORY_LOCK`
  - Make history writes atomic (write-then-rename pattern)
  - Add corruption recovery on read

- [x] **Fix memory leaks**
  - Add background cleanup thread for expired rate limit buckets
  - Add session cleanup scheduler (not just on-access)
  - Implement max age purge for old history files

- [x] **Convert to true async**
  - Replace threading in `/stream` endpoint with proper `async`/`await`
  - Use `asyncio.to_thread()` for blocking operations
  - Fix LLM client to use async HTTP calls

- [x] **Bonus: Timing attack protection**
  - Use `secrets.compare_digest()` for API key comparison
  - Fix datetime deprecation warnings

---

## ✅ Phase 3: Production Hardening (COMPLETE)

Make it safe to expose to the internet or share with others.

### Security Hardening
- [x] Fix CORS configuration (restrict origins from env var)
- [x] Add CSRF protection tokens
- [x] HTML-escape tool results before streaming to client
- [x] Add output sanitization for XSS prevention
- [x] Implement symlink validation in filesystem tools

### Observability
- [x] Add Prometheus `/metrics` endpoint
  - Track: requests/sec, latency (p50/p95/p99), errors, tool usage
- [x] Add request ID to all logs
- [x] Implement distributed tracing headers
- [x] Add deep health checks (Ollama connectivity, disk space)

### Reliability
- [x] Add retry logic with exponential backoff (Ollama calls)
- [x] Implement circuit breaker for LLM failures
- [x] Add graceful shutdown handling
- [x] Implement request timeout middleware

---

## 📊 Phase 4: Scalability (2-3 weeks)

Support multiple users and horizontal scaling.

- [ ] **Redis integration**
  - Migrate rate limiting to Redis (distributed support)
  - Move sessions to Redis
  - Add history backup to Redis with TTL

- [ ] **Database migration**
  - SQLite for persistent history
  - User preferences and settings
  - Tool usage analytics

- [ ] **Worker pool configuration**
  - Multi-process Uvicorn workers
  - Shared state via Redis
  - Load balancer ready

- [ ] **Caching layer**
  - Cache API keys in memory (30 min TTL)
  - Cache environment detection results
  - LRU cache for frequent queries

---

## 🎯 Phase 5: Killer Features (3-4 weeks)

What makes Jarvis unique vs ChatGPT/Claude.

### Multi-Agent System
- [ ] Specialist agent framework
  - Security auditor (scans for vulnerabilities)
  - Cost optimizer (analyzes resource usage)
  - Debugger (analyzes errors + suggests fixes)
- [ ] Agent delegation (main agent spawns specialists)
- [ ] Parallel agent execution with result aggregation

### Homelab Specialization
- [ ] Proxmox API integration (VM management)
- [ ] TrueNAS API integration (storage management)
- [ ] Kubernetes tools (kubectl wrapper, pod logs, deployments)
- [ ] Network diagnostics (ping, traceroute, port scan)
- [ ] Service health monitoring dashboard
- [ ] Cost tracking (energy usage estimation)

### Workflow Automation
- [ ] Runbook save/replay system
  - Save successful tool sequences
  - One-click replay for common tasks
- [ ] Scheduled agents (cron-like execution)
- [ ] Webhook triggers (GitHub, Grafana alerts)
- [ ] No-code workflow builder UI (drag-and-drop)

---

## 🔌 Phase 6: Plugin Ecosystem (4-6 weeks)

Make it extensible for community contributions.

- [ ] Plugin SDK (Python decorators for custom tools)
- [ ] Plugin marketplace/registry
- [ ] Hot-reload for plugin development
- [ ] Custom LLM provider interface (OpenAI, Anthropic, local models)
- [ ] Tool sandboxing (separate process per plugin)
- [ ] Plugin permission system (declare required capabilities)

### Developer Tools
- [ ] VS Code extension (Jarvis in sidebar)
- [ ] CLI companion tool (`jarvis ask "..."`)
- [ ] Code indexing with embeddings (semantic search)
- [ ] Auto-documentation generation from code

---

## ✅ Phase 7: Intelligence (PARTIALLY COMPLETE)

Advanced AI capabilities.

- [x] **RAG for long-term memory**
  - ✅ SQLite vector database (semantic search via embeddings)
  - ✅ Index conversation history (every 10 exchanges)
  - ✅ Semantic search for context (top-3 retrieval)
  - ✅ Auto-inject memories into system prompt
  - Database: `~/.jarvis/memory.db`
  - Embedding model: `nomic-embed-text` (Ollama)
  - Storage: LLM summarization → embeddings → SQLite
  - Retrieval: Cosine similarity search (threshold > 0.5)

- [ ] **Learning system**
  - Track successful tool patterns
  - Learn user preferences
  - Suggest optimizations based on history

- [ ] **Advanced reasoning**
  - Test-driven development mode (write tests first)
  - Security scanner integration (automatic vuln detection)
  - Performance profiler integration
  - Self-correction on errors (retry with different approach)

---

## 🏢 Phase 8: Enterprise (Future)

If you want to offer this as a service.

- [ ] Multi-tenancy (org/team isolation)
- [ ] RBAC (roles: admin, operator, viewer)
- [ ] SSO integration (SAML, OIDC)
- [ ] Approval workflows for destructive actions
- [ ] Audit trail export (compliance logging)
- [ ] SLA monitoring and alerting
- [ ] White-label customization

---

## 🐛 Known Issues

### Critical
- Thread safety race condition in history persistence (Phase 2)
- Memory leaks in rate limiter and session cleanup (Phase 2)
- Blocking LLM calls in async endpoint (Phase 2)

### High
- CORS misconfigured (allow_origins=["*"])
- No CSRF protection
- No output sanitization (XSS risk)
- Plaintext API key comparison (timing attack)

### Medium
- Import pattern fragility (triple try/except chains)
- No retry logic for transient failures
- No rollback for failed operations
- Session/rate limit state lost on restart

### Low
- Test coverage only ~5-10%
- No pre-commit hooks
- No CI/CD pipeline

---

## 💡 Future Ideas (Backlog)

- Mobile app (React Native)
- Slack/Discord bot integration
- Email/SMS notifications for long-running tasks
- Model fine-tuning on user's codebase
- Collaborative sessions (screen sharing, multi-user)
- Time-travel debugging (replay requests)
- Infrastructure cost optimization AI
- Auto-scaling recommendations

---

## 📝 Development Notes

### Current Status
- **Maturity**: Early production (personal use ready)
- **Codebase**: ~2,300 LOC Python
- **Test Coverage**: ~5-10% (needs expansion)
- **Architecture**: Single-service FastAPI + Ollama

### Quick Commands
```bash
# Run tests
cd backend && pytest tests/ -v

# Start dev server
cd backend && python run.py

# Docker deployment
docker-compose up -d

# Check logs
docker-compose logs -f jarvis
```

### Configuration Priority
- Phase 2+: Set `CORS_ORIGINS` env var
- Phase 3: Enable `METRICS_ENABLED=true`
- Phase 4: Configure Redis via `REDIS_URL`

### Next Session Priorities
1. Expand test coverage around live streaming + tool error recovery in the TUI
2. Add optional keyboard shortcut customization for advanced operators
3. Improve prompt-evaluation harness with scenario-based regression tests
