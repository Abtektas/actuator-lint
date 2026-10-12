import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from px4_ca_lint.engine import (
    ENGINE_ENV,
    PX4_ENV,
    EngineError,
    check_px4_version,
    find_engine,
    installed_versions,
    requested_px4,
    run_engine,
    user_engine_path,
    versioned_engine_path,
)


def fake_engine(directory: Path, script: str) -> Path:
    """An executable that stands in for px4_ca_engine. $1 is the parameter file, $2 the output."""
    path = directory / "px4_ca_engine"
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class FindEngine(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        # no engine from the environment or the current directory
        self.enterContext(mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.directory / "data")}))
        os.environ.pop(ENGINE_ENV, None)
        os.environ.pop(PX4_ENV, None)
        previous = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)

    def install(self, px4: str) -> Path:
        versioned_engine_path(px4).parent.mkdir(parents=True)
        return fake_engine(versioned_engine_path(px4).parent, "exit 0\n")

    def test_user_data_directory(self):
        self.assertEqual(user_engine_path(), self.directory / "data" / "px4-ca-lint" / "px4_ca_engine")

        with self.assertRaises(EngineError) as raised:
            find_engine()

        self.assertIn(str(user_engine_path().parent / "engines"), str(raised.exception))
        user_engine_path().parent.mkdir(parents=True)
        fake_engine(user_engine_path().parent, "exit 0\n")
        self.assertEqual(find_engine(), user_engine_path())

    def test_one_installed_version_is_used(self):
        self.assertEqual(
            versioned_engine_path("v1.17.0"),
            self.directory / "data" / "px4-ca-lint" / "engines" / "v1.17.0" / "px4_ca_engine",
        )
        engine = self.install("v1.17.0")
        self.assertEqual(installed_versions(), ["v1.17.0"])
        self.assertEqual(find_engine(), engine)

    def test_several_installed_versions_need_a_choice(self):
        old, new = self.install("v1.17.0"), self.install("v1.18.0")

        with self.assertRaises(EngineError) as raised:
            find_engine()

        self.assertIn("v1.17.0, v1.18.0", str(raised.exception))
        self.assertIn("--px4", str(raised.exception))
        self.assertEqual(find_engine(px4="v1.17.0"), old)
        self.assertEqual(find_engine(px4="v1.18.0"), new)

        with mock.patch.dict(os.environ, {PX4_ENV: "1.18.0"}):
            self.assertEqual(find_engine(px4=requested_px4()), new)
            # the command line wins over the environment
            self.assertEqual(find_engine(px4=requested_px4("v1.17.0")), old)

    def test_a_version_that_is_not_installed(self):
        with self.assertRaises(EngineError) as raised:
            find_engine(px4="v1.18.0")

        self.assertIn("No engine is installed", str(raised.exception))
        self.install("v1.17.0")

        with self.assertRaises(EngineError) as raised:
            find_engine(px4="v1.18.0")

        self.assertIn("Installed: v1.17.0.", str(raised.exception))
        self.assertIn(str(versioned_engine_path("v1.18.0")), str(raised.exception))

    def test_a_named_engine_is_used_whatever_version_is_asked_for(self):
        self.install("v1.17.0")
        (self.directory / "own").mkdir()
        own = fake_engine(self.directory / "own", "exit 0\n")
        self.assertEqual(find_engine(str(own), "v1.17.0"), own)

        with mock.patch.dict(os.environ, {ENGINE_ENV: str(own)}):
            self.assertEqual(find_engine(px4="v1.17.0"), own)

    def test_the_single_engine_location_wins_over_installed_versions(self):
        self.install("v1.17.0")
        self.install("v1.18.0")
        user_engine_path().parent.mkdir(parents=True, exist_ok=True)
        single = fake_engine(user_engine_path().parent, "exit 0\n")
        self.assertEqual(find_engine(), single)

    def test_a_release_without_its_own_directory_falls_back_to_the_other_locations(self):
        # the engine of an earlier tool version: check_px4_version decides after the run whether it fits
        user_engine_path().parent.mkdir(parents=True)
        single = fake_engine(user_engine_path().parent, "exit 0\n")
        self.assertEqual(find_engine(px4="v1.17.0"), single)
        installed = self.install("v1.17.0")
        self.assertEqual(find_engine(px4="v1.17.0"), installed)

        # a name that is not a release has nothing to be checked against, so only its own directory counts
        with self.assertRaises(EngineError):
            find_engine(px4="main")

    def test_px4_version_names(self):
        self.assertIsNone(requested_px4())
        self.assertIsNone(requested_px4(""))
        self.assertEqual(requested_px4("1.17.0"), "v1.17.0")
        self.assertEqual(requested_px4(" v1.18.0-rc1 "), "v1.18.0-rc1")
        self.assertEqual(requested_px4("main"), "main")

        for name in ("../v1.17.0", "v1/17", "..", "-v1"):
            with self.assertRaises(EngineError, msg=name):
                requested_px4(name)

    def test_order(self):
        user_engine_path().parent.mkdir(parents=True)
        fake_engine(user_engine_path().parent, "exit 0\n")
        (self.directory / "build" / "engine").mkdir(parents=True)
        local = fake_engine(self.directory / "build" / "engine", "exit 0\n")
        self.assertEqual(find_engine().resolve(), local.resolve())

        (self.directory / "env").mkdir()
        from_environment = fake_engine(self.directory / "env", "exit 0\n")

        with mock.patch.dict(os.environ, {ENGINE_ENV: str(from_environment)}):
            self.assertEqual(find_engine(), from_environment)
            self.assertEqual(find_engine(str(local)), local)

    def test_a_file_that_is_not_executable_is_refused(self):
        plain = self.directory / "px4_ca_engine"
        plain.write_text("")

        with self.assertRaises(EngineError):
            find_engine(str(plain))


