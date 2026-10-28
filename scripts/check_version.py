"""Fails when a change to the schemas doesn't bump VERSION.

While the catalog is below 1.0, any schema change bumps MINOR. From 1.0, an additive change bumps
MINOR and a breaking one MAJOR. Run in a pull request, with the base branch's commit as the
argument."""

import subprocess
import sys


def changed(base, path):
    return subprocess.run(["git", "diff", "--quiet", base, "HEAD", "--", path]).returncode != 0


def main():
    base = sys.argv[1]

    if changed(base, "schema") and not changed(base, "VERSION"):
        print("The schemas changed, so VERSION needs a new MAJOR.MINOR.", file=sys.stderr)
        sys.exit(1)


main()
