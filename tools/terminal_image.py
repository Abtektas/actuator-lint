#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Write docs/images/terminal.svg: the tool in a terminal, for the README.

usage: tools/terminal_image.py [--check]

The picture is made from what the tool prints for one of the files in
examples/, with the engine the tool finds (see the README), which has to be
one built against the PX4 version named below. Lines that are left out are
counted in the picture. With --check nothing is written and the exit code
says whether the stored picture is up to date; the tests do that.
"""

import importlib.util
import sys
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("example_reports", ROOT / "tools" / "example_reports.py")
example_reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example_reports)

EXAMPLE = "examples/standard_vtol_pusher_offset.params"
OUTPUT = ROOT / "docs" / "images" / "terminal.svg"

COLUMNS = 96
FONT_SIZE = 13
# the width of a character in the monospace fonts named below is 0.6 em
CHARACTER = FONT_SIZE * 0.6
LINE = 18
PADDING = 16
TITLE_BAR = 34

STYLE = """
text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; white-space: pre; }
.plain { fill: #c9d1d9; }
.title { fill: #f0f6fc; font-weight: bold; }
.dim { fill: #8b949e; }
.omitted { fill: #8b949e; font-style: italic; }
.prompt { fill: #3fb950; }
.warning { fill: #d29922; font-weight: bold; }
.error { fill: #f85149; font-weight: bold; }
/* Without animation everything is visible: the picture is complete in a viewer that does not animate. */
@media (prefers-reduced-motion: no-preference) {
  .cover { animation: type 1.2s steps(STEPS, end) 0.4s backwards; }
  .part { animation: appear 0.25s ease-out backwards; }
  .part1 { animation-delay: 1.9s; }
  .part2 { animation-delay: 2.4s; }
  .part3 { animation-delay: 3.0s; }
  .part4 { animation-delay: 3.6s; }
}
@keyframes type { from { transform: translateX(0); } to { transform: translateX(WIDTHpx); } }
@keyframes appear { from { opacity: 0; } to { opacity: 1; } }
"""


def selected(report: list[str]) -> list[list[tuple[str, str]]]:
    """The parts of the picture, each a list of (kind, line).

    Part 1 is the header, 2 the mix of the first matrix, 3 the findings, 4 the disclaimer. What lies
    between them is counted, not shown.
    """
    matrix = report.index(next(line for line in report if line.startswith("Matrix 0")))
    mix = next(index for index in range(matrix, len(report)) if report[index].startswith("  Mix:"))
    mix_end = report.index("", mix)
    findings = report.index("Findings")
    findings_end = report.index("", findings)
    disclaimer = len(report) - 1

    if not report[disclaimer].startswith("This report is a review aid"):
        raise SystemExit("the report does not end with the disclaimer")

    def omitted(count: int) -> tuple[str, str]:
        return "omitted", f"  ... {count} lines left out"

    def lines(start: int, end: int) -> list[tuple[str, str]]:
        return [("line", line) for line in report[start:end]]

    return [
        lines(0, matrix),
        [("title", report[matrix]), omitted(mix - matrix - 1), *lines(mix, mix_end), omitted(findings - mix_end)],
        [("title", report[findings]), *lines(findings + 1, findings_end)],
        [omitted(disclaimer - findings_end), ("line", ""), ("dim", report[disclaimer])],
    ]


def wrapped(line: str) -> list[str]:
    if len(line) <= COLUMNS:
        return [line]

    indent = line[: len(line) - len(line.lstrip())]
    return textwrap.wrap(
        line, COLUMNS, subsequent_indent=indent + "  ", break_long_words=False, break_on_hyphens=False
    )


def spans(kind: str, line: str, first: bool = True) -> str:
    """The content of a text element: a line of the report, or a piece of a wrapped one, with its colours."""
    if kind != "line":
        return f'<tspan class="{kind}">{escape(line)}</tspan>'

    for level in ("warning", "error"):
        # only the first piece of a wrapped finding starts with its level
        if first and line.startswith(f"  {level} "):
            rest = escape(line[len(level) + 2 :])
            return (
                f'<tspan class="plain">  </tspan><tspan class="{level}">{level}</tspan>'
                f'<tspan class="plain">{rest}</tspan>'
            )

    return f'<tspan class="{"dim" if "https://" in line else "plain"}">{escape(line)}</tspan>'


def text(row: int, content: str, length: int) -> str:
    y = TITLE_BAR + PADDING + row * LINE + FONT_SIZE
    # textLength keeps the columns where they are, whatever monospace font the viewer has
    return (
        f'<text x="{PADDING}" y="{y}" font-size="{FONT_SIZE}" xml:space="preserve" '
        f'textLength="{length * CHARACTER:.1f}" lengthAdjust="spacing">{content}</text>'
    )


def build() -> str:
    code, report = example_reports.run(EXAMPLE)
    report_lines = report.rstrip("\n").split("\n")

    if f"PX4:       {example_reports.PX4_VERSION} " not in report:
        raise SystemExit(f"the engine is not built against PX4 {example_reports.PX4_VERSION}")

    command = f"px4-ca-lint {EXAMPLE}"
    prompt = f'<tspan class="prompt">$ </tspan><tspan class="title">{escape(command)}</tspan>'
    body = [text(0, prompt, len(command) + 2)]
    cover_y = TITLE_BAR + PADDING - 2
    cover_width = len(command) * CHARACTER + 4
    body.append(
        f'<rect class="cover" x="{PADDING + 2 * CHARACTER:.1f}" y="{cover_y}" width="{cover_width:.1f}" '
        f'height="{LINE}" fill="#0d1117" style="transform: translateX({cover_width:.1f}px)"/>'
    )
    row = 1

    for number, part in enumerate(selected(report_lines), 1):
        body.append(f'<g class="part part{number}">')

        for kind, line in part:
            pieces = wrapped(line)

            for index, piece in enumerate(pieces):
                if piece:
                    body.append(text(row, spans(kind, piece, index == 0), len(piece)))

                row += 1

        body.append("</g>")

    width = int(2 * PADDING + COLUMNS * CHARACTER) + 1
    height = TITLE_BAR + 2 * PADDING + row * LINE
    style = STYLE.replace("STEPS", str(len(command))).replace("WIDTH", f"{cover_width:.1f}")
    summary = next(line.strip() for line in report_lines if "error(s)" in line)
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" aria-labelledby="title description">',
            "<title id=\"title\">px4-ca-lint in a terminal</title>",
            f'<desc id="description">The command {escape(command)} and a shortened copy of the report it '
            f"prints: the header, the mix of the first matrix, the findings ({escape(summary)}, exit code {code}) "
            "and the disclaimer.</desc>",
            f"<style>{style}</style>",
            f'<rect width="{width}" height="{height}" rx="8" fill="#0d1117"/>',
            f'<path d="M0 {TITLE_BAR}V8a8 8 0 0 1 8-8H{width - 8}a8 8 0 0 1 8 8V{TITLE_BAR}z" fill="#161b22"/>',
            '<circle cx="20" cy="17" r="6" fill="#f85149"/>',
            '<circle cx="40" cy="17" r="6" fill="#d29922"/>',
            '<circle cx="60" cy="17" r="6" fill="#3fb950"/>',
            *body,
            "</svg>",
            "",
        ]
    )


def out_of_date() -> list[str]:
    """What differs between the stored picture and the one made now, one line per difference."""
    new = build()

    if not OUTPUT.is_file():
        return [f"{OUTPUT.name}: not stored"]

    old = OUTPUT.read_text(encoding="utf-8")

    if example_reports.same(old, new):
        return []

    old_lines, new_lines = old.splitlines(), new.splitlines()
    problems = []

    if len(old_lines) != len(new_lines):
        problems.append(f"{OUTPUT.name}: {len(old_lines)} lines stored, {len(new_lines)} made")

    differing = [(a, b) for a, b in zip(old_lines, new_lines) if not example_reports.same(a, b)]
    return problems + [f"{OUTPUT.name}: stored {a!r}, made {b!r}" for a, b in differing[:6]]


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        problems = out_of_date()

        if problems:
            raise SystemExit("out of date, run tools/terminal_image.py:\n" + "\n".join(problems))

    elif sys.argv[1:]:
        raise SystemExit(__doc__)

    else:
        OUTPUT.write_text(build(), encoding="utf-8")
        print("wrote", OUTPUT.relative_to(ROOT))
