# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are explained in [docs/versioning.md](docs/versioning.md).

## Unreleased

### Added

- Documentation for new users: [Getting started](docs/getting-started.md),
  [Reading a report](docs/reading-a-report.md) with a figure of the body axes
  and motor numbers, and the report of every file in `examples/` in
  [docs/example-reports](docs/example-reports/README.md). The example reports
  are written by `tools/example_reports.py`, and a test fails when one of them
  is out of date.
  [Reading a report](docs/reading-a-report.md#mix) says how far mix values can
  differ between CPU types.
- A picture of the tool in a terminal at the top of the README. It is written
  by `tools/terminal_image.py` from what the tool prints, and a test fails
  when it is out of date.
- `px4-ca-lint license` prints the license and the notices, which are now
  part of the Python package. The engine prints its notice with its usage,
  and every source file names its license.
- A [GitHub Action](docs/github-action.md): `uses: Abtektas/px4-ca-lint@...`
  installs a release on the runner, checks the files you name and adds the
  reports to the job summary.
- Package metadata for the Python Package Index and a workflow that uploads
  a published release there. It does nothing until the repository variable
  `PYPI_PUBLISH` is set; see [docs/versioning.md](docs/versioning.md).

### Changed

- `px4-ca-lint --version` prints the copyright, the license and the terms in
  short after the version line. The first line is unchanged.

## 0.4.0 - 2026-10-13

Prebuilt engines contain the control allocation code of PX4 v1.17.0
(`engine_schema` 1), as in 0.3.0. They are new builds: the flight phases and
the check of integer parameters need the engine of this release, so replace
the engine when you update the tool.

### Added

- Engines for several PX4 versions can be installed side by side, in
  `~/.local/share/px4-ca-lint/engines/<PX4 version>/px4_ca_engine`. The new
  option `--px4 VERSION` (or `$PX4_CA_PX4`) chooses one. When only one is
  installed it is used without the option; when several are installed and none
  is chosen, the tool stops with an error.
- When `--px4` names a PX4 release, an engine built against anything else is
  refused, wherever it was found, also one given with `--engine` or
  `$PX4_CA_ENGINE`.
- `px4-ca-lint engines` lists the engines the tool finds, the PX4 version each
  was built against and the one a run without `--engine` and `--px4` uses.
- For VTOLs the report lists the motors PX4 stops in a flight phase whatever
  the setpoint, and the mix of the motors that are left: for a standard VTOL
  the lift motors in forward flight, for a tiltrotor the motors that do not
  tilt. Motors that PX4 stops only while there is no thrust demand for them,
  such as a pusher in hover, are not listed. The JSON report has the new entry
  `flight_phases`. An engine built from this version is needed; with an older
  engine the report says that the flight phases are missing.
- The golden reports of the seven standard VTOL and three tiltrotor scripts of
  PX4 v1.17.0 that have such motors now store them.
- Rule CA005 (error): an axis the vehicle cannot be flown without is not
  controlled by any matrix, for example roll and pitch of a multirotor whose
  rotor positions are missing, or forward thrust of a standard VTOL. Such
  configurations gave no finding before. New example
  `examples/quad_no_positions.params`. Of PX4's own airframe scripts only
  `1002_standard_vtol.hil` is affected, whose forward rotor is not counted.
- Rule CA006 (error, or warning for an axis the vehicle type does not need):
  an axis cannot be controlled independently of the others, for example yaw
  of a quadrotor whose rotors all turn the same way. It is the test
  PX4 `main` applies when it drops an axis (CA002), applied by the tool for PX4
  versions that do not have it, which are v1.17.0 and release/1.18. Such
  configurations gave no finding there. The result was compared with PX4
  `main` for 4400 random configurations. New example
  `examples/quad_same_spin.params`; `examples/hexa_rotor_count_4.params` gets
  the finding for yaw as well. None of the airframe scripts of PX4 v1.17.0 is
  affected; of release/1.18 only `5021_xplane_qtailsitter`, with two warnings.
- Rule CA012 (error): the thrust of a rotor points down or backwards, for
  example a lift rotor with `CA_ROTORn_AZ 1`, a forward rotor with
  `CA_ROTORn_AX -1`, or a negative `CA_ROTORn_CT`. Such configurations gave no
  finding before. Multirotors with rotors along other axes than the vertical,
  such as PX4's omnicopter airframes, are left alone. New examples
  `examples/quad_rotor_down.params` and
  `examples/standard_vtol_pusher_backwards.params`. None of PX4's own airframe
  scripts is affected.
- Rule CA030 (error): a line of the parameter file could not be used, for
  example a value with a decimal comma. Rule CA031 (warning): a `CA_*`
  parameter does not exist in the PX4 version of the engine, for example a
  misspelled name. Both were notes before, with exit code 0. New example
  `examples/standard_vtol_typing_mistakes.params`.

### Changed

- Every report, the help text, the README and the release notes now say in so
  many words that there is no warranty, that the authors accept no liability
  and no responsibility, and that using the tool is the user's own decision.
- CA002 is a warning, no longer an error, for an axis the vehicle type does not
  need. PX4 `main` drops thrust_x and thrust_y of its own airframe
  `5021_xplane_qtailsitter`, which gave two errors and exit code 1 for a
  working airframe. For an axis the vehicle type needs, and for vehicle types
  the tool knows nothing about, it stays an error.
- The single engine location of earlier versions,
  `~/.local/share/px4-ca-lint/px4_ca_engine`, keeps working and is tried before
  the new directories. The message for a missing engine names the new location.

### Fixed

- A parameter file that starts with a byte order mark lost its first line, so
  that for example `CA_AIRFRAME` kept its default and the report was for a
  multirotor.
- A value written with digits that are not ASCII ended in a Python traceback.
- Values that Python reads as a number but the engine does not, such as `1_0`,
  were passed on and read as another number. Only plain decimal numbers are
  accepted now.
- An integer parameter with a fractional value was rounded, for example
  `CA_AIRFRAME 2.5` to a tiltrotor. The engine now leaves such a parameter at
  its default and CA030 reports it. This needs an engine built from this
  version.

## 0.3.0 - 2026-10-09

Prebuilt engines contain the control allocation code of PX4 v1.17.0
(`engine_schema` 1), as in 0.2.0.

### Added

- Tiltrotor VTOLs (`CA_AIRFRAME` 3), tailsitter VTOLs (`CA_AIRFRAME` 4) and
  multirotors with tilt (`CA_AIRFRAME` 8). The golden tests now cover 11 more
  airframe scripts of PX4 v1.17.0, 91 in total, and the SITL cross-check
  includes the three types. New examples `examples/tailsitter.params`,
  `examples/tiltrotor.params` and `examples/tricopter_tilt.params`. An engine
  built from this version is needed; the prebuilt engines of 0.2.0 report these
  airframes as not supported.
- For a tiltrotor the report shows the matrices PX4 computes after a parameter
  change, with the tilt servos in the hover position, and says so in a note.
  The matrices PX4 uses during the transition and in forward flight are not
  covered.
- Rule CA022: a rotor is assigned to a tilt servo that does not exist
  (`CA_ROTORn_TILT` above `CA_SV_TL_COUNT`), so PX4 treats it as not tilting.
  New example `examples/tiltrotor_tilt_servo_missing.params`.

### Changed

- The text report says in which order servos are numbered: control surfaces
  first, then tilt servos.
- The SITL cross-check also compares the name of the effectiveness class PX4
  reports with the one the engine used.

## 0.2.0 - 2026-10-07

Prebuilt engines contain the control allocation code of PX4 v1.17.0
(`engine_schema` 1), as in 0.1.0.

### Added

- Fixed-wing vehicles (`CA_AIRFRAME` 1). The golden tests now cover the 23
  plane airframe scripts of PX4 v1.17.0 and the SITL cross-check includes
  PX4's SIH plane. New examples `examples/fixed_wing.params` and
  `examples/fixed_wing_thrust_offset.params`. An engine built from this
  version is needed; the prebuilt engines of 0.1.0 report the airframe as not
  supported.
- Rule CA021: a rotor has geometry parameters but its index is
  `CA_ROTOR_COUNT` or higher, so PX4 ignores it. New example
  `examples/hexa_rotor_count_4.params`.
- `install check` workflow: follows the install steps, with uv and with a
  virtual environment, with the files of a published release on clean
  machines.

### Changed

- The install instructions recommend `uv tool install`, with pipx and a
  virtual environment as alternatives.

## 0.1.0 - 2026-10-02

First release. Prebuilt engines contain the control allocation code of PX4
v1.17.0 (`engine_schema` 1).

### Added

- Engine built against PX4 v1.17.0 that writes the effectiveness and mix
  matrices as JSON (`engine_schema` 1). Supported `CA_AIRFRAME` values: 0
  (multirotor) and 2 (standard VTOL).
- Command line tool with text and JSON reports. Input formats: plain, PX4
  airframe script, QGroundControl export.
- Rules CA001, CA002, CA003, CA004, CA010, CA011 and CA020.
- Golden tests over the airframe scripts shipped with PX4 v1.17.0 and a
  cross-check against PX4 SITL.
- `--format markdown` for reports that are pasted into issues and pull
  requests.
- `px4-ca-lint diff BEFORE AFTER` compares two parameter files: parameters,
  matrix values and findings.
- Prebuilt engines for Linux x86_64, Linux arm64 and macOS arm64, with
  checksums and build provenance.
- A downloaded engine is found in `~/.local/share/px4-ca-lint/`.
- Findings link to the document of their rule.
