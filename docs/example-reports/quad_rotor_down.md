### px4-ca-lint report: 1 error(s), 0 warning(s)

- Input: `examples/quad_rotor_down.params` (plain format, 15 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 0 (Multirotor), 4 motors, 0 servos
- Tool: px4-ca-lint 0.4.0

#### Findings

- **error [CA012](https://github.com/Abtektas/px4-ca-lint/blob/v0.4.0/rules/CA012.md)** (matrix 0): motor1: PX4 takes the thrust as pointing down (positive thrust_z effectiveness), but the rotors that lift this vehicle have to point up. Check the sign of CA_ROTORn_AZ and CA_ROTORn_CT
- CA002 was not checked: this PX4 version does not report dropped axes

<details><summary>Matrix 0 (sequential_desaturation, roll/pitch/yaw normalised)</summary>

Effectiveness: what each actuator produces on each axis

| axis | motor0 | motor1 | motor2 | motor3 |
|---|---:|---:|---:|---:|
| roll | -0.975 | -0.975 | 0.975 | -0.975 |
| pitch | 0.975 | 0.975 | 0.975 | -0.975 |
| yaw | 0.325 | -0.325 | -0.325 | -0.325 |
| thrust_x | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | -6.500 | 6.500 | -6.500 | -6.500 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor0 | -0.707 | 0.707 | 1.000 | 0.000 | 0.000 | -1.000 |
| motor1 | -0.707 | 0.707 | -1.000 | 0.000 | 0.000 | 1.000 |
| motor2 | 0.707 | 0.707 | -1.000 | 0.000 | 0.000 | -1.000 |
| motor3 | -0.707 | -0.707 | -1.000 | 0.000 | 0.000 | -1.000 |

</details>

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
