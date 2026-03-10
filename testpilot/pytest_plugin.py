"""
pytest plugin — adds --testpilot-diff flag.

After `pip install testpilot`, this works in ANY project:
    pytest --testpilot-diff             # only tests for uncommitted changes
    pytest --testpilot-diff HEAD~1      # only tests for last commit
    pytest --testpilot-diff origin/main # only tests changed vs main (for PRs)
"""
import os
import pytest
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption(
        "--testpilot-diff",
        nargs="?",
        const="HEAD",
        default=None,
        metavar="GIT_REF",
        help="Run only tests for files changed since GIT_REF (default: HEAD = uncommitted)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "testpilot: test was selected by TestPilot diff analysis"
    )


def pytest_collection_modifyitems(session, config, items):
    since = config.getoption("--testpilot-diff", default=None)
    if since is None:
        return

    from .git_diff import get_changed_files
    from .test_mapper import resolve

    cwd = os.getcwd()
    changed = get_changed_files(since)

    if not changed:
        print("\n[TestPilot] No changed files — running full suite\n")
        return

    mapping = resolve(changed, cwd)

    if mapping["run_all"]:
        print("\n[TestPilot] Infrastructure change — running full suite\n")
        return

    relevant = set(mapping["test_files"])
    changed_stems = {Path(f).stem.lower() for f in mapping["changed_py"]}

    kept = skipped = 0
    for item in items:
        item_path = str(item.fspath).replace("\\", "/")
        is_relevant = (
            any(Path(rf).name in item_path for rf in relevant)
            or any(stem in item.name.lower() for stem in changed_stems)
        )
        if is_relevant:
            item.add_marker(pytest.mark.testpilot)
            kept += 1
        else:
            item.add_marker(pytest.mark.skip(
                reason=f"Not affected by {mapping['changed_py']} [TestPilot]"
            ))
            skipped += 1

    print(f"\n[TestPilot] diff:{since} | changed:{mapping['changed_py']} "
          f"| running {kept} tests, skipping {skipped}\n")
