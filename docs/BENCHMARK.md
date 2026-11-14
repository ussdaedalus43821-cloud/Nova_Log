# BENCHMARK.md - Nova_Log on a 50 MB access log

> ## This is a `trusted` run. It is not a sandbox result.
> The 50 MB log was analysed on NovaLang's **`trusted` profile: no sandbox, no limits.** The `restricted` profile
> **cannot read a file this size at all**: its default `string` limit is 1,000,000 characters
> ([`GAPS.md`](GAPS.md) G-036), and the limit was deliberately **not** raised to make this pass. The `restricted`
> runs in the test suite use the default limits on logs under 1 MB. This page shows the engine's raw speed, and
> nothing about what the sandbox can do.

## What was run
- **Program:** `nova_log.nova`, unmodified (the one in this repository), on the bytecode VM, `trusted`:
  `python3 novalang/novalang.py nova_log.nova LOG`
- **Log:** `tools/make_log.py` (seeded, reproducible): **50.0 MB, 303,684 lines**, combined log format, 13 status
  codes with realistic weights, plus on purpose about 0.05 % lines with a quote inside the request, 0.05 % with a bare
  `"-"` request, and 0.02 % garbage lines. Not committed (`*.log` is git-ignored); regenerate it with
  `python3 tools/make_log.py /tmp/nova_log_50mb.log 50`.
- **Machine:** Apple M1, 8 GB, macOS, CPython 3.9.6 (the interpreter NovaLang runs on). **On battery power** at the
  time of the run (the laptop was unplugged), which can lower sustained speed; it was not repeated plugged in.
- **Method:** three fresh processes (`python3 tests/bench.py LOG --runs 3`). Before any time is reported the counts
  are compared with an independent Python regex oracle; all three runs matched exactly.

## Results (trusted, VM)

| Run | Wall | `read` | Parse | Lines/s | Peak memory |
| --- | --- | --- | --- | --- | --- |
| 1 | 13.07 s | 0.03 s | 12.93 s | 23,484 | 212 MB |
| 2 | 12.86 s | 0.02 s | 12.73 s | 23,864 | 212 MB |
| 3 | 12.92 s | 0.02 s | 12.79 s | 23,749 | 212 MB |

**Best: 12.86 s wall, 3.9 MB/s.** Run to run the spread is under 2 %.

| Same job in CPython 3.9.6 | Time | NovaLang is |
| --- | --- | --- |
| a regex per line (the test oracle) | 0.55 s | 23x slower |
| `split` on the quote, same method as Nova_Log | 0.23 s | 56x slower |

The counts (identical in all runs and to the oracle): 200: 188,168 - 304: 42,526 - 404: 27,364 - 301: 12,119 -
302: 8,986 - 500: 6,607 - 403: 4,533 - 401: 3,016 - 502: 2,472 - 400: 2,435 - 206: 2,165 - 429: 1,530 -
503: 1,524 - 408: 187. 303,632 lines have a status; 125 of them needed the count-from-the-end rule; 52 are unparsed
garbage lines.

## What the numbers say
- **Reading is free; parsing is the cost.** `read` of 50 MB takes 0.03 s. Splitting into lines takes about 0.3 s
  (measured in an earlier probe). The other ~12.5 s is the per-line work: one `split` on `"`, one `split` of a piece,
  a validity check and a dictionary update, about 42 microseconds per line.
- **An earlier probe ran 2.5x faster, and the difference is a lesson.** A throwaway version of the same idea, written
  inline with no functions and no fallback, parsed this log in 4.99 s. The shipped program is cleaner (`status_of`
  returns `[status, strategy]`, `is_status` validates, a second strategy handles escaped quotes) and costs 12.8 s.
  The likely cause is function-call and list-allocation overhead, two calls and one list per line, but **that was not
  isolated**; it is a hypothesis. Nova_Log keeps the clearer version.