class CheckVersion(unittest.TestCase):
    ENGINE = Path("px4_ca_engine")

    def test_another_release_is_refused(self):
        with self.assertRaises(EngineError) as raised:
            check_px4_version("v1.18.0", self.ENGINE, {"px4_version": "v1.17.0"})

        self.assertIn("v1.18.0 was asked for", str(raised.exception))
        self.assertIn("built against PX4 v1.17.0", str(raised.exception))

        with self.assertRaises(EngineError):
            check_px4_version("v1.18.0", self.ENGINE, {"px4_version": "v1.18.0-rc1-30-g492d132563"})

    def test_the_release_asked_for_passes(self):
        check_px4_version("v1.17.0", self.ENGINE, {"px4_version": "v1.17.0"})
        check_px4_version("v1.18.0-rc1", self.ENGINE, {"px4_version": "v1.18.0-rc1"})

    def test_nothing_is_checked_without_a_release(self):
        check_px4_version(None, self.ENGINE, {"px4_version": "v1.17.0"})
        # a name that is not a release tag only selects where the engine is taken from
        check_px4_version("main", self.ENGINE, {"px4_version": "v1.18.0-beta1-934-g8c243a2cd6"})


class RunEngine(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def run_fake(self, script: str) -> dict:
        return run_engine(fake_engine(self.directory, script), {"CA_AIRFRAME": "0"})

    def test_parameters_are_passed_and_output_is_read(self):
        result = self.run_fake(
            'grep -q "^CA_AIRFRAME 0$" "$1" || exit 1\n'
            'echo \'{"engine_schema": 1, "matrices": []}\' > "$2"\n'
        )
        self.assertEqual(result["matrices"], [])

    def test_unknown_schema_is_refused(self):
        with self.assertRaises(EngineError) as raised:
            self.run_fake('echo \'{"engine_schema": 99}\' > "$2"\n')

        self.assertIn("engine_schema 99", str(raised.exception))

    def test_failure_is_reported_with_the_last_error_line(self):
        with self.assertRaises(EngineError) as raised:
            self.run_fake("echo first >&2\necho broken >&2\nexit 3\n")

        self.assertIn("exit code 3", str(raised.exception))
        self.assertIn("broken", str(raised.exception))

    def test_invalid_json_is_a_failure(self):
        with self.assertRaises(EngineError):
            self.run_fake('echo "{" > "$2"\n')

    def test_px4_failure_is_passed_on_for_the_rules(self):
        result = self.run_fake(
            'echo \'{"engine_schema": 1, "error": "PX4 did not produce an effectiveness matrix"}\' > "$2"\nexit 67\n'
        )
        self.assertIn("error", result)

    def test_unsupported_airframe(self):
        with self.assertRaises(EngineError) as raised:
            self.run_fake(
                'echo \'{"engine_schema": 1, "ca_airframe": 3, "px4_version": "v1.17.0"}\' > "$2"\nexit 66\n'
            )

        self.assertIn("CA_AIRFRAME 3 is not supported yet", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
