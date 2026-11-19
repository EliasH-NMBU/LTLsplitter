# smvUseCases

`.smv` files used to test `core/smv_import.py` (the plain NuSMV/nuXmv importer, for specs that
didn't come from a FRET export) against genuine nuXmv input rather than only hand-written toy
examples.

The first three are copied as-is from nuXmv 2.2.0's own bundled `examples/` directory (shipped
alongside the real binary this project already shells out to) -- nothing in them was written
for this project.

- **growing-counter-integer.smv**, **growing-counter-real.smv** (`examples/growing-counters/`)
  -- small state-machine models with an enum `VAR`, an unbounded `integer`/`real` `VAR`, an
  `ASSIGN`/`INVARSPEC` section the importer correctly ignores (out of scope -- it only reads
  `VAR` and `LTLSPEC`), and a single future-time `LTLSPEC`. `growing-counter-integer.smv`'s
  `LTLSPEC G F (state = s3)` is also what caught a real bug while building this importer: `s3`
  is an *enum literal* of `state`, not a second variable, and an early version of
  `smv_import.py` auto-discovered it as one anyway.
- **krca1p1.smv** (`examples/ltlsat-polimi/`) -- a real LTL-satisfiability benchmark: 16 plain
  boolean `VAR`s, no `ASSIGN` at all, and one large `LTLSPEC` mixing past-time (`H`/`O`/`S`/`Y`)
  and future-time (`G`/`X`/`U`) operators, with **no trailing `;`** on the last statement in the
  file -- confirmed against the real nuXmv binary that this still parses and checks cleanly, so
  `smv_import.py`'s `LTLSPEC` terminator has to accept end-of-file, not just a semicolon. It
  also has exactly **one** `LTLSPEC` statement (it's a single satisfiability query, not a
  multi-property spec) -- importing it as one requirement is correct, not a parsing miss.
- **arbiter_multi_property.smv** -- hand-written for this project, *not* from nuXmv's examples.
  Checked every file nuXmv 2.2.0 ships, including the three above: none has more than one
  `LTLSPEC` statement, so there was no real file to demonstrate `smv_import.py` importing
  several requirements out of one. Three independent `NAME`d properties (mutual exclusion,
  eventual response, and a mixed future+past one) over a small request/grant arbiter; each
  requirement's extracted formula was checked for self-equivalence against the real nuXmv/Spot
  binaries before this was added.
