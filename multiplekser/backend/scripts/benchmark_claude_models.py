#!/usr/bin/env python3
"""Manual Claude Pro OCR benchmark: identical image and prompt, vary model and effort.

No paid Anthropic API key, no output to production, no automatic retries.
The official Claude Code CLI is invoked read-only with a single local image.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path("/var/tmp/multiplekser_claude_shadow")
PROMPT = ROOT / "prompt.txt"
MODELS = {"haiku", "sonnet", "opus"}
EFFORTS = {"low", "medium", "high"}


def run_one(model: str, effort: str, page: int) -> int:
    if model not in MODELS or effort not in EFFORTS or page not in (1, 2, 3):
        print("Unknown model/effort/page")
        return 2
    image = ROOT / f"page{page}.jpg"
    if not image.is_file() or not PROMPT.is_file():
        print("Missing test input")
        return 3
    out_dir = ROOT / "bench"
    out_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(out_dir, 0o700)
    result_path = out_dir / f"{model}_{effort}_page{page}.json"
    if result_path.exists():
        print("ALREADY_TESTED:", result_path)
        return 0
    prompt = PROMPT.read_text(encoding="utf-8").replace(
        str(ROOT / "page1.jpg"), str(image)
    )
    env = dict(os.environ)
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"):
        env.pop(key, None)
    cmd = [
        "claude", "--print", "--restricted", "--strict-mcp-config",
        "--disable-slash-commands", "--tools", "Read", "--allowedTools", "Read",
        "--model", model, "--effort", effort,
        "--max-turns", "3", "--no-session-persistence",
        "--output-format", "json", prompt,
    ]
    started = time.perf_counter()
    try:
        response = subprocess.run(
            cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=180, check=False,
        )
    except subprocess.TimeoutExpired:
        print("TIMEOUT model", model, "effort", effort, "page", page)
        return 4
    duration = round(time.perf_counter() - started, 1)
    try:
        envelope = json.loads(response.stdout)
    except json.JSONDecodeError:
        print("INVALID_ENVELOPE", model, effort, page, "exit", response.returncode,
              "stderr", response.stderr[:180])
        return 5
    answer = str(envelope.get("result") or "").strip()
    if response.returncode or envelope.get("is_error"):
        print("MODEL_ERROR", model, effort, page, "time", duration, "error", answer[:250])
        return 6
    if answer.startswith("```"):
        answer = re.sub(r"^\x60{3}(?:json)?\s*", "", answer)
        answer = re.sub(r"\s*\x60{3}$", "", answer)
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        print("INVALID_OCR_JSON", model, effort, page, duration, "preview", answer[:180])
        return 7
    rows = parsed.get("pozycje") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        print("MISSING_POSITIONS", model, effort, page, duration)
        return 8
    report = {
        "model_alias": model, "effort": effort, "page": page,
        "seconds": duration, "positions": len(rows),
        "num_turns": envelope.get("num_turns"),
        "model_usage": [
            {"model": str(k)} for k in (envelope.get("modelUsage") or {})
        ],
        "ocr": parsed,
    }
    os.umask(0o077)
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    result_path.chmod(0o600)
    print("BENCH_OK", model, effort, "page", page, "positions", len(rows),
          "seconds", duration, "model_usage", report["model_usage"],
          "report", result_path, flush=True)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=sorted(MODELS), required=True)
    p.add_argument("--effort", choices=sorted(EFFORTS), required=True)
    p.add_argument("--page", type=int, choices=(1, 2, 3), default=2)
    a = p.parse_args()
    sys.exit(run_one(a.model, a.effort, a.page))
