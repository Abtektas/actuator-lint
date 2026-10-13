### px4-ca-lint report: 0 error(s), 0 warning(s)

- Input: `examples/tricopter_tilt.params` (plain format, 13 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 8 (MC Tilt), 3 motors, 1 servos
- Tool: px4-ca-lint 0.4.0

#### Findings

- CA002 was not checked: this PX4 version does not report dropped axes

<details><summary>Matrix 0 (sequential_desaturation, roll/pitch/yaw normalised)</summary>

Effectiveness: what each actuator produces on each axis

| axis | motor0 | motor1 | motor2 | servo0 |
|---|---:|---:|---:|---:|
| roll | -2.815 | 2.795 | 0.000 | 0.000 |
| pitch | 1.625 | 1.625 | -3.250 | 0.000 |
| yaw | 0.000 | 0.000 | 0.000 | -1.000 |
| thrust_x | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | -6.500 | -6.500 | -6.500 | 0.000 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor0 | -0.707 | 0.405 | 0.000 | 0.000 | 0.000 | -0.997 |
| motor1 | 0.707 | 0.408 | 0.000 | 0.000 | 0.000 | -1.003 |
| motor2 | 0.000 | -0.814 | 0.000 | 0.000 | 0.000 | -1.000 |
| servo0 | 0.000 | 0.000 | -1.000 | 0.000 | 0.000 | 0.000 |

</details>

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
