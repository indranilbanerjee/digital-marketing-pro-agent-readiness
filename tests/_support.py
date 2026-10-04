"""Shared helpers for the test suite. Standard library only.

The tests import this as a top-level module (the tests folder has no
__init__.py), which works under both `python -m pytest tests` and
`python -m unittest discover -s tests`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # parity imports another checkout; never write into it

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "agent-readiness-audit"
SCRIPT = SKILL / "scripts" / "agent_readiness_audit.py"
SKILL_MD = SKILL / "SKILL.md"
README = ROOT / "README.md"
EXAMPLES = ROOT / "examples"


def read(path) -> str:
    return Path(path).read_text(encoding="utf-8")


def norm_eol(data: bytes) -> bytes:
    """Line endings may differ between a Windows working copy and a clone."""
    return data.replace(b"\r\n", b"\n")


def load_module(name: str, path, register: bool = True):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(*args, script=SCRIPT, cwd=None, env_extra=None, stdin=None):
    """Run a script as a subprocess, as a real caller would. Returns
    (returncode, stdout_text, stderr_text); output is decoded as UTF-8."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.update(env_extra or {})
    proc = subprocess.run([sys.executable, "-B", str(script), *[str(a) for a in args]],
                          input=stdin, capture_output=True, cwd=cwd, env=env, timeout=120)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def run_json(*args, script=SCRIPT, cwd=None):
    """run_script + parse stdout as JSON. Returns (data, returncode)."""
    code, out, err = run_script(*args, script=script, cwd=cwd)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = {"_raw_stdout": out, "_stderr": err}
    return data, code


# ---------------------------------------------------------------------------
# Small parsers shared by the SKILL.md, README and parity tests
# ---------------------------------------------------------------------------

def frontmatter(text: str):
    """(fields, body) for a SKILL.md. Only unindented `key: value` lines count."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    assert m, "SKILL.md must open with a --- frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if km:
            fields[km.group(1)] = km.group(2).strip()
    return fields, text[m.end():]


def crawler_rows(text: str):
    """Rows of the AI-crawler table in a SKILL.md: {token: (vendor, role_cell)}."""
    rows = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*`([A-Za-z-]+)`\s*\|(.*)\|\s*$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        rows[m.group(1)] = (cells[0], cells[1])
    return rows


def fenced_after(text: str, label_line: str) -> str:
    """Contents of the first fenced code block after the line equal to `label_line`."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = lines.index(label_line)
    i = start + 1
    while not lines[i].startswith("```"):
        i += 1
    i += 1
    block = []
    while not lines[i].startswith("```"):
        block.append(lines[i])
        i += 1
    return "\n".join(block) + "\n"