- **Memory is about 4.2 times the file** (212 MB for 50 MB) because the text and the list of every line are both held
  ([`GAPS.md`](GAPS.md) G-041).
- **Throughput is a sandbox question as well.** At 24,000 lines/s the default 5 s `time` limit would stop a
  `restricted` run at roughly 120,000 lines (about 20 MB of this shape) even without the string limit (G-042, derived
  and not tested).

## Reproduce
```bash
python3 tests/bench.py                 # generates a 50 MB log in the temp folder, runs 3 times, compares with the oracle
python3 tests/bench.py my.log --runs 1 # any log you already have
```

## Real-World Baseline (Pre-M12)

These benchmarks establish the performance and security baseline for the M12 (Bytecode Cache & Performance) and M13 (Libraries) milestones. Run on a MacBook Pro M1 (8GB RAM). Unless noted, engine is the Bytecode VM.

### 1. Nova_Stats (System Telemetry)
- **Throughput:** 11 ms per tick on the VM (649 ms on self-hosted).
- **Memory Profile:** 212 MB peak while sampling six system modules.
- **Findings:** Detected a 100% CPU load spike and memory pressure flip to "warning" caused by parallel Python processes. Established that macOS `pmset` uses a heavily smoothed historical average for battery, while NovaLang correctly calculates instantaneous physics.
- **Gaps:** G-026 (Ctrl-C traceback in embedding API).

### 2. Nova_Sort (Sandbox & File I/O)
- **Throughput:** Instantaneous for a 5-item folder. 
- **Security Baseline:** The sandbox successfully enforced `files.read` and `files.write`. However, it revealed two critical flaws: `files.write` implicitly grants `remove`/`delete` (G-027), and `rename` silently overwrites existing files (G-028). 
- **Findings:** Because the sandbox could not prevent deletions or overwrites, the `Nova_Sort` program had to implement its own safety layer (forbidding delete keywords and checking `exists()` before renaming) to safely manage file system operations.

### 3. Nova_Log (Text Parsing at Scale)
- **Throughput:** Consistent ~24,500 lines/sec across all datasets.
- **Memory Profile:** 212 MB peak for a 50 MB file (proves G-036: no streaming read).
- **Datasets & Results:**
  | Dataset | Lines | Time | Unparsed | Notes |
  |---|---|---|---|---|
  | Sample access log (May 2015) | 10,000 | 0.42s | 0 | Combined log format; 10,000-line sample file, dated 17 May 2015 |
  | Synthetic (Tesla/Starlink) | 50,000 | 2.05s | 0 | 50/50 split of 200s/404s |
  | Nginx (Modern) | 51,462 | 2.09s | 0 | 6.8MB file, universal parsing |
- **Sandbox Limit:** Refused a 1.1MB file with `a string cannot grow beyond 1000000 characters`. Successfully parsed a 488KB chunk (2,154 lines) in the sandbox.

### 4. Nova_Data (Financial Math)
- **Throughput:** 5,916 records/s (1.69s for 10,000 rows).
- **Dataset:** 10,000 synthetic financial transactions (CSV).
- **Precision Baseline:** 
  - Exact sum (integer cents): `$2,231,316.93`
  - Naive float sum (via `str()`): `2231316.930000008`
  - **Drift:** `$0.000000008` after 9,993 additions (Proves the requirement for exact decimal math, G-044).
- **Resilience:** Successfully rejected 6 corrupted rows (leap year 2025-02-29, `N/A` text, `4.999` fraction, missing fields, month 13) without crashing.
- **Sandbox:** Successfully processed a 700KB CSV in `restricted` mode with `--allow-read data`.

### Summary for M12
The core bottleneck across all PoCs is the VM interpreter's overhead when handling string manipulation, floating-point conversions, and massive memory allocations (e.g., reading whole files into memory). The lack of native `regex`, `index`, and streaming reads forces NovaLang to do heavy lifting in the interpreter rather than in optimized C-level standard library functions.
