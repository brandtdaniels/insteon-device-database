"""Fails when a change to the schemas doesn't raise VERSION.

While the catalog is below 1.0, any schema change raises MINOR. From 1.0, an additive change raises
MINOR and a breaking one MAJOR. Run in a pull request, with the base branch's commit as the
argument."""

import re
import subprocess
import sys


def changed(base, path):
    result = subprocess.run(["git", "diff", "--quiet", base, "HEAD", "--", path])

    if result.returncode not in (0, 1):
        sys.exit(f"git couldn't compare {path} with {base}")

    return result.returncode == 1


def version(text):
    match = re.fullmatch(r"(\d+)\.(\d+)", text.strip())

    if match is None:
        sys.exit(f"VERSION must be MAJOR.MINOR, not {text.strip()!r}")

    return int(match[1]), int(match[2])


def main():
    base = sys.argv[1]
    old = subprocess.run(["git", "show", f"{base}:VERSION"], capture_output=True, text=True)
    new = version(open("VERSION").read())

    if old.returncode == 0 and new < version(old.stdout):
        sys.exit("VERSION went down.")

    # A base without VERSION predates versioning, so adding it counts as raising it.
    if changed(base, "schema") and old.returncode == 0 and new <= version(old.stdout):
        sys.exit("The schemas changed, so VERSION needs a higher MAJOR.MINOR.")


main()
