### actuator-lint report: 1 error(s), 1 warning(s)

- Input: `examples/no_rotors.params` (plain format, 5 parameters)
- PX4: `v1.17.0` (`d6f12ad1c4`)
- Airframe: `CA_AIRFRAME` 0 (Multirotor), 0 motors, 0 servos
- Tool: actuator-lint 0.4.2

#### Findings

- **error [CA001](https://github.com/Abtektas/actuator-lint/blob/v0.4.2/rules/CA001.md)**: the configuration has no actuators; check CA_ROTOR_COUNT
- **warning [CA021](https://github.com/Abtektas/actuator-lint/blob/v0.4.2/rules/CA021.md)**: motor0, motor1: rotor parameters are set, but CA_ROTOR_COUNT is 0 (not set in the input); PX4 uses no rotors
- CA002 was not checked: this PX4 version does not report dropped axes

_This report is a review aid, not an airworthiness approval. No findings does not mean the configuration is safe. There is no warranty, and the authors accept no liability and no responsibility: whether and how you use it is your own decision, at your own risk._
