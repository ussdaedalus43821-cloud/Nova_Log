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

    def test_without_the_regex_grant_the_import_is_refused(self):
        # std:regex declares the `regex` capability, so the import itself fails, before any line is read
        done = c.run(self.log, profile="restricted", regex=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("std:regex needs the 'regex' capability", done.stderr + done.stdout)

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
    """The program keeps to what the brief allows: one standard import (std:regex), no Python, no write."""

    def code(self):
        import re
        with open(c.PROGRAM, encoding="utf-8") as f:
            source = f.read()
        source = re.sub(r"#[^\n]*", "", source)
        return re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', source)

    def test_the_only_import_is_std_regex(self):
        import re
        with open(c.PROGRAM, encoding="utf-8") as f:
            imports = [line.strip() for line in f if line.lstrip().startswith("import")]
        self.assertEqual(imports, ['import "std:regex" as re'])
        self.assertEqual(len(re.findall(r"\bimport\b", self.code())), 1, "an import in the middle of the program")

    def test_no_python_or_file_writes(self):
        import re
        code = self.code()
        for name in ["python", "write", "remove", "delete", "rename", "copy", "append", "mkdir", "stdin", "env"]:
            self.assertIsNone(re.search(r"\b%s\b" % name, code), "nova_log.nova uses " + name)

    def test_the_status_is_found_by_one_std_regex_pattern(self):
        code = self.code()
        self.assertEqual(code.count("re.match("), 1)
        self.assertNotIn("status_of", code)
        self.assertNotIn("split(", code)  # the hand-written split-based parser is gone (split_lines stays)


def split_status(line):
    """The parser the program had before std:regex, line for line, as the oracle: (status, strategy) or ("", 0)."""
    def is_status(t):
        return len(t) == 3 and t[0] in "12345" and t[1] in "0123456789" and t[2] in "0123456789"

    def words(t):  # NovaLang's split(text): the six ASCII whitespace characters, empty pieces dropped
        import re
        return [w for w in re.split(r"[ \t\n\r\f\v]+", t) if w]

    parts = line.split('"')
    n = len(parts)
    if n >= 3:
        w = words(parts[2])
        if w and is_status(w[0]):
            return w[0], 1
    if n >= 6:
        w = words(parts[n - 5])
        if w and is_status(w[0]):
            return w[0], 2
    return "", 0


class Pattern(unittest.TestCase):
    """The STATUS pattern, run by NovaLang's std:regex on all three engines, gives exactly what the split-based parser gave:
    the same status and the same strategy (1: after the second quote, 2: counted from the end), on hand-picked and random lines."""

    def test_the_pattern_agrees_with_the_old_split_parser(self):
        import json, random, re, subprocess, sys
        with open(c.PROGRAM, encoding="utf-8") as f:
            source = f.read()
        pattern_line = re.search(r"^let STATUS = .*$", source, re.M).group(0)
        lines = ['1.2.3.4 - - [t] "GET / HTTP/1.1" 200 5 "-" "ua"', '1.2.3.4 - - [t] "GET /odd"path HTTP/1.1" 404 5 "-" "ua"',
                 '"x" \t301\t5', '"x" 600 5', '"x" 2000', '"x" 20 5', '"x" 099', '"a"503', '"a" 503', '"a""b" 503 "x" "y"',
                 '"a"b"c" 302 "x" "y"', '"a" "b"c"d" 502 "r" "u"', '"x" 500"y" "z"', '"q" \x0b201 x', '"q"  201 x',
                 '"a"b"c"d"e" 304 "f" "g"', '"x"y" 200 "r" "u"', '"a"  ', '"a"" 200', 'no quotes 200', '"', '""', '"""']
        rng = random.Random(37)
        pieces = ['"', " ", "200", "404", "5", "a", "\t", "GET", "-", '"-"', "301", "1234", "5xx"]
        lines += ["".join(rng.choice(pieces) for _ in range(rng.randint(1, 14))) for _ in range(4000)]
        want = [list(split_status(l)) for l in lines]
        d = c.tempdir()
        self.addCleanup(c.cleanup, d)
        c.write(d, "lines.json", json.dumps(lines))  # NovaLang has no \\u escape, so the lines go through a file, not a literal
        program = ('import "std:regex" as re\n' + pattern_line + "\nlet lines = json.loads(read(\"lines.json\"))\n"
                   "for line in lines {\n"
                   "    let m = re.match(STATUS, line)\n"
                   "    if type(m) != \"dict\" {\n        print(json.dumps([\"\", 0]))\n"
                   "    } else if type(m.groups[0]) == \"string\" {\n        print(json.dumps([m.groups[0], 1]))\n"
                   "    } else {\n        print(json.dumps([m.groups[1], 2]))\n    }\n}\n")
        path = c.write(d, "pattern.nova", program)
        for engine, flags in (("vm", []), ("tree", ["--tree-walk"]), ("bootstrap", ["--bootstrap"])):
            with self.subTest(engine=engine):
                done = subprocess.run([sys.executable, c.NOVA] + flags + [path], capture_output=True, text=True, timeout=600, cwd=d)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual([json.loads(g) for g in done.stdout.splitlines()], want)
        self.assertGreater(sum(1 for w in want if w[1] == 2), 10)  # the count-from-the-end alternative is exercised


if __name__ == "__main__":
    unittest.main()
