"""The 50 MB benchmark. THIS IS A `trusted` RUN: no sandbox, no limits. It exists to show the engine's raw speed,
because the `restricted` profile cannot read a file this size at all (docs/GAPS.md G-036).

    python3 tests/bench.py [LOG_PATH] [--runs N] [--megabytes M]

The log is generated (tools/make_log.py, seeded) if LOG_PATH does not exist, and is never added to git.
Each run is a fresh process; the counts are checked against the Python oracle before any time is reported."""
import os, re, resource, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import common as c


def peak_mb(args):
    """Run args, return (seconds, peak resident MB of the child, stdout). ru_maxrss is bytes on macOS, KB on Linux."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    started = time.perf_counter()
    done = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    seconds = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return seconds, peak / (1048576 if sys.platform == "darwin" else 1024), done


def python_baseline(path):
    """The same job in plain Python, two ways: a regex per line, and the same split-on-quote method."""
    started = time.perf_counter()
    counts = c.oracle(path)[0]
    regex_s = time.perf_counter() - started
    started = time.perf_counter()
    other = {}
    with open(path, encoding="utf-8") as f:
        for ln in f.read().splitlines():
            parts = ln.split('"')
            code = parts[2].split()[0] if len(parts) >= 3 and parts[2].split() else ""
            other[code] = other.get(code, 0) + 1
    split_s = time.perf_counter() - started
    return regex_s, split_s, counts


def main(argv):
    runs, megabytes, path = 3, 50, None
    i = 0
    while i < len(argv):
        if argv[i] == "--runs":
            runs = int(argv[i + 1]); i += 2
        elif argv[i] == "--megabytes":
            megabytes = float(argv[i + 1]); i += 2
        else:
            path = argv[i]; i += 1
    path = path or os.path.join(tempfile.gettempdir(), "nova_log_%dmb.log" % megabytes)
    if not os.path.exists(path):
        subprocess.run([sys.executable, c.MAKE_LOG, path, str(megabytes)], check=True)
    size = os.path.getsize(path)
    counts, total, unparsed, _ = c.oracle(path)
    print("profile: TRUSTED (no sandbox, no limits)   file: %s   %.1f MB   %d lines" % (path, size / 1048576, total))
    results = []
    for n in range(runs):
        seconds, mb, done = peak_mb([sys.executable, c.NOVA, c.PROGRAM, path])
        if done.returncode:
            print(done.stdout, done.stderr)
            return 1
        got = c.parse(done.stdout)
        if dict(got["rows"]) != dict(counts) or got["unparsed"] != unparsed:
            print("MISMATCH against the Python oracle:\n" + done.stdout)
            return 1
        inside = re.search(r"read ([\d.]+) s, parse ([\d.]+) s, ([\d,]+) lines/s", done.stdout)
        results.append((seconds, mb, float(inside.group(1)), float(inside.group(2)), int(inside.group(3).replace(",", ""))))
        print("run %d: wall %.2f s   read %.2f s   parse %.2f s   %s lines/s   peak %.0f MB   counts match the oracle"
              % (n + 1, seconds, results[-1][2], results[-1][3], inside.group(3), mb))
    best = min(results)
    regex_s, split_s, _ = python_baseline(path)
    print("best:   wall %.2f s (%.1f MB/s)   parse %.2f s   peak %.0f MB" % (best[0], size / 1048576 / best[0], best[3], best[1]))
    print("python: regex per line %.2f s   split on quote %.2f s   (CPython %s)" % (regex_s, split_s, sys.version.split()[0]))
    print("ratio:  NovaLang wall / Python regex = %.1fx   / Python split = %.1fx" % (best[0] / regex_s, best[0] / split_s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
