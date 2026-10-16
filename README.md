# ReAct + Reflexion Self-Correcting Python Agent

Full-stack demo: React (Vite) frontend + FastAPI backend + Groq API code generation + retry/reflection loop.

## Requirements
- Python 3.10+
- Node.js 20+
- A Groq API key from https://console.groq.com/
- Optional: Docker (recommended for stronger isolation)

> Security note: this project uses a restricted subprocess prototype, not a hardened security sandbox. Generated code is untrusted. Run it only on a disposable/local machine with no secrets or sensitive files. For real multi-user deployment, execute code inside a locked-down container/VM with network disabled, resource limits, read-only filesystem, and no host mounts.

## Setup

### 1. Backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```
Edit `backend/.env` and set `GROQ_API_KEY=...`. On macOS/Linux use `cp .env.example .env`.

Start API:
```bash
uvicorn app.main:app --reload --port 8000
```
Health endpoint: http://localhost:8000/health

### 2. Frontend
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open the URL Vite prints, usually http://localhost:5173.

## Demo
The UI includes a demo task. Click **Run agent**. To test repair, use a task that requires a calculation and set a small retry limit; actual failures depend on model output.

## API
`POST /api/run`
```json
{
  "task": "Calculate the mean of [4, 8, 10] and print it.",
  "max_attempts": 4
}
```
`GET /health`

## Design
- ReAct: plan/generate → act (execute) → observe output.
- Reflexion: include traceback + prior attempts in the next code-generation prompt.
- Logs: each attempt includes code, stdout, stderr, exit code, and status.
- Verification: an LLM checks whether output appears to satisfy the task; treat this as heuristic, not proof.
- Guardrails: timeout, code-size limit, bounded retries, restricted environment, and blocked dangerous AST patterns. These checks are defense-in-depth only; they do not make arbitrary Python safe.

## Troubleshooting
- `GROQ_API_KEY is missing`: set it in `backend/.env`, then restart API.
- CORS: frontend dev server is allowed at `http://localhost:5173`.
- Groq model errors: set `GROQ_MODEL` to a model available in your Groq account.
- Windows subprocess: the backend creates a temporary script and invokes the configured Python executable with a timeout.
