"""Behaviour: nova_log.nova counts exactly what an independent Python regex counts, on all three engines."""
import os, unittest

from tests import common as c

ENGINES = ["vm", "tree", "bootstrap"]


def line(request, status="200", size="512", ref="-", agent="curl/8.4.0", ip="10.0.0.1"):
    return '%s - - [12/Nov/2026:10:00:00 +0000] "%s" %s %s "%s" "%s"' % (ip, request, status, size, ref, agent)


# Each entry: (label, log line, status it must be counted as, or None for "unparsed")
EDGES = [
    ("plain", line("GET / HTTP/1.1"), "200"),
    ("404", line("GET /nope HTTP/1.1", "404"), "404"),
    ("a quote inside the request", line('GET /odd\\"path HTTP/1.1', "500"), "500"),
    ("two quotes inside the request", line('GET /a\\"b\\"c HTTP/1.1', "503"), "503"),
    ("a request of just a dash", '1.2.3.4 - - [12/Nov/2026:10:00:00 +0000] "-" 408 - "-" "-"', "408"),
    ("an IPv6 client", line("GET / HTTP/1.1", "301", ip="2001:db8::ff00:42:8329"), "301"),
    ("a bare dash for the size", line("GET / HTTP/1.1", "304", size="-"), "304"),
    ("a space-filled agent", line("GET / HTTP/1.1", "206", agent="Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101"), "206"),
    ("a status with no known name", line("GET / HTTP/1.1", "418"), "418"),
    ("a 1xx status", line("GET / HTTP/1.1", "101"), "101"),
    ("status 999", line("GET / HTTP/1.1", "999"), None),
    ("status 099", line("GET / HTTP/1.1", "099"), None),
    ("status 20", line("GET / HTTP/1.1", "20"), None),
    ("status 2000", line("GET / HTTP/1.1", "2000"), None),
    ("a letter in the status", line("GET / HTTP/1.1", "2o0"), None),
    ("garbage", "garbage line 7 with no structure", None),
    ("a lone quote", '"', None),
    ("just spaces", "   ", None),
]


