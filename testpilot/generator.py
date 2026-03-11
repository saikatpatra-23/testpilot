"""AI-powered test generator for TestPilot v0.2.

For each changed Python file that has no matching test, this module:
  1. Reads the source file and extracts top-level functions/classes via AST.
  2. Gets the raw git diff snippet for context.
  3. Prompts Claude to write pytest unit tests covering the changed code.
  4. Saves the generated test file under .testpilot_cache/.
"""
import ast
import subprocess
from pathlib import Path

from .ai_client import generate_text
from .impact import analyze_impact, format_impact_for_prompt


CACHE_DIR = ".testpilot_cache"

_SYSTEM = """\
You are an expert Python engineer who writes clean, idiomatic pytest unit tests.

## Non-negotiable rules
- Output ONLY the Python test file — no markdown fences, no explanations.
- Import the module under test using the path relative to the project root.
- Use pytest conventions: functions prefixed test_, clear assert statements.
- Each test must be independent and fully deterministic.
- Do not repeat source code in comments — focus on coverage and intent.

## External dependency mocking (CRITICAL)
- If the module imports requests, httpx, aiohttp, or any HTTP library → mock ALL HTTP calls
  with `unittest.mock.patch` or `responses` library. Never make real network calls in tests.
- If the module imports sqlite3, sqlalchemy, psycopg2, pymongo, or any DB driver →
  use an in-memory SQLite DB or mock the connection/cursor entirely.
- If the module imports subprocess → patch `subprocess.run` / `subprocess.Popen`.
- If the module imports anthropic, openai, or any AI SDK → mock the client and its methods.
- If the module imports boto3, supabase, or any cloud SDK → mock the client.
- For filesystem operations (open, Path.read_text, etc.) → use `tmp_path` fixture or patch.

## Integration-level tests
- When the Dependency & Impact Analysis section lists callers, also write at least one
  integration-style test that exercises the function through a realistic call chain,
  not just in isolation.
- For functions with multiple call sites, parameterize tests to cover varied inputs.
- Use descriptive test names: test_<function>_<scenario>_<expected_outcome>.
"""


def _get_diff_snippet(filepath: str, since: str = "HEAD") -> str:
    """Return the git diff for a single file (truncated to 120 lines for prompt safety)."""
    if not since:
        since = "HEAD"
    cmds = [
        ["git", "diff", since, "--", filepath],
        ["git", "diff", "--cached", "--", filepath],
        ["git", "diff", "--", filepath],
    ]
    for cmd in cmds:
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            snippet = (out.stdout or "").strip()
        except Exception:
            continue
        if snippet:
            lines = snippet.splitlines()
            return "\n".join(lines[:120])
    return ""


def _extract_public_symbols(source: str) -> list[str]:
    """Return names of top-level public functions and classes in the source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    symbols = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.append(node.name)
    return symbols


def _build_prompt(
    filepath: str,
    source: str,
    diff: str,
    symbols: list[str],
    impact_section: str = "",
) -> str:
    symbol_list = ", ".join(symbols) if symbols else "(all visible functions/classes)"
    diff_section = f"\n## Git diff\n```diff\n{diff}\n```\n" if diff else ""
    impact_block = f"\n{impact_section}\n" if impact_section else ""
    return f"""\
Generate pytest unit tests for the following Python module.

## File: {filepath}
## Public symbols to test: {symbol_list}
{diff_section}{impact_block}
## Source code
```python
{source}
```

Write a complete pytest test file that thoroughly covers the public API above.
Include integration-level tests and proper mocks for any external dependencies identified above.
"""


def generate_tests_for_file(
    filepath: str,
    since: str = "HEAD",
    cache_dir: str | None = None,
    verbose: bool = True,
) -> Path | None:
    """
    Generate a pytest file for `filepath` and save it to the cache directory.
    Returns the Path to the generated file, or None if the source couldn't be read.
    """
    src_path = Path(filepath)
    if not src_path.exists():
        if verbose:
            print(f"  [generate] Skipping {filepath} — file not found on disk.")
        return None

    source = src_path.read_text(encoding="utf-8", errors="replace")
    if not source.strip():
        return None

    diff = _get_diff_snippet(filepath, since)
    symbols = _extract_public_symbols(source)

    # v0.3: gather dependency & impact context
    cwd = str(Path(filepath).parent)
    impact = analyze_impact(filepath, root=".")
    impact_section = format_impact_for_prompt(impact)

    prompt = _build_prompt(filepath, source, diff, symbols, impact_section)

    if verbose:
        sym_display = ", ".join(symbols[:5]) + ("..." if len(symbols) > 5 else "")
        ext_display = f", external deps: {', '.join(impact.external_deps)}" if impact.external_deps else ""
        callers_count = sum(len(f.call_sites) for f in impact.functions)
        caller_display = f", {callers_count} call site(s)" if callers_count else ""
        print(f"  [generate] Generating tests for {filepath} ({sym_display or 'no public symbols'}{ext_display}{caller_display})")

    try:
        generated = generate_text(prompt, system=_SYSTEM)
    except Exception as exc:
        print(f"  [generate] ERROR calling Claude: {exc}")
        return None

    # Strip accidental markdown fences the model may include despite instructions
    lines = generated.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    clean = "\n".join(lines)

    # Save to cache
    out_dir = Path(cache_dir or CACHE_DIR)
    out_dir.mkdir(exist_ok=True)

    # Ensure pytest can import from the project root when running from cache dir
    conftest = out_dir / "conftest.py"
    if not conftest.exists():
        conftest.write_text(
            "import sys, os\n"
            "sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\n",
            encoding="utf-8",
        )

    out_name = f"test_{src_path.stem}.py"
    out_path = out_dir / out_name
    out_path.write_text(clean, encoding="utf-8")

    if verbose:
        print(f"  [generate] Saved -> {out_path}")

    return out_path.resolve()


def generate_missing_tests(
    changed_py: list[str],
    mapped_test_files: list[str],
    since: str = "HEAD",
    cache_dir: str | None = None,
    verbose: bool = True,
) -> list[str]:
    """
    For each changed Python file that has NO corresponding mapped test,
    call Claude to generate one. Returns paths of all newly generated test files.
    """
    # Determine which source files are truly unmapped
    unmapped = []
    for src in changed_py:
        stem = Path(src).stem.lower()
        has_test = any(stem in Path(t).stem.lower() for t in mapped_test_files)
        if not has_test:
            unmapped.append(src)

    if not unmapped:
        return []

    if verbose:
        print(f"\n  [AI Generate] No tests found for {len(unmapped)} file(s) — asking Claude to write them...")

    generated = []
    for src in unmapped:
        path = generate_tests_for_file(src, since=since, cache_dir=cache_dir, verbose=verbose)
        if path:
            generated.append(str(path))

    return generated
