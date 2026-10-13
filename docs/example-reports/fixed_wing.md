### px4-ca-lint report: 0 error(s), 0 warning(s)

- Input: `examples/fixed_wing.params` (plain format, 12 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 1 (Fixed Wing), 1 motors, 4 servos
- Tool: px4-ca-lint 0.4.0

#### Findings

- CA002 was not checked: this PX4 version does not report dropped axes

<details><summary>Matrix 0 (pseudo_inverse)</summary>

Effectiveness: what each actuator produces on each axis

| axis | motor0 | servo0 | servo1 | servo2 | servo3 |
|---|---:|---:|---:|---:|---:|
| roll | 0.000 | -0.500 | 0.500 | 0.000 | 0.000 |
| pitch | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| yaw | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| thrust_x | 6.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor0 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 |
| servo0 | -1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo1 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo2 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| servo3 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |

</details>

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
