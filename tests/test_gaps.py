"""Gap probes: each one PASSES while the gap exists and FAILS the day NovaLang is fixed, so docs/GAPS.md cannot rot.
Each runs a few lines of NovaLang on the VM and on the self-hosted engine."""
import os, subprocess, sys, unittest

from tests import common as c


def nova(source, bootstrap=False):
    d = c.tempdir()
    try:
        path = c.write(d, "probe.nova", source)
        args = [sys.executable, c.NOVA] + (["--bootstrap"] if bootstrap else []) + [path]
        done = subprocess.run(args, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr
    finally:
        c.cleanup(d)


class Gaps(unittest.TestCase):
    def both(self, source):
        return [(e, nova(source, e)) for e in (False, True)]

    def test_G037_there_is_no_index_find_or_startswith(self):
        for name in ["index", "index_of", "find", "startswith", "starts_with", "contains_at"]:
            for engine, (code, out) in self.both('print(%s("abc", "b"))' % name):
                with self.subTest(name=name, bootstrap=engine):
                    self.assertNotEqual(code, 0)
                    self.assertIn("undefined name '%s'" % name, out)

    def test_G037_but_split_and_slicing_are_enough_to_get_a_status(self):
        src = 'let w = split(split("ip - - [t] \\"GET / HTTP/1.1\\" 404 12 \\"-\\" \\"ua\\"", "\\"")[2])\nprint(w[0])\nprint("abcdef"[2:4])'
        for engine, (code, out) in self.both(src):
            with self.subTest(bootstrap=engine):
                self.assertEqual((code, out.split()), (0, ["404", "cd"]))

    def test_G038_sorted_cannot_order_pairs_or_take_a_key(self):
        for engine, (code, out) in self.both('print(sorted([[2, "b"], [1, "a"]]))'):
            with self.subTest(bootstrap=engine):
                self.assertNotEqual(code, 0)
                self.assertIn("sorted() needs items that can be compared with each other", out)
        for engine, (code, out) in self.both('print(sorted([3, 1, 2], true))'):
            with self.subTest(bootstrap=engine):
                self.assertEqual((code, out.strip()), (0, "[3, 2, 1]"))  # a plain number list is fine, descending

    def test_G039_num_throws_and_accepts_more_than_digits(self):
        for engine, (code, out) in self.both('print(num(" 7"))\nprint(num("+5"))\nprint(num("0200"))'):
            with self.subTest(bootstrap=engine):
                self.assertEqual((code, out.split()), (0, ["7", "5", "200"]))
        for text in ["abc", "1e2", "0x10", "1_0", ""]:
            for engine, (code, out) in self.both('print(num("%s"))' % text):
                with self.subTest(text=text, bootstrap=engine):
                    self.assertNotEqual(code, 0)
                    self.assertIn("num() cannot read a number from", out)

    def test_G040_an_expression_cannot_continue_on_the_next_line(self):
        for src in ['let b = "x" +\n  "y"\nprint(b)', 'let b = ("x" +\n  "y")\nprint(b)']:
            for engine, (code, out) in self.both(src):
                with self.subTest(bootstrap=engine, source=src):
                    self.assertNotEqual(code, 0)
                    self.assertIn("the expression ends too early", out)
        for engine, (code, out) in self.both('let b = "x"\n  + "y"\nprint(b)'):
            with self.subTest(bootstrap=engine):
                self.assertIn("cannot apply unary '+' to a string", out)

    def test_G041_split_lines_holds_every_line_at_once(self):
        # no lazy line reader: 'read' gives one string and split_lines one list of all the lines
        for engine, (code, out) in self.both('print(len(split_lines("a\\nb\\nc\\n")))\nprint(type(split_lines("a")))'):
            with self.subTest(bootstrap=engine):
                self.assertEqual(code, 0)
                self.assertEqual(out.split()[0], "3")


if __name__ == "__main__":
    unittest.main()
