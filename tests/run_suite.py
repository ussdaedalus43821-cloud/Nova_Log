"""The whole suite, timed. Run from anywhere: python3 tests/run_suite.py
(The 50 MB benchmark is separate: python3 tests/bench.py, see docs/BENCHMARK.md.)"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEPS = [
    ("behaviour: edge lines, ordering, top-N, on VM, tree-walker and self-hosted", ["tests.test_log"]),
    ("gap probes: what NovaLang lacks, pinned so docs/GAPS.md cannot rot", ["tests.test_gaps"]),
    ("sandbox: restricted profile, default limits, and the G-036 probes", ["tests.test_sandbox"]),
    ("chaos: a 500 MB line, invalid UTF-8, a .zip renamed to .log", ["tests.test_chaos"]),
]
failed = False
for title, modules in STEPS:
    started = time.time()
    done = subprocess.run([sys.executable, "-m", "unittest"] + modules, cwd=ROOT, capture_output=True, text=True)
    ran = [l for l in done.stderr.splitlines() if l.startswith("Ran ")]
    print("%-80s %5.1fs  exit %d  %s" % (title, time.time() - started, done.returncode, ran[0] if ran else ""))
    if done.returncode:
        failed = True
        print(done.stderr)
print("RED" if failed else "GREEN")
sys.exit(1 if failed else 0)
