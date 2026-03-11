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
import time
import shutil
from pathlib import Path

from .git_diff import get_changed_files
from .test_mapper import resolve
from .runner import run_pytest, run_jest, run_all_tests, run_frontend
from .reporter import generate, print_summary
from .generator import generate_missing_tests


def cmd_run(since: str, run_all: bool, app_url: str, no_generate: bool = False, keep_tests: bool = False):
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
        print(f"\n  Changed   : {mapping['changed']}")
        print(f"  Tests (py): {mapping['test_files'] or '(none found)'}")
        print(f"  Tests (js): {mapping['jest_files'] or '(none found)'}")

        if mapping["run_all"]:
            print("  Infrastructure change — running full suite")
            result = run_all_tests(cwd)
        elif not mapping["test_files"] and not mapping["jest_files"] and not mapping["has_frontend"]:
            if no_generate or not mapping["changed_py"]:
                print("\n  [!] No test files found for changed code.")
                print("  Add tests to tests/ or __tests__/ folder matching the source file name.")
                sys.exit(0)

            # AI generation path: ask Claude to write tests for unmapped Python files
            generated = generate_missing_tests(
                changed_py=mapping["changed_py"],
                mapped_test_files=mapping["test_files"],
                since=since,
            )
            if not generated:
                print("\n  [!] AI generation produced no test files. Exiting.")
                sys.exit(0)

            mapping["test_files"] = generated
            print(f"\n  Running AI-generated tests from .testpilot_cache/ ...")
            t0 = time.time()
            result = {
                "passed":       [],
                "failed":       [],
                "errors":       [],
                "changed":      changed,
                "test_files":   generated,
                "file_mapping": mapping.get("file_mapping", {}),
                "since":        since,
                "ai_generated": generated,
            }
            backend = run_pytest(generated, extra_args=[f"--rootdir={cwd}"])
            result["passed"]   += backend.get("passed", [])
            result["failed"]   += backend.get("failed", [])
            result["errors"]   += backend.get("errors", [])
            result["exit_code"] = backend.get("exit_code", 0)
            result["duration_seconds"] = round(time.time() - t0, 2)
        else:
            t0 = time.time()
            result = {
                "passed":       [],
                "failed":       [],
                "errors":       [],
                "changed":      changed,
                "test_files":   mapping["test_files"] + mapping["jest_files"],
                "file_mapping": mapping.get("file_mapping", {}),
                "since":        since,
            }

            # Backend (pytest) tests
            if mapping["test_files"]:
                backend = run_pytest(mapping["test_files"])
                result["passed"]    += backend.get("passed", [])
                result["failed"]    += backend.get("failed", [])
                result["errors"]    += backend.get("errors", [])
                result["exit_code"]  = backend.get("exit_code", 0)

            # Frontend unit tests (Jest / RTL)
            if mapping["jest_files"]:
                jest = run_jest(mapping["jest_files"], cwd=cwd)
                result["passed"]   += jest.get("passed", [])
                result["failed"]   += jest.get("failed", [])
                result["errors"]   += jest.get("errors", [])
                result["exit_code"] = jest.get("exit_code", 0)
                if jest.get("raw_output"):
                    result["jest_output"] = jest["raw_output"]

            # Playwright (frontend routes) — only if --app-url is explicitly provided
            if app_url and mapping["has_frontend"] and mapping["routes"]:
                fe = run_frontend(mapping["routes"], app_url)
                result["frontend"] = fe

            result["duration_seconds"] = round(time.time() - t0, 2)

    print_summary(result)
    json_p, md_p = generate(result, cwd)
    print(f"\n  Report : {md_p}")
    print(f"  JSON   : {json_p}\n")

    # Clean up AI-generated test cache unless --keep-tests is set
    if result.get("ai_generated") and not keep_tests:
        from .generator import CACHE_DIR
        cache_path = Path(cwd) / CACHE_DIR
        if cache_path.exists():
            shutil.rmtree(cache_path)
            print(f"  Cleaned up {CACHE_DIR}/  (use --keep-tests to preserve)\n")

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
    additions = ["testpilot_report.json", "testpilot_report.md", ".testpilot_cache/"]
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
    # Ensure UTF-8 output on Windows to prevent UnicodeEncodeErrors
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="testpilot", description="TestPilot — targeted test runner")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run tests for changed files")
    run_p.add_argument("since", nargs="?", default="HEAD",
                       help="Git ref (HEAD, HEAD~1, origin/main). Default: HEAD (uncommitted changes)")
    run_p.add_argument("--all", action="store_true", help="Run full test suite")
    run_p.add_argument("--app-url", default=None,
                       help="Frontend URL for Playwright tests (enables Playwright route testing)")
    run_p.add_argument("--no-generate", action="store_true",
                       help="Skip AI test generation when no tests are found")
    run_p.add_argument("--keep-tests", action="store_true",
                       help="Keep AI-generated tests in .testpilot_cache/ after the run")

    sub.add_parser("init", help="Scaffold config + .vscode/tasks.json")

    args = parser.parse_args()

    if args.cmd == "run":
        cmd_run(since=args.since, run_all=args.all, app_url=args.app_url, no_generate=args.no_generate, keep_tests=args.keep_tests)
    elif args.cmd == "init":
        cmd_init()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
