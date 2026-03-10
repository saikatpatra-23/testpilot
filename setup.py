from setuptools import setup, find_packages

setup(
    name="testpilot",
    version="0.1.0",
    description="Targeted test runner — only test what changed via git diff",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "pytest>=8.0.0",
        "pytest-json-report>=1.5.0",
        "httpx>=0.27.0",
    ],
    entry_points={
        "console_scripts": ["testpilot=testpilot.cli:main"],
        "pytest11":        ["testpilot=testpilot.pytest_plugin"],
    },
)
