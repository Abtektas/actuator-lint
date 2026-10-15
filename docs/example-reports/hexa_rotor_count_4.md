### actuator-lint report: 1 error(s), 1 warning(s)

- Input: `examples/hexa_rotor_count_4.params` (plain format, 20 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 0 (Multirotor), 4 motors, 0 servos
- Tool: actuator-lint 0.4.2

#### Findings

- **warning [CA021](https://github.com/Abtektas/actuator-lint/blob/v0.4.2/rules/CA021.md)**: motor4, motor5: rotor parameters are set, but CA_ROTOR_COUNT is 4; PX4 uses rotors 0 to 3 only
- **error [CA006](https://github.com/Abtektas/actuator-lint/blob/v0.4.2/rules/CA006.md)** (matrix 0): yaw cannot be controlled independently: its effectiveness row is a combination of the rows of roll and pitch, so no actuator command changes yaw without changing them. PX4 v1.17.0 computes a mix for it all the same; PX4 main drops such an axis (CA002)
- CA002 was not checked: this PX4 version does not report dropped axes

<details><summary>Matrix 0 (sequential_desaturation, roll/pitch/yaw normalised)</summary>

Effectiveness: what each actuator produces on each axis

| axis | motor0 | motor1 | motor2 | motor3 |
|---|---:|---:|---:|---:|
| roll | -1.625 | 1.625 | 0.812 | -0.812 |
| pitch | 0.000 | 0.000 | 1.407 | -1.407 |
| yaw | -0.325 | 0.325 | -0.325 | 0.325 |
| thrust_x | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_y | 0.000 | 0.000 | 0.000 | 0.000 |
| thrust_z | -6.500 | -6.500 | -6.500 | -6.500 |

Mix: actuator command per unit of setpoint on each axis

| actuator | roll | pitch | yaw | thrust_x | thrust_y | thrust_z |
|---|---:|---:|---:|---:|---:|---:|
| motor0 | -0.822 | 0.405 | -1.000 | 0.000 | 0.000 | -1.000 |
| motor1 | 0.822 | -0.405 | 1.000 | 0.000 | 0.000 | -1.000 |
| motor2 | 0.061 | 0.915 | -1.000 | 0.000 | 0.000 | -1.000 |
| motor3 | -0.061 | -0.915 | 1.000 | 0.000 | 0.000 | -1.000 |

</details>

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
