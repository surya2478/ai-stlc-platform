"""
Code Analysis Agent (GAP-3)
Parses a GitHub repository (cloned via git) or a local directory tree and
derives structured software requirements from the source code.

Pipeline:
  1. Collect source files (Python / JS / TS / Java / Go) — respects language
     filter and skips hidden / dependency dirs.
  2. For each file, run a lightweight static extraction:
       - Module / file docstring
       - Public function signatures + docstrings
       - Class names + class-level docstrings
       - REST endpoint decorators (@router.get, @app.post, express routes …)
  3. Group files into logical chunks (≤ 80 kB each to stay within LLM context).
  4. Send each chunk to the LLM to derive structured requirements.
  5. Collect all requirements; return via BaseAgent result protocol.

Edge cases:
  - Repos > 500 MB are rejected before cloning.
  - Private repos require a PAT in github_token.
  - Local paths that don't exist or aren't readable are skipped.
  - Binary / generated / vendor files are excluded.
  - LLM failures on individual chunks are logged and skipped (partial result).
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.base.base_agent import BaseAgent
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output

# ── Constants ──────────────────────────────────────────────────────────────────

_MAX_REPO_BYTES = 500 * 1024 * 1024  # 500 MB
_MAX_CHUNK_BYTES = 60 * 1024          # 60 KB — safe LLM context per chunk
_MAX_FILES = 500                       # stop collecting after this many files
_SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".mypy_cache", ".tox", "target", "vendor", "Pods", ".gradle",
}
_LANGUAGE_EXTS: dict[str, list[str]] = {
    "python":     [".py"],
    "javascript": [".js", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx"],
    "java":       [".java"],
    "go":         [".go"],
}
_DERIVE_SYSTEM = """\
You are a senior QA/business analyst. You receive a summary of source-code \
constructs (module docstrings, public functions with signatures and docstrings, \
class definitions, and REST endpoint routes) extracted from one or more files \
of a software project.

Your task: derive a list of structured software requirements that the code \
implements or exposes.  Each requirement should represent ONE testable \
behaviour, feature, API contract, or business rule.

Return ONLY a valid JSON object in this exact shape:
{
  "requirements": [
    {
      "title": "<short imperative sentence>",
      "summary": "<2-4 sentence description of the behaviour>",
      "acceptance_criteria": ["<criterion 1>", "<criterion 2>", ...],
      "business_rules": ["<rule>"],
      "user_roles": ["<role>"],
      "systems_impacted": ["<system>"],
      "apis": ["<endpoint or function signature>"],
      "risks": ["<risk>"],
      "telecom_domain": null,
      "risk_level": "Medium",
      "test_phase": "SIT",
      "source_file": "<relative path>"
    }
  ]
}

Guidelines:
- One requirement per distinct function / endpoint / behaviour.
- Merge trivial getters/setters into a single CRUD requirement.
- Do NOT invent requirements not evidenced by the code.
- risk_level must be one of: Critical, High, Medium, Low.
- test_phase must be one of: SIT, UAT, Regression, NFT, Production_Validation.
- telecom_domain may be null or one of: Mobile, Fixed, Digital, Billing, Charging,
  CRM, OSS, BSS, Middleware, Integration, Network, Data.
