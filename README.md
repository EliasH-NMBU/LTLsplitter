# LTLsplitter

A GUI pipeline that imports a [NASA FRET](https://github.com/NASA-SW-VnV/fret) project export, uses an LLM to propose and perform a split of an LTL requirement into independent sub-properties, cross-validates that split with three different model checkers, checks realizability against the rest of the system with two independent tools, and exports the result to NASA's [Ogma](https://github.com/nasa/ogma) for ROS2 Copilot runtime-monitor generation.

**Platform: Linux only.** See [docs/pipeline-design-research.md](docs/pipeline-design-research.md) for why (Ogma, Strix, Spot, SPIN, and Kind2 are Linux-native only).

## Pipeline stages

1. **Import & Split Review** — import a FRET project export (`requirements`/`variables` JSON), pick one requirement, and let an LLM suggest whether/how many ways to split its LTL formula. Review and accept or reject the suggestion; if accepted, the LLM performs the split into editable sub-formulas. If the LLM doesn't recommend a split, a "Force split anyway" option appears to ask it for one regardless. Accepting a split prompts for a filename and saves it as a **new copy** of the FRET file, with the sub-formulas appended as requirements nested under the original (shown as a dropdown in the requirement tree) — the original file is never modified, and the new copy becomes the active file for the rest of the session.
2. **Decomposition Validation** — nuXmv, Spot, and SPIN each independently check that the sub-formulas' conjunction is logically equivalent to the original formula, and that no single sub-formula is -- by itself -- already equivalent to the whole original (i.e. it's a genuine split, not a degenerate one). A failure can be sent back to the LLM as feedback for another attempt.
3. **Realizability Check** — checks whether a system strategy exists that satisfies the accepted formula(s) together with every *other* requirement already in the imported FRET file, against adversarial environment input — the "combined back with the entire system" check. Strix (game synthesis) and Kind2 (SMT/k-induction contract analysis) run side by side as a cross-check, not one replacing the other.
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

## Strix/Spot/SPIN's shared known limitation (stages 2 and 3)

**nuXmv and Kind2 are the only two tools in this pipeline that natively understand typed/arithmetic FRET variables** -- nuXmv has real `VAR`/`DEFINE` declarations with actual integer/enum domains, and Kind2's Lustre has real `int`/`real` stream types, neither limited to opaque boolean atoms. Strix and Spot's LTL grammars, by contrast, only accept pure boolean atomic propositions (bare identifiers) at the leaves — not arithmetic/equality expressions over typed variables, e.g. `classifier = 1` or `state = 2`, which is exactly what FRET-imported integer/enum variables produce. Confirmed directly against both installed binaries:

- `strix -f "G ((classifier = 1) -> x)"` → `no viable alternative at input '((classifier='`
- `ltlfilt -f "G(distance_to_target > 3)"` → `syntax error, unexpected invalid token`

**SPIN is the interesting exception**: `spin -f`'s own LTL parser actually *does* accept arithmetic/equality expressions like `distance_to_target > 3` or `state = 0` as a literal atomic proposition (confirmed against the real binary — this contradicted an earlier, unverified assumption in this file that SPIN shared Strix/Spot's restriction; it doesn't). The catch is downstream: this project's Promela model generator (`_promela_model` in `equivalence_check.py`) only ever declares plain `bool` variables for the free/nondeterministic model it builds, so if it were allowed to compile a formula referencing a typed comparison, that variable's real range would be silently collapsed to true/false — which could produce a *wrong* "tautology" verdict (a real soundness bug, not just an inconvenience), not merely a parse error.

Because of that, **both Spot and SPIN check upfront** (`_unsupported_variables` in `equivalence_check.py`, no subprocess call needed) **whether the formula being checked references any non-boolean or `Internal`-role variable, and report a clear error instead of attempting the check** — turning what would otherwise be a cryptic Spot parser dump, or a silently-unsound SPIN pass, into one honest "not supported for this formula" message. (The same check also catches `Internal`-role variables, e.g. `dgt_7`, since neither Spot nor SPIN has nuXmv's `DEFINE`-equivalent to resolve what such a variable actually means — referencing one undeclared would otherwise crash SPIN's `spin -a` compile step outright.) This means that for most real FRET-sourced requirements (which commonly compare an enum/int-typed variable, as the `tests/fixtures/sRobotFRETfile.json` example does throughout), **stage 2's Spot/SPIN checks will report that clear error** rather than a silent wrong answer, leaving nuXmv as the sole working verdict for decomposition validation on those requirements. There's no code-level workaround for that gap yet: it would need a comparison→fresh-boolean-proposition rewrite step (predicate abstraction, or for SPIN specifically, a properly-ranged Promela `int` declaration) applied before calling out to Spot/SPIN, which is real additional scope beyond this pass. Stage 3 (realizability) doesn't have this gap at all, since **Kind2 was added specifically to cover it** -- Strix's result will report the same kind of parse error on a typed formula, but Kind2 checks the same requirement natively and gives a real verdict (see "Installing Kind2" below).

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
- Kind2 only accepts **Lustre** as input, not a raw LTL formula on the command line (unlike every other tool here) -- `kind2_check.py` generates a minimal Lustre file per check: an `imported` node (no body, matching the "does some implementation exist" realizability question) whose inputs/outputs mirror the FRET variables' Input/Output roles, with the requirement(s) as `guarantee`s inside a `(*@contract ... *)` block.
- **Kind2 has no built-in past-time operator.** FRET's own `CoCoSpecCode` export field (e.g. `H(((classifier = 1) => ...))`) suggests one should exist, but that's a syntax from CoCoSpec, an older/separate FRET-adjacent dialect -- plain `H` is an undefined identifier to Kind2 v3.0.0. Since FRET's pt formulas always take the shape `(H (...))` -- a single H wrapping an otherwise-propositional body (the same shape Ogma's own parser requires) -- `_strip_top_level_h` extracts that body and `_build_lustre_contract` compiles `H (body)` by hand into a Lustre ghost variable recurring on `pre`: `var h: bool = (body) and (true -> pre h);`. Nested or multiple top-level H's per formula aren't supported; such formulas are reported as skipped rather than mistranslated.
- **Lustre's `->` is not LTL implication** -- it's the temporal "followed by"/init operator. Translating our formulas' `->` (implication) to Lustre's `=>` (also implication) rather than leaving it as `->` is essential and easy to get backwards; `<->` must be translated before `->` since it contains `->` as a substring, or it gets corrupted into something else entirely. `_translate_propositional` handles the ordering.
- Kind2's `-json` output is a flat, time-ordered event stream, not nested -- a `"realizabilityCheck"` event's context (the contract realizability verdict we want, vs. a separate "is the environment/assumptions satisfiable" check Kind2 always also runs) has to be tracked positionally against the preceding `"analysisStart"` event, not read off the object itself.
- Exit codes follow Kind2's own documented convention (0 = realizable, 40 = unrealizable, 30 = undetermined) -- `check_realizability_kind2` parses the JSON regardless of exit code rather than branching on it first, which is simpler and doesn't need to special-case three different "successful run" exit codes.

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
