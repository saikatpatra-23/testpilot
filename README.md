# TestPilot

**Only test what changed.** Targeted test runner powered by git diff.

```bash
pip install git+https://github.com/saikatpatra-23/testpilot.git
```

## Usage

```bash
# In any project — run tests for uncommitted changes only
testpilot run

# Test changes since last commit
testpilot run HEAD~1

# Test changes vs main branch (for PRs)
testpilot run origin/main

# Run full suite
testpilot run --all

# Setup: creates testpilot.cfg + .vscode/tasks.json
testpilot init
```

## pytest flag

```bash
pytest --testpilot-diff             # only tests for uncommitted changes
pytest --testpilot-diff HEAD~1      # only tests for last commit
pytest --testpilot-diff origin/main # only tests changed vs main
```

## How it works

```
git diff HEAD
     ↓
changed files detected
     ↓
test_mapper finds relevant test files by name matching
     ↓
pytest runs ONLY those test files
     ↓
report.md + report.json generated
```

## Generated reports

- `testpilot_report.md` — human readable
- `testpilot_report.json` — machine readable (for CI)

## Requirements

- Python 3.11+
- pytest
- git