- Output ONLY the JSON. No markdown fences, no explanation.
"""


# ── Static extraction helpers ──────────────────────────────────────────────────

def _extract_python(source: str, rel_path: str) -> str:
    """Extract Python module docstring, public classes, and public functions."""
    lines: list[str] = [f"# File: {rel_path}"]
    try:
        tree = ast.parse(source)
    except SyntaxError:
        lines.append(f"# (parse error — raw first 2000 chars)\n{source[:2000]}")
        return "\n".join(lines)

    # Module docstring
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        lines.append(f'"""\n{mod_doc[:800]}\n"""')

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            args = [a.arg for a in node.args.args]
            sig = f"def {node.name}({', '.join(args)})"
            doc = ast.get_docstring(node)
            lines.append(sig + (f'\n    """{doc[:400]}"""' if doc else ""))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            doc = ast.get_docstring(node)
            lines.append(f"class {node.name}:" + (f'\n    """{doc[:400]}"""' if doc else ""))

    # FastAPI / Flask / Starlette route decorators
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                dec_src = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                if any(kw in dec_src for kw in ("router.", "app.", "blueprint.")):
                    lines.append(f"# ROUTE: @{dec_src} → {node.name}")
    return "\n".join(lines)


def _extract_js_ts(source: str, rel_path: str) -> str:
    """Best-effort extraction for JS/TS: JSDoc comments, exports, Express routes."""
    lines: list[str] = [f"// File: {rel_path}"]
    # JSDoc blocks
    for m in re.finditer(r"/\*\*(.*?)\*/", source, re.DOTALL):
        block = m.group(1).strip()
        lines.append(f"/** {block[:500]} */")
    # exported function / class / const
    for m in re.finditer(
        r"export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)",
        source,
    ):
        lines.append(f"export {m.group(1)}")
    # Express-style routes
    for m in re.finditer(
        r"(?:router|app)\.(get|post|put|patch|delete|use)\s*\(\s*['\"]([^'\"]+)['\"]",
        source,
    ):
        lines.append(f"// ROUTE: {m.group(1).upper()} {m.group(2)}")
    return "\n".join(lines)


def _extract_generic(source: str, rel_path: str) -> str:
    """Generic extraction: first 3000 chars for Java / Go etc."""
    return f"// File: {rel_path}\n{source[:3000]}"


def _extract_file(path: Path, rel_path: str) -> str:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _extract_python(source, rel_path)
    if suffix in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        return _extract_js_ts(source, rel_path)
    return _extract_generic(source, rel_path)


# ── File collection ────────────────────────────────────────────────────────────

def _allowed_exts(languages: list[str]) -> set[str]:
    exts: set[str] = set()
    for lang in languages:
        exts.update(_LANGUAGE_EXTS.get(lang.lower().strip(), []))
    return exts or {".py", ".js", ".ts"}  # default if unknown


def _collect_files(root: Path, languages: list[str]) -> list[Path]:
    exts = _allowed_exts(languages)
    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune hidden / dependency dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in exts:
                collected.append(fpath)
                if len(collected) >= _MAX_FILES:
                    return collected
    return collected


def _chunk_files(files: list[Path], root: Path) -> list[str]:
    """Group extracted summaries into chunks of ≤ _MAX_CHUNK_BYTES."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_size = 0
    for fpath in files:
        rel = str(fpath.relative_to(root))
        extracted = _extract_file(fpath, rel)
        if not extracted.strip():
            continue
        size = len(extracted.encode("utf-8"))
        if current_size + size > _MAX_CHUNK_BYTES and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_size = 0
        current_parts.append(extracted)
        current_size += size
    if current_parts:
        chunks.append("\n\n".join(current_parts))
    return chunks


# ── Clone helper ───────────────────────────────────────────────────────────────

def _clone_repo(github_url: str, branch: str, token: str | None, dest: Path) -> None:
    """Clone a GitHub repo into *dest*.  Raises RuntimeError on failure."""
    # Inject PAT into URL for private repos
    if token:
        # https://github.com/org/repo → https://TOKEN@github.com/org/repo
        clone_url = github_url.replace("https://", f"https://{token}@")
    else:
        clone_url = github_url

    cmd = [
        "git", "clone",
        "--depth", "1",
        "--branch", branch,
        "--single-branch",
        clone_url,
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed: {result.stderr[:500] or result.stdout[:500]}"
        )


