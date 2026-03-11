"""Run only the mapped test files via subprocess."""
import subprocess
import sys
import json
import os
import time
import tempfile
from pathlib import Path


def run_pytest(test_files: list[str], extra_args: list[str] = None) -> dict:
    """Run specific test files with pytest. Returns structured result."""
    if not test_files:
        return {"skipped": True, "reason": "No test files mapped to changed code"}

    report_path = Path(tempfile.gettempdir()) / "testpilot_report.json"
    cmd = [
        sys.executable, "-m", "pytest",
        "--tb=short", "-v",
        "--json-report",
        f"--json-report-file={report_path}",
    ] + (extra_args or []) + test_files

    print(f"\n  Running: pytest {' '.join(test_files)}")
    t0 = time.time()
    result = subprocess.run(
        cmd, capture_output=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    duration = round(time.time() - t0, 2)

    passed, failed, errors = [], [], []
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text())
            for t in data.get("tests", []):
                node = t["nodeid"]
                if t["outcome"] == "passed":
                    passed.append(node)
                elif t["outcome"] in ("failed", "error"):
                    longrepr = t.get("call", {}).get("longrepr", "")
                    failed.append(f"{node}\n    {str(longrepr)[:200]}")
        except Exception:
            pass

    return {
        "exit_code":        result.returncode,
        "passed":           passed,
        "failed":           failed,
        "errors":           errors,
        "test_files":       test_files,
        "duration_seconds": duration,
    }


def run_jest(test_files: list[str], cwd: str = ".") -> dict:
    """
    Run specific Jest test files via npx jest.
    Returns structured result with passed/failed counts.
    """
    if not test_files:
        return {"skipped": True, "reason": "No Jest test files mapped to changed code"}

    # Jest accepts specific file paths as positional args (or patterns)
    cmd = ["npx", "jest", "--no-coverage", "--forceExit"] + test_files

    print(f"\n  Running: jest {' '.join(test_files)}")
    t0 = time.time()
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=(os.name == "nt"),
    )
    duration = round(time.time() - t0, 2)

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    output = stdout + stderr

    # Parse Jest output for pass/fail counts
    passed: list[str] = []
    failed: list[str] = []
    errors: list[str] = []

    # Print output to console
    print(output)

    # Parse individual test results from verbose output (✓ / ✗ / ● lines)
    for line in output.splitlines():
        line_s = line.strip()
        if line_s.startswith(("✓", "✔", "√", "PASS", "pass")):
            passed.append(line_s)
        elif line_s.startswith(("✕", "✗", "×", "FAIL", "fail", "●")):
            failed.append(line_s)

    # Fallback: use regex to find summary line like "X passed, Y failed"
    import re
    m = re.search(r"(\d+) passed", output)
    if m and not passed:
        passed = [f"(jest: {m.group(1)} tests passed)"]
    m2 = re.search(r"(\d+) failed", output)
    if m2:
        count = int(m2.group(1))
        if count > 0 and not failed:
            failed = [f"(jest: {count} tests failed)"]

    return {
        "exit_code":        result.returncode,
        "passed":           passed,
        "failed":           failed,
        "errors":           errors,
        "test_files":       test_files,
        "duration_seconds": duration,
        "raw_output":       output[:2000],
    }


def run_all_tests(root: str = ".") -> dict:
    """Run the full test suite (non-targeted fallback)."""
    test_dirs = [d for d in ["tests", "test"] if (Path(root) / d).exists()]
    if not test_dirs:
        return {"skipped": True, "reason": "No tests/ directory found"}
    return run_pytest(test_dirs)


def run_frontend(routes: list[str], app_url: str = "http://localhost:3000") -> dict:
    """Run Playwright chain tests for specific routes."""
    skill_dir = "C:/Users/Student/.claude/skills/playwright-skill"
    if not Path(skill_dir).exists():
        return {"skipped": True, "reason": "Playwright skill not found"}

    script = _build_playwright_script(app_url, routes)
    script_path = str(Path(tempfile.gettempdir()) / "testpilot_playwright.js")
    Path(script_path).write_text(script, encoding="utf-8")

    print(f"\n  Running Playwright on routes: {routes}")
    result = subprocess.run(
        ["node", "run.js", script_path], cwd=skill_dir,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return {"exit_code": result.returncode, "routes": routes}


def _build_playwright_script(app_url: str, routes: list[str]) -> str:
    shots_dir  = str(Path(tempfile.gettempdir()) / "testpilot_screenshots").replace("\\", "/")
    results_fp = str(Path(tempfile.gettempdir()) / "testpilot_playwright_results.json").replace("\\", "/")
    routes_json = json.dumps(routes)

    return (
        "const { chromium } = require('playwright');\n"
        "const fs = require('fs');\n"
        "const SHOTS = '" + shots_dir + "';\n"
        "fs.mkdirSync(SHOTS, { recursive: true });\n"
        "const APP = '" + app_url + "';\n"
        "const ROUTES = " + routes_json + ";\n"
        "const results = { passed: [], failed: [] };\n"
        "(async () => {\n"
        "  const browser = await chromium.launch({ headless: false });\n"
        "  const page = await browser.newPage();\n"
        "  const calls = [];\n"
        "  page.on('request', r => {\n"
        "    if (r.url().includes('/api/')) calls.push(r.method() + ' ' + r.url().split('/api/')[1]);\n"
        "  });\n"
        "  for (const route of ROUTES) {\n"
        "    calls.length = 0;\n"
        "    try {\n"
        "      await page.goto(APP + route, { waitUntil: 'domcontentloaded', timeout: 12000 });\n"
        "      await page.waitForTimeout(1500);\n"
        "      const slug = route.replace(/[^a-z0-9]/gi, '_') || 'home';\n"
        "      await page.screenshot({ path: SHOTS + '/' + slug + '.png', fullPage: true });\n"
        "      results.passed.push(route + ' [chain: ' + calls.join(' -> ') + ']');\n"
        "      console.log('  PASS ' + route + '  chain: ' + calls.join(' -> '));\n"
        "    } catch(e) {\n"
        "      results.failed.push(route + ': ' + e.message.split('\\n')[0]);\n"
        "      console.log('  FAIL ' + route + ': ' + e.message.split('\\n')[0]);\n"
        "    }\n"
        "  }\n"
        "  await browser.close();\n"
        "  fs.writeFileSync('" + results_fp + "', JSON.stringify(results));\n"
        "  process.exit(results.failed.length > 0 ? 1 : 0);\n"
        "})();\n"
    )
