# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are explained in [docs/versioning.md](docs/versioning.md).

## Unreleased

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

### Changed

- The single engine location of earlier versions,
  `~/.local/share/px4-ca-lint/px4_ca_engine`, keeps working and is tried before
  the new directories. The message for a missing engine names the new location.

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
