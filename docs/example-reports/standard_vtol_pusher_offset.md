### actuator-lint report: 0 error(s), 2 warning(s)

- Input: `examples/standard_vtol_pusher_offset.params` (plain format, 26 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 2 (Standard VTOL), 5 motors, 3 servos
- Tool: actuator-lint 0.4.1

#### Findings

- **warning [CA010](https://github.com/Abtektas/actuator-lint/blob/v0.4.1/rules/CA010.md)** (matrix 0): motor4: thrust_x gain up to 4.00 (limit 2); the output saturates at a thrust_x setpoint of 0.25
- **warning [CA011](https://github.com/Abtektas/actuator-lint/blob/v0.4.1/rules/CA011.md)** (matrix 0): motor0, motor1, motor2, motor3: commanded by the thrust_x setpoint without producing thrust_x thrust; a thrust_x setpoint changes their output
- CA002 was not checked: this PX4 version does not report dropped axes

#### Flight phases

The motors PX4 stops in a flight phase, whatever the setpoint:

| Flight phase | Stopped motors |
|---|---|
| hover | none |
| transition to forward flight | none |
| forward flight | motor0, motor1, motor2, motor3 |
| transition to hover | none |

PX4 can also stop a motor while there is no thrust demand for it, for example a pusher in hover. That depends on the setpoints and is not listed.

PX4 does not recompute the matrices when the flight phase changes, and it sends no command to a stopped motor.

Mix of the other motors in forward flight:

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor4 | 0.000 | 0.000 | 0.000 | 4.000 | 0.000 | 0.000 |

<details><summary>Matrix 0 (sequential_desaturation, roll/pitch/yaw normalised)</summary>

Effectiveness: what each actuator produces on each axis

| axis | motor0 | motor1 | motor2 | motor3 | motor4 |
|---|---:|---:|---:|---:|---:|
| roll | -1.300 | 1.300 | 1.300 | -1.300 | 0.000 |
| pitch | 1.300 | -1.300 | 1.300 | -1.300 | -0.325 |
| yaw | 0.325 | 0.325 | -0.325 | -0.325 | 0.000 |
| thrust_x | 0.000 | 0.000 | 0.000 | 0.000 | 6.500 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | -6.500 | -6.500 | -6.500 | -6.500 | 0.000 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor0 | -0.707 | 0.707 | 1.000 | 0.250 | 0.000 | -1.000 |
| motor1 | 0.707 | -0.707 | 1.000 | -0.250 | 0.000 | -1.000 |
| motor2 | 0.707 | 0.707 | -1.000 | 0.250 | 0.000 | -1.000 |
| motor3 | -0.707 | -0.707 | -1.000 | -0.250 | 0.000 | -1.000 |
| motor4 | 0.000 | 0.000 | 0.000 | 4.000 | 0.000 | 0.000 |

</details>

<details><summary>Matrix 1 (pseudo_inverse)</summary>

Effectiveness: what each actuator produces on each axis

| axis | servo0 | servo1 | servo2 |
|---|---:|---:|---:|
| roll | 1.000 | 0.000 | 0.000 |
| pitch | 0.000 | 1.000 | 0.000 |
| yaw | 0.000 | 0.000 | 1.000 |
| thrust_x | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 |
| thrust_z | 0.000 | 0.000 | 0.000 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| servo0 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo1 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo2 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |

</details>

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
