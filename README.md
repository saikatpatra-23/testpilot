# TestPilot

**Only test what changed.** TestPilot is a plug-and-play testing plugin for any project. When you change code, instead of running the full test suite (which can take minutes), TestPilot detects which files changed via `git diff`, maps those to their relevant test files, runs **only those tests**, and generates a clean report. Works with any Python (pytest) or JavaScript (Jest) project — zero config needed.

## Install

```bash
pip install git+https://github.com/saikatpatra-23/testpilot.git
```

## CLI Usage

```bash
# Run tests for uncommitted changes (most common)
testpilot run

# Run tests for changes since last commit
testpilot run HEAD~1

# Run tests for changes vs main branch (for PRs)
testpilot run origin/main

# Run full test suite (no filtering)
testpilot run --all

# Enable Playwright frontend tests (requires app running)
testpilot run --app-url http://localhost:3000

# Scaffold config + VS Code tasks
testpilot init
```

## pytest Plugin

```bash
# Only run tests for uncommitted changes
pytest --testpilot-diff

# Only run tests for changes since last commit
pytest --testpilot-diff HEAD~1

# Only run tests changed vs main branch (for PRs)
pytest --testpilot-diff origin/main
```

## How to Add to a New Project

1. **Install TestPilot:**
   ```bash
   pip install git+https://github.com/saikatpatra-23/testpilot.git
   ```

2. **Name your test files to match source files:**
   - `src/utils/auth.py` → `tests/test_auth.py`
   - `src/components/Button.tsx` → `src/components/__tests__/Button.test.tsx`

3. **Run from your project root:**
   ```bash
   testpilot run
   ```

4. **Optional — scaffold config:**
   ```bash
   testpilot init
   ```
   This creates `testpilot.cfg` and `.vscode/tasks.json` so you can run TestPilot from VS Code's task runner.

5. **Add to CI (GitHub Actions):**
   ```yaml
   - name: Run TestPilot
     run: testpilot run origin/main
   ```

## Sample Report Output

```
====================================================
  [PASS]  TestPilot -- PASS  |  9.6s
  ----------------------------------------------
  Files changed : 2
  Test files    : 1
  Passed        : 12
  Failed        : 0
====================================================

  Report : testpilot_report.md
  JSON   : testpilot_report.json
```

**testpilot_report.md** (human-readable):
```markdown
# PASS

Generated: 2026-03-11 10:30:00  |  Diff since: HEAD~1  |  9.6s

## Summary
| Metric         | Value |
|----------------|-------|
| Files changed  | 2     |
| Test files found | 1   |
| Tests passed   | 12    |
| Tests failed   | 0     |

## Changed Files & Mapped Tests
| Changed File                          | Mapped Test(s)                              |
|---------------------------------------|---------------------------------------------|
| src/components/ControlsCard.tsx       | `__tests__/ControlsCard.test.tsx`           |
| src/components/__tests__/ControlsCard.test.tsx | `__tests__/ControlsCard.test.tsx`  |

## Passed Tests
- ControlsCard > renders Trading Engine Controls heading
- ControlsCard > shows "Start Trading Engine" when trading is disabled
...
```

## Architecture

```
git diff HEAD (or HEAD~1, origin/main)
     |
     v
git_diff.py        — detects changed files
     |
     v
test_mapper.py     — maps each changed file to its test file(s)
                     (by name matching: Button.tsx → Button.test.tsx)
     |
     v
runner.py          — runs ONLY those test files
                     (pytest for .py, Jest/npx for .ts/.tsx/.js)
     |
     v
reporter.py        — generates testpilot_report.md + testpilot_report.json
```

**Test mapping rules:**
- `src/foo/bar.py` → `tests/test_bar.py` or `tests/bar_test.py`
- `src/components/Foo.tsx` → `src/components/__tests__/Foo.test.tsx`
- Infrastructure files (`package.json`, `Dockerfile`, etc.) → run full suite

## Requirements

- Python 3.11+
- pytest
- git
- For JS/TS projects: Node.js + Jest configured in `package.json`
