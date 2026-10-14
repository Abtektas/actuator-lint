### px4-ca-lint report: 0 error(s), 0 warning(s)

- Input: `examples/tiltrotor.params` (plain format, 26 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 3 (VTOL Tiltrotor), 4 motors, 6 servos
- Tool: px4-ca-lint 0.4.1

#### Findings

- CA002 was not checked: this PX4 version does not report dropped axes

#### Notes

- tiltrotor: matrix 0 is the one PX4 computes after a parameter change, with the tilt servos at their minimum angle (CA_SV_TLn_MINA), which is the hover position; in flight PX4 recomputes it with the tilt angle, which this report does not cover

#### Flight phases

The motors PX4 stops in a flight phase, whatever the setpoint:

| Flight phase | Stopped motors |
|---|---|
| hover | none |
| transition to forward flight | none |
| forward flight | motor1, motor3 |
| transition to hover | none |

PX4 can also stop a motor while there is no thrust demand for it, for example a pusher in hover. That depends on the setpoints and is not listed.

PX4 recomputes the matrices of this airframe in flight, so the mix of the other motors is not shown.

<details><summary>Matrix 0 (sequential_desaturation, roll/pitch/yaw normalised)</summary>

Effectiveness: what each actuator produces on each axis

| axis | motor0 | motor1 | motor2 | motor3 | servo4 | servo5 |
|---|---:|---:|---:|---:|---:|---:|
| roll | -6.500 | 6.500 | 6.500 | -6.500 | 0.000 | 0.000 |
| pitch | 6.500 | -6.500 | 6.500 | -6.500 | 0.000 | 0.000 |
| yaw | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | -1.000 |
| thrust_x | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | -6.500 | -6.500 | -6.500 | -6.500 | 0.000 | 0.000 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor0 | -0.707 | 0.707 | 0.000 | 0.000 | 0.000 | -1.000 |
| motor1 | 0.707 | -0.707 | 0.000 | 0.000 | 0.000 | -1.000 |
| motor2 | 0.707 | 0.707 | 0.000 | 0.000 | 0.000 | -1.000 |
| motor3 | -0.707 | -0.707 | 0.000 | 0.000 | 0.000 | -1.000 |
| servo4 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| servo5 | 0.000 | 0.000 | -1.000 | 0.000 | 0.000 | 0.000 |

</details>

<details><summary>Matrix 1 (pseudo_inverse)</summary>

Effectiveness: what each actuator produces on each axis

| axis | servo0 | servo1 | servo2 | servo3 |
|---|---:|---:|---:|---:|
| roll | -0.500 | 0.500 | 0.000 | 0.000 |
| pitch | 0.000 | 0.000 | 0.500 | 0.500 |
| yaw | 0.000 | 0.000 | 0.500 | -0.500 |
| thrust_x | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | 0.000 | 0.000 | 0.000 | 0.000 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| servo0 | -1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo1 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo2 | 0.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| servo3 | 0.000 | 1.000 | -1.000 | 0.000 | 0.000 | 0.000 |

</details>

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
