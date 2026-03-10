"""Run only the mapped test files via subprocess."""
import subprocess
import sys
import json
import os
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
    result = subprocess.run(cmd, capture_output=False)

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
        "exit_code":  result.returncode,
        "passed":     passed,
        "failed":     failed,
        "errors":     errors,
        "test_files": test_files,
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
    result = subprocess.run(["node", "run.js", script_path], cwd=skill_dir)
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
