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
