"""Find and run the px4_ca_engine executable."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

# engine_schema values this version of the tool can read, see docs/versioning.md
SUPPORTED_ENGINE_SCHEMAS = (1,)

ENGINE_ENV = "PX4_CA_ENGINE"
PX4_ENV = "PX4_CA_PX4"
ENGINE_NAME = "px4_ca_engine"
_TIMEOUT_S = 60

# exit codes of px4_ca_engine
_EXIT_INPUT = 65
_EXIT_UNSUPPORTED = 66
_EXIT_PX4_FAILED = 67


class EngineError(Exception):
    """The engine is missing, failed, or wrote output this tool cannot read."""


def user_data_directory() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "px4-ca-lint"


def user_engine_path() -> Path:
    """Where a single downloaded engine is expected: the user's data directory."""
    return user_data_directory() / ENGINE_NAME


def versioned_engine_path(px4: str) -> Path:
    """Where the engine for one PX4 version is expected when several are installed."""
    return user_data_directory() / "engines" / px4 / ENGINE_NAME


def _is_engine(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def installed_versions() -> list[str]:
    """The PX4 versions that have an engine in the user's data directory."""
    directory = user_data_directory() / "engines"

    if not directory.is_dir():
        return []

    return sorted(entry.name for entry in directory.iterdir() if _is_engine(entry / ENGINE_NAME))


# a PX4 release tag such as v1.17.0 or v1.18.0-rc1
_RELEASE = re.compile(r"v\d+\.\d+\.\d+(-(alpha|beta|rc)\d+)?")


def requested_px4(option: str | None = None) -> str | None:
    """The PX4 version asked for with --px4 or $PX4_CA_PX4, written the way PX4 tags it."""
    name = (option or os.environ.get(PX4_ENV) or "").strip()

    if not name:
        return None

    if name[0].isdigit():
        name = "v" + name

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise EngineError(f"'{name}' is not a PX4 version, for example v1.17.0")

    return name


def default_locations() -> list[Path]:
    # an engine built in the current directory wins over an installed one
    return [Path("build") / "engine" / ENGINE_NAME, user_engine_path()]


def find_engine(explicit: str | None = None, px4: str | None = None) -> Path:
    """Choose the engine.

    An engine named with --engine or $PX4_CA_ENGINE is used as it is. Otherwise a PX4 version
    (--px4 or $PX4_CA_PX4, see requested_px4) selects the engine installed for that version, and
    without one the default locations are tried. They are also tried for a PX4 release that has
    no engine installed under its name: check_px4_version then decides whether the engine fits.
    """
    named = explicit or os.environ.get(ENGINE_ENV)

    if named:
        if _is_engine(Path(named)):
            return Path(named)

        raise EngineError(f"{'--engine' if explicit else ENGINE_ENV}: '{named}' is not an executable file")

    versions = installed_versions()

    if px4 and _is_engine(versioned_engine_path(px4)):
        return versioned_engine_path(px4)

    if not px4 or _RELEASE.fullmatch(px4):
        for candidate in default_locations():
            if _is_engine(candidate):
                return candidate

    if px4:
        installed = (
            f"Installed: {', '.join(versions)}." if versions else "No engine is installed for any version."
        )
        raise EngineError(
            f"no engine for PX4 {px4}: '{versioned_engine_path(px4)}' is not an executable file. "
            f"{installed} See the Install section of the README."
        )

    if len(versions) == 1:
        return versioned_engine_path(versions[0])

    if versions:
        raise EngineError(
            f"engines for several PX4 versions are installed ({', '.join(versions)}). "
            f"Choose one with --px4 VERSION or {PX4_ENV}."
        )

    raise EngineError(
        f"{ENGINE_NAME} not found. Put the engine at '{versioned_engine_path('<PX4 version>')}', "
        f"pass --engine PATH or set {ENGINE_ENV}. See the Install section of the README."
    )


def check_px4_version(px4: str | None, engine: Path, result: dict) -> None:
    """Refuse a result from an engine that was built against another PX4 release than asked for."""
    if px4 and _RELEASE.fullmatch(px4) and result.get("px4_version") != px4:
        raise EngineError(
            f"PX4 {px4} was asked for, but the engine '{engine}' was built against "
            f"PX4 {result.get('px4_version')}"
        )


def engine_locations() -> list[tuple[str, Path]]:
    """Every place an engine is looked for, in the order of find_engine, with a name for it."""
    locations = []

    if os.environ.get(ENGINE_ENV):
        locations.append((f"${ENGINE_ENV}", Path(os.environ[ENGINE_ENV])))

    locations.append(("current directory", default_locations()[0]))
    locations.append(("user data directory", user_engine_path()))
    locations += [(f"--px4 {px4}", versioned_engine_path(px4)) for px4 in installed_versions()]
    return locations


def run_engine(engine: Path, params: dict[str, str]) -> dict:
    """Run the engine on the given parameters and return its JSON output.

    When PX4 cannot produce a matrix the output has an "error" entry and no matrices.
    """
    with tempfile.TemporaryDirectory(prefix="px4-ca-lint-") as directory:
        params_path = Path(directory) / "input.params"
        output_path = Path(directory) / "output.json"
        params_path.write_text(
            "".join(f"{name} {value}\n" for name, value in params.items()), encoding="ascii"
        )

        try:
            # PX4 prints start-up messages to stdout, the result goes to the output file
            process = subprocess.run(
                [str(engine), str(params_path), str(output_path)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=_TIMEOUT_S,
                check=False,
            )

        except subprocess.TimeoutExpired as error:
            raise EngineError(f"the engine did not finish within {_TIMEOUT_S} s") from error

        except OSError as error:
            raise EngineError(f"cannot run '{engine}': {error.strerror}") from error

        result = None

        if output_path.is_file():
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))

            except json.JSONDecodeError:
                result = None

    code = process.returncode

    if code == _EXIT_UNSUPPORTED and result is not None:
        raise EngineError(
            f"CA_AIRFRAME {result.get('ca_airframe')} is not supported yet "
            f"(engine built against PX4 {result.get('px4_version')})"
        )

    if code == _EXIT_PX4_FAILED and result is not None and "error" in result:
        # not a tool failure: the rules report it as a finding
        code = 0

    if code != 0 or result is None:
        detail = process.stderr.strip().splitlines()[-1:] or ["no error message"]
        raise EngineError(f"the engine failed (exit code {code}): {detail[0]}")

    schema = result.get("engine_schema")

    if schema not in SUPPORTED_ENGINE_SCHEMAS:
        raise EngineError(
            f"the engine writes engine_schema {schema}, this tool reads "
            f"{', '.join(str(s) for s in SUPPORTED_ENGINE_SCHEMAS)}. "
            "Use a matching engine and tool version."
        )

    return result
