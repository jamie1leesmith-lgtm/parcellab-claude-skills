#!/usr/bin/env python3
"""Validate a built branded-template layout before it is pushed to parcelLab.

Catches the failure modes that browsers silently auto-correct, so the preview
looks perfect while broken markup is what reaches parcelLab.
"""
import pathlib
import re
import sys

REQUIRED_TOKENS = [
    "{{content}}",
    "{{preview}}",
    "{{schemaOrgMarkup}}",
    "{{generated/campaignManager/banner}}",
    "{{generated/campaignManager/html}}",
    "{{generated/campaignManager/productRecommendation}}",
]
BALANCED_TAGS = ["table", "tr", "td"]


def check(html):
    """Return a list of problem strings. Empty list means the layout is clean."""
    problems = []

    for token in REQUIRED_TOKENS:
        if token not in html:
            problems.append(f"required parcelLab token missing: {token}")

    for leftover in sorted(set(re.findall(r"__BRAND_[A-Z_]*__", html))):
        problems.append(f"unsubstituted token left in output: {leftover}")

    # A double quote inside a style="..." value closes the attribute early.
    # In well-formed markup the character after the closing quote is
    # whitespace, '>' or '/'. Anything else means the attribute ended where
    # it should not have.
    for match in re.finditer(r'style="', html):
        end = html.find('"', match.end())
        if end == -1:
            problems.append("style attribute is never closed")
            continue
        following = html[end + 1:end + 2]
        if following and not following.isspace() and following not in ">/":
            snippet = html[match.start():end + 20].replace("\n", " ")
            problems.append(
                "style attribute closed early — a quoted value (usually the "
                f"font stack) terminated it: {snippet!r}"
            )

    for tag in BALANCED_TAGS:
        opens = len(re.findall(rf"<{tag}[ >]", html))
        closes = html.count(f"</{tag}>")
        if opens != closes:
            problems.append(
                f"unbalanced <{tag}>: {opens} opened, {closes} closed"
            )

    return problems


def main():
    if len(sys.argv) != 2:
        print("usage: check_layout_html.py <path-to-html>")
        return 1
    html = pathlib.Path(sys.argv[1]).read_text()
    problems = check(html)
    for problem in problems:
        print(f"PROBLEM: {problem}")
    if problems:
        return 1
    print("OK: layout is clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
