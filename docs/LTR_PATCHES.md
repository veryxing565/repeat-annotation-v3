# Bundled LTR wrapper modifications

These are the text sources used by the current outgroup v3 workflow, not
unmodified copies from a new upstream release. Original authorship and MIT
licenses are retained in each source directory.

## Source baselines

| Wrapper | Upstream release archive | Archive SHA256 from the installed recipe |
| --- | --- | --- |
| LTR_FINDER_parallel 1.4 | https://github.com/oushujun/LTR_FINDER_parallel/archive/v1.4.tar.gz | `8c6cceb76c7ce2f4c9a68037f9d565fc751422957323061d7a57b611f98476a4` |
| LTR_HARVEST_parallel 1.3 | https://github.com/oushujun/LTR_HARVEST_parallel/archive/v1.3.tar.gz | `877df9f8964c8ed94eb15af831c47aa6f048708e889f3905e6133e30810e84ef` |

These archive hashes identify the upstream inputs, not the modified files.
The modified source hashes are recorded in `provenance/source_snapshot.json`.

## Timeout salvage fix (v3, before publication)

The original single-thread shortcut ignored window size and timeout when a
timed-out large region recursively invoked the same wrapper with
`-threads 1 -try1 0`. The v3 change routes such salvage calls through the
queue/splitting branch by using `if ($threads == 1 && $try1 != 0)`.

- Main windows: 5,000,000 bp, overlap 100,000 bp, timeout 300 seconds.
- Salvage windows: 50,000 bp, overlap 5,000 bp, no recursive salvage.
- Finder salvage timeout: 10 seconds per subwindow.
- Harvest salvage timeout: 30 seconds per subwindow; inspect the source for
  individual GenomeTools commands rather than assuming one genome-wide limit.

Timed-out subwindows can still be lost. This is a bounded runtime policy, not
a guarantee of complete structural discovery. Wrapper windowing is internal
LTR candidate generation; it does not split an assembly into independent TE
libraries or independent RepeatModeler runs.

The upstream `-o`/`-overlap` support and corresponding `cut.pl` helpers are
retained. They are not claimed as new contributions of this packaging work.

## Portability boundary

The wrappers still use shell commands internally. The public runner therefore
requires a shell-safe installation/work path and creates shell-safe normalized
FASTA IDs. Use ASCII letters, digits, `_`, `.`, `-`, and `/` in those paths;
avoid spaces, quotes, shell expansion characters, colons, and commas.
The original genome can reside elsewhere; it is read by the Python normalizer.

Do not replace the bundled wrappers with unpatched conda copies when
reproducing this workflow. The runner calls the bundled paths explicitly.
