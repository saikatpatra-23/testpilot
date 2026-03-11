"""Map changed source files to their relevant test files."""
import re
from pathlib import Path


TEST_DIRS = ["tests", "test", "__tests__"]

# Component → route mapping for frontend
COMPONENT_ROUTE_MAP = {
    "controlscard": "/",
    "statuscard":   "/",
    "fundscard":    "/",
    "positionstable": "/",
    "login":        "/login",
    "dashboard":    "/dashboard",
    "search":       "/",
    "apply":        "/jobs",
    "home":         "/",
    "page":         "/",
}

# Extensions that indicate a Jest/frontend test file
JEST_TEST_PATTERNS = [
    "*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx",
    "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.spec.jsx",
]

# Extensions that indicate a pytest file
PYTEST_PATTERNS = ["test_*.py", "*_test.py"]


def find_all_test_files(root: str = ".") -> dict:
    """
    Return {"pytest": [...Path], "jest": [...Path]} discovered under root.
    Searches TEST_DIRS and also full tree for __tests__ folders.
    """
    root_p = Path(root)
    pytest_files: list[Path] = []
    jest_files: list[Path] = []

    # Search standard test dirs
    for d in TEST_DIRS:
        p = root_p / d
        if p.exists():
            for pat in PYTEST_PATTERNS:
                pytest_files += list(p.rglob(pat))
            for pat in JEST_TEST_PATTERNS:
                jest_files += list(p.rglob(pat))

    # Also search recursively for __tests__ folders anywhere in the tree
    for tests_dir in root_p.rglob("__tests__"):
        if tests_dir.is_dir():
            for pat in JEST_TEST_PATTERNS:
                for f in tests_dir.glob(pat):
                    if f not in jest_files:
                        jest_files.append(f)

    # And find *.test.* / *.spec.* co-located with source files (outside __tests__)
    for pat in JEST_TEST_PATTERNS:
        for f in root_p.rglob(pat):
            if f not in jest_files:
                jest_files.append(f)

    return {"pytest": list(set(pytest_files)), "jest": list(set(jest_files))}


def _stem_base(path: Path) -> str:
    """Return lowercase base stem stripping .test/.spec suffix: 'ControlsCard.test' → 'controlscard'."""
    stem = path.stem.lower()
    for suffix in (".test", ".spec"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def map_py_to_tests(changed_py: list[str], all_pytest: list[Path]) -> list[str]:
    """
    Map changed .py files → pytest test files.
    Strategy (in order):
      1. Exact stem match:    api/search.py → tests/test_search*.py
      2. Chain convention:    api/search.py → tests/test_chain_search.py
      3. Keyword substring:   "controls" in changed → tests/*controls*.py
    """
    matched: set[str] = set()
    for src in changed_py:
        stem = Path(src).stem.lower()
        for tf in all_pytest:
            tf_stem = tf.stem.lower()
            if (stem in tf_stem or
                    tf_stem in (f"test_{stem}", f"test_chain_{stem}", f"{stem}_test")):
                matched.add(str(tf))
    return sorted(matched)


def map_fe_to_tests(changed_fe: list[str], all_jest: list[Path]) -> tuple[list[str], dict]:
    """
    Map changed .tsx/.ts/.js/.jsx files → Jest test files.
    Returns (sorted_test_paths, file_mapping_dict).
    Strategy:
      1. Exact stem match: ControlsCard.tsx → ControlsCard.test.tsx
      2. Keyword substring match
    """
    matched: set[str] = set()
    mapping: dict[str, list[str]] = {}

    for src in changed_fe:
        src_stem = Path(src).stem.lower()
        src_matches: list[str] = []
        for tf in all_jest:
            tf_base = _stem_base(tf)
            if src_stem == tf_base or src_stem in tf_base or tf_base in src_stem:
                matched.add(str(tf))
                src_matches.append(str(tf))
        mapping[src] = sorted(src_matches)

    return sorted(matched), mapping


def map_frontend_to_routes(changed_frontend: list[str]) -> list[str]:
    """Map changed .tsx/.jsx files to page routes to Playwright-test."""
    routes: set[str] = set()
    for f in changed_frontend:
        key = Path(f).stem.lower()
        route = COMPONENT_ROUTE_MAP.get(key)
        if route:
            routes.add(route)
        else:
            routes.add("/")   # fallback
    return sorted(routes)


def resolve(changed_files: list[str], root: str = ".") -> dict:
    """
    Full mapping: changed files → {test_files, jest_files, routes, run_all, file_mapping}.
    Returns dict safe to pass directly to runner.
    """
    py  = [f for f in changed_files if f.endswith(".py")]
    fe  = [f for f in changed_files if f.endswith((".ts", ".tsx", ".js", ".jsx"))]
    infra = any(
        Path(f).name in ("requirements.txt", "package.json", "pyproject.toml", "setup.py", ".env")
        for f in changed_files
    )

    all_tests = find_all_test_files(root)

    pytest_files = map_py_to_tests(py, all_tests["pytest"])
    jest_files, fe_mapping = map_fe_to_tests(fe, all_tests["jest"])

    # Combined file_mapping for report: source → [test_files]
    file_mapping: dict[str, list[str]] = {}
    for src in py:
        stem = Path(src).stem.lower()
        file_mapping[src] = [t for t in pytest_files if stem in Path(t).stem.lower()]
    for src, tests in fe_mapping.items():
        file_mapping[src] = tests

    return {
        "changed":      changed_files,
        "changed_py":   py,
        "changed_fe":   fe,
        "test_files":   pytest_files,       # pytest files
        "jest_files":   jest_files,         # jest/RTL files
        "file_mapping": file_mapping,
        "routes":       map_frontend_to_routes(fe),
        "run_all":      infra,
        "has_backend":  bool(py),
        "has_frontend": bool(fe),
    }
