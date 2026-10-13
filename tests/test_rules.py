import unittest

from px4_ca_lint.rules import RULES, Options, check

AXES = ("roll", "pitch", "yaw", "thrust_x", "thrust_y", "thrust_z")


def matrix(effectiveness, mix, types=None, **overrides):
    """Build one engine matrix from rows given as {axis: [per actuator]} and [per actuator {axis: v}]."""
    count = len(mix)
    types = types or ["motor"] * count
    result = {
        "index": 0,
        "num_actuators": count,
        "method": "pseudo_inverse",
        "normalize_rpy": True,
        "dropped_axes_bitmask": 0,
        "actuators": [{"type": kind, "index": index} for index, kind in enumerate(types)],
        "weak_axes_zeroed": [],
        "effectiveness": {axis: effectiveness.get(axis, [0] * count) for axis in AXES},
        "mix": [{axis: row.get(axis, 0) for axis in AXES} for row in mix],
    }
    result.update(overrides)
    return result


def engine_result(*matrices, **overrides):
    result = {"num_motors": 2, "num_servos": 0, "matrices": list(matrices)}
    result.update(overrides)
    return result


def healthy():
    return matrix(
        {"roll": [-1, 1], "pitch": [1, 1], "yaw": [0.3, -0.3], "thrust_z": [-6.5, -6.5]},
        [
            {"roll": -0.7, "pitch": 0.7, "yaw": 1, "thrust_z": -1},
            {"roll": 0.7, "pitch": 0.7, "yaw": -1, "thrust_z": -1},
        ],
    )


def rules(result):
    return [finding.rule for finding in result.findings]


