from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="ReAct + Reflexion Agent", version="1.0.0")
origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class RunRequest(BaseModel):
    task: str = Field(min_length=5, max_length=4000)
    max_attempts: int = Field(default=4, ge=1, le=6)
    timeout_seconds: int = Field(default=5, ge=1, le=10)

class Attempt(BaseModel):
    number: int
    code: str
    stdout: str
    stderr: str
    exit_code: int | None
    success: bool
    duration_ms: int
    reflection: str = ""

class RunResponse(BaseModel):
    task: str
    success: bool
    attempts_used: int
    final_output: str
    summary: str
    attempts: list[Attempt]

SYSTEM_PROMPT = """You write Python 3 code to solve a user's task.
Return ONLY executable Python source code. No markdown fences, no explanations.
The code must print useful results to stdout. Keep it self-contained and deterministic.
Do not use network, subprocess, sockets, file access, imports except standard-library
math, statistics, json, re, datetime, collections, itertools, functools, decimal.
Never attempt to inspect environment variables or the host. Avoid infinite loops.
"""

def groq_chat(messages: list[dict[str, str]], temperature: float = 0.1) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key == "replace_me":
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is missing. Set it in backend/.env and restart the API.")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": temperature},
            timeout=45.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise HTTPException(status_code=502, detail=f"Groq API error ({exc.response.status_code}): {detail}")
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not get a valid response from Groq: {exc}")

def strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:python)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

ALLOWED_IMPORTS = {
    "math", "statistics", "json", "re", "datetime", "collections",
    "itertools", "functools", "decimal"
}
BLOCKED_CALLS = {"eval", "exec", "compile", "open", "input", "__import__", "breakpoint"}
BLOCKED_NAMES = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil", "ctypes",
    "multiprocessing", "threading", "asyncio", "requests", "httpx", "urllib",
    "builtins", "importlib"
}

def validate_code(code: str) -> str | None:
    max_bytes = int(os.getenv("MAX_CODE_BYTES", "20000"))
    if len(code.encode("utf-8")) > max_bytes:
        return f"Generated code exceeds {max_bytes} bytes."
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "SyntaxError:\n" + traceback.format_exc()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            bad = [n for n in names if n not in ALLOWED_IMPORTS]
            if bad:
                return f"Blocked import(s): {', '.join(bad)}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            return f"Blocked call: {node.func.id}()"
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            return f"Blocked name: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"Blocked dunder attribute: {node.attr}"
    return None

def execute_restricted(code: str, timeout_seconds: int) -> dict[str, Any]:
    issue = validate_code(code)
    if issue:
        return {"stdout": "", "stderr": issue, "exit_code": 2, "success": False, "duration_ms": 0}
    start = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="react_agent_") as temp_dir:
            script = Path(temp_dir) / "agent_code.py"
            script.write_text(code, encoding="utf-8")
            # env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [sys.executable,  str(script)],
                cwd=temp_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            stdout = completed.stdout[-12000:]
            stderr = completed.stderr[-12000:]
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": completed.returncode,
                "success": completed.returncode == 0,
                "duration_ms": int((time.perf_counter() - start) * 1000),
            }
    except subprocess.TimeoutExpired as exc:
        return {
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds.",
            "exit_code": 124,
            "success": False,
            "duration_ms": int((time.perf_counter() - start) * 1000),
        }
    except Exception:
        return {
            "stdout": "",
            "stderr": traceback.format_exc()[-12000:],
            "exit_code": 1,
            "success": False,
            "duration_ms": int((time.perf_counter() - start) * 1000),
        }

def generate_code(task: str, previous_code: str = "", error: str = "", history: list[dict[str, str]] | None = None) -> str:
    history_text = ""
    for item in (history or [])[-3:]:
        history_text += f"\nAttempt {item['number']}:\nCODE:\n{item['code'][:5000]}\nERROR/OUTPUT:\n{item['feedback'][:3000]}\n"
    user_prompt = f"""USER TASK:
{task}

PREVIOUS CODE (may be empty):
{previous_code or '(none)'}

LATEST EXECUTION ERROR OR OBSERVATION:
{error or '(none; this is the first attempt)'}

PRIOR ATTEMPT HISTORY:
{history_text or '(none)'}

Repair the code based on the actual traceback/observation. Do not repeat a known failed approach.
Return the complete replacement Python program only. Print the final answer/result.
"""
    return strip_fences(groq_chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]))

def verify_task(task: str, output: str, code: str) -> tuple[bool, str]:
    # A second model judgment is useful but heuristic; it is not a formal proof.
    answer = groq_chat([
        {"role": "system", "content": "You are a strict task verifier. Respond as JSON only: {\"complete\": true/false, \"reason\": \"short reason\"}. Mark complete only if the stdout plausibly contains the requested result. Do not execute code."},
        {"role": "user", "content": f"TASK:\n{task}\nSTDOUT:\n{output[:6000]}\nCODE:\n{code[:6000]}"},
    ], temperature=0)
    try:
        parsed = json.loads(strip_fences(answer))
        return bool(parsed.get("complete")), str(parsed.get("reason", "No reason provided"))[:500]
    except Exception:
        return False, "Verifier response was not valid JSON."

@app.get("/health")
def health():
    return {"ok": True, "provider": "groq", "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")}

@app.post("/api/run", response_model=RunResponse)
def run_agent(request: RunRequest):
    attempts: list[Attempt] = []
    history: list[dict[str, str]] = []
    code = ""
    feedback = ""
    final_output = ""
    summary = "Maximum attempts reached without verified completion."
    success = False

    for number in range(1, request.max_attempts + 1):
        code = generate_code(request.task, code, feedback, history)
        execution = execute_restricted(code, request.timeout_seconds)
        reflection = ""
        if execution["success"]:
            final_output = execution["stdout"].strip()
            verified, reason = verify_task(request.task, final_output, code)
            reflection = f"Verifier: {reason}"
            if verified:
                success = True
                summary = "Execution succeeded and the verifier judged the task complete."
            else:
                summary = "Code ran, but task completion was not verified."
                feedback = (
                    "The program exited successfully but task completion is not verified.\n"
                    f"Verifier feedback: {reason}\nStdout:\n{final_output}"
                )
        else:
            feedback = f"Exit code: {execution['exit_code']}\nSTDERR/TRACEBACK:\n{execution['stderr']}\nSTDOUT:\n{execution['stdout']}"
            reflection = "Execution failed; traceback/output will be fed into the next generation prompt."

        attempts.append(Attempt(
            number=number,
            code=code,
            stdout=execution["stdout"],
            stderr=execution["stderr"],
            exit_code=execution["exit_code"],
            success=execution["success"],
            duration_ms=execution["duration_ms"],
            reflection=reflection,
        ))
        history.append({
            "number": str(number),
            "code": code,
            "feedback": feedback if not execution["success"] or not success else "Verified complete.",
        })
        if success:
            break
        if execution["success"] and not feedback:
            feedback = f"Program output:\n{final_output}\nPlease ensure the output directly answers the task."

    if not final_output and attempts:
        final_output = attempts[-1].stdout.strip()
    return RunResponse(
        task=request.task,
        success=success,
        attempts_used=len(attempts),
        final_output=final_output,
        summary=summary,
        attempts=attempts,
    )
