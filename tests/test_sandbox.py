"""The restricted profile: what Nova_Log needs, what it is refused, and the 1,000,000-character gap (G-036).

The restricted runs use the DEFAULT limits and a log under 1 MB. Nothing here raises a limit to make a test pass."""
import os, unittest

from tests import common as c

ENGINES = ["vm", "bootstrap"]


class Restricted(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = c.tempdir()
        cls.log = c.make_synthetic(cls.dir, 0.2)  # well under the 1,000,000-character string limit
        cls.size = os.path.getsize(cls.log)

    @classmethod
    def tearDownClass(cls):
        c.cleanup(cls.dir)

    def test_the_log_is_under_the_limit(self):
        self.assertLess(self.size, 1000000)

    def test_restricted_run_with_default_limits_matches_the_oracle(self):
        counts, total, unparsed, _ = c.oracle(self.log)
        for engine in ENGINES:
            with self.subTest(engine=engine):
                done = c.run(self.log, engine, profile="restricted")
                self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
                got = c.parse(done.stdout)
                self.assertEqual(dict(got["rows"]), dict(counts))
                self.assertEqual((got["total"], got["unparsed"]), (total, unparsed))
                self.assertIn("lines/s", done.stdout)  # clock was granted

    def test_without_the_clock_grant_the_timings_are_left_out(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                done = c.run(self.log, engine, profile="restricted", clock=False)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertNotIn("lines/s", done.stdout)
                self.assertEqual(dict(c.parse(done.stdout)["rows"]), dict(c.oracle(self.log)[0]))

    def test_without_the_process_grant_it_cannot_receive_the_file_name(self):
        # G-033 (Nova_Sort) again: `args` belongs to `process`, so a path cannot reach the program without it.
        done = c.run(self.log, profile="restricted", process=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("undefined name 'args'", done.stderr + done.stdout)

    def test_a_file_outside_the_read_grant_is_refused(self):
        other = c.tempdir()
        self.addCleanup(c.cleanup, other)
        elsewhere = c.write(other, "elsewhere.log", "x\n")
        done = c.run(elsewhere, profile="restricted", read_dir=self.dir)
        self.assertEqual(done.returncode, 1)
        self.assertIn("outside the folders this program may use", done.stdout)


class StringLimit(unittest.TestCase):
    """G-036: `read` builds one string, and a restricted string stops at 1,000,000 characters. A web-server log
    is almost always bigger, and there is no streaming read, so the sandbox cannot analyse one."""

    def setUp(self):
        self.dir = c.tempdir()
        self.addCleanup(c.cleanup, self.dir)

    def test_G036_exactly_one_million_characters_is_the_most_it_can_read(self):
        # one long line: the self-hosted engine is ~30x slower and would hit the 5 s time limit on 10,000 lines
        ok = c.write(self.dir, "exact.log", "a" * 999999 + "\n")
        over = c.write(self.dir, "over.log", "a" * 1000000 + "\n")
        self.assertEqual(os.path.getsize(ok), 1000000)
        for engine in ENGINES:
            with self.subTest(engine=engine):
                self.assertEqual(c.run(ok, engine, profile="restricted").returncode, 0)
                done = c.run(over, engine, profile="restricted")
                self.assertEqual(done.returncode, 1)
                self.assertIn("a string cannot grow beyond 1000000 characters", done.stdout)

    def test_G036_a_realistic_log_is_refused_and_the_message_does_not_say_it_was_a_file_read(self):
        big = c.make_synthetic(self.dir, 1.5, "big.log")
        done = c.run(big, profile="restricted")
        self.assertEqual(done.returncode, 1)
        self.assertIn("a string cannot grow beyond 1000000 characters", done.stdout)
        self.assertNotIn("file", done.stdout.replace("cannot read " + big, ""))

    def test_G036_the_same_log_is_read_whole_on_the_trusted_profile(self):
        big = c.make_synthetic(self.dir, 1.5, "big.log")
        done = c.run(big)  # the CLI default profile
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(dict(c.parse(done.stdout)["rows"]), dict(c.oracle(big)[0]))


class Source(unittest.TestCase):
    """The program keeps to what the brief allows: split, slicing and len, no regex, no import, no write."""

    def code(self):
        import re
        with open(c.PROGRAM, encoding="utf-8") as f:
            source = f.read()
        source = re.sub(r"#[^\n]*", "", source)
        return re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', source)

    def test_no_regex_import_python_or_file_writes(self):
        import re
        code = self.code()
        for name in ["regex", "import", "python", "write", "remove", "delete", "rename", "copy", "append", "mkdir", "stdin", "env"]:
            self.assertIsNone(re.search(r"\b%s\b" % name, code), "nova_log.nova uses " + name)

    def test_it_uses_split_slicing_and_len(self):
        code = self.code()
        for name in ["split(", "len(", "[:"]:
            self.assertIn(name, code)


if __name__ == "__main__":
    unittest.main()
