# GAPS.md - where NovaLang struggled building Nova_Log

The third proof of concept, after [Nova_Stats](https://github.com/ussdaedalus43821-cloud/Nova_Stats) (the language)
and [Nova_Sort](https://github.com/ussdaedalus43821-cloud/Nova_Sort) (the sandbox). This one is **text processing at
scale**: read a web-server access log, pull the HTTP status out of every line without regular expressions, count,
and print a table sorted by frequency. Numbering continues the ecosystem list (Nova_Stats G-001 to G-026, Nova_Sort
G-027 to G-035), so these start at G-036.

Written against NovaLang v2.2.0 (`develop` at f458f1d). Entries marked **M13** are the ones to fix there.

> **Status after NovaLang 2.4 (M14 slice P1):** G-037 has a library route. `std:regex` has captures and `std:text` has
> `find`/`starts_with`, and the program now finds the status with one `std:regex` pattern: `status_of` and `is_status` are
> deleted, and the report is byte for byte the same. The cost is the `regex` grant (`--allow-regex`) and speed: NovaLang's
> matcher is about 4.5 times slower than the two `split`s were. The entries below are the record of what the program did before.

**How to read an entry.** *Tried* is what was attempted and the exact result. *Workaround* says what the code does
instead and **who does the work**: `program` (nova_log.nova), `host` (a Python launcher: none here) or `none` (cannot
be done). *Probe* is a reproducible check in `tests/`; the ones marked "gap probe" pass while the gap exists and fail
the day NovaLang is fixed, so this log cannot rot.

**Severity:** LIMIT (the sandbox cannot express what is needed) - BLOCKER - FRICTION (worked around in the program) - minor.

| # | Gap | Severity | Who works around it | M13 |
| --- | --- | --- | --- | --- |
| G-036 | A `restricted` program cannot read a file over 1,000,000 characters, and there is no streaming read | BLOCKER (for real logs) | none (trusted profile for the benchmark) | yes |
| G-037 | No `index`/`find`/`startswith`: the status is found by splitting on the quote character | FRICTION | program | yes |
| G-038 | `sorted()` cannot order pairs or take a key: counts and codes are packed into one number | FRICTION | program | yes |
| G-039 | `num()` throws on bad text and accepts more than digits; no `isdigit`/`try_num` | minor | program | yes |
| G-040 | An expression cannot continue on the next line, even inside parentheses | FRICTION | program | yes |
| G-041 | No lazy line reader: a 50 MB file becomes 212 MB of strings | LIMIT | none | yes |
| G-042 | The `restricted` time limit is wall-clock, so a slower engine can process less data | LIMIT | none | |

---

## G-036 A `restricted` program cannot read a file over 1,000,000 characters - BLOCKER (M13)
- **Tried:** `read(path)` on a log under the `restricted` profile with the default limits. A file of exactly 1,000,000
  characters reads; one character more fails, on the VM and on the self-hosted engine:
  `a string cannot grow beyond 1000000 characters`. A realistic 1.5 MB log fails the same way. The same file reads
  whole on the `trusted` profile. `read` is the only way to get a file's text: there is no `readline`, no chunked read,
  no `read(path, offset, count)`, no iterator over lines.
- **Why it matters:** the default `string` limit (1,000,000) is a sensible guard for a string a program builds, but for a
  program whose whole job is to look at a file it is a hard cap on the file. A day of traffic on a small site is tens
  of megabytes. The sandbox is the right place to run a log analyser (it needs `files.read` and nothing else) and it
  is the one place this program cannot do its job.
- **Not worked around, on purpose:** the limit can be raised with `--limit string=N`, but a limit that is lifted
  until the test passes is not a test of the sandbox. The restricted runs here use the **default limits** and a log
  under 1 MB (`tests/test_sandbox.py` `Restricted`), and the 50 MB run is a `trusted` run, labelled as such everywhere
  ([`BENCHMARK.md`](BENCHMARK.md)).
- **Also:** the message does not say a *file read* hit the limit (`cannot read over.log: a string cannot grow beyond
  1000000 characters` is the program's own prefix around it). A program cannot tell a file that is too big from any
  other string that grew too big.
- **Suggested for M13:** a streaming read under `files.read`, for example `for line in lines(path) { ... }` or
  `open(path)` with `readline()`/`read(n)`, whose memory is one line or one chunk and which is not subject to the
  string limit; or a separate, larger default for `read` than for strings a program builds. Either one makes
  G-041 go away too.
- **Probe:** `tests/test_sandbox.py` `StringLimit` (`test_G036_*`, gap probes on VM and self-hosted).

## G-037 No `index`/`find`/`startswith`: the status is found by splitting on the quote character - FRICTION (M13)
- **Brief vs language:** the brief said to use `split`, `index` and slicing. **There is no `index`** (nor `index_of`,
  `find`, `startswith`, `starts_with`, `contains_at`: each is `undefined name`). `in` tells whether a substring is
  present but not where. Same gap as Nova_Stats G-006.
- **Tried, and how painful was it?** For the ordinary line it was **not painful**: a combined-format line is
  `ip - user [time] "METHOD /path HTTP/1.1" STATUS BYTES "referrer" "agent"`, so splitting on `"` puts the status
  at the head of piece number 2, and `split(piece)` on whitespace gives it as the first word. Two lines of code
  (`status_of`). It is the **awkward lines** that are painful:
  - a quote inside the request (`"GET /odd\"path HTTP/1.1"`) adds one piece and moves everything, so the first
    strategy finds `path` instead of a number. The fix is a second strategy that counts from the *end* (the piece
    five from the last). That works only because every combined-format line ends the same way; an agent string that
    itself contains a quote breaks both strategies, and the line is then reported as unparsed rather than miscounted.
  - nothing validates the answer for free: `is_status` checks length 3, first digit 1-5 and the rest digits by hand.
  - with an `index`, the whole thing would be "the position after the second unescaped quote", which is what
    a person means, and what the regex in the test oracle says in one line.
- **Workaround (program):** `status_of` in `nova_log.nova`: two strategies and a validity check; lines that satisfy
  neither are counted as *unparsed* and the first five are printed. 9 of the 12,131 lines in the 2 MB log needed the
  second strategy and one was garbage. On the generated test logs and the 50 MB benchmark log the program's counts equal the Python regex oracle's exactly.
- **Suggested for M13:** `find(text, part)` (and `find(text, part, start)`), `startswith`, `endswith`, returning
  -1 or `nil` when absent. Capture groups under `regex` would make this one line, but `regex` is a capability the
  sandbox may not grant, and `find` is not.
- **Probe:** `tests/test_gaps.py` `test_G037_*`; `tests/test_log.py` `Edges` and `Synthetic` (oracle comparison).

## G-038 `sorted()` cannot order pairs or take a key - FRICTION (M13)
- **Tried:** the table must be "sorted by count, then code". `sorted([[2, "b"], [1, "a"]])` is
  `TypeError: sorted() needs items that can be compared with each other`. There is no `key=`, and a dict has no
  `items()` to sort anyway.
- **Workaround (program):** encode each (code, count) pair as one number, `count * 1000 + (1000 - code)`, sort the
  numbers descending (`sorted(list, true)` works) and decode with `//` and `%`. Most frequent first, lower code first
  on a tie. It is correct only while codes are below 1000, which an HTTP status is by definition; a general
  "sort by count" would need a hand-written sort or a bigger packing, and a string key (a path, an IP) cannot be
  packed this way at all.
- **Suggested for M13:** `sorted(items, key)` taking a function (or a list-comparison rule: lexicographic order for
  lists), plus `items(dict)`.
- **Probe:** `tests/test_gaps.py` `test_G038_*`; the order is checked against the oracle in `tests/test_log.py`
  (`test_ties_put_the_lower_code_first`).

## G-039 `num()` throws on bad text and accepts more than digits - minor (M13)
- **Tried:** `num("abc")`, `num("1e2")`, `num("0x10")`, `num("1_0")` and `num("")` all throw
  `num() cannot read a number from ...`; `num(" 7")`, `num("+5")` and `num("0200")` succeed (7, 5, 200). There is no
  `isdigit`, `isnumeric` or `try_num`, so "is this three digits?" cannot be asked of the text without a `try` block
  or a hand-written loop. (Nova_Stats G-002.)
- **Workaround (program):** `is_status` tests the three characters against `"0123456789"` with `in`, so `num` is only
  ever called on text already known to be digits (the code in the sort key).
- **Suggested for M13:** `isdigit(text)`, and either `num(text, default)` or `try_num`.
- **Probe:** `tests/test_gaps.py` `test_G039_*` (gap probe, both engines).

## G-040 An expression cannot continue on the next line - FRICTION (M13)
- **Tried:** a long `print("..." + x +` with the rest on the next line fails: `NovaError: the expression ends too
  early`. Wrapping the whole thing in parentheses does not help, and starting the next line with the operator
  parses `+ "y"` as a new statement: `cannot apply unary '+' to a string`. (Brackets of a *literal*, a list or dict
  spread over lines, are fine; that is how the `NAMES` table is written.)
- **Workaround (program):** build long lines in two statements (`let row = ...` then `row = row + ...`).
- **Suggested for M13:** let a line end inside parentheses and after a binary operator continue the expression,
  as most languages do. The tell is how many error messages the first draft of any formatted output produces.
- **Probe:** `tests/test_gaps.py` `test_G040_*` (gap probe, both engines).

## G-041 No lazy line reader: a 50 MB file becomes 212 MB of strings - LIMIT (M13)
- **Tried:** `split_lines(read(path))` holds the whole file twice (the text, then a list of every line). Measured on
  the 50 MB benchmark (`trusted`): peak resident memory **212 MB**, about 4.2 times the file. That is fine for this
  file on a laptop and not fine for a 2 GB log, and in the sandbox the `list` limit (1,000,000 items) would also stop
  a log of more than a million lines.
- **Workaround:** none; the whole file is read, which is also what G-036 forbids in the sandbox.
- **Suggested for M13:** the same streaming read as G-036.
- **Probe:** `tests/test_gaps.py` `test_G041_*` (documents the shape: a list of every line); the number is in
  [`BENCHMARK.md`](BENCHMARK.md).

## G-042 The `restricted` time limit is wall-clock, so a slower engine can process less data - LIMIT
- **Tried:** the default limit is 5000 ms and fatal. On the VM, parsing runs at about 24,000 lines per second, so the
  default alone would stop a log of roughly 120,000 lines (about 20 MB of this shape) even if G-036 were solved.
  That figure is **derived from the measured rate, not tested** (the string limit stops the program first). What was
  observed: on the **self-hosted engine**, which is about 30 times slower, a 10,000-line, 1,000,000-character log
  under the default limits ends with `LimitError: time limit of 5000 ms exceeded`. The same program and grants
  finish on the VM. The self-hosted engine therefore cannot analyse the largest log the VM can, inside the same sandbox.
- **Workaround (tests):** the sandbox boundary test for the string limit uses one long line instead of 10,000
  short ones, so the two limits are not confused (`tests/test_sandbox.py`). Nothing was raised.
- **Note:** a time limit counted in steps would give the same answer on every engine; one counted in milliseconds
  gives the answer of the machine and the engine. Both exist (`steps` 5,000,000 and `time` 5000 ms); the time limit is
  the one that bites first.
- **Probe:** not pinned (a timing probe would be flaky); the one-long-line test is the guard against confusing it
  with G-036.

---

## What worked (no entry needed)
- **`split`, slicing and `len` are enough for the ordinary line,** and the program is one 242-line file with no
  imports, no regex and no Python host.
- **Speed is acceptable for a language like this.** The 50 MB, 303,684-line log is analysed in about 12.9 s on the
  bytecode VM, **trusted**, with every count identical to a Python regex oracle ([`BENCHMARK.md`](BENCHMARK.md)).
  `read` itself takes 0.03 s; the time is in the per-line parse.
- **The same answer on every engine.** VM, tree-walker and self-hosted interpreter agree with the oracle on the
  edge lines and on generated logs (`tests/test_log.py`).
- **A read-only grant is enough, and proves the program never writes.** `restricted` with `--allow-read` on the log's
  folder (plus `--allow-process` for `args()` and optionally `--allow-clock` for the timings) is the whole grant, and
  a write would be an undefined name. `tests/test_sandbox.py` `Restricted`.
- **A path outside the grant is refused** with `outside the folders this program may use`, caught by the program's
  own `try`.
- **`split_lines` handles CRLF and a missing final newline;** `trim` and `split` handle the stray `\r`.
