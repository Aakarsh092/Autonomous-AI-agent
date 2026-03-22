# 🤖 Autonomous AI Agent — GitHub API Endpoint Extractor

An autonomous Python agent that accepts a GitHub repository URL as input, crawls its source files, extracts all REST API endpoints, and generates structured request/response schemas — without requiring the repository to be cloned locally.

Built for the **OWASP Juice Shop** repository as the primary target.

---

## 📋 Features

- **Zero-clone extraction** — Uses the GitHub REST API to fetch files on demand
- **Multi-strategy parsing**:
  - Express.js `app.get/post/put/delete/patch` route definitions
  - `router.*` middleware mounts
  - Frisby / Supertest API test files
  - OpenAPI / Swagger YAML and JSON specs
- **Schema inference** — Generates JSON Schema for request bodies, path parameters, query parameters, and responses based on endpoint semantics
- **Auth detection** — Detects `security.isAuthorized()`, `isAccounting()`, `denyAll()`, etc.
- **Dual output** — Produces both a structured **JSON report** and a human-readable **Markdown report**
- **Configurable** — Supports GitHub Personal Access Tokens for higher rate limits

---

## 🗂 Project Structure

```
juice-shop-api-agent/
├── main.py                  # CLI entry point
├── requirements.txt
├── src/
│   ├── agent.py             # Orchestration agent (fetches + dispatches)
│   ├── github_client.py     # GitHub REST API wrapper
│   ├── parser.py            # Multi-strategy endpoint parser + schema builder
│   └── reporter.py          # Markdown report generator
├── output/
│   ├── api_report.json      # Machine-readable output
│   └── api_report.md        # Human-readable output
└── tests/
    └── test_parser.py       # Unit tests for the parser
```

---

## ⚙️ Setup

### Requirements
- Python 3.10+ (uses `list[str]` and `|` union type hints)
- Internet access (to reach GitHub API)

### Install

```bash
git clone https://github.com/YOUR_USERNAME/juice-shop-api-agent.git
cd juice-shop-api-agent
pip install -r requirements.txt
```

---

## 🚀 Usage

### Basic (default target: OWASP Juice Shop)

```bash
python main.py
```

### With a specific GitHub URL

```bash
python main.py https://github.com/juice-shop/juice-shop
```

### With a GitHub token (recommended — avoids rate limiting)

```bash
python main.py https://github.com/juice-shop/juice-shop --token ghp_YOUR_TOKEN_HERE
```

### Custom output path and format

```bash
python main.py https://github.com/juice-shop/juice-shop \
  --output results/juice_shop \
  --format both \
  --token ghp_YOUR_TOKEN_HERE
```

### Output format options

| Flag | Description |
|------|-------------|
| `--format json` | JSON only |
| `--format markdown` | Markdown only |
| `--format both` | Both (default) |

---

## 📊 Output

### JSON Report (`output/api_report.json`)

```json
{
  "meta": {
    "repository": "https://github.com/juice-shop/juice-shop",
    "branch": "master",
    "extracted_at": "2026-03-21T10:00:00Z",
    "total_endpoints": 90
  },
  "summary": {
    "total_endpoints": 90,
    "by_method": { "GET": 50, "POST": 22, "PUT": 12, "DELETE": 6 },
    "by_tag": { "Users": 5, "Products": 5, "Feedbacks": 5 },
    "auth_required_count": 60
  },
  "endpoints": [
    {
      "method": "POST",
      "path": "/rest/user/login",
      "source_file": "server.ts",
      "line_number": 42,
      "description": "Create login",
      "tags": ["User", "Login"],
      "auth_required": false,
      "path_params": [],
      "query_params": [],
      "middlewares": [],
      "request_schema": {
        "type": "object",
        "properties": {
          "email": { "type": "string" },
          "password": { "type": "string" }
        },
        "required": ["email", "password"]
      },
      "response_schema": {
        "success": {
          "status": 201,
          "schema": {
            "type": "object",
            "properties": {
              "authentication": {
                "type": "object",
                "properties": {
                  "token": { "type": "string" },
                  "bid": { "type": "integer" },
                  "umail": { "type": "string" }
                }
              }
            }
          }
        },
        "error": { "status": 400, "schema": { "type": "object" } }
      }
    }
  ]
}
```

### Markdown Report (`output/api_report.md`)

The Markdown report includes:
- **Summary table** (total endpoints, method breakdown, tag breakdown)
- **Per-endpoint detail blocks** with auth badge (🔒), source file, line number, middlewares, and formatted schemas
- **Source file appendix**

---

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

---

## 🏗 How It Works

```
GitHub URL
    │
    ▼
GitHubClient.parse_repo_url()    → extract owner/repo
GitHubClient.get_default_branch()→ find branch (master/main)
GitHubClient.get_tree()          → fetch full recursive file tree
    │
    ▼  [file selection]
Agent._select_files()
  • Priority 1: server.ts, app.ts, routes.ts
  • Priority 2: any file with route/api/controller/handler/spec in path
  • Priority 3: other .ts/.js files (capped at 80)
    │
    ▼  [per-file parsing]
EndpointParser.parse_file()
  • Express routes   → regex on app.get/post/put/delete/patch
  • Middleware scan  → detect isAuthorized(), denyAll(), etc.
  • Schema inference → map endpoint semantics → JSON Schema
  • Frisby tests     → extract API calls from test specs
  • OpenAPI YAML/JSON→ structured spec parsing
    │
    ▼
Report Builder
  → JSON (machine-readable, integrable with Postman/OpenAPI tooling)
  → Markdown (human-readable documentation)
```

---

## 🔑 GitHub Token (Optional but Recommended)

Without a token: 60 API requests/hour.  
With a token: 5,000 API requests/hour.

Generate one at: https://github.com/settings/tokens  
Only `public_repo` read scope needed for public repositories.

---

## 📌 Notes

- Schema generation is **heuristic** — it infers field types from route naming conventions and known Juice Shop patterns. For production use, combine with runtime traffic capture for complete accuracy.
- The agent is designed to be **extensible**: add new `_parse_*` methods to `EndpointParser` to handle additional frameworks (e.g., Fastify, NestJS decorators, Spring annotations for Java repos).
- For very large repositories, use `--token` to avoid rate limiting.
