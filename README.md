# LTLsplitter

A GUI pipeline that imports a [NASA FRET](https://github.com/NASA-SW-VnV/fret) project export, uses an LLM to propose and perform a split of an LTL requirement into independent sub-properties, cross-validates that split with three different model checkers, checks realizability against the rest of the system with two independent tools, and exports the result to NASA's [Ogma](https://github.com/nasa/ogma) for ROS2 Copilot runtime-monitor generation.

**Platform: Linux only.** See [docs/pipeline-design-research.md](docs/pipeline-design-research.md) for why (Ogma, Strix, Spot, SPIN, and Kind2 are Linux-native only).

## Pipeline stages

1. **Import & Split Review** — import a FRET project export (`requirements`/`variables` JSON), pick one requirement, and let an LLM suggest whether/how many ways to split its LTL formula. Review and accept or reject the suggestion; if accepted, the LLM performs the split into editable sub-formulas. If the LLM doesn't recommend a split, a "Force split anyway" option appears to ask it for one regardless. Accepting a split prompts for a filename and saves it as a **new copy** of the FRET file, with the sub-formulas appended as requirements nested under the original (shown as a dropdown in the requirement tree) — the original file is never modified, and the new copy becomes the active file for the rest of the session. Each requirement also has an **Assumption** checkbox (seeded from FRET's `*_assumption` naming convention, correctable by hand) marking it as an environment constraint rather than a system guarantee -- used by stage 3.
2. **Decomposition Validation** — nuXmv, Spot, and SPIN each independently check that the sub-formulas' conjunction is logically equivalent to the original formula, and that no single sub-formula is -- by itself -- already equivalent to the whole original (i.e. it's a genuine split, not a degenerate one). A failure can be sent back to the LLM as feedback for another attempt.
3. **Realizability Check** — checks whether a system strategy exists that satisfies the *entire current system*: every requirement in the imported FRET file, counted exactly once -- a split's sub-formulas, once saved (stage 1), stand in for the original requirement they came from rather than being added alongside it (`FretImport.leaf_requirements()` -- a requirement with children, via `parent_reqid`, is excluded in favor of them). No requirement needs to be selected; this reads directly off the current state of the imported file. Requirements marked as assumptions (stage 1's checkbox) are treated as environment constraints rather than system guarantees -- Strix checks `assumptions -> guarantees` instead of a flat conjunction, and Kind2 gets an `assume` contract item instead of `guarantee` (see "Assumptions vs. guarantees" below for why this matters). Strix (game synthesis) and Kind2 (SMT/k-induction contract analysis) run side by side as a cross-check, not one replacing the other -- they can and sometimes do disagree (see below), which is itself useful information, not a bug to silently resolve.
4. **Ogma/Copilot Export** — generates a ROS2 Copilot runtime-verification monitor package via Ogma, one property per accepted sub-formula.

### Which LTL form each stage uses

FRET exports every requirement in both a **past-time** form (`H`/`O`/`S`/`Y`, what the FRET/Ogma ecosystem calls pmLTL) and a **future-time** form (`G`/`F`/`X`/`U`). This pipeline doesn't pick just one -- each external tool gets whichever form it actually understands, confirmed empirically against the installed binaries, not assumed. It turns out **only nuXmv supports past-time operators** -- Spot and SPIN both only parse future-time LTL (`H`/`O` fail to parse on Spot; SPIN doesn't have the concept at all):

