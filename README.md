# Nova_Log

> **The third proof of concept for [NovaLang](https://github.com/ussdaedalus43821-cloud/Nova_Lang), after [Nova_Stats](https://github.com/ussdaedalus43821-cloud/Nova_Stats) and [Nova_Sort](https://github.com/ussdaedalus43821-cloud/Nova_Sort).**
> A web-server log analyzer written entirely in NovaLang: one program, no Python host; since NovaLang 2.4 it finds the status with one `std:regex` pattern.
> It tests **text processing at scale**.

It reads an access log, finds the HTTP status code on every line, counts them, and prints a table sorted by frequency.

> ### Read this before the numbers: the 50 MB run is a `trusted` run
> The 50 MB benchmark (**12.9 s**, 303,684 lines, every count identical to a Python regex) ran on the **`trusted`
> profile: no sandbox and no limits.** NovaLang's `restricted` profile **cannot read a file that large**: a string
> stops at 1,000,000 characters and there is no streaming read ([`docs/GAPS.md`](docs/GAPS.md) **G-036**). That limit
> was left alone, not raised to make a test pass. The `restricted` runs in the tests use the default limits on logs
> under 1 MB. Details: [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

## Run

```bash
python3 novalang/novalang.py nova_log.nova access.log        # the whole table
python3 novalang/novalang.py nova_log.nova access.log 5      # only the 5 most frequent codes
```

Example (a generated 2 MB log, abridged):

```
Nova_Log: access_2mb.log
  12,131 lines: 12,130 with a status, 1 unparsed, 0 blank
  9 of those were found by counting from the end of the line (a quote inside the request)

  Status  Meaning                      Count    Share  Bar
  200     OK                           7,479    61.7%  ███████████████
  304     Not Modified                 1,733    14.3%  ███
  404     Not Found                    1,111     9.2%  ██
  301     Moved Permanently              483     4.0%  █
  ...
  By class
  2xx success                7,564    62.4%
  3xx redirect               2,560    21.1%
  4xx client error           1,603    13.2%
  5xx server error             403     3.3%

  Unparsed lines (first 1):
    garbage line 5295 with no structure
  read 0.00 s, parse 0.50 s, 24,024 lines/s
```

Needs only Python 3 to start NovaLang. Logs are made by `python3 tools/make_log.py OUT.log [MEGABYTES]` (seeded,
reproducible, includes awkward lines on purpose); they are never committed.

## How it finds the status

The combined log format is `ip - user [time] "METHOD /path HTTP/1.1" STATUS BYTES "referrer" "agent"`.
Since NovaLang 2.4 the status is found by **one `std:regex` pattern** (`STATUS` in `nova_log.nova`) with two alternatives:

1. after the second quote of the line: optional spaces, then three digits 100-599, ended by a space, a quote or the end
   of the line (capture group 1);
2. if a quote inside the request shifted the pieces, counting **from the end**: the quote-delimited piece with exactly
   four more quotes after it (capture group 2).
3. If neither matches, the line is counted as *unparsed* and the first five are shown. Nothing is guessed.

Until 2.4 the program did this by hand with `split(line, "\"")`, slicing and `len` (`status_of` and `is_status`,
because there was no `find` and no regex captures, G-037). Those helpers are deleted. The report is **byte for byte the
same** on `small_log.txt`, the three large logs, a 0.95 MB generated log and 3,000 random edge lines, on all three
engines, and `tests/test_sandbox.py` `Pattern` checks the pattern against the old split parser line by line. The
cost: NovaLang's own regex matcher is slower than two `split`s, about 4,000 lines/s against 17,800 on the VM.

The table is ordered with `sorted()` on one number per code (`count * 1000 + (1000 - code)`), because `sorted` cannot
order pairs ([G-038](docs/GAPS.md)).

## Sandbox use

The program only reads, and needs `process` (for `args()`), plus `clock` for the timings if you grant it:

```bash
python3 novalang/novalang.py --profile restricted --allow-read LOGDIR --allow-process --allow-regex --allow-clock nova_log.nova LOGDIR/access.log
```

That works for a log up to **1,000,000 characters**. A larger one stops with `a string cannot grow beyond 1000000
characters` (G-036). On the self-hosted engine (`--bootstrap`, which must be the last flag before the program) the
default 5 s time limit also ends a restricted run at roughly 10,000 lines (G-042).

## Results

| | |
| --- | --- |
| Tests | **29**, green on the VM, the tree-walker (`--tree-walk`) and the self-hosted interpreter |
| 50 MB benchmark (**trusted**) | 12.86 s best of 3 (3.9 MB/s), 212 MB peak, counts equal the oracle |
| Python on the same log | regex 0.55 s, `split` 0.23 s (NovaLang about 23x and 56x slower) |
| Gaps found | **7**, G-036 to G-042 |

The gaps, in short: a restricted program cannot read a large file and there is no streaming read (G-036, the one
for M13), no `index`/`find` (G-037), `sorted` cannot order pairs (G-038), `num` is too permissive and throws
(G-039), no line continuation (G-040), the whole file is held in memory (G-041), and the restricted time limit
is wall-clock (G-042). **How painful was extracting the status without regex?** Not very for the normal line;
painful only for the quote inside the request ([G-037](docs/GAPS.md)).

## Layout

| Path | Role |
| --- | --- |
| `nova_log.nova` | the program: read, parse, count, report (242 lines) |
| `tools/make_log.py` | seeded synthetic log generator (the only thing here that needs Python) |
| `tests/` | `test_log.py` behaviour, `test_gaps.py` gap probes, `test_sandbox.py` restricted runs and G-036, `bench.py` the 50 MB run |
| `docs/GAPS.md` | every gap found (G-036 to G-042) and what worked |
| `docs/BENCHMARK.md` | the 50 MB trusted run, method and numbers |
| `novalang/` | the interpreter, copied unmodified (see `novalang/VENDORED.md`) |

## Test

```bash
python3 tests/run_suite.py       # ~45 s: behaviour, gap probes, sandbox
python3 tests/bench.py           # the 50 MB trusted benchmark
```

The behaviour tests compare the program with an **independent oracle**, a Python regular expression, on hand-made
edge lines (escaped quotes, a bare `"-"` request, IPv6, bogus statuses such as 999, CRLF, a missing final newline,
an empty file) and on generated logs, on all three engines.

## Limits

Combined-format logs only (a status is the first word after the request); a quote inside the user-agent defeats both
strategies and the line is reported as unparsed. The whole file is held in memory. One file per run.
