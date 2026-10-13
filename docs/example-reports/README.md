# Example reports

The report of every file in [`examples/`](../../examples), as the tool prints it with
`--format markdown` and the engine for PX4 v1.17.0. They are written by
`tools/example_reports.py`, and the tests fail when one of them is out of date.

[Reading a report](../reading-a-report.md) explains the parts of a report.

| Parameter file | What it is | Findings | Errors | Warnings | Exit code | Report |
|---|---|---|---:|---:|---:|---|
| [`quad_qgc_export.params`](../../examples/quad_qgc_export.params) | A quadrotor X, as a parameter file saved by QGroundControl | none | 0 | 0 | 0 | [report](quad_qgc_export.md) |
| [`quad_wrong_spin.params`](../../examples/quad_wrong_spin.params) | A quadrotor with the wrong spin direction on one motor | [CA020](../../rules/CA020.md) | 0 | 1 | 0 | [report](quad_wrong_spin.md) |
| [`quad_same_spin.params`](../../examples/quad_same_spin.params) | A quadrotor whose rotors all turn the same way | [CA006](../../rules/CA006.md) | 1 | 0 | 1 | [report](quad_same_spin.md) |
| [`quad_no_positions.params`](../../examples/quad_no_positions.params) | A quadrotor whose rotor positions were never entered | [CA005](../../rules/CA005.md) | 2 | 0 | 1 | [report](quad_no_positions.md) |
| [`quad_rotor_down.params`](../../examples/quad_rotor_down.params) | A quadrotor with one rotor axis pointing down | [CA012](../../rules/CA012.md) | 1 | 0 | 1 | [report](quad_rotor_down.md) |
| [`hexa_rotor_count_4.params`](../../examples/hexa_rotor_count_4.params) | A hexarotor whose `CA_ROTOR_COUNT` was left at 4 | [CA021](../../rules/CA021.md), [CA006](../../rules/CA006.md) | 1 | 1 | 1 | [report](hexa_rotor_count_4.md) |
| [`no_rotors.params`](../../examples/no_rotors.params) | Rotor positions without `CA_ROTOR_COUNT` | [CA001](../../rules/CA001.md), [CA021](../../rules/CA021.md) | 1 | 1 | 1 | [report](no_rotors.md) |
| [`tricopter_tilt.params`](../../examples/tricopter_tilt.params) | A tricopter with a tilt servo for yaw | none | 0 | 0 | 0 | [report](tricopter_tilt.md) |
| [`fixed_wing.params`](../../examples/fixed_wing.params) | A plane with one motor, two ailerons, an elevator and a rudder | none | 0 | 0 | 0 | [report](fixed_wing.md) |
| [`fixed_wing_thrust_offset.params`](../../examples/fixed_wing_thrust_offset.params) | The same plane with the motor above the centre of gravity | [CA011](../../rules/CA011.md) | 0 | 1 | 0 | [report](fixed_wing_thrust_offset.md) |
| [`standard_vtol.params`](../../examples/standard_vtol.params) | PX4's SIH standard VTOL: four lift motors, a pusher and three control surfaces | none | 0 | 0 | 0 | [report](standard_vtol.md) |
| [`standard_vtol_pusher_offset.params`](../../examples/standard_vtol_pusher_offset.params) | The standard VTOL with the pusher 5 cm above the centre of gravity | [CA010](../../rules/CA010.md), [CA011](../../rules/CA011.md) | 0 | 2 | 0 | [report](standard_vtol_pusher_offset.md) |
| [`standard_vtol_pusher_backwards.params`](../../examples/standard_vtol_pusher_backwards.params) | The standard VTOL with the axis of the pusher turned around | [CA012](../../rules/CA012.md) | 1 | 0 | 1 | [report](standard_vtol_pusher_backwards.md) |
| [`standard_vtol_typing_mistakes.params`](../../examples/standard_vtol_typing_mistakes.params) | The standard VTOL with a decimal comma and a misspelled parameter name | [CA030](../../rules/CA030.md), [CA031](../../rules/CA031.md) | 1 | 1 | 1 | [report](standard_vtol_typing_mistakes.md) |
| [`tailsitter.params`](../../examples/tailsitter.params) | A tailsitter VTOL with two motors and two elevons | none | 0 | 0 | 0 | [report](tailsitter.md) |
| [`tiltrotor.params`](../../examples/tiltrotor.params) | A tiltrotor VTOL with four motors, two of which tilt | none | 0 | 0 | 0 | [report](tiltrotor.md) |
| [`tiltrotor_tilt_servo_missing.params`](../../examples/tiltrotor_tilt_servo_missing.params) | The tiltrotor with a rotor assigned to a tilt servo that does not exist | [CA022](../../rules/CA022.md) | 0 | 1 | 0 | [report](tiltrotor_tilt_servo_missing.md) |