- **nuXmv** validates the **pt** form -- the same form that ultimately ships to Ogma.
- **Spot** and **SPIN** both validate the **ft** form instead. Rather than implementing general past→future LTL translation (an open research problem -- see `docs/pipeline-design-research.md`), the LLM decomposition step is asked to produce both forms for each sub-formula directly, the same way FRET itself carries both forms per requirement.
- **Strix** (stage 3, realizability) also only parses future-time LTL -- `strix -f "H (x -> y)"` fails with a parser error (`no viable alternative at input 'H'`). So Strix's half of stage 3 is built from the **ft** forms, not pt.
- **Kind2** (stage 3, realizability) is the other way round: it has no built-in past-time operator at all (`H` is an undefined identifier to it, confirmed against the real binary -- it's plain Lustre, not FRET's older CoCoSpec dialect, despite FRET's own `CoCoSpecCode` export field suggesting otherwise). Rather than a general LTL-to-Lustre compiler, `kind2_check.py` hand-compiles the specific `H (...)` shape FRET always produces into a Lustre ghost variable recurring on `pre` (`h = BODY and (true -> pre h)`), so Kind2's half of stage 3 is built from the **pt** forms.
- **Ogma** (stage 4) is given the **pt** forms, per Ogma/Copilot's own expectations (see the nested-operator note below).

SPIN also needs its own operator spelling translated: `spin -f` uses symbolic `[]`/`<>` for always/eventually rather than the keywords `G`/`F` that every other tool here and FRET's export both use (`X`/`U`/`R`/`V`/`!`/`&`/`|`/`->`/`<->` all already match). `equivalence_check.py`'s `_to_spin_syntax()` does this translation before every `spin -f` call -- confirmed against the real binary.

## Importing a FRET file

Export a project from FRET (Menu → Export → "Export Requirements and Variables as JSON", or equivalent) to get a JSON file shaped like:

```json
{"requirements": [{"reqid": "...", "fulltext": "...", "semantics": {"pt": "...", "ptExpanded": "...", "ft": "...", "ftExpanded": "...", "ftInfAUExpanded": "...", "variables": ["..."]}}],
 "variables": [{"variable_name": "...", "dataType": "boolean|integer|...", "idType": "Input|Output|Internal", "assignment": "...", "copilotAssignment": "..."}]}
```

`core/fret_import.py` reads `ptExpanded`/`pt` for the past-time form, and prefers `ftInfAUExpanded` over `ftExpanded`/`ft` for the future-time form -- `ft`/`ftExpanded` encode FRET's finite-trace semantics via a special `LAST` atomic proposition (e.g. `"LAST V (...)"`) that Spot/SPIN don't know about, while `ftInfAUExpanded` is the same obligation in plain infinite-trace future LTL. This was confirmed against a real FRET export, not assumed -- see a worked example under `tests/fixtures/sRobotFRETfile.json`.

`Internal`-role variables (derived propositions, e.g. `dgt_3 := distance_to_target > 3`) carry two expressions: `assignment` (plain/Lustre-ish syntax, used as a nuXmv `DEFINE` during equivalence checking) and `copilotAssignment` (Copilot syntax, embedded into the generated monitor by Ogma) -- these are genuinely different syntaxes for the same thing, not redundant fields.

### Saving a split as a new file

Accepting (or forcing) a split on stage 1 prompts for a filename and writes a **new** FRET-shaped JSON file next to the one that was imported, under an `ltlsplitter_exports/` subdirectory -- the original file is read but never modified. The new file is the original's full content with the split's sub-formulas appended to `"requirements"`, each carrying `"parent_reqid"` set to the original requirement's id -- this is FRET's own existing convention for marking a requirement as a sub-part of another (seen in real FRET realizability exports, e.g. this machine's own `~/Desktop/M30-RB_RV_FrameWork/fret/FRETex/.../sRobotNoChildRealizability.json`), reused here rather than inventing a new field. `core/fret_import.py`'s `append_sub_formulas_and_save()` does the read-append-write; the requirement tree on stage 1 groups by `parent_reqid` so a split's sub-formulas show up nested under the original as an expandable item. The newly-saved copy becomes the active file for the rest of the session (and the base for the next split, so repeated splits accumulate in one file rather than each only ever branching off the original).

## Typed/arithmetic FRET variables and the boolean-only LTL tools (stages 2 and 3)

**nuXmv and Kind2 are the only two tools in this pipeline with native typed/arithmetic variables** -- nuXmv has real `VAR`/`DEFINE` declarations with actual integer/enum domains, and Kind2's Lustre has real `int`/`real` stream types. Strix, Spot, and SPIN's LTL grammars, by contrast, are all fundamentally **propositional**: an atomic proposition is just an opaque boolean label to them, not a typed comparison with its own semantics. Confirmed directly against all three installed binaries, each fails differently on a bare `classifier = 1`:

- `strix -f "G ((classifier = 1) -> x)"` → `no viable alternative at input '((classifier='`
- `ltlfilt -f "G(distance_to_target > 3)"` → `syntax error, unexpected invalid token`
- `spin -f "!(distance_to_target > 3)"` → actually **parses fine** -- SPIN's own LTL parser accepts an arbitrary expression as a literal atomic proposition, unlike Strix/Spot. The real bug was downstream, in this project's own Promela model generator (see below), not SPIN's parser.

Since every one of these three tools genuinely only reasons about opaque boolean propositions, `core/typed_atoms.py`'s `extract_typed_comparisons()` finds every `variable OP literal` comparison in a formula (e.g. `"classifier = 1"`) against the set of non-boolean variable names, and each tool integration turns that comparison into something its own grammar accepts as one single, consistent, opaque proposition -- **not** three copies of the same fix, since each tool needed a different mechanism:

- **Spot** accepts a double-quoted string as a native opaque atomic proposition (confirmed against the real binary), so `_check_tautology_spot` just quotes each comparison in place: `"classifier = 1"` — no renaming needed, and identical text is automatically the identical proposition everywhere it recurs.
- **Strix** has no equivalent -- it crashes outright (`IllegalArgumentException`) on a quoted atomic proposition, confirmed empirically -- so `check_realizability_typed` in `core/realizability.py` instead substitutes a fresh, descriptive, valid identifier (`_classifier_eq_1`) in place of each comparison, and classifies that fresh name into Strix's required `--ins`/`--outs` lists based on the source variable's own Input/Output role (an `Internal`-role variable, or one derived from a comparison on one, defaults to the input side -- a documented simplification, correct for every `Internal` variable in this project's real FRET data so far, since each is derived purely from an Input).
- **SPIN** needed no formula-text change at all (its parser already accepts the raw comparison) -- the actual bug was that this project's own Promela model generator (`_promela_model` in `equivalence_check.py`) declared every free variable as `bool` regardless of its real type, silently collapsing a typed variable's range to true/false. It now declares a Promela `int` ranging nondeterministically over the literal values actually compared against that variable in the formula, plus one sentinel value standing in for "anything else" -- sound without needing to know the variable's true domain, and far smaller than defaulting to an arbitrary wide range.

A formula using something none of this covers (compound arithmetic combining multiple variables, e.g. `distance + 1 > 3`) still can't be made sense of this way; `extract_typed_comparisons` reports any variable still referenced outside a simple comparison as "leftover", and all three integrations report one clear, upfront error for it rather than guessing.

### A real, confirmed SPIN soundness bug this surfaced (not hypothetical)

Fixing the type-domain issue above led directly to a second, more serious bug, reproduced with a real formula from this project's own `tests/fixtures/sRobotFRETfile.json`, not a contrived example: **SPIN's never claim is evaluated against the Promela-compiler's own default initial values** (0 for `int`, `false` for `bool`) **as the very first state** -- and if that one fixed combination doesn't happen to satisfy any of the never claim's initial guards, `pan`'s search gets permanently stuck at depth 0 with zero transitions taken, which it reports as `"errors: 0"`, silently misread by this project as "tautology" -- not because the check passed, but because nothing was ever actually explored. This reproduced even for two entirely unrelated plain boolean propositions (`(G a) <-> (G b)`, wrongly reported equivalent), and no single fixed starting combination is safe for every formula -- a formula built from negated atoms needs the opposite starting point from one built from bare atoms, confirmed by constructing both.

`_check_tautology_spin` now tries two complementary starting-value combinations for every free variable, and only trusts a `"tautology"` verdict from a run that actually explored past the initial state (`depth reached > 0` in `pan`'s own output) -- a found counterexample from *either* run is trusted immediately, since finding one is proof on its own. If every combination tried gets stuck at depth 0, it reports a clear `"error"` rather than ever silently guessing "tautology" again. Separately, `_is_trivial_tautology()` fast-paths the single most common case this project hits -- checking an unsplit formula against an exact textual copy of itself -- without invoking any tool at all, which both sidesteps this ambiguity entirely for that case and is a meaningful performance win (used by all three of nuXmv/Spot/SPIN, not just SPIN).

Two smaller SPIN syntax issues were found and fixed alongside this: `spin -f` needs `&&`/`||`, not the single `&`/`|` this project's formulas otherwise use everywhere else (a bare `!(x & y)` happening to parse was misleading -- it isn't reliable once combined with a temporal operator like `[]`/`<>` immediately to its left); and Promela's `=` is assignment, not equality, a syntax error inside a compound boolean guard expression (only `==` is valid there) -- `_check_tautology_spin` rewrites just the known comparisons to `==` in the generated never-claim text specifically, leaving this project's own model-generation code (where `=` is a genuine assignment) untouched.

## Ogma's known limitation (stage 4)

Ogma's LTL parser (as installed, `ogma-cli` 1.15.0) accepts a single temporal operator wrapping an otherwise-propositional formula (`G (x)`, `H (x -> y)`) but not formulas with *nested* temporal operators — `G (x -> F y)`, one of the most common LTL patterns — which fails with a misleadingly worded `cannot open input specification file` error. `ogma.py` detects that specific message and appends a clarifying note rather than leaving it cryptic, but there's no code-level workaround — it's a real limitation of the tool as installed.

## Installing nuXmv and Strix (stages 2 and 3)

Neither ships as a distro package, so they're installed as standalone binaries rather than via `pip`/`apt`. `check_realizability` (`src/ltlsplitter/core/realizability.py`) and the nuXmv half of `validate_decomposition` (`src/ltlsplitter/core/equivalence_check.py`) look for them, in order: an `NUXMV_PATH`/`STRIX_PATH` env var pointing at the binary, then `PATH`, then `~/.local/bin/nuXmv` / `~/.local/bin/strix`. The convention below (symlinking into `~/.local/bin`) satisfies the last of those with no env var or PATH change needed.

```bash
# nuXmv (non-commercial/academic license) -- verify the sha256sum published alongside
# the download at https://nuxmv.fbk.eu/download.html before trusting the archive.
curl -LO https://nuxmv.fbk.eu/downloads/2.2.0/nuXmv-2.2.0-linux64.tar.xz
mkdir -p ~/.local/share/ltlsplitter-tools
tar -xf nuXmv-2.2.0-linux64.tar.xz -C ~/.local/share/ltlsplitter-tools
mkdir -p ~/.local/bin
ln -sf ~/.local/share/ltlsplitter-tools/nuXmv-2.2.0-linux64/usr/local/bin/nuXmv ~/.local/bin/nuXmv

# Strix (github.com/meyerphi/strix releases) -- verify against that release's sha256sums.txt.
curl -LO https://github.com/meyerphi/strix/releases/download/21.0.0/strix-21.0.0-1-x86_64-linux.tar.gz
tar -xf strix-21.0.0-1-x86_64-linux.tar.gz -C ~/.local/share/ltlsplitter-tools
ln -sf ~/.local/share/ltlsplitter-tools/strix ~/.local/bin/strix
```

**nuXmv's bundled `libxml2.so.2` needs help being found.** Its Linux binary depends on `libxml2.so.2`/`libicuuc.so.70`/`libicudata.so.70` at an old SONAME most current distros no longer ship — but the archive bundles its own copies under `usr/local/lib/x86_64-linux-gnu/`. Don't use nuXmv's own `bin/nuXmv.sh` wrapper to fix this: it points `LD_LIBRARY_PATH` at that *entire* bundled `lib/` directory, which also contains an old `libc.so.6` that will shadow the system one and break every subprocess nuXmv spawns (`realizability.py` hit this directly — nuXmv's own `-source` scripting broke with `GLIBC_2.38 not found` from the `/bin/sh` it invokes internally). Instead, symlink just the three needed libraries into their own directory and point `LD_LIBRARY_PATH` at *that*:

```bash
SHIM=~/.local/share/ltlsplitter-tools/nuxmv-libshim
BUNDLED=~/.local/share/ltlsplitter-tools/nuXmv-2.2.0-linux64/usr/local/lib/x86_64-linux-gnu
mkdir -p "$SHIM"
for lib in libxml2.so.2 libicuuc.so.70 libicudata.so.70; do ln -sf "$BUNDLED/$lib" "$SHIM/$lib"; done
```

`realizability.py` already does this automatically at runtime if `~/.local/share/ltlsplitter-tools/nuxmv-libshim` exists, so following the commands above (which create exactly that path) is enough — no extra configuration needed.

## Installing Spot and SPIN (stage 2)

SPIN is a standard Ubuntu/Debian package:

```bash
sudo apt install -y spin
```

This installs the `spin` binary used by the SPIN half of `validate_decomposition`'s equivalence checks (`SPIN_PATH` env var override, same lookup convention as the other tools). It additionally needs a C compiler to build the generated verifier (`pan.c`) -- `gcc` (already required for Ogma, see below) covers it.

**Spot is not packaged for this release** (checked `apt-cache search` under every plausible name on Ubuntu "resolute" 26.04 -- not there, confirmed, not a configuration issue). Two options, in order of preference:

1. **The LRE's own OBS-built `.deb` repo** (fastest if it works -- their newest build target at the time of writing is `xUbuntu_25.10`, one release behind; close enough to usually install cleanly, but not guaranteed):
   ```bash
   wget -q -O - 'https://build.opensuse.org/projects/home:adl/signing_keys/download?kind=gpg' | sudo gpg --dearmor -o /etc/apt/keyrings/home-adl-obs.gpg
   echo 'deb [signed-by=/etc/apt/keyrings/home-adl-obs.gpg] https://download.opensuse.org/repositories/home:/adl/xUbuntu_25.10/ ./' | sudo tee /etc/apt/sources.list.d/home-adl-obs.list
   sudo apt-get update && sudo apt-get install -y spot
   ```
2. **Build from source** (what was actually used to verify this integration -- reliable, ~10 minutes, no sudo needed if installed under your home directory):
   ```bash
   wget http://www.lre.epita.fr/dload/spot/spot-2.16.tar.gz
   tar xf spot-2.16.tar.gz && cd spot-2.16
   ./configure --prefix="$HOME/.local" --disable-python --disable-static
   make -j"$(nproc)"
   make install   # no sudo -- installs under ~/.local, already on PATH by convention here
   ```
   `--disable-python` skips Spot's Python bindings (not needed -- this project only shells out to the `ltlfilt` CLI) and avoids a `python3-dev` dependency.

`SPOT_LTLFILT_PATH` env var override, same lookup convention as the other tools. The Spot integration (`_check_tautology_spot` in `src/ltlsplitter/core/equivalence_check.py`) has been verified against a real build: `--equivalent-to` takes an inline `FORMULA` directly (not a filename, despite that being the convention for most of Spot's other formula-reference options), and a formula is a tautology iff `ltlfilt --equivalent-to=1 -f FORMULA -q` exits 0.

## Installing Kind2 (stage 3)

Not a distro package -- download the prebuilt binary from GitHub releases and drop it in `~/.local/bin` (no sudo, same convention as the other tools; it's statically linked, no further dependencies):

```bash
wget https://github.com/kind2-mc/kind2/releases/download/v3.0.0/kind2-v3.0.0-linux-x86_64.tar.gz
tar xf kind2-v3.0.0-linux-x86_64.tar.gz
mkdir -p ~/.local/bin
mv kind2 ~/.local/bin/kind2
```

`KIND2_PATH` env var override, same lookup convention as the other tools. `core/kind2_check.py` checks realizability via Kind2's **contract realizability** analysis (`kind2 -json --enable CONTRACTCK <file>`) -- the same mechanism FRET's own built-in realizability checker already uses (confirmed against this machine's own `~/Desktop/M30-RB_RV_FrameWork/fret/FRETex/sRobotNoChildClass_OP/sRobotNoChildRealizability.json`, which records `"solver": "kind2"`), so this isn't an arbitrary tool choice -- it's the same backend FRET's own ecosystem already trusts for this exact question, just invoked directly on the requirement(s) involved in a given split rather than FRET's whole-project analysis.

A few things confirmed empirically while building this integration, not assumed:
- Kind2 only accepts **Lustre** as input, not a raw LTL formula on the command line (unlike every other tool here) -- `kind2_check.py` generates a minimal Lustre file per check: an `imported` node (no body, matching the "does some implementation exist" realizability question) whose inputs/outputs mirror the FRET variables' Input/Output roles, with each requirement as a `guarantee` (or `assume`, for one marked as an environment assumption -- see "Assumptions vs. guarantees" below) inside a `(*@contract ... *)` block.
- **Kind2 has no built-in past-time operator.** FRET's own `CoCoSpecCode` export field (e.g. `H(((classifier = 1) => ...))`) suggests one should exist, but that's a syntax from CoCoSpec, an older/separate FRET-adjacent dialect -- plain `H` is an undefined identifier to Kind2 v3.0.0. Since FRET's pt formulas always take the shape `(H (...))` -- a single H wrapping an otherwise-propositional body (the same shape Ogma's own parser requires) -- `_strip_top_level_h` extracts that body and `_build_lustre_contract` compiles `H (body)` by hand into a Lustre ghost variable recurring on `pre`: `var h: bool = (body) and (true -> pre h);`. Nested or multiple top-level H's per formula aren't supported; such formulas are reported as skipped rather than mistranslated.
- **Lustre's `->` is not LTL implication** -- it's the temporal "followed by"/init operator. Translating our formulas' `->` (implication) to Lustre's `=>` (also implication) rather than leaving it as `->` is essential and easy to get backwards; `<->` must be translated before `->` since it contains `->` as a substring, or it gets corrupted into something else entirely. `_translate_propositional` handles the ordering.
- Kind2's `-json` output is a flat, time-ordered event stream, not nested -- a `"realizabilityCheck"` event's context (the contract realizability verdict we want, vs. a separate "is the environment/assumptions satisfiable" check Kind2 always also runs) has to be tracked positionally against the preceding `"analysisStart"` event, not read off the object itself.
- Exit codes follow Kind2's own documented convention (0 = realizable, 40 = unrealizable, 30 = undetermined) -- `check_realizability_kind2` parses the JSON regardless of exit code rather than branching on it first, which is simpler and doesn't need to special-case three different "successful run" exit codes.

### Assumptions vs. guarantees

FRET's export has no structural field distinguishing an environment assumption (a constraint the
system benefits from but doesn't have to enforce itself) from a system guarantee -- only a naming
convention seen in real exports (e.g. `classifier_assumption`, `dtt_assumption` in the sRobot
fixture). Early on, stage 3 ANDed every requirement in as a guarantee uniformly, which produced a
real, confirmed false-"unrealizable" result from Kind2: guaranteeing something like "classifier is
in {0,1,2}" is unrealizable by construction once `classifier` is an input the system doesn't
control -- not a genuine synthesis failure, just a modeling artifact of not having assume/guarantee
as a choice. Fixed by giving `FretRequirement` an `is_assumption` flag (seeded by the naming
heuristic above, correctable via a checkbox on stage 1) that both tools now honor: Strix checks
`(assumptions) -> (guarantees)` instead of flat conjunction (the standard LTL assume-guarantee
encoding), and Kind2 gets the assumption formulas as `assume` contract items instead of
`guarantee`. Confirmed against the sRobot fixture: Kind2 flips from unrealizable to realizable
once `classifier_assumption`/`dtt_assumption` are marked as assumptions.

Strix still reports `UNREALIZABLE` on that same fixture even after this fix (confirmed this isn't
a regression -- it reported the same under the old flat-conjunction encoding too), and this one
*was* investigated further: it traces back to the typed-comparison abstraction from "Typed/
arithmetic FRET variables" below. That abstraction gives Strix something parseable, but it's
lossy -- it drops real relationships the original int/enum-typed comparisons had, like mutual
exclusivity between `classifier = 0`/`= 1`/`= 2`, or a derived variable's correlation with the
real variable it comes from (`dgt_7`/`dgt_3`, both derived from `distance_to_target`, are
abstracted into two *independent* fresh booleans with no link between them, even though
`distance_to_target > 7` implies `distance_to_target > 3`). Confirmed by hand -- splicing either
of those constraints back into the abstracted formula as extra conjuncts can flip a real
`UNREALIZABLE` verdict to `REALIZABLE` on this exact fixture. Neither one, nor a one-at-a-time
removal of each of the 11 guarantees, fully explains the sRobot fixture's `UNREALIZABLE` result on
its own, so the precise combination responsible there remains unresolved -- but the general
mechanism is real and demonstrated, not speculative.

This only ever hands the *environment* side (input-bucketed propositions) combinations it
wouldn't really have, which gives it strictly more power than the real adversary -- so a
`REALIZABLE` verdict from Strix stays sound (a strategy that wins against a harder,
over-approximated environment also wins against the real one), but `UNREALIZABLE` is not reliable
whenever the formula involves typed comparisons: it may just be an artifact of this missing
correlation, not a genuine synthesis failure. `check_realizability_typed` now appends a caveat to
any `UNREALIZABLE` result that went through this abstraction, saying exactly that. Kind2 has no
equivalent gap here, since it models these variables with their real int/enum types natively
rather than abstracting them into fresh booleans -- which is why, for formulas like this, a
Kind2 `REALIZABLE` carries more weight than a Strix `UNREALIZABLE` disagreeing with it.

## Installing Ogma (stage 4)

Ogma is a Haskell package published on Hackage, built via `cabal`. This is the heaviest install in the pipeline — expect a long build.

```bash
sudo apt install -y ghc cabal-install z3 libz3-dev zlib1g-dev libbz2-dev libexpat1-dev g++
cabal update
cabal install --lib copilot copilot-core copilot-c99 copilot-language \
    copilot-theorem copilot-libraries copilot-interpreter copilot-prettyprinter
cabal install ogma-cli:ogma
```

`cabal install` symlinks the built binary to `~/.local/bin/ogma` automatically — no manual symlinking needed (`ogma.py` looks it up the same way as nuXmv/Strix: `OGMA_PATH` env var, then `PATH`, then `~/.local/bin/ogma`). Verify with `ogma --help`.

`g++` specifically is easy to miss: the `digest` package (a transitive dependency of `ogma-cli`) needs a C++ compiler to build, and its failure mode (`ghc-9.10.3: C++ Compiler: could not execute: x86_64-linux-gnu-g++`) doesn't obviously point at a missing package.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows (GUI dev only, see note below)
pip install -e ".[dev]"
```

Note: the GUI itself (PySide6) is cross-platform and can be developed on any OS, but `core/ogma.py`, `core/realizability.py`, `core/equivalence_check.py`, and `core/kind2_check.py` shell out to Linux-native CLI tools (Ogma, nuXmv, Strix, Spot, SPIN, Kind2) — those pieces only run on Linux.

## Running

```bash
ltlsplitter
# or
python -m ltlsplitter.app
```

## Testing

```bash
pytest
```

## Building a standalone Linux executable

```bash
pip install -e ".[build]"
pyinstaller ltlsplitter.spec
```

Produces a single self-contained binary at `dist/ltlsplitter` — no Python interpreter or `.venv` activation needed to run it, since PyInstaller bundles the interpreter and all Python dependencies (PySide6, anthropic, etc.) inside. It does **not** bundle Ogma/nuXmv/Strix/Spot/SPIN/Kind2 — those remain external CLI tools the binary shells out to at runtime, same as when running from source (see the install sections above), so they still need to be installed on whatever machine runs the binary. `ltlsplitter.spec` is checked in for a reproducible build; `dist/` and `build/` (PyInstaller's output directories) are gitignored since the binary is a large, platform-specific build artifact, not source.
