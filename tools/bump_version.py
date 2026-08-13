#!/usr/bin/env python3
"""Bump the version and close off the changelog section, in one step.

    python tools/bump_version.py patch
    python tools/bump_version.py minor --dry-run

Takes the level as an argument because that is the part needing a human. Nothing can
infer it from a diff, and in this project the call is unusually load-bearing: the
changelog's own rule is that *any* change to resolved geometry is breaking, even with
an untouched API, because a diagram that moves is a broken diagram for anyone diffing
rendered output. A renderer that draws two nodes in a different order has broken its
consumers as surely as a renamed function would.

What it edits, together, so the two cannot drift:

* ``__version__`` in ``src/sankey_mpl/__init__.py``, which is the single version
  source. ``[tool.hatch.version]`` reads it, so the built artifact takes its version
  from here and nowhere else.
* ``CHANGELOG.md``: converts ``## [Unreleased]`` into a dated section for the new
  version, opens a fresh empty ``## [Unreleased]``, and maintains the link
  definitions at the bottom.

It deliberately refuses to run when ``[Unreleased]`` is empty. Releasing with nothing
to say about it is the failure this exists to prevent, and on PyPI it is permanent.
Pass ``--allow-empty`` if you really mean it, for instance for a packaging-only
release where the code is untouched.

It does not commit, tag or push. The publish workflow checks that the tag, the version
and the changelog all agree, so those stay deliberate acts.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "sankey_mpl" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/nrrb/sankey_mpl"

VERSION_RE = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', re.M)
UNRELEASED_RE = re.compile(r"^## \[Unreleased\]\n(.*?)(?=^## \[|\Z)", re.M | re.S)
RELEASED_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)

PLACEHOLDER = "Nothing yet."


def read_version() -> tuple[str, tuple[int, int, int]]:
    text = INIT.read_text()
    match = VERSION_RE.search(text)
    if match is None:
        sys.exit(f'could not find a `__version__ = "X.Y.Z"` line in {INIT}')
    return text, (int(match[1]), int(match[2]), int(match[3]))


def bumped(current: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = current
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def rewrite_changelog(text: str, new: str, previous: str | None, today: str) -> str:
    """Move [Unreleased] under a dated heading and reopen an empty [Unreleased]."""
    match = UNRELEASED_RE.search(text)
    if match is None:
        sys.exit("CHANGELOG.md has no `## [Unreleased]` section to close off")

    body = match.group(1).strip("\n").strip() or PLACEHOLDER
    # The trailing blank line matters: what follows is the previous release's heading,
    # and a heading on the line straight after a list item is malformed Markdown.
    fresh = f"## [Unreleased]\n\n{PLACEHOLDER}\n\n## [{new}] - {today}\n\n{body}\n\n"
    text = text[: match.start()] + fresh + text[match.end() :]

    # Link definitions. [Unreleased] always compares the newest tag to HEAD; a release
    # compares against its predecessor, except the first, which has nothing to compare
    # to and so points at its own tag.
    text = re.sub(
        r"^\[Unreleased\]: .*$",
        f"[Unreleased]: {REPO}/compare/v{new}...HEAD",
        text,
        count=1,
        flags=re.M,
    )
    if previous is None:
        definition = f"[{new}]: {REPO}/releases/tag/v{new}"
    else:
        definition = f"[{new}]: {REPO}/compare/v{previous}...v{new}"
    return re.sub(
        r"^(\[Unreleased\]: .*)$", rf"\1\n{definition}", text, count=1, flags=re.M
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("level", choices=["major", "minor", "patch"])
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="bump even though [Unreleased] describes no changes",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change, write nothing"
    )
    args = parser.parse_args()

    init_text, current = read_version()
    old = ".".join(str(part) for part in current)
    new = ".".join(str(part) for part in bumped(current, args.level))

    changelog = CHANGELOG.read_text()
    match = UNRELEASED_RE.search(changelog)
    body = match.group(1).strip() if match else ""
    if body in ("", PLACEHOLDER) and not args.allow_empty:
        sys.exit(
            "refusing to bump: CHANGELOG.md's [Unreleased] section is empty, so this "
            "release would ship with nothing describing it, permanently. Write the "
            "entries first, or pass --allow-empty for a packaging-only release."
        )

    previous = RELEASED_RE.search(changelog)
    today = datetime.date.today().isoformat()

    new_init = VERSION_RE.sub(f'__version__ = "{new}"', init_text, count=1)
    new_changelog = rewrite_changelog(
        changelog, new, previous.group(1) if previous else None, today
    )

    print(f"{args.level}: {old} -> {new}   ({today})")
    if args.dry_run:
        print("dry run, nothing written")
        return

    INIT.write_text(new_init)
    CHANGELOG.write_text(new_changelog)
    print(f"  wrote {INIT.relative_to(ROOT)}")
    print(f"  wrote {CHANGELOG.relative_to(ROOT)}")
    print("\nNext, once you are happy with the changelog wording:")
    print(f"  git commit -am 'Released {new}'")
    print(f"  git tag -a v{new} -m 'sankey_mpl {new}'")
    print(f"  git push origin main && git push origin v{new}")


if __name__ == "__main__":
    main()
