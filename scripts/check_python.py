"""Check Python formatting and concise function documentation without worker processes."""

import argparse
import ast
from pathlib import Path

import black

PROJECT = Path(__file__).resolve().parents[1]


def main():
    """Format or check application and test files, and report undocumented functions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    failures = []
    paths = sorted(
        [
            *PROJECT.glob("*.py"),
            *(PROJECT / "tests").rglob("*.py"),
            *(PROJECT / "scripts").glob("*.py"),
        ]
    )
    for path in paths:
        source = path.read_text()
        formatted = black.format_str(source, mode=black.Mode())
        if args.write:
            path.write_text(formatted)
        elif source != formatted:
            failures.append(f"{path.relative_to(PROJECT)}: formatting differs")
        for node in ast.walk(ast.parse(source)):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not ast.get_docstring(node):
                failures.append(
                    f"{path.relative_to(PROJECT)}:{node.lineno}: document {node.name}"
                )
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"Python formatting and function documentation passed for {len(paths)} files."
    )


if __name__ == "__main__":
    main()