class Rules(unittest.TestCase):
    def test_every_rule_has_a_document(self):
        from pathlib import Path

        for rule in RULES:
            self.assertTrue(Path("rules", f"{rule}.md").is_file(), rule)

    def test_rule_links_follow_the_version(self):
        from unittest import mock

        from px4_ca_lint.rules import rule_url

        with mock.patch("px4_ca_lint.__version__", "0.2.0.dev0"):
            self.assertIn("/blob/main/rules/CA010.md", rule_url("CA010"))

        with mock.patch("px4_ca_lint.__version__", "0.2.0"):
            self.assertIn("/blob/v0.2.0/rules/CA010.md", rule_url("CA010"))

    def test_healthy_matrix_has_no_findings(self):
        result = check(engine_result(healthy()))
        self.assertEqual(result.findings, [])
        self.assertEqual(result.not_checked, {})

    def test_ca001_px4_failed(self):
        result = check({"error": "PX4 did not produce an effectiveness matrix"})
        self.assertEqual(rules(result), ["CA001"])
        self.assertEqual(result.findings[0].level, "error")

    def test_ca001_no_actuators(self):
        empty = matrix({}, [])
        self.assertEqual(rules(check(engine_result(empty, num_motors=0))), ["CA001"])

    def test_ca002_dropped_axis(self):
        # bit 2 is yaw
        result = check(engine_result(matrix({}, [{}], dropped_axes_bitmask=1 << 2)))
        self.assertEqual(rules(result), ["CA002"])
        self.assertEqual(result.findings[0].axis, "yaw")

    def test_ca002_level_follows_what_the_vehicle_needs(self):
        # bits 3 and 5 are thrust_x and thrust_z
        dropped = dict(healthy(), dropped_axes_bitmask=(1 << 3) | (1 << 5))
        ignore = Options(ignore=frozenset({"CA005"}))
        tailsitter = check(engine_result(dropped, ca_airframe=4), ignore)
        levels = [(item.axis, item.level) for item in tailsitter.findings]
        self.assertEqual(levels, [("thrust_x", "warning"), ("thrust_z", "error")])
        # a standard VTOL needs forward thrust
        levels = [item.level for item in check(engine_result(dropped, ca_airframe=2), ignore).findings]
        self.assertEqual(levels, ["error", "error"])
        # nothing is known about what other vehicle types need
        for airframe in (7, None):
            levels = [item.level for item in check(engine_result(dropped, ca_airframe=airframe), ignore).findings]
            self.assertEqual(levels, ["error", "error"], airframe)

    def test_ca006_yaw_that_depends_on_thrust(self):
        same_spin = matrix(
            {"roll": [-1, 1, 1, -1], "pitch": [1, -1, 1, -1], "yaw": [0.3] * 4, "thrust_z": [-6.5] * 4},
            [{"roll": 0.7, "pitch": 0.7, "yaw": 1, "thrust_z": -1}] * 4,
            dropped_axes_bitmask=None,
        )
        result = check(engine_result(same_spin, ca_airframe=0, px4_version="v1.17.0"))
        self.assertEqual(rules(result), ["CA006"])
        self.assertNotIn("CA006", result.not_checked)
        finding = result.findings[0]
        self.assertEqual((finding.level, finding.matrix, finding.axis), ("error", 0, "yaw"))
        self.assertIn("yaw cannot be controlled independently", finding.message)
        self.assertIn("a combination of the row of thrust_z, so no actuator command changes yaw", finding.message)
        self.assertIn("PX4 v1.17.0 computes a mix for it all the same", finding.message)
        # where PX4 drops such axes itself, CA002 is the finding
        reported = dict(same_spin, dropped_axes_bitmask=0)
        self.assertEqual(rules(check(engine_result(reported, ca_airframe=0))), [])

    def test_ca006_names_the_rows_an_axis_depends_on(self):
        from px4_ca_lint.rules import dependent_axes

        # yaw is roll minus pitch; thrust_x is a little of pitch, as with canted rotors
        canted = matrix(
            {
                "roll": [-1, 1, 1, -1],
                "pitch": [1, -1, 1, -1],
                "yaw": [-2, 2, 0, 0],
                "thrust_x": [0.2, -0.2, 0.2, -0.2],
                "thrust_z": [-6.5] * 4,
            },
            [{}] * 4,
            dropped_axes_bitmask=None,
        )
        self.assertEqual(dependent_axes(canted), [("thrust_x", ["pitch"]), ("yaw", ["roll", "pitch"])])
        ignore = Options(ignore=frozenset({"CA020"}))
        findings = check(engine_result(canted, ca_airframe=4, px4_version="v1.17.0"), ignore).findings
        self.assertEqual([(item.rule, item.axis, item.level) for item in findings],
                         [("CA006", "thrust_x", "warning"), ("CA006", "yaw", "error")])
        self.assertIn("the rows of roll and pitch, so no actuator command changes yaw without changing them",
                      findings[1].message)

    def test_ca006_uses_the_limits_of_px4(self):
        from px4_ca_lint.rules import dependent_axes

        def yaw_with(part):
            # a yaw row with the given part that is independent of the thrust_z row
            return matrix({"yaw": [1 + part, 1 - part], "thrust_z": [-1, -1]}, [{}] * 2)

        # PX4 keeps a row when at least 0.01 of the squared unit row is independent
        self.assertEqual(dependent_axes(yaw_with(0.11)), [])
        self.assertEqual(dependent_axes(yaw_with(0.09)), [("yaw", ["thrust_z"])])
        # rows without an entry are not looked at, and the order of priority decides which row goes
        self.assertEqual(dependent_axes(matrix({"roll": [1, 1], "thrust_z": [0, 0]}, [{}] * 2)), [])
        tied = matrix({"roll": [1, 1], "pitch": [2, 2]}, [{}] * 2)
        self.assertEqual(dependent_axes(tied), [("pitch", ["roll"])])

    def test_ca002_not_checked_without_px4_support(self):
        result = check(engine_result(matrix({}, [{}], dropped_axes_bitmask=None)))
        self.assertEqual(result.findings, [])
        self.assertIn("CA002", result.not_checked)

    def test_ca003_nan_stops_the_other_rules(self):
        broken = matrix({"thrust_x": [None]}, [{"thrust_x": 9}], weak_axes_zeroed=["yaw"])
        self.assertEqual(rules(check(engine_result(broken))), ["CA003"])

    def test_ca004_weak_axis(self):
        result = check(engine_result(matrix({}, [{}], weak_axes_zeroed=["yaw"])))
        self.assertEqual(rules(result), ["CA004"])
        self.assertEqual(result.findings[0].level, "warning")

    def test_ca010_thrust_gain(self):
        high = matrix({"thrust_x": [6.5, 6.5]}, [{"thrust_x": 4.0}, {"thrust_x": 1.0}])
        result = check(engine_result(high))
        self.assertEqual(rules(result), ["CA010"])
        self.assertEqual(result.findings[0].actuators, ["motor0"])
        self.assertIn("setpoint of 0.25", result.findings[0].message)

    def test_ca010_limit_is_an_option(self):
        high = matrix({"thrust_x": [6.5]}, [{"thrust_x": 4.0}])
        self.assertEqual(rules(check(engine_result(high), Options(max_thrust_gain=5))), [])

    def test_ca010_ignores_torque_axes(self):
        self.assertEqual(rules(check(engine_result(matrix({"yaw": [1]}, [{"yaw": 9}])))), [])

    def test_ca011_command_without_thrust(self):
        coupled = matrix(
            {"thrust_x": [0, 6.5], "thrust_z": [-6.5, 0]},
            [{"thrust_x": 0.25, "thrust_z": -1}, {"thrust_x": 1}],
        )
        result = check(engine_result(coupled))
        self.assertEqual(rules(result), ["CA011"])
        self.assertEqual(result.findings[0].actuators, ["motor0"])

    def test_ca012_thrust_down(self):
        one_down = matrix({"thrust_z": [-6.5, 6.5]}, [{"thrust_z": -1}, {"thrust_z": 1}])
        ignore = Options(ignore=frozenset({"CA005"}))

        for airframe in (0, 2, 3, 4, 8):
            result = check(engine_result(one_down, ca_airframe=airframe), ignore)
            self.assertEqual(rules(result), ["CA012"], airframe)
            finding = result.findings[0]
            self.assertEqual((finding.level, finding.matrix, finding.axis), ("error", 0, "thrust_z"))
            self.assertEqual(finding.actuators, ["motor1"])
            self.assertIn("motor1: PX4 takes the thrust as pointing down", finding.message)

        # PX4 reads the rotor axis for a multirotor, but not for a multirotor with tilt
        message = check(engine_result(one_down, ca_airframe=0), ignore).findings[0].message
        self.assertTrue(message.endswith("Check the sign of CA_ROTORn_AZ and CA_ROTORn_CT"), message)
        message = check(engine_result(one_down, ca_airframe=8), ignore).findings[0].message
        self.assertTrue(message.endswith("Check the sign of CA_ROTORn_CT"), message)

    def test_ca012_thrust_backwards(self):
        pusher = matrix(
            {"thrust_x": [0, 0, -6.5], "thrust_z": [-6.5, -6.5, 0]},
            [{"thrust_z": -1}, {"thrust_z": -1}, {"thrust_x": -1}],
        )
        ignore = Options(ignore=frozenset({"CA005"}))
        result = check(engine_result(pusher, ca_airframe=2), ignore)
        found = [(item.rule, item.axis, item.actuators) for item in result.findings]
        self.assertEqual(found, [("CA012", "thrust_x", ["motor2"])])
        self.assertIn("pointing backwards (negative thrust_x effectiveness)", result.findings[0].message)
        self.assertTrue(result.findings[0].message.endswith("CA_ROTORn_AX and CA_ROTORn_CT"))
        # the rotors of a fixed-wing always point forwards, only the thrust coefficient can turn them
        plane = matrix({"thrust_x": [-6.5, 0]}, [{"thrust_x": -1}, {}], types=["motor", "servo"])
        message = check(engine_result(plane, ca_airframe=1), ignore).findings[0].message
        self.assertTrue(message.endswith("Check the sign of CA_ROTORn_CT"), message)

    def test_ca012_direction_is_the_largest_thrust_axis(self):
        ignore = Options(ignore=frozenset({"CA005"}))
        # a forward rotor that is tilted down a little, and a lift rotor that is tilted back a little
        tilted = matrix({"thrust_x": [6.4, -1.1], "thrust_z": [1.1, -6.4]}, [{"thrust_x": 1}, {"thrust_z": -1}])
        self.assertEqual(rules(check(engine_result(tilted, ca_airframe=2), ignore)), [])
        # no single largest axis, and no thrust at all
        unclear = matrix({"thrust_x": [-4.6, 0], "thrust_z": [4.6, 0]}, [{"thrust_x": -1}, {}])
        self.assertEqual(rules(check(engine_result(unclear, ca_airframe=2), ignore)), [])

    def test_ca012_leaves_other_vehicles_alone(self):
        ignore = Options(ignore=frozenset({"CA005"}))
        down_and_back = matrix({"thrust_x": [-6.5, 0], "thrust_z": [0, 6.5]}, [{"thrust_x": -1}, {"thrust_z": 1}])
        # an omnidirectional multirotor has rotors in every direction
        self.assertEqual(rules(check(engine_result(down_and_back, ca_airframe=0), ignore)), [])
        sideways = matrix({"thrust_y": [6.5, 0], "thrust_z": [0, 6.5]}, [{"thrust_y": 1}, {"thrust_z": 1}])
        self.assertEqual(rules(check(engine_result(sideways, ca_airframe=0), ignore)), [])
        # nothing is known about what other vehicle types need, for example an underwater vehicle
        self.assertEqual(rules(check(engine_result(down_and_back, ca_airframe=7))), [])
        self.assertEqual(rules(check(engine_result(down_and_back))), [])
        # the other VTOLs are checked in both directions
        standard_vtol = check(engine_result(down_and_back, ca_airframe=2), ignore)
        self.assertEqual([item.axis for item in standard_vtol.findings], ["thrust_z", "thrust_x"])
        # a servo is not a rotor
        servos = matrix({"thrust_z": [6.5, 6.5]}, [{"thrust_z": 1}, {"thrust_z": 1}], types=["servo", "servo"])
        self.assertEqual(rules(check(engine_result(servos, ca_airframe=2), ignore)), [])

    def test_ca020_unused_motor(self):
        unused = matrix(
            {"roll": [1, 1], "pitch": [1, -1]},
            [{"roll": 0.7, "pitch": 0.7}, {"roll": 0, "pitch": 0}],
        )
        result = check(engine_result(unused))
        self.assertEqual(rules(result), ["CA020"])
        self.assertEqual(result.findings[0].actuators, ["motor1"])

    def test_ca020_skips_motors_on_one_axis_and_servos(self):
        # a pusher above the centre of gravity only produces pitch torque
        pusher = matrix({"pitch": [-0.3], "thrust_x": [6.5]}, [{"thrust_x": 1}])
        servo = matrix({"roll": [1], "pitch": [1]}, [{}], types=["servo"])
        self.assertEqual(rules(check(engine_result(pusher, servo))), [])

    def test_ca021_rotors_beyond_the_count(self):
        params = {"CA_ROTOR_COUNT": "2", "CA_ROTOR1_PX": "0.2", "CA_ROTOR2_PX": "0.2", "CA_ROTOR5_AX": "1"}
        result = check(engine_result(healthy()), params=params)
        self.assertEqual(rules(result), ["CA021"])
        self.assertEqual(result.findings[0].level, "warning")
        self.assertEqual(result.findings[0].actuators, ["motor2", "motor5"])
        self.assertIn("CA_ROTOR_COUNT is 2; PX4 uses rotors 0 to 1 only", result.findings[0].message)

    def test_ca021_count_not_set(self):
        params = {"CA_ROTOR0_PX": "0.15", "CA_ROTOR0_PY": "0.15", "CA_ROTOR1_TILT": "1"}
        result = check(engine_result(matrix({}, []), num_motors=0), params=params)
        self.assertEqual(rules(result), ["CA001", "CA021"])
        self.assertEqual(result.findings[1].actuators, ["motor0", "motor1"])
        self.assertIn("CA_ROTOR_COUNT is 0 (not set in the input); PX4 uses no rotors", result.findings[1].message)

    def test_ca021_ignores_defaults_and_other_parameters(self):
        # a parameter export lists every rotor; unused ones keep PX4's defaults
        params = {
            "CA_ROTOR_COUNT": "2",
            "CA_ROTOR2_PX": "0.000000000000000000",
            "CA_ROTOR2_AZ": "-1.0",
            "CA_ROTOR2_CT": "6.5",
            "CA_ROTOR2_KM": "0.05",
            "CA_ROTOR_COUNTX": "9",
            "CA_ROTOR12_NEW": "3",
        }
        self.assertEqual(rules(check(engine_result(healthy()), params=params)), [])

    def test_ca021_uses_the_count_of_the_file_when_px4_gave_no_result(self):
        failed = {"error": "PX4 did not produce an effectiveness matrix"}
        self.assertEqual(
            rules(check(failed, params={"CA_ROTOR_COUNT": "4", "CA_ROTOR4_PX": "1"})), ["CA001", "CA021"]
        )
        self.assertEqual(rules(check(failed, params={"CA_ROTOR4_PX": "1"})), ["CA001"])

    def test_ca021_needs_the_input_parameters(self):
        self.assertEqual(rules(check(engine_result(matrix({}, []), num_motors=0))), ["CA001"])

    def test_ca022_tilt_servo_does_not_exist(self):
        tiltrotor = engine_result(healthy(), ca_airframe=3)
        params = {"CA_SV_TL_COUNT": "1", "CA_ROTOR0_TILT": "2", "CA_ROTOR1_TILT": "1"}
        result = check(tiltrotor, params=params)
        self.assertEqual(rules(result), ["CA022"])
        self.assertEqual(result.findings[0].level, "warning")
        self.assertEqual(result.findings[0].actuators, ["motor0"])
        self.assertIn(
            "motor0: CA_ROTOR0_TILT is 2, but CA_SV_TL_COUNT is 1; PX4 treats the rotor as not tilting",
            result.findings[0].message,
        )

    def test_ca022_count_not_set(self):
        tilted = engine_result(healthy(), ca_airframe=8)
        result = check(tilted, params={"CA_ROTOR0_TILT": "1", "CA_ROTOR1_TILT": "1.0"})
        self.assertEqual(rules(result), ["CA022"])
        self.assertEqual(result.findings[0].actuators, ["motor0", "motor1"])
        self.assertIn(
            "CA_SV_TL_COUNT is 0 (not set in the input); PX4 treats these rotors", result.findings[0].message
        )

    def test_ca022_accepts_existing_servos_and_rotors_without_one(self):
        tiltrotor = engine_result(healthy(), ca_airframe=3)
        params = {"CA_SV_TL_COUNT": "2", "CA_ROTOR0_TILT": "2", "CA_ROTOR1_TILT": "0"}
        self.assertEqual(rules(check(tiltrotor, params=params)), [])
        # rotor 2 is not counted, which is CA021
        params = {"CA_SV_TL_COUNT": "1", "CA_ROTOR0_TILT": "1", "CA_ROTOR2_TILT": "3"}
        self.assertEqual(rules(check(tiltrotor, params=params)), ["CA021"])

    def test_ca022_only_where_px4_reads_the_tilt_assignment(self):
        params = {"CA_ROTOR0_TILT": "2"}

        for airframe in (0, 1, 4):
            self.assertEqual(rules(check(engine_result(healthy(), ca_airframe=airframe), params=params)), [])

        # the stand-in has no forward thrust, which a standard VTOL needs
        self.assertEqual(rules(check(engine_result(healthy(), ca_airframe=2), params=params)), ["CA005"])

        self.assertEqual(rules(check(engine_result(healthy(), ca_airframe=3))), [])

    def test_ca005_a_needed_axis_without_any_effect(self):
        no_yaw = matrix(
            {"roll": [-1, 1], "pitch": [1, 1], "thrust_z": [-6.5, -6.5]},
            [{"roll": -0.7, "pitch": 0.7, "thrust_z": -1}, {"roll": 0.7, "pitch": 0.7, "thrust_z": -1}],
        )
        result = check(engine_result(no_yaw, ca_airframe=0, effectiveness_source="Multirotor"))
        self.assertEqual(rules(result), ["CA005"])
        finding = result.findings[0]
        self.assertEqual((finding.level, finding.axis, finding.matrix), ("error", "yaw", None))
        self.assertIn("yaw is not controlled: no actuator has an effect on it", finding.message)
        self.assertIn("A vehicle with CA_AIRFRAME 0 (Multirotor) needs it", finding.message)
        # a flying wing has no yaw control and a glider no thrust
        self.assertEqual(rules(check(engine_result(no_yaw, ca_airframe=1))), [])
        # nothing is known about what other vehicle types need
        self.assertEqual(rules(check(engine_result(no_yaw, ca_airframe=7))), [])
        self.assertEqual(rules(check(engine_result(no_yaw))), [])

    def test_ca005_every_missing_axis_is_reported(self):
        only_thrust = matrix({"thrust_z": [-6.5, -6.5]}, [{"thrust_z": -1}, {"thrust_z": -1}])
        result = check(engine_result(only_thrust, ca_airframe=0))
        self.assertEqual([finding.axis for finding in result.findings], ["roll", "pitch", "yaw"])
        standard_vtol = check(engine_result(healthy(), ca_airframe=2))
        self.assertEqual([finding.axis for finding in standard_vtol.findings], ["thrust_x"])

    def test_ca005_another_matrix_can_control_the_axis(self):
        motors = matrix({"thrust_z": [-6.5, -6.5]}, [{"thrust_z": -1}, {"thrust_z": -1}])
        surfaces = matrix(
            {"roll": [1, -1], "pitch": [1, 1], "yaw": [0.2, 0.2]},
            [{"roll": 0.5, "pitch": 0.5}, {"roll": -0.5, "pitch": 0.5}],
            types=["servo", "servo"],
            index=1,
        )
        self.assertEqual(rules(check(engine_result(motors, surfaces, ca_airframe=4))), [])

    def test_ca005_names_the_cause_px4_reports(self):
        weak = matrix(
            {"roll": [-1, 1], "pitch": [1, 1], "thrust_z": [-6.5, -6.5]},
            [{"roll": -0.7, "pitch": 0.7, "thrust_z": -1}, {"roll": 0.7, "pitch": 0.7, "thrust_z": -1}],
            weak_axes_zeroed=["yaw"],
        )
        result = check(engine_result(weak, ca_airframe=0))
        self.assertEqual(rules(result), ["CA004", "CA005"])
        self.assertIn("see CA004", result.findings[1].message)
        # bit 2 is yaw
        dropped = dict(healthy(), dropped_axes_bitmask=1 << 2)
        result = check(engine_result(dropped, ca_airframe=0))
        self.assertEqual(rules(result), ["CA002", "CA005"])
        self.assertIn("see CA002", result.findings[1].message)

    def test_ca005_not_on_top_of_ca001_and_ca003(self):
        failed = {"error": "PX4 did not produce an effectiveness matrix", "ca_airframe": 0}
        self.assertEqual(rules(check(failed)), ["CA001"])
        empty = engine_result(matrix({}, []), num_motors=0, ca_airframe=0)
        self.assertEqual(rules(check(empty)), ["CA001"])
        broken = matrix({"roll": [None, 1]}, [{"roll": 1}, {"roll": 1}])
        self.assertEqual(rules(check(engine_result(broken, ca_airframe=0))), ["CA003"])

    def test_ca030_lines_that_could_not_be_used(self):
        unread = ["line 3: CA_ROTOR4_PZ has the value '-0,05', which is not a number, skipped"]
        result = check(engine_result(healthy()), params={"CA_AIRFRAME": "0"}, unread=unread)
        self.assertEqual(rules(result), ["CA030"])
        self.assertEqual((result.findings[0].level, result.findings[0].message), ("error", unread[0]))
        # rules that look at the input do not run without the input
        self.assertEqual(rules(check(engine_result(healthy()), unread=unread)), [])

    def test_ca030_integer_parameter_with_another_value(self):
        engine = engine_result(healthy(), not_integer_parameters=["CA_ROTOR_COUNT"])
        result = check(engine, params={"CA_ROTOR_COUNT": "3.6"})
        self.assertEqual(rules(result), ["CA030"])
        self.assertIn("CA_ROTOR_COUNT is an integer parameter, but the value is '3.6'", result.findings[0].message)

    def test_ca031_unknown_control_allocation_parameters(self):
        unknown = ["MPC_NEW", "CA_ROTOR4_PZZ", "CA_ABC"]
        engine = engine_result(healthy(), unknown_parameters=unknown, px4_version="v1.17.0")
        result = check(engine, params={})
        self.assertEqual(rules(result), ["CA031"])
        self.assertEqual(result.findings[0].level, "warning")
        self.assertIn("CA_ABC, CA_ROTOR4_PZZ: not a parameter of PX4 v1.17.0, ignored", result.findings[0].message)
        self.assertNotIn("MPC_NEW", result.findings[0].message)
        # parameters of other modules are not this tool's business
        self.assertEqual(rules(check(engine_result(healthy(), unknown_parameters=["MPC_NEW"]), params={})), [])

    def test_ignore(self):
        result = check(
            engine_result(matrix({}, [{}], weak_axes_zeroed=["yaw"], dropped_axes_bitmask=None)),
            Options(ignore=frozenset({"CA004", "CA002"})),
        )
        self.assertEqual(result.findings, [])
        self.assertEqual(result.not_checked, {})


if __name__ == "__main__":
    unittest.main()
