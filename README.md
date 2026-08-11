# LTLsplitter

A GUI pipeline for splitting natural-language requirements into formal specs (LTL or behavior trees), checking their consistency/realizability, and deploying live ROS2 runtime monitors generated via NASA's [Ogma](https://github.com/nasa/ogma).

**Platform: Linux only.** See [docs/pipeline-design-research.md](docs/pipeline-design-research.md) for why (Ogma, Strix, and other tools in the pipeline are Linux-native only).

## Pipeline stages

1. **Requirement splitting** — an LLM splits a natural-language requirement into sub-requirements for human review.
2. **Variable declaration** — declare variables (type, range, ROS node).
3. **Spec authoring** — author LTL or behavior-tree specs over the declared variables.
4. **Consistency & realizability check** — verify the requirement set is satisfiable and realizable.
5. **Monitor generation** — generate ROS2 runtime monitors via Ogma.
6. **Deployment & live visualization** — deploy monitors against a live ROS2 system and show violations/state in real time.

The GUI wizard (one page per stage) is fully wired up and navigable. Stages 1–5 are fully functional. Stage 6 is still stubbed pending its external tool integration — that page calls the stub, catches the tool-missing error, and tells you what's needed rather than pretending to work:

- **Stage 6** (`ros_monitor.py`): needs a sourced ROS2 environment (rclpy).

**Stage 5's known limitation:** Ogma's LTL parser (as installed, `ogma-cli` 1.15.0) accepts a single temporal operator wrapping an otherwise-propositional formula (`G (x)`, `H (x -> y)`) but not formulas with *nested* temporal operators — `G (x -> F y)`, one of the most common LTL patterns and exactly what stage 3 typically produces, fails with a misleadingly worded `cannot open input specification file` error. `ogma.py` detects that specific message and appends a clarifying note rather than leaving it cryptic, but there's no code-level workaround — it's a real limitation of the tool as installed, matching the project's own design doc, which flags the future-LTL → past-time-monitorable translation (`FRETish → pmLTL`) as an unsolved problem, not something this wiring papers over.

## Installing nuXmv and Strix (stage 4)

Neither ships as a distro package, so they're installed as standalone binaries rather than via `pip`/`apt`. `check_consistency`/`check_realizability` (`src/ltlsplitter/core/realizability.py`) look for them, in order: an `NUXMV_PATH`/`STRIX_PATH` env var pointing at the binary, then `PATH`, then `~/.local/bin/nuXmv` / `~/.local/bin/strix`. The convention below (symlinking into `~/.local/bin`) satisfies the last of those with no env var or PATH change needed.

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

## Installing Ogma (stage 5)

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

Note: the GUI itself (PySide6) is cross-platform and can be developed on any OS, but the `core/ros_monitor.py` module requires a sourced ROS2 environment (rclpy) and the `core/ogma.py` / `core/realizability.py` modules shell out to Linux-native CLI tools (Ogma, nuXmv, Strix) — those pieces only run on Linux.

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
