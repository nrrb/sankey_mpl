#!/usr/bin/env python3
"""Advisory reminder: library code has moved since the last release.

Run by the Stop hook in .claude/settings.json. Prints a note when `src/` has changed
since the newest tag while `__version__` still equals that tag, which is the state
that quietly produces two different installs reporting the same version.

Three deliberate constraints:

* **It never edits anything.** Choosing patch, minor or major is judgment, and in
  this project an unusually consequential one: the changelog's rule is that any
  change to resolved geometry is breaking even with an untouched API. A hook cannot
  make that call, so it does not try.
* **It always exits 0.** A reminder that blocks the session is a worse trade than a
  reminder that is occasionally ignored.
* **It is not the enforcement point.** Hooks only run on the machine that has them,
  so a collaborator or a github.com web edit bypasses this entirely. The real gate is
  in .github/workflows/publish.yml, which refuses to publish unless the tag,
  `__version__` and the changelog all agree. This just moves the discovery earlier.

Usage:

    python3 .claude/hooks/version-reminder.py [tag]

The optional tag overrides "newest tag", which exists so both branches can be
exercised without inventing throwaway tags.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys


def git(*args: str, cwd: str | None = None) -> str | None:
    """Run git, returning stripped stdout, or None if it failed for any reason."""
    try:
        done = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def main() -> None:
    root = git("rev-parse", "--show-toplevel")
    if root is None:
        return  # not a git checkout, or no git at all

    tag = (
        sys.argv[1]
        if len(sys.argv) > 1
        else git("describe", "--tags", "--abbrev=0", cwd=root)
    )
    if not tag:
        return  # nothing released yet, so nothing to be behind

    init = f"{root}/src/sankey_mpl/__init__.py"
    try:
        with open(init) as handle:
            source = handle.read()
    except OSError:
        return
    found = re.search(r'__version__ = "([^"]+)"', source)
    if found is None:
        return
    version = found.group(1)

    # Already bumped past the last release: the decision has been made.
    if tag.removeprefix("v") != version:
        return

    # `git diff --quiet` exits 1 when there are differences, so a None return from
    # the helper is the signal we want here rather than an error.
    changed = git("diff", "--quiet", tag, "--", "src/", cwd=root) is None
    if not changed:
        return

    files = git("diff", "--name-only", tag, "--", "src/", cwd=root) or ""
    count = len([line for line in files.splitlines() if line])

    print(
        json.dumps(
            {
                "systemMessage": (
                    f"Version reminder: {count} file(s) under src/ changed since {tag}, "
                    f"but __version__ is still {version}. Anything installing from the "
                    f"branch now gets different code under the same version number. "
                    f"Before the next release run "
                    f"`python tools/bump_version.py <major|minor|patch>`, which updates "
                    f"__version__ and CHANGELOG.md together. Reminder only, nothing was "
                    f"changed."
                )
            }
        )
    )


if __name__ == "__main__":
    main()
