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


def find_all_test_files(root: str = ".") -> list[Path]:
    tests = []
    for d in TEST_DIRS:
        p = Path(root) / d
        if p.exists():
            tests += list(p.rglob("test_*.py"))
            tests += list(p.rglob("*_test.py"))
            tests += list(p.rglob("test_*.js"))
    return tests


def map_py_to_tests(changed_py: list[str], root: str = ".") -> list[str]:
    """
    Map changed .py files to test files.
    Strategy (in order):
      1. Exact name match:   api/search.py → tests/test_search*.py
      2. Chain convention:   api/search.py → tests/test_chain_search.py
      3. Keyword in test:    "controls" in changed → tests/*controls*.py
    """
    all_tests = find_all_test_files(root)
    matched = set()

    for src in changed_py:
        stem = Path(src).stem.lower()   # e.g. "search", "controls"
        for tf in all_tests:
            tf_stem = tf.stem.lower()
            if (stem in tf_stem or
                    tf_stem in (f"test_{stem}", f"test_chain_{stem}", f"{stem}_test")):
                matched.add(str(tf))

    return sorted(matched)


def map_frontend_to_routes(changed_frontend: list[str]) -> list[str]:
    """Map changed .tsx/.jsx files to page routes to test."""
    routes = set()
    for f in changed_frontend:
        key = Path(f).stem.lower()
        route = COMPONENT_ROUTE_MAP.get(key)
        if route:
            routes.add(route)
        else:
            routes.add("/")   # fallback: test homepage
    return sorted(routes)


def resolve(changed_files: list[str], root: str = ".") -> dict:
    """
    Full mapping: changed files → {test_files, routes, run_all}.
    Returns dict safe to pass directly to runner.
    """
    py   = [f for f in changed_files if f.endswith(".py")]
    fe   = [f for f in changed_files if f.endswith((".ts", ".tsx", ".js", ".jsx"))]
    infra = any(Path(f).name in
                ("requirements.txt", "package.json", "pyproject.toml", "setup.py", ".env")
                for f in changed_files)

    return {
        "changed":      changed_files,
        "changed_py":   py,
        "changed_fe":   fe,
        "test_files":   map_py_to_tests(py, root),
        "routes":       map_frontend_to_routes(fe),
        "run_all":      infra,
        "has_backend":  bool(py),
        "has_frontend": bool(fe),
    }
