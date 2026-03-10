"""
TestPilot CLI — testpilot run

Usage:
    testpilot run                  # test changes since HEAD (uncommitted)
    testpilot run HEAD~1           # test changes since last commit
    testpilot run origin/main      # test changes vs main branch (for PRs)
    testpilot run --all            # run full test suite
    testpilot init                 # scaffold config + .vscode/tasks.json
"""
import argparse
import sys
import os
from pathlib import Path

from .git_diff import get_changed_files
from .test_mapper import resolve
from .runner import run_pytest, run_all_tests, run_frontend
from .reporter import generate, print_summary


def cmd_run(since: str, run_all: bool, app_url: str):
    cwd = os.getcwd()

    if run_all:
        print("\nTestPilot — full suite")
        result = run_all_tests(cwd)
    else:
        print(f"\nTestPilot — diff since {since}")
        changed = get_changed_files(since)

        if not changed:
            print("  No changed files detected. Nothing to test.")
            sys.exit(0)

        mapping = resolve(changed, cwd)
        print(f"\n  Changed  : {mapping['changed']}")
        print(f"  Tests    : {mapping['test_files'] or '(none found)'}")

        if mapping["run_all"]:
            print("  Infrastructure change — running full suite")
            result = run_all_tests(cwd)
        elif not mapping["test_files"] and not mapping["has_frontend"]:
            print("\n  ⚠  No test files found for changed code.")
            print("  Add tests to tests/ folder matching the source file name.")
            sys.exit(0)
        else:
            # Backend tests
            result = {"passed": [], "failed": [], "errors": [], "changed": changed,
                      "test_files": mapping["test_files"], "since": since}

            if mapping["test_files"]:
                backend = run_pytest(mapping["test_files"])
                result["passed"]     = backend.get("passed", [])
                result["failed"]     = backend.get("failed", [])
                result["errors"]     = backend.get("errors", [])
                result["exit_code"]  = backend.get("exit_code", 0)

            # Frontend tests
            if mapping["has_frontend"] and mapping["routes"]:
                fe = run_frontend(mapping["routes"], app_url)
                result["frontend"] = fe

    print_summary(result)
    json_p, md_p = generate(result, cwd)
    print(f"\n  Report : {md_p}")
    print(f"  JSON   : {json_p}\n")

    sys.exit(0 if not result.get("failed") else 1)


def cmd_init():
    cwd = Path.cwd()
    print(f"\nTestPilot — init in {cwd}\n")

    # config
    cfg = cwd / "testpilot.cfg"
    if not cfg.exists():
        cfg.write_text(
            "[testpilot]\nbackend_url = http://localhost:8000\nfrontend_url = http://localhost:3000\n",
            encoding="utf-8"
        )
        print("  created testpilot.cfg")

    # tests/
    (cwd / "tests").mkdir(exist_ok=True)
    gitkeep = cwd / "tests" / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
        print("  created tests/")

    # .vscode/tasks.json
    vscode = cwd / ".vscode"
    vscode.mkdir(exist_ok=True)
    tasks = vscode / "tasks.json"
    if not tasks.exists():
        import json
        tasks.write_text(json.dumps({
            "version": "2.0.0",
            "tasks": [
                {"label": "TestPilot: Run (changed only)", "type": "shell",
                 "command": "testpilot run", "group": {"kind": "test", "isDefault": True},
                 "presentation": {"reveal": "always"}},
                {"label": "TestPilot: Run all", "type": "shell",
                 "command": "testpilot run --all",
                 "presentation": {"reveal": "always"}},
            ]
        }, indent=2), encoding="utf-8")
        print("  created .vscode/tasks.json")

    # .gitignore additions
    gi = cwd / ".gitignore"
    additions = ["testpilot_report.json", "testpilot_report.md"]
    if gi.exists():
        content = gi.read_text(encoding="utf-8")
        new = [a for a in additions if a not in content]
        if new:
            with open(gi, "a") as f:
                f.write("\n# TestPilot\n" + "\n".join(new) + "\n")
            print(f"  updated .gitignore")
    else:
        gi.write_text("# TestPilot\n" + "\n".join(additions) + "\n")
        print("  created .gitignore")

    print("\n  Done. Run: testpilot run\n")


def main():
    parser = argparse.ArgumentParser(prog="testpilot", description="TestPilot — targeted test runner")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run tests for changed files")
    run_p.add_argument("since", nargs="?", default="HEAD",
                       help="Git ref (HEAD, HEAD~1, origin/main). Default: HEAD (uncommitted changes)")
    run_p.add_argument("--all", action="store_true", help="Run full test suite")
    run_p.add_argument("--app-url", default="http://localhost:3000",
                       help="Frontend URL for Playwright tests")

    sub.add_parser("init", help="Scaffold config + .vscode/tasks.json")

    args = parser.parse_args()

    if args.cmd == "run":
        cmd_run(since=args.since, run_all=args.all, app_url=args.app_url)
    elif args.cmd == "init":
        cmd_init()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
