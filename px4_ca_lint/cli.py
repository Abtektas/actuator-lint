"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, diff
from . import report as single
from .engine import (
    ENGINE_ENV,
    PX4_ENV,
    EngineError,
    check_px4_version,
    engine_locations,
    find_engine,
    requested_px4,
    run_engine,
)
from .params import FORMATS, ParamFileError, parse_file
from .rules import ERROR, LEVELS, RULES, WARNING, Options, check

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

_DESCRIPTION = (
    "Run PX4's control allocation code on a parameter file and report the resulting matrices "
    "and findings. A review aid, not an airworthiness approval; use at your own risk."
)
_ENGINES_DESCRIPTION = (
    "List the engines this tool finds, the PX4 version each was built against, and the one a "
    "run without --engine and --px4 uses."
)
_DIFF_DESCRIPTION = (
    "Compare two parameter files: changed parameters, changed matrix values, and findings that "
    "are new or gone in the second file. A review aid, not an airworthiness approval."
)


def _rule_list(text: str) -> frozenset[str]:
    rules = frozenset(part.strip().upper() for part in text.split(",") if part.strip())
    unknown = sorted(rules - RULES.keys())

    if unknown:
        raise argparse.ArgumentTypeError(f"unknown rule(s): {', '.join(unknown)}")

    return rules


def _positive(text: str) -> float:
    try:
        value = float(text)

    except ValueError:
        value = 0

    if not value > 0:
        raise argparse.ArgumentTypeError(f"'{text}' is not a positive number")

    return value


def _add_common_options(parser: argparse.ArgumentParser, fail_on_help: str) -> None:
    parser.add_argument(
        "--input-format",
        choices=("auto", *FORMATS),
        default="auto",
        help="format of the parameter file (default: auto)",
    )
    parser.add_argument(
        "--format",
        choices=tuple(single.RENDERERS),
        default="text",
        help="report format (default: text)",
    )
    parser.add_argument("--output", metavar="FILE", help="write the report to FILE instead of stdout")
    parser.add_argument(
        "--engine",
        metavar="PATH",
        help=f"path to px4_ca_engine (default: ${ENGINE_ENV}, then build/engine, then the user data directory)",
    )
    parser.add_argument(
        "--px4",
        metavar="VERSION",
        help=f"PX4 version to check against, for example v1.17.0: uses the engine installed for it "
        f"and refuses an engine built against another release (default: ${PX4_ENV})",
    )
    parser.add_argument("--fail-on", choices=(*LEVELS, "never"), default=ERROR, help=fail_on_help)
    parser.add_argument(
        "--ignore",
        metavar="RULES",
        type=_rule_list,
        default=frozenset(),
        help="comma separated rules to skip, for example CA011,CA020",
    )
    parser.add_argument(
        "--max-thrust-gain",
        metavar="GAIN",
        type=_positive,
        default=Options.max_thrust_gain,
        help=f"limit for rule CA010 (default: {Options.max_thrust_gain})",
    )
    parser.add_argument("--version", action="version", version=f"px4-ca-lint {__version__}")


def _check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="px4-ca-lint",
        description=_DESCRIPTION,
        epilog="To compare two parameter files: px4-ca-lint diff BEFORE AFTER. "
        "To list the installed engines: px4-ca-lint engines",
    )
    parser.add_argument("file", help="parameter file (plain, PX4 airframe script or QGroundControl export)")
    _add_common_options(parser, "lowest finding level that gives exit code 1 (default: error)")
    return parser


def _diff_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="px4-ca-lint diff", description=_DIFF_DESCRIPTION)
    parser.add_argument("before", help="parameter file to compare from")
    parser.add_argument("after", help="parameter file to compare to")
    _add_common_options(
        parser, "lowest level of a new finding that gives exit code 1 (default: error)"
    )
    return parser


def _engines_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="px4-ca-lint engines", description=_ENGINES_DESCRIPTION)
    parser.add_argument("--version", action="version", version=f"px4-ca-lint {__version__}")
    return parser


def _engines() -> str:
    lines = []

    for name, path in engine_locations():
        if not path.is_file():
            continue

        try:
            # any parameter file makes the engine report what it was built against
            probe = run_engine(path, {"CA_AIRFRAME": "0"})
            built = f"PX4 {probe.get('px4_version')} ({str(probe.get('px4_commit'))[:10]})"

        except EngineError as error:
            built = f"not usable: {error}"

        lines.append(f"  {name}: {path}\n      {built}")

    if not lines:
        lines.append("  none")

    try:
        default = str(find_engine(px4=requested_px4()))

    except EngineError as error:
        default = f"none: {error}"

    return "Engines found:\n" + "\n".join(lines) + f"\n\nUsed without --engine and --px4: {default}\n"


def _analyse(path: str, args: argparse.Namespace) -> dict:
    param_file = parse_file(path, None if args.input_format == "auto" else args.input_format)
    px4 = requested_px4(args.px4)
    engine = find_engine(args.engine, px4)
    engine_result = run_engine(engine, param_file.params)
    check_px4_version(px4, engine, engine_result)
    options = Options(max_thrust_gain=args.max_thrust_gain, ignore=args.ignore)
    checked = check(engine_result, options, param_file.params)
    return single.build_report(param_file, engine_result, checked)


def _write(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")

    else:
        sys.stdout.write(text)


def _fails(findings: list[dict], fail_on: str) -> bool:
    failing = {ERROR: (ERROR,), WARNING: (ERROR, WARNING), "never": ()}[fail_on]
    return any(finding["level"] in failing for finding in findings)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    comparing = bool(argv) and argv[0] == "diff"

    try:
        if argv and argv[0] == "engines":
            _engines_parser().parse_args(argv[1:])
            sys.stdout.write(_engines())
            return EXIT_OK

        if comparing:
            args = _diff_parser().parse_args(argv[1:])
            result = diff.build_diff(_analyse(args.before, args), _analyse(args.after, args))
            text = diff.RENDERERS[args.format](result)
            findings = result["findings"]["new"]

        else:
            args = _check_parser().parse_args(argv)
            result = _analyse(args.file, args)
            text = single.RENDERERS[args.format](result)
            findings = result["findings"]

        _write(text, args.output)

    except (ParamFileError, EngineError) as error:
        print(f"px4-ca-lint: error: {error}", file=sys.stderr)
        return EXIT_ERROR

    except OSError as error:
        print(f"px4-ca-lint: error: {error.filename}: {error.strerror}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_FINDINGS if _fails(findings, args.fail_on) else EXIT_OK