class Edges(unittest.TestCase):
    def setUp(self):
        self.dir = c.tempdir()
        self.addCleanup(c.cleanup, self.dir)

    def check(self, path, engine):
        done = c.run(path, engine)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        got = c.parse(done.stdout)
        counts, total, unparsed, blank = c.oracle(path)
        self.assertEqual(dict(got["rows"]), dict(counts), done.stdout)
        self.assertEqual((got["total"], got["unparsed"], got["blank"]), (total, unparsed, blank), done.stdout)
        self.assertEqual([code for code, _ in got["rows"]], c.expected_order(counts), "the table is not in frequency order")
        return done.stdout

    def test_each_edge_line_is_counted_as_the_oracle_counts_it(self):
        for engine in ENGINES:
            for label, text, status in EDGES:
                with self.subTest(engine=engine, line=label):
                    path = c.write(self.dir, "one.log", text + "\n")
                    got = c.parse(c.run(path, engine).stdout)
                    # the oracle agrees with the table written here, so the table itself is right
                    self.assertEqual(c.oracle(path)[0], {status: 1} if status else {})
                    self.assertEqual(got["rows"], [(status, 1)] if status else [])
                    self.assertEqual(got["unparsed"], 0 if status else 1)

    def test_all_edges_together(self):
        path = c.write(self.dir, "all.log", "\n".join(t for _l, t, _s in EDGES) + "\n")
        for engine in ENGINES:
            with self.subTest(engine=engine):
                self.check(path, engine)

    def test_a_quote_in_the_request_is_found_from_the_end(self):
        path = c.write(self.dir, "q.log", line('GET /odd\\"path HTTP/1.1', "500") + "\n" + line("GET / HTTP/1.1") + "\n")
        out = self.check(path, "vm")
        self.assertIn("1 of those were found by counting from the end", out)

    def test_crlf_blank_lines_and_a_missing_final_newline(self):
        text = line("GET / HTTP/1.1") + "\r\n\r\n" + line("GET /x HTTP/1.1", "404") + "\r\n" + line("GET /y HTTP/1.1", "404")
        path = c.write(self.dir, "crlf.log", text)
        for engine in ENGINES:
            with self.subTest(engine=engine):
                out = self.check(path, engine)
                got = c.parse(out)
                self.assertEqual((got["rows"], got["blank"]), ([("404", 2), ("200", 1)], 1))

    def test_an_empty_file(self):
        path = c.write(self.dir, "empty.log", "")
        for engine in ENGINES:
            with self.subTest(engine=engine):
                done = c.run(path, engine)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(c.parse(done.stdout)["rows"], [])

    def test_ties_put_the_lower_code_first(self):
        text = "".join(line("GET / HTTP/1.1", s) + "\n" for s in ["503", "404", "200", "503", "404", "200", "301"])
        path = c.write(self.dir, "tie.log", text)
        self.assertEqual(c.parse(c.run(path).stdout)["rows"], [("200", 2), ("404", 2), ("503", 2), ("301", 1)])

    def test_top_n_cuts_the_table_but_not_the_class_totals(self):
        text = "".join(line("GET / HTTP/1.1", s) + "\n" for s in ["200"] * 5 + ["404"] * 3 + ["500"] * 2 + ["301"])
        path = c.write(self.dir, "top.log", text)
        done = c.run(path, extra=["2"])
        self.assertEqual(c.parse(done.stdout)["rows"], [("200", 5), ("404", 3)])
        self.assertIn("... and 2 more status codes", done.stdout)
        self.assertIn("5xx server error", done.stdout)

    def test_a_missing_file_and_no_argument_exit_with_a_message(self):
        done = c.run(os.path.join(self.dir, "nope.log"))
        self.assertEqual(done.returncode, 1)
        self.assertIn("cannot read", done.stdout)
        import subprocess, sys
        bare = subprocess.run([sys.executable, c.NOVA, c.PROGRAM], capture_output=True, text=True)
        self.assertEqual(bare.returncode, 2)
        self.assertIn("usage", bare.stdout)

    def test_it_never_writes(self):
        # restricted with ONLY a read grant on the log's folder: a write would be an undefined name.
        path = c.write(self.dir, "ro.log", line("GET / HTTP/1.1") + "\n")
        before = sorted(os.listdir(self.dir))
        done = c.run(path, profile="restricted")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(os.listdir(self.dir)), before)


class Synthetic(unittest.TestCase):
    """Generated logs (tools/make_log.py): the awkward lines come out at random places."""

    @classmethod
    def setUpClass(cls):
        cls.dir = c.tempdir()
        cls.small = c.make_synthetic(cls.dir, 0.25)
        cls.medium = c.make_synthetic(cls.dir, 0.9, "medium.log")

    @classmethod
    def tearDownClass(cls):
        c.cleanup(cls.dir)

    def match(self, path, engine):
        done = c.run(path, engine)
        self.assertEqual(done.returncode, 0, done.stderr)
        got = c.parse(done.stdout)
        counts, total, unparsed, blank = c.oracle(path)
        self.assertEqual(dict(got["rows"]), dict(counts), "counts differ from the Python oracle")
        self.assertEqual((got["total"], got["unparsed"], got["blank"]), (total, unparsed, blank))
        self.assertEqual([code for code, _ in got["rows"]], c.expected_order(counts))
        self.assertGreater(len(counts), 8)

    def test_vm_matches_the_oracle(self):
        self.match(self.medium, "vm")

    def test_tree_walker_matches_the_oracle(self):
        self.match(self.small, "tree")

    def test_self_hosted_matches_the_oracle(self):
        self.match(self.small, "bootstrap")

    def test_the_generator_is_reproducible(self):
        again = c.make_synthetic(self.dir, 0.25, "again.log")
        with open(self.small, "rb") as a, open(again, "rb") as b:
            self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
