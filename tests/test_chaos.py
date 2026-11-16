"""Chaos test: hostile logs. Run from the project root: python3 -m unittest tests.test_chaos

- one line of 500 MB with no line end (NOVA_LOG_CHAOS_MB sets the size; CI uses the default);
- invalid UTF-8 byte sequences in otherwise good lines;
- a real .zip archive renamed to .log (binary data).

Pass condition, on the restricted profile with its default limits: exit 1, one clean line saying why
(`nova_log: cannot read PATH: ...`), and no Python traceback. The interpreter must not crash. What each
case prints, and where it differs from the requested std:files.lines() / LimitError behaviour, is in
docs/CHAOS.md.
"""
import io, os, subprocess, sys, unittest, zipfile

from tests import common as c

MB = int(os.environ.get("NOVA_LOG_CHAOS_MB", "500"))
LIMIT = "a string cannot grow beyond 1000000 characters"


def peak_rss_mb(argv):
    """(completed process, peak resident memory of the child in MB). A fresh Python in between, so
    RUSAGE_CHILDREN holds that one child only. ru_maxrss is bytes on macOS and KiB on Linux."""
    probe = ("import resource, subprocess, sys\n"
             "done = subprocess.run(sys.argv[1:], capture_output=True)\n"
             "sys.stdout.buffer.write(done.stdout); sys.stderr.buffer.write(done.stderr)\n"
             "rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss\n"
             "sys.stderr.write('\\nPEAK %d\\n' % (rss // (1 << 20) if sys.platform == 'darwin' else rss // 1024))\n"
             "sys.exit(done.returncode)\n")
    done = subprocess.run([sys.executable, "-c", probe] + argv, capture_output=True, text=True, timeout=600)
    return done, int(done.stderr.rsplit("PEAK ", 1)[1])


class Chaos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = c.tempdir()
        cls.huge = os.path.join(cls.dir, "huge.log")
        with open(cls.huge, "wb") as f:
            block = b"A" * (1 << 20)
            for _ in range(MB):
                f.write(block)
        cls.bad = os.path.join(cls.dir, "badutf8.log")
        with open(cls.bad, "wb") as f:
            f.write(b'10.0.0.1 - - [10/Oct/2026:13:55:36 +0000] "GET / HTTP/1.1" 200 512\n'
                    b'\xff\xfe\xc3\x28 broken \x80\x80\n'
                    b'10.0.0.2 - - [10/Oct/2026:13:55:37 +0000] "GET /\xe9 HTTP/1.1" 404 1\n')
        cls.zip = os.path.join(cls.dir, "archive.log")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("access.log", os.urandom(200000))
        with open(cls.zip, "wb") as f:
            f.write(buffer.getvalue())

    @classmethod
    def tearDownClass(cls):
        c.cleanup(cls.dir)

    def refused(self, done, path, why):
        self.assertNotIn("Traceback", done.stdout + done.stderr)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        lines = done.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, done.stdout)
        self.assertTrue(lines[0].startswith("nova_log: cannot read " + path + ": "), lines[0])
        self.assertIn(why, lines[0])

    def test_a_500_mb_line_hits_the_string_limit(self):
        self.assertEqual(os.path.getsize(self.huge), MB << 20)
        for engine in ("vm", "tree"):
            with self.subTest(engine=engine):
                self.refused(c.run(self.huge, engine, profile="restricted"), self.huge, LIMIT)

    def test_invalid_utf8_is_a_clean_file_error(self):
        for engine in ("vm", "tree", "bootstrap"):
            for profile in ("restricted", None):
                with self.subTest(engine=engine, profile=profile):
                    self.refused(c.run(self.bad, engine, profile=profile), self.bad, "FileError: ")

    def test_a_zip_renamed_to_log_is_a_clean_file_error(self):
        for engine in ("vm", "tree", "bootstrap"):
            for profile in ("restricted", None):
                with self.subTest(engine=engine, profile=profile):
                    self.refused(c.run(self.zip, engine, profile=profile), self.zip, "FileError: ")

    def test_the_interpreter_survives_all_three_in_a_row(self):
        for path in (self.huge, self.bad, self.zip):
            done = c.run(path, profile="restricted")
            self.assertIn(done.returncode, (0, 1))
            self.assertGreater(len(done.stdout), 0, "the program said nothing: did the interpreter die?")
            self.assertNotIn("Traceback", done.stderr)

    @unittest.expectedFailure
    def test_requested_the_refusal_is_made_before_the_file_is_read_whole(self):
        """The requested behaviour: a streaming reader stops at the limit, so memory does not grow with
        the file. Today `read()` loads all of it first and then refuses it (about 2 bytes of memory per
        byte of file: ~1 GB for 500 MB), so a log of several GB could exhaust memory before the clean
        message. Expected to fail until NovaLang's read() checks the size first (docs/CHAOS.md)."""
        argv = [sys.executable, c.NOVA, "--profile", "restricted", "--allow-read", self.dir, "--allow-process",
                "--allow-regex", c.PROGRAM, self.huge]
        done, peak = peak_rss_mb(argv)
        self.assertEqual(done.returncode, 1)
        self.assertLess(peak, 200, "peak memory %d MB for a %d MB file" % (peak, MB))


if __name__ == "__main__":
    unittest.main()
