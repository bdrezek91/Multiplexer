#!/usr/bin/env python3
"""One-page Claude Code Pro shadow OCR, explicitly initiated by account owner.

Uses the UNMODIFIED official Claude Code CLI authenticated by the owner.
No Anthropic API key, no production document mutation, no daemon/automatic dispatch.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/var/tmp/multiplekser_claude_shadow")
IMAGE = ROOT / "page1.jpg"
PROMPT = ROOT / "prompt.txt"
RESULT = ROOT / "result.json"
REPORT = ROOT / "report.json"


def main(page: int = 1) -> int:
    if page not in (1, 2, 3):
        print("Dopuszczalne tylko trzy przygotowane strony: 1, 2, 3.")
        return 2
    image = ROOT / f"page{page}.jpg" if page != 1 else IMAGE
    report_file = ROOT / f"report_page{page}.json" if page != 1 else REPORT
    if not image.is_file() or not PROMPT.is_file():
        print("Brak testowej strony JPG lub promptu w prywatnym katalogu.")
        return 2
    os.umask(0o077)
    env = dict(os.environ)
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        env.pop(key, None)
    command = [
        "claude", "--print", "--restricted", "--strict-mcp-config",
        "--disable-slash-commands", "--tools", "Read",
        "--allowedTools", "Read", "--model", "sonnet", "--effort", "low",
        "--max-turns", "3", "--no-session-persistence",
        "--output-format", "json", PROMPT.read_text(encoding="utf-8").replace(str(IMAGE), str(image)),
    ]
    try:
        run = subprocess.run(
            command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=240, check=False,
        )
    except subprocess.TimeoutExpired:
        print("Claude timeout 240 s - niczego nie zmieniono w produkcji.")
        return 3
    except FileNotFoundError:
        print("Brak oficjalnego programu Claude Code w PATH.")
        return 4
    if run.stderr.strip():
        print("CLI:", run.stderr.strip()[:180])
    try:
        envelope = json.loads(run.stdout)
    except json.JSONDecodeError:
        print("Claude nie zwrocil poprawnej koperty JSON. EXIT=", run.returncode)
        return 5
    if run.returncode != 0 or envelope.get("is_error"):
        info = str(envelope.get("result") or "")
        if "OAuth session expired" in info or "Login expired" in info:
            print("Claude Pro: sesja wygasla. Na VPS uruchom: claude auth login")
        else:
            print("Claude nieudany:", info[:240], "EXIT", run.returncode)
        return 6
    output = str(envelope.get("result") or "").strip()
    if output.startswith("!!!"):
        print("Unexpected CLI format")
        return 7
    if output.startswith("```"):
        output = re.sub(r"^\x60{3}(?:json)?\s*", "", output)
        output = re.sub(r"\s*\x60{3}$", "", output)
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        print("Claude zwrocil tekst, ale niepoprawny JSON; niczego nie zapisano.")
        return 8
    rows = parsed.get("pozycje", []) if isinstance(parsed, dict) else []
    if not isinstance(rows, list):
        print("Claude nie zwrocil tablicy pozycji.")
        return 9
    report = {
        "status": "shadow_only",
        "model": "claude-sonnet",
        "pages": 1,
        "page_index": page,
        "positions": len(rows),
        "ocr": parsed,
        "num_turns": envelope.get("num_turns"),
        "usage": envelope.get("usage"),
    }
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_file.chmod(0o600)
    print("CLAUDE_SHADOW_SUCCESS page=", page, "positions=", len(rows))
    for item in rows[:12]:
        print("ROW", str(item.get("nazwa", ""))[:55], item.get("ilosc_wydana"), item.get("ilosc_zuzyta"))
    print("Report saved in", report_file, "(permissions 600)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Pro: reczny benchmark strony 1-3")
    parser.add_argument("--page", type=int, default=1, choices=(1, 2, 3))
    args = parser.parse_args()
    sys.exit(main(args.page))
