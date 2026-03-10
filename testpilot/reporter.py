"""Generate report.md and report.json from run results."""
import json
from datetime import datetime
from pathlib import Path


def generate(results: dict, output_dir: str = ".") -> tuple[str, str]:
    """
    Write report.json and report.md to output_dir.
    Returns (json_path, md_path).
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ── JSON ────────────────────────────────────────────────────────────────
    report = {
        "timestamp":   ts,
        "since":       results.get("since", "HEAD"),
        "changed":     results.get("changed", []),
        "test_files":  results.get("test_files", []),
        "passed":      results.get("passed", []),
        "failed":      results.get("failed", []),
        "errors":      results.get("errors", []),
        "frontend":    results.get("frontend"),
        "exit_code":   results.get("exit_code", 0),
        "summary": {
            "total":  len(results.get("passed", [])) + len(results.get("failed", [])),
            "passed": len(results.get("passed", [])),
            "failed": len(results.get("failed", [])),
        }
    }
    json_path = out / "testpilot_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ── Markdown ─────────────────────────────────────────────────────────────
    passed = report["summary"]["passed"]
    failed = report["summary"]["failed"]
    status = "✅ PASSED" if failed == 0 else "❌ FAILED"

    lines = [
        f"# TestPilot Report — {status}",
        f"**{ts}** | diff since `{report['since']}`",
        "",
        f"| | Count |",
        f"|---|---|",
        f"| ✅ Passed | {passed} |",
        f"| ❌ Failed | {failed} |",
        f"| Total | {report['summary']['total']} |",
        "",
    ]

    if report["changed"]:
        lines += ["## Changed Files", ""]
        for f in report["changed"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report["test_files"]:
        lines += ["## Tests Run", ""]
        for f in report["test_files"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report["failed"]:
        lines += ["## ❌ Failures", ""]
        for f in report["failed"]:
            lines.append(f"```\n{f}\n```")
        lines.append("")

    if report["passed"]:
        lines += ["## ✅ Passed Tests", ""]
        for p in report["passed"]:
            lines.append(f"- `{p}`")
        lines.append("")

    fe = report.get("frontend")
    if fe and not fe.get("skipped"):
        lines += ["## Frontend (Playwright)", ""]
        exit_code = fe.get("exit_code", 0)
        routes = fe.get("routes", [])
        lines.append(f"Routes tested: {', '.join(routes) or 'none'}")
        lines.append(f"Result: {'✅ Passed' if exit_code == 0 else '❌ Failed'}")
        lines.append("")

    md_path = out / "testpilot_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return str(json_path), str(md_path)


def print_summary(results: dict):
    passed = len(results.get("passed", []))
    failed = len(results.get("failed", []))
    changed = results.get("changed", [])
    test_files = results.get("test_files", [])

    status = "PASSED" if failed == 0 else "FAILED"
    print(f"\n{'='*50}")
    print(f"  TestPilot -- {status}")
    print(f"  Changed : {len(changed)} file(s)")
    print(f"  Ran     : {len(test_files)} test file(s)")
    print(f"  Passed  : {passed}  |  Failed: {failed}")
    if failed:
        print(f"\n  Failed tests:")
        for f in results["failed"]:
            print(f"    FAIL: {f.splitlines()[0]}")
    print(f"{'='*50}")
