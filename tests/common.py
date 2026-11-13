"""Shared helpers: build logs, count them with an independent Python oracle, run nova_log.nova on any
engine and profile, and read its table back into numbers."""
import collections, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOVA = os.path.join(ROOT, "novalang", "novalang.py")
PROGRAM = os.path.join(ROOT, "nova_log.nova")
MAKE_LOG = os.path.join(ROOT, "tools", "make_log.py")

# The oracle is written in a different language with a different method, on purpose: a regular expression
# with real escape handling (the part NovaLang has to do by hand). A status is the 3-digit code 100-599 that
# follows the closing quote of the request, and the request may contain \" .
LINE = re.compile(r'^\S+ \S+ \S+ \[[^\]]*\] "(?:[^"\\]|\\.)*" ([1-5]\d\d) ')


def oracle(path):
    """-> (Counter of status codes, total lines, unparsed lines, blank lines), counted the Python way."""
    counts, total, unparsed, blank = collections.Counter(), 0, 0, 0
    with open(path, encoding="utf-8", newline="") as f:
        data = f.read()
    for line in data.splitlines():
        total += 1
        line = line.rstrip("\r")
        if line == "":
            blank += 1
            continue
        found = LINE.match(line)
        if found:
            counts[found.group(1)] += 1
        else:
            unparsed += 1
    return counts, total, unparsed, blank


def expected_order(counts):
    """Most frequent first, lower code first on a tie: the order the table must have."""
    return [code for code, _ in sorted(counts.items(), key=lambda kv: (-kv[1], int(kv[0])))]


def run(log, engine="vm", profile=None, extra=(), cwd=None, process=True, clock=True, read_dir=None):
    """Run nova_log.nova on `log`. engine: vm | tree | bootstrap (self-hosted, CLI only).
    profile=None is the CLI default (trusted); "restricted" grants only what the program needs."""
    args = [sys.executable, NOVA]
    if engine == "tree":
        args += ["--tree-walk"]
    if profile == "restricted":
        args += ["--profile", "restricted", "--allow-read", read_dir or os.path.dirname(os.path.abspath(log))]
        if process:
            args += ["--allow-process"]
        if clock:
            args += ["--allow-clock"]
    if engine == "bootstrap":
        args += ["--bootstrap"]  # must come last before the program: docs/GAPS.md (G-034 in Nova_Sort)
    args += [PROGRAM, log] + list(extra)
    return subprocess.run(args, capture_output=True, text=True, timeout=600, cwd=cwd)


ROW = re.compile(r"^  (\d{3}) +[A-Za-z ]*?\s*([\d,]+) +(\d+\.\d)% +█+$", re.M)
SUMMARY = re.compile(r"^  ([\d,]+) lines: ([\d,]+) with a status, ([\d,]+) unparsed, ([\d,]+) blank$", re.M)


def parse(output):
    """Read the printed table back: -> dict(rows=[(code, count)] in printed order, total, parsed, unparsed, blank)."""
    rows = [(code, int(count.replace(",", ""))) for code, count, _share in ROW.findall(output)]
    m = SUMMARY.search(output)
    total, parsed, unparsed, blank = (int(g.replace(",", "")) for g in m.groups()) if m else (None,) * 4
    return {"rows": rows, "total": total, "parsed": parsed, "unparsed": unparsed, "blank": blank}


def make_synthetic(directory, megabytes, name="synthetic.log"):
    path = os.path.join(directory, name)
    subprocess.run([sys.executable, MAKE_LOG, path, str(megabytes)], check=True, capture_output=True)
    return path


def write(directory, name, data):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    return path


def tempdir():
    return tempfile.mkdtemp(prefix="nova_log_test_")


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)
