# Aegis — Responsible AI Knowledge Assistant

Portfolio prototype demonstrating RAG concepts, responsible AI governance, human-in-the-loop decision design, and grounded LLM synthesis in a fictional law-firm setting.

## Deployment-safe portfolio version

This version adds:
- 500-character question limit
- in-memory rate limiting (8 requests/hour/IP by default)
- `/health` endpoint for hosting health checks
- server-side Anthropic API key only
- "How Aegis Works" architecture section
- knowledge-boundary refusal
- policy hierarchy and primary/supporting citations
- deterministic risk/action guardrails separate from Claude generation

> The in-memory rate limiter is appropriate for this small single-instance portfolio demo. A production enterprise deployment would use a shared datastore or API gateway for distributed rate limiting.

## Local run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

Local environment:
```powershell
$env:ANTHROPIC_API_KEY="YOUR_KEY"
$env:ANTHROPIC_MODEL="claude-sonnet-5"
```

## Render

This repository includes `render.yaml`.

When creating a Render Blueprint, Render will prompt for `ANTHROPIC_API_KEY` because it is declared with `sync: false`. Never put the API key in GitHub.

The service uses:
- build: `pip install -r requirements.txt`
- start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- health check: `/health`

All firm names, policies, tools, and scenarios are fictional. This prototype is not legal advice.
