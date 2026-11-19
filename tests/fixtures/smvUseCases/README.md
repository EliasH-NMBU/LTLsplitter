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
  several requirements out of one. Four properties over a small arbiter (`mode`, two typed
  `0..5` variables, a few booleans), chosen to actually exercise LTLsplitter's own job
  (suggesting/validating a *decomposition*), not just to prove multiple requirements import --
  an earlier version used three independently trivial, already-atomic properties, which proved
  nothing about the splitting methodology:
  - `mutual_exclusion` -- a genuine cross-output coupling with **no** sound decomposition
    (negative control: splitting it into independent per-output rules is strictly stronger and
    not equivalent -- confirmed `not_tautology`).
  - `hidden_disjunctive_trigger` and `hidden_biconditional_past` -- "hidden conjunction"
    properties, true only via a propositional law (distributing an implication over a
    disjunctive antecedent; splitting a biconditional) rather than readable off the formula's
    surface syntax -- the latter is also the file's one past-time (`H`) property. Both splits,
    and that neither half alone already equals the whole, were confirmed `tautology`/
    `not_tautology` as expected against the real nuXmv/Spot/SPIN binaries, using the exact text
    `import_smv_file` parses out of this file.
  - `typed_variable_comparison` -- a variable-to-variable comparison (`x = y`, not `x = 3`),
    exercising the SPIN domain-widening path that kind of comparison specifically needs.
