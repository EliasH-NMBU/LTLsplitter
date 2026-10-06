# LTLsplitter

A GUI pipeline that imports a [NASA FRET](https://github.com/NASA-SW-VnV/fret) project export, uses an LLM to propose and perform a split of an LTL requirement into independent sub-properties, cross-validates that split with three different model checkers, checks realizability against the rest of the system, and exports the result to NASA's [Ogma](https://github.com/nasa/ogma) for ROS2 Copilot runtime-monitor generation.

**Platform: Linux only.** See [docs/pipeline-design-research.md](docs/pipeline-design-research.md) for why (Ogma, Strix, Spot, and SPIN are Linux-native only).

## Pipeline stages

1. **Import & Split Review** — import a FRET project export (`requirements`/`variables` JSON), pick one requirement, and let an LLM suggest whether/how many ways to split its LTL formula. Review and accept or reject the suggestion; if accepted, the LLM performs the split into editable sub-formulas. If the LLM doesn't recommend a split, a "Force split anyway" option appears to ask it for one regardless.
2. **Decomposition Validation** — nuXmv, Spot, and SPIN each independently check that the sub-formulas' conjunction is logically equivalent to the original formula, and that no single sub-formula is -- by itself -- already equivalent to the whole original (i.e. it's a genuine split, not a degenerate one). A failure can be sent back to the LLM as feedback for another attempt.
3. **Realizability Check** — checks whether a system strategy exists that satisfies the accepted formula(s) together with every *other* requirement already in the imported FRET file, against adversarial environment input — the "combined back with the entire system" check.
4. **Ogma/Copilot Export** — generates a ROS2 Copilot runtime-verification monitor package via Ogma, one property per accepted sub-formula.

### Which LTL form each stage uses

FRET exports every requirement in both a **past-time** form (`H`/`O`/`S`/`Y`, what the FRET/Ogma ecosystem calls pmLTL) and a **future-time** form (`G`/`F`/`X`/`U`). This pipeline doesn't pick just one -- each external tool gets whichever form it actually understands, confirmed empirically against the installed binaries, not assumed. It turns out **only nuXmv supports past-time operators** -- Spot and SPIN both only parse future-time LTL (`H`/`O` fail to parse on Spot; SPIN doesn't have the concept at all):

- **nuXmv** validates the **pt** form -- the same form that ultimately ships to Ogma.
- **Spot** and **SPIN** both validate the **ft** form instead. Rather than implementing general past→future LTL translation (an open research problem -- see `docs/pipeline-design-research.md`), the LLM decomposition step is asked to produce both forms for each sub-formula directly, the same way FRET itself carries both forms per requirement.
- **Strix** (stage 3, realizability) also only parses future-time LTL -- `strix -f "H (x -> y)"` fails with a parser error (`no viable alternative at input 'H'`). So stage 3 is built from the **ft** forms, not pt.
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

## Strix/Spot/SPIN's shared known limitation (stages 2 and 3)

**nuXmv is the only one of the four tools in this pipeline that natively understands typed/arithmetic FRET variables** (it has real `VAR`/`DEFINE` declarations with actual integer/enum domains, not just opaque boolean atoms). Strix and Spot's LTL grammars only accept pure boolean atomic propositions (bare identifiers) at the leaves — not arithmetic/equality expressions over typed variables, e.g. `classifier = 1` or `state = 2`, which is exactly what FRET-imported integer/enum variables produce. Confirmed directly against both installed binaries:

- `strix -f "G ((classifier = 1) -> x)"` → `no viable alternative at input '((classifier='`
- `ltlfilt -f "G(distance_to_target > 3)"` → `syntax error, unexpected invalid token`

**SPIN is the interesting exception**: `spin -f`'s own LTL parser actually *does* accept arithmetic/equality expressions like `distance_to_target > 3` or `state = 0` as a literal atomic proposition (confirmed against the real binary — this contradicted an earlier, unverified assumption in this file that SPIN shared Strix/Spot's restriction; it doesn't). The catch is downstream: this project's Promela model generator (`_promela_model` in `equivalence_check.py`) only ever declares plain `bool` variables for the free/nondeterministic model it builds, so if it were allowed to compile a formula referencing a typed comparison, that variable's real range would be silently collapsed to true/false — which could produce a *wrong* "tautology" verdict (a real soundness bug, not just an inconvenience), not merely a parse error.

Because of that, **both Spot and SPIN check upfront** (`_unsupported_variables` in `equivalence_check.py`, no subprocess call needed) **whether the formula being checked references any non-boolean or `Internal`-role variable, and report a clear error instead of attempting the check** — turning what would otherwise be a cryptic Spot parser dump, or a silently-unsound SPIN pass, into one honest "not supported for this formula" message. (The same check also catches `Internal`-role variables, e.g. `dgt_7`, since neither Spot nor SPIN has nuXmv's `DEFINE`-equivalent to resolve what such a variable actually means — referencing one undeclared would otherwise crash SPIN's `spin -a` compile step outright.) This means that for most real FRET-sourced requirements (which commonly compare an enum/int-typed variable, as the `tests/fixtures/sRobotFRETfile.json` example does throughout), **stage 2's Spot/SPIN checks and stage 3's Strix check will report that clear error** rather than a silent wrong answer, leaving nuXmv as the sole working verdict for those requirements. There's no code-level workaround for the underlying gap yet: that would need a comparison→fresh-boolean-proposition rewrite step (predicate abstraction, or for SPIN specifically, a properly-ranged Promela `int` declaration) applied before calling out to these tools, which is real additional scope beyond this pass.

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

Note: the GUI itself (PySide6) is cross-platform and can be developed on any OS, but `core/ogma.py`, `core/realizability.py`, and `core/equivalence_check.py` shell out to Linux-native CLI tools (Ogma, nuXmv, Strix, Spot, SPIN) — those pieces only run on Linux.

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

Produces a single self-contained binary at `dist/ltlsplitter` — no Python interpreter or `.venv` activation needed to run it, since PyInstaller bundles the interpreter and all Python dependencies (PySide6, anthropic, etc.) inside. It does **not** bundle Ogma/nuXmv/Strix/Spot/SPIN — those remain external CLI tools the binary shells out to at runtime, same as when running from source (see the install sections above), so they still need to be installed on whatever machine runs the binary. `ltlsplitter.spec` is checked in for a reproducible build; `dist/` and `build/` (PyInstaller's output directories) are gitignored since the binary is a large, platform-specific build artifact, not source.
