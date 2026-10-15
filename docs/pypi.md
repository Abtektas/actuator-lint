# actuator-lint

Check a PX4 control allocation configuration before it flies.

`actuator-lint` reads the `CA_*` parameters of a vehicle from a file, runs PX4's
own actuator effectiveness and control allocation code on them, and reports the
resulting matrices and likely configuration mistakes. No vehicle and no
simulator are needed.

![actuator-lint in a terminal](https://raw.githubusercontent.com/Abtektas/actuator-lint/main/docs/images/terminal.svg)

## Safety and liability

- This software is provided "as is", without warranty of any kind. The
  authors and contributors accept no liability and no responsibility for any
  use of the tool or of its results. Whether and how you use it is entirely
  your own decision, at your own risk. The terms are in the
  [license](https://github.com/Abtektas/actuator-lint/blob/main/LICENSE), which
  `actuator-lint license` prints.
- It is a review aid. It does not approve a vehicle as safe or airworthy, and
  a report without findings does not mean the configuration is safe.
- It does not replace bench tests, motor tests without propellers, or careful
  step-by-step flight testing.
- This project is not affiliated with or endorsed by the PX4 project or the
  Dronecode Foundation. PX4 is a trademark of Dronecode Project, Inc. It is
  used here only to name the software this tool works with.

## Install

This package is the Python part. It needs Python 3.11 or newer and has no
Python dependencies:

```
pip install actuator-lint
```

The tool also needs the **engine**, a program built from the control
allocation code of one PX4 version. Prebuilt engines for Linux (x86_64 and
arm64) and macOS (arm64) are files of each
[release on GitHub](https://github.com/Abtektas/actuator-lint/releases); the
[README](https://github.com/Abtektas/actuator-lint#install) has the commands to
download, check and install one, and says how to build an engine for another
PX4 version. A result is only valid for the PX4 version the engine was built
against, which every report names.

## Documentation

- [Getting started](https://github.com/Abtektas/actuator-lint/blob/main/docs/getting-started.md)
- [Reading a report](https://github.com/Abtektas/actuator-lint/blob/main/docs/reading-a-report.md)
- [Example reports](https://github.com/Abtektas/actuator-lint/blob/main/docs/example-reports/README.md)
- [Rules](https://github.com/Abtektas/actuator-lint/tree/main/rules)
- [Changelog](https://github.com/Abtektas/actuator-lint/blob/main/CHANGELOG.md)
