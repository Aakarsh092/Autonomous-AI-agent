# Autonomous-AI-agent

An autonomous AI agent that takes a GitHub repository link as input and extracts all API endpoints along with their request/response schemas.

Built and tested on the OWASP Juice Shop repository.

---

## How to Run

**1. Clone the repository**

```bash
git clone https://github.com/Aakarsh092/Autonomous-AI-agent.git
cd Autonomous-AI-agent
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Run the agent**

```bash
python main.py https://github.com/juice-shop/juice-shop
```

**4. Check the output**

Once it finishes, two files will be generated inside the `output/` folder:

- `api_report.json` — all endpoints with schemas in JSON format
- `api_report.md` — human readable version of the same report

---

## Optional — GitHub Token

Without a token the GitHub API is limited to 60 requests per hour. For large repos this can cause rate limiting. To avoid it, pass your token like this:

```bash
python main.py https://github.com/juice-shop/juice-shop --token YOUR_GITHUB_TOKEN
```

You can generate a token from your GitHub settings under Developer Settings → Personal Access Tokens. Only the `public_repo` scope is needed.