def _repo_size_bytes(path: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fname in filenames:
            try:
                total += (Path(dirpath) / fname).stat().st_size
            except OSError:
                pass
    return total


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class CodeAnalysisAgentResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    logs: list[dict] = field(default_factory=list)


# ── Agent ──────────────────────────────────────────────────────────────────────

class CodeAnalysisAgent(BaseAgent):
    """
    GAP-3: Derives structured requirements from a GitHub repo or local directory.
    """

    async def run(
        self,
        source: str,               # "github" | "local"
        project_id: int = 0,
        source_label: str = "github_repo",
        # GitHub params
        github_url: str | None = None,
        github_branch: str = "main",
        github_token: str | None = None,
        github_subpath: str | None = None,
        # Local params
        local_path: str | None = None,
        # Shared
        languages: list[str] | None = None,
    ) -> CodeAnalysisAgentResult:
        self._logs.clear()
        languages = languages or ["python", "javascript", "typescript"]
        tmp_dir: str | None = None

        try:
            # ── 1. Resolve the root directory ─────────────────────────────────
            if source == "github":
                if not github_url:
                    return CodeAnalysisAgentResult(
                        success=False, error="github_url is required"
                    )
                self.log("info", "clone", f"Cloning {github_url} branch={github_branch}")
                tmp_dir = tempfile.mkdtemp(prefix="gap3_repo_")
                try:
                    _clone_repo(github_url, github_branch, github_token, Path(tmp_dir))
                except (RuntimeError, subprocess.TimeoutExpired) as exc:
                    return CodeAnalysisAgentResult(
                        success=False, error=f"Clone failed: {exc}"
                    )
                root = Path(tmp_dir)
                if github_subpath:
                    sub_root = root / github_subpath
                    if not sub_root.exists() or not sub_root.is_dir():
                        return CodeAnalysisAgentResult(
                            success=False,
                            error=f"GitHub subdirectory not found in repository: {github_subpath}",
                        )
                    root = sub_root
            else:
                if not local_path:
                    return CodeAnalysisAgentResult(
                        success=False, error="local_path is required"
                    )
                root = Path(local_path)
                if not root.exists() or not root.is_dir():
                    return CodeAnalysisAgentResult(
                        success=False, error=f"local_path not found: {local_path}"
                    )

            # ── 2. Size check ─────────────────────────────────────────────────
            repo_size = _repo_size_bytes(root)
            self.log("info", "size", f"Repository size: {repo_size / 1024 / 1024:.1f} MB")
            if repo_size > _MAX_REPO_BYTES:
                return CodeAnalysisAgentResult(
                    success=False,
                    error=f"Repository is too large ({repo_size // 1024 // 1024} MB > 500 MB limit)",
                )

            # ── 3. Collect + chunk source files ───────────────────────────────
            files = _collect_files(root, languages)
            self.log("info", "collect", f"Collected {len(files)} source files for languages={languages}")
            if not files:
                return CodeAnalysisAgentResult(
                    success=False,
                    error=f"No source files found for languages: {languages}. Check the repository path and language filter.",
                )

            chunks = _chunk_files(files, root)
            self.log("info", "chunk", f"Split into {len(chunks)} LLM chunks")

            # ── 4. LLM derivation per chunk ───────────────────────────────────
            llm = get_llm()
            all_requirements: list[dict] = []
            repo_display = github_url or str(local_path)
            if github_url and github_subpath:
                repo_display = f"{github_url}/tree/{github_branch}/{github_subpath}"

            for idx, chunk in enumerate(chunks):
                self.log("info", "llm", f"Processing chunk {idx + 1}/{len(chunks)}")
                prompt = (
                    f"Repository: {repo_display}\n"
                    f"Languages: {', '.join(languages)}\n\n"
                    f"--- SOURCE CODE SUMMARY ---\n{chunk}\n--- END ---"
                )
                try:
                    raw = await llm.generate(
                        system=_DERIVE_SYSTEM,
                        user=prompt,
                        temperature=0.2,
                        max_tokens=3000,
                    )
                    parsed = _parse_json(raw)
                    chunk_reqs = parsed.get("requirements", [])
                    # Tag each requirement with the source type
                    for r in chunk_reqs:
                        r["_source_label"] = source_label
                        r["_repo_url"] = github_url
                        r["_repo_subpath"] = github_subpath
                        r["_local_path"] = local_path
                    all_requirements.extend(chunk_reqs)
                    self.log("info", "llm", f"Chunk {idx + 1}: derived {len(chunk_reqs)} requirements")
                except Exception as exc:  # noqa: BLE001
                    self.log("warning", "llm_error", f"Chunk {idx + 1} failed: {exc}")
                    continue

            self.log("info", "done", f"Total requirements derived: {len(all_requirements)}")
            if not all_requirements:
                warning_messages = [
                    entry["message"]
                    for entry in self._logs
                    if entry.get("level") == "warning"
                ]
                error_detail = "; ".join(warning_messages[:3])
                return CodeAnalysisAgentResult(
                    success=False,
                    error=(
                        "Code analysis produced no requirements."
                        + (f" {error_detail}" if error_detail else "")
                    ),
                    data={
                        "requirements": [],
                        "count": 0,
                        "source": source,
                        "source_label": source_label,
                        "repo_url": github_url,
                        "repo_subpath": github_subpath,
                        "local_path": local_path,
                        "file_count": len(files),
                        "chunk_count": len(chunks),
                    },
                    logs=list(self._logs),
                )
            return CodeAnalysisAgentResult(
                success=True,
                data={
                    "requirements": all_requirements,
                    "count": len(all_requirements),
                    "source": source,
                    "source_label": source_label,
                    "repo_url": github_url,
                    "repo_subpath": github_subpath,
                    "local_path": local_path,
                    "file_count": len(files),
                    "chunk_count": len(chunks),
                },
                logs=list(self._logs),
            )

        finally:
            # Always clean up cloned temp dir
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            source=input_data.get("source", "github"),
            project_id=input_data.get("project_id", 0),
            source_label=input_data.get("source_label", "github_repo"),
            github_url=input_data.get("github_url"),
            github_branch=input_data.get("github_branch", "main"),
            github_token=input_data.get("github_token"),
            github_subpath=input_data.get("github_subpath"),
            local_path=input_data.get("local_path"),
            languages=input_data.get("languages", ["python", "javascript", "typescript"]),
        )
        if not result.success:
            raise RuntimeError(result.error or "Code analysis failed")
        return result.data



def _parse_json(raw: str) -> dict:
    """Extract and parse the first JSON object from an LLM response."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    # Find the outermost { ... }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return {}
