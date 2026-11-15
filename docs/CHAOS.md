# Chaos test: hostile logs

`tests/test_chaos.py` (in `tests/run_suite.py` and CI) feeds `nova_log.nova` three hostile files on the
restricted profile with its default limits:

| File | What it is | Result (VM and tree-walker; the last two on the self-hosted engine and the trusted profile too) |
| --- | --- | --- |
| `huge.log` | one line of 500 MB (`A` × 524,288,000), no line end | exit 1, `nova_log: cannot read huge.log: a string cannot grow beyond 1000000 characters` |
| `badutf8.log` | good lines around `\xff\xfe\xc3\x28` and a lone `\x80` | exit 1, `nova_log: cannot read badutf8.log: FileError: …: 'utf-8' codec can't decode byte 0xff in position 67: invalid start byte` |
| `archive.log` | a real `.zip` (200 KB of random bytes, deflated) renamed | exit 1, the same `FileError`, for byte 0xb2 |

**Pass condition**: exit 1, one clean line saying why, and no Python traceback. All three cases pass, and
the interpreter is still running after each one. `NOVA_LOG_CHAOS_MB` sets the size of the long line.

## Where this differs from what was asked for

The request said "`std:files.lines()` should hit the 1,000,000-character limit and throw a clean
`LimitError`". Three points differ:

1. **Nova_Log does not use `std:files.lines()`.** It reads with `read(path)` and then `split_lines`. The PoC was
   written to measure that path (G-036), and its report times "read" and "parse" separately. The limit it
   hits is still the 1,000,000-character string limit, with a clean message.
2. **No error is called `LimitError`.** The string limit's error has no label: `str(e)` is just
   `a string cannot grow beyond 1000000 characters`. Read errors are labelled `FileError`.
3. **The refusal comes after the whole file is in memory.** `read()` (NovaLang `builtin_read`) reads the
   file whole, then the limit check refuses it. Peak memory for the 500 MB line was **1,082 MB**, so a
   log of several GB could run out of memory before the clean message. This is pinned as an
   `expectedFailure` test (peak memory under 200 MB). The fix belongs in NovaLang: `read()` should refuse a
   file whose size is already over the string limit before reading it.

   `std:files.lines()` would not be the cure as it stands. With no line end in sight, `files.next_lines`
   grows its chunk up to 16 MiB and then stops with `FileError: …: a line is longer than 16777216 bytes`
   (not the 1,000,000-character limit). It builds that chunk with `bytes +=`, and measured on macOS about
   1 GB peak, the same for a 50 MB file as for a 500 MB one. Memory there is bounded but not small.
