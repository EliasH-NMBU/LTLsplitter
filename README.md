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

The GUI wizard (one page per stage) is fully wired up and navigable, and **all six stages are fully functional**, verified end-to-end against a real (simulated) ROS2 system: a TurtleBot3 patrolling a Gazebo world, detecting a humanoid stand-in via its camera, safety-stopping in response, and an Ogma-generated LTL monitor confirming the safety property live against the running system with zero violations. See "The demo ROS2 system" below.

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

## Installing ROS2 + the demo system (stage 6)

This machine's Ubuntu 26.04 pairs with **ROS2 "Lyrical"** in the official ROS2 apt repo. This is the heaviest install in the whole pipeline (ROS2 desktop + Gazebo + vision packages — several GB).

```bash
curl -LO https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.2.0/ros2-apt-source_1.2.0.resolute_all.deb
sudo apt install -y ./ros2-apt-source_1.2.0.resolute_all.deb
sudo apt update
sudo apt install -y ros-lyrical-desktop ros-dev-tools python3-colcon-common-extensions \
    python3-rosdep ros-lyrical-ros-gz-sim ros-lyrical-ros-gz-bridge ros-lyrical-ros-gz-image \
    ros-lyrical-nav2-minimal-tb3-sim ros-lyrical-cv-bridge ros-lyrical-vision-opencv python3-opencv
```

**This ROS2 release doesn't ship classic Nav2** (`navigation2`/`nav2-bringup` aren't in the repo) — it's been replaced by a new framework called EasyNav (`ros-lyrical-easynav*`). The demo system (`~/ltl_demo_ws/src/ltl_demo`, not checked into this repo) doesn't depend on either: it drives the robot with a small reactive LIDAR-based wander/obstacle-avoidance controller instead of a full planning stack.

**The "human" the camera detects** is a plain colored cylinder+sphere model placed in the world (`worlds/tb3_sandbox_human.sdf`), not a photorealistic mesh or animated actor — `detector.py` finds it via HSV color thresholding on the RGB camera feed, not a pedestrian classifier. The robot's stock camera sensor is depth-only (no RGB `image` topic); a copy of its SDF (`urdf/gz_waffle_rgb.sdf.xacro`) adds a real RGB camera sensor alongside it.

**Two environment-specific issues to know about, both already worked around in `launch/demo.launch.py`:**
- If this whole app (or `ros2 launch` directly) runs from inside a snap-confined shell — e.g. a VSCode integrated terminal, since VSCode itself ships as a snap — Gazebo's GUI crashes immediately with `symbol lookup error: ... undefined symbol: __libc_pthread_init, version GLIBC_PRIVATE`. The launch file unsets the relevant snap/GTK env vars for the whole launch; none of them matter to Gazebo or any ROS node here.
- The robot's visual meshes need `ROS_PACKAGE_PATH` set to resolve their `package://` URIs, or it spawns and works fully (physics/sensors/topics all fine) but renders with missing geometry in the GUI — cosmetic only, also handled in the launch file.

**`rclpy` lives in ROS2's own Python, not this app's `.venv`.** A plain `python -m venv` can't see it, so `core/ros_monitor.py`'s `MonitorDeployment` never imports `rclpy` in-process — it shells out to a small watcher script via `source <ROS setup> && python3 watcher.py`, the same "external tool" pattern used for nuXmv/Strix/Ogma, reading its stdout for violation reports.

**Ogma's generated `CMakeLists.txt` doesn't build on this ROS2 release** — it calls `ament_target_dependencies()`, which has been fully removed here in favor of `target_link_libraries()` with imported targets (`Unknown CMake command "ament_target_dependencies"` otherwise). `ogma.py`'s `generate_ros2_monitor()` patches every generated package's CMakeLists.txt automatically; you don't need to do anything.

**A genuine LTL semantics finding, not a bug:** the wander controller originally only re-published `/stopped` on its periodic control timer, independent of when `/human_detected` changed. That left a brief window where detection had fired but the stop hadn't been republished yet — and because the demo requirement uses `H` (historically), a single violation at any point makes the property false forever after (the past can't be undone), so the monitor reported continuous violations from that first transient onward. The fix (`wander.py`'s `_on_human_detected` now re-evaluates the control output immediately, not just on the next timer tick) isn't a hack around the monitor — it's a real latency bug the monitor correctly caught.

`ROS_SETUP_BASH` (default `/opt/ros/lyrical/setup.bash`) and `LTL_DEMO_WS_SETUP_BASH` (default `~/ltl_demo_ws/install/setup.bash`) are configurable via env var if your paths differ — same convention as `NUXMV_PATH`/`STRIX_PATH`/`OGMA_PATH` above.

**The demo's source lives in this repo under [`ros2_demo/`](ros2_demo/)** — `ltl_demo/` (the ROS2 package: detector, wander controller, launch file, world/robot SDF) and `ltl_monitor_gen/` (the Ogma-generated monitor package for this demo's requirement, `H (human_detected -> stopped)`, checked in as a working example). It needs to be built into a colcon workspace before "Launch Simulation" / "Start Monitoring" will find anything:

```bash
mkdir -p ~/ltl_demo_ws/src
cp -r ros2_demo/ltl_demo ~/ltl_demo_ws/src/
source /opt/ros/lyrical/setup.bash
cd ~/ltl_demo_ws && colcon build --packages-select ltl_demo
```

(`ltl_monitor_gen/` doesn't need a manual build step — stage 6's `MonitorDeployment` copies and builds it into its own dedicated workspace automatically.)

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
