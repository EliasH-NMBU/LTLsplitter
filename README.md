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

The current codebase is a scaffold: the GUI wizard (one page per stage) is wired up and navigable, but the stage 1/4/5/6 core logic (`src/ltlsplitter/core/`) is stubbed pending the tool integrations described in the design doc.

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
