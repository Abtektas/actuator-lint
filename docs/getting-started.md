# Getting started

From a vehicle to a report in a few minutes. You need a computer with Linux
or macOS; no vehicle has to be connected and no simulator has to run.

Before you start, read the [Safety and liability](../README.md#safety-and-liability)
section of the README. The tool is a review aid. Using it and acting on what
it prints is your own decision, at your own risk.

## 1. Install the tool and the engine

Follow [Install](../README.md#install) in the README: one command for the
Python package and a few lines for the engine of your platform. Then check
both:

```
$ actuator-lint --version
actuator-lint 0.4.1
Copyright (c) 2026, the actuator-lint contributors
...
$ actuator-lint engines
```

`actuator-lint engines` lists the engine that was found and the PX4 version it
was built against. The prebuilt engines are for PX4 v1.17.0. A report is only
valid for the PX4 version of the engine, so the firmware of your vehicle
should be that version.

## 2. Get the parameters of your vehicle

Any of these works; the tool finds out which format a file has.

**From QGroundControl.** Connect the vehicle, open the Parameters page of the
vehicle setup, then choose Tools and "Save to file...". Pass the saved file to
the tool as it is. It contains every parameter of the vehicle; the tool uses
the `CA_*` ones and tells you when the file has parameters that the PX4
version of the engine does not know.

**From a PX4 airframe script.** A file from
`ROMFS/px4fmu_common/init.d/airframes` of the PX4 source tree, with lines like
`param set-default CA_ROTOR_COUNT 4`. Leave the script where it is in the PX4
tree, so that the files it sources are read as well.

**Written by hand.** One parameter per line, name and value:

```
CA_AIRFRAME 0
CA_ROTOR_COUNT 4
CA_ROTOR0_PX 0.15
CA_ROTOR0_PY 0.15
CA_ROTOR0_KM 0.05
```

A parameter that is not in the file keeps the default of PX4, as on a vehicle
where it was never set. In a hand-written file that is easy to overlook: a
rotor without `CA_ROTORn_PX` and `CA_ROTORn_PY` sits at the centre of gravity.

## 3. Run it

```
actuator-lint my_vehicle.params
```

Look at the first lines before anything else. For the small QGroundControl
file in `examples/` they are:

```
Input:     examples/quad_qgc_export.params (qgc format, 15 parameters)
PX4:       v1.17.0 (d6f12ad1c4)
Airframe:  CA_AIRFRAME 0 (Multirotor)
Actuators: 4 motors, 0 servos
```

If the airframe or the number of motors and servos is not what your vehicle
has, the rest of the report is about another vehicle. Fix that first; a
missing `CA_ROTOR_COUNT`, for example, gives a vehicle without motors.

## 4. Read the findings

The findings are near the end of the report. Each one names a rule, and the
line below it links to the page of that rule, which says what was checked, why
it matters and what to look at:

```
Findings
  error CA006 matrix 0: yaw cannot be controlled independently: ...
      an axis cannot be controlled independently of the others: https://github.com/Abtektas/actuator-lint/blob/v0.4.1/rules/CA006.md
  1 error(s), 0 warning(s)
```

- An **error** means that the configuration is most likely wrong, or that the
  file could not be read as it was meant.
- A **warning** is something to understand before flying. It can be intended.
- **No findings** means that none of the rules objected. It does not mean the
  configuration is safe: the tool only checks what it knows about.

The exit code is 1 when there is an error, so the tool can be used in a
script; see the [README](../README.md#findings) for the options.

[Reading a report](reading-a-report.md) explains the matrices and the other
parts. To see what the tool prints for known mistakes without installing
anything, look at the [example reports](example-reports/README.md).

## 5. Try a mistake on purpose

The files in `examples/` are small and each shows one thing. For example a
quadrotor whose rotors all turn the same way:

```
actuator-lint examples/quad_same_spin.params
```

Changing a value in a copy of your own file and looking at what the report
says is a good way to learn what a parameter does.

## 6. Compare two files

After changing parameters, compare the old and the new file:

```
actuator-lint diff before.params after.params
```

This lists the parameters that differ, the matrix values that changed and the
findings that are new or gone.

## 7. Share a report

```
actuator-lint --format markdown my_vehicle.params
```

prints a report that can be pasted into a GitHub issue or a forum post, and
`--format json` one for other programs.

## What the tool does not do

- It does not look at the outputs: which motor is on which pin, PWM limits,
  motor order on the vehicle and propeller directions are not checked. Do the
  motor test without propellers that PX4 describes.
- It does not look at controller gains, sensors, the battery or the airframe
  itself.
- It checks a PX4 version, not a vehicle. Parameters that were changed on the
  vehicle after the file was saved are not in the report.
