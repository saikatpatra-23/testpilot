"""
Dependency impact analysis for TestPilot v0.3.

For each changed Python file:
  - Extract all public function/method names via AST.
  - Search the project for call sites using git grep.
  - Detect external system dependencies (network, DB, subprocess, etc.).
  - Return structured impact report for use in test generation prompts.
"""
import ast
import subprocess
from pathlib import Path
from dataclasses import dataclass, field


# External module roots that require mocking in tests
EXTERNAL_MODULES = {
    # HTTP / network
    "requests", "httpx", "aiohttp", "urllib", "urllib3",
    # Databases
    "sqlite3", "psycopg2", "sqlalchemy", "pymongo", "motor", "asyncpg", "aiomysql",
    # Cloud / services
    "boto3", "botocore", "supabase",
    # Message queues / caches
    "redis", "pika",
    # Subprocess
    "subprocess",
    # AI APIs
    "anthropic", "openai",
}


@dataclass
class CallSite:
    file: str
    line: int
    snippet: str


@dataclass
class FunctionImpact:
    name: str
    filepath: str
    call_sites: list[CallSite] = field(default_factory=list)
    callers: list[str] = field(default_factory=list)


@dataclass
class FileImpact:
    filepath: str
    functions: list[FunctionImpact] = field(default_factory=list)
    external_deps: list[str] = field(default_factory=list)
    has_external: bool = False


def extract_public_functions(source: str) -> list[str]:
    """Return all public function/method names (including Class.method) from source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not child.name.startswith("_"):
                        names.append(f"{node.name}.{child.name}")
    return names


def detect_external_deps(source: str) -> list[str]:
    """Return sorted list of external module roots imported by the source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in EXTERNAL_MODULES:
                    deps.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in EXTERNAL_MODULES:
                    deps.add(root)
    return sorted(deps)


def find_call_sites(func_name: str, root: str = ".") -> list[CallSite]:
    """Search Python files in the project for call sites of func_name using git grep."""
    # For Class.method names, search only the method part
    search_name = func_name.split(".")[-1]

    try:
        result = subprocess.run(
            ["git", "grep", "-n", "--", search_name],
            cwd=root,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout or ""
    except Exception:
        return []

    sites: list[CallSite] = []
    for line in output.splitlines():
        # git grep format: filepath:lineno:content
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        filepath, lineno, snippet = parts[0], parts[1], parts[2]
        if not filepath.endswith(".py"):
            continue
        # Only count actual call sites (function invocation syntax)
        if f"{search_name}(" in snippet or f"{search_name} (" in snippet:
            sites.append(CallSite(
                file=filepath,
                line=int(lineno) if lineno.isdigit() else 0,
                snippet=snippet.strip()[:200],
            ))
    return sites[:10]  # cap per function to keep prompt size manageable


def analyze_impact(filepath: str, root: str = ".") -> FileImpact:
    """Full impact analysis for a single changed Python file."""
    src_path = Path(filepath)
    if not src_path.exists():
        return FileImpact(filepath=filepath)

    source = src_path.read_text(encoding="utf-8", errors="replace")
    func_names = extract_public_functions(source)
    external_deps = detect_external_deps(source)

    functions: list[FunctionImpact] = []
    for name in func_names:
        sites = find_call_sites(name, root=root)
        callers = sorted(set(s.file for s in sites if s.file != filepath))
        functions.append(FunctionImpact(
            name=name,
            filepath=filepath,
            call_sites=sites,
            callers=callers,
        ))

    return FileImpact(
        filepath=filepath,
        functions=functions,
        external_deps=external_deps,
        has_external=bool(external_deps),
    )


def format_impact_for_prompt(impact: FileImpact) -> str:
    """Render an impact analysis as a Markdown prompt section."""
    if not impact.functions and not impact.external_deps:
        return ""

    lines: list[str] = ["## Dependency & Impact Analysis"]

    if impact.external_deps:
        lines.append(
            f"\n### External systems detected: `{', '.join(impact.external_deps)}`\n"
            "→ You MUST mock/stub these in every test that exercises code paths touching them.\n"
            "  Use `unittest.mock.patch` or `pytest-mock` as appropriate."
        )

    funcs_with_sites = [f for f in impact.functions if f.call_sites]
    if funcs_with_sites:
        lines.append("\n### Call-site analysis (where changed functions are consumed):")
        for func in funcs_with_sites:
            lines.append(f"\n**`{func.name}`** is called from:")
            for site in func.call_sites[:5]:
                lines.append(f"  - `{site.file}:{site.line}` → `{site.snippet}`")
            if func.callers:
                lines.append(
                    f"  _Caller modules_: {', '.join(func.callers)}\n"
                    "  → Consider adding integration-level tests that test this function "
                    "as a component within its callers' context."
                )

    return "\n".join(lines)
