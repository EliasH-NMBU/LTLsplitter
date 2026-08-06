# LTLsplitter — Pipeline Design Research

Status: pre-implementation. This document captures technical research to ground the architecture before any code is written. Last updated 2026-08-06.

## 1. The pipeline (target)

1. **LLM requirement splitting**: LLM splits a natural-language requirement into sub-requirements (r1.1 ∧ r1.2 ⇒ R1), keeping the original alongside the split for traceability.
2. **Variable declaration**: user declares variables (type, range, associated ROS node).
3. **Spec authoring**: from declared variables, author a state-space/behavior-tree or LTL requirement set.
4. **Consistency / realizability check**: verify requirements can coexist (satisfiability) and the spec is not non-deterministic (realizability).
5. **Monitor generation**: feed the tree/LTL to NASA's Ogma to generate ROS2 runtime monitors.
6. **Deployment & live visualization**: deploy monitors from the app; show live node activity, violations, and current state-space position against the running ROS2 system.

## 2. Platform scope: Linux only (decided 2026-08-06)

Originally scoped as Windows + Linux, but nearly every serious tool in this pipeline is Linux/macOS-native only:

| Tool | Purpose | Windows support |
|---|---|---|
| **Ogma** (nasa/ogma) | Stage 5 monitor generation | None documented. Needs GHC + Cabal + Z3 (Haskell toolchain). |
| **Strix** | GR(1) realizability synthesis | Linux/macOS build only (GraalVM native-image). |
| **Spot / ltlsynt** | LTL sat-checking / synthesis | Linux/macOS only (conda-forge covers those two). |
| **Slugs** | GR(1) synthesis + spec debugger | Linux/macOS, Boost required. |
| **nuXmv / NuSMV** | LTL satisfiability (BMC) | Native Windows, Linux, macOS binaries — was the only cross-platform option. |
| **Spectra** | GR(1) DSL + realizability | Eclipse/Java — JVM-portable but heavy. |

Given this, and that ROS2 itself is primarily developed for Linux, the decision is to **target Linux only**. This removes the need for a WSL2/container backend split entirely: the GUI, rclpy, Ogma, and the realizability tools can all run as native processes on the same machine, invoked directly via subprocess. Packaging becomes a single-OS concern (e.g. PyInstaller/Nuitka producing a Linux binary, or an AppImage), and there's no cross-platform IPC boundary to design around.

## 3. Prior art — study this directly before designing from scratch

**NASA's FRET → Ogma → ROS2 pipeline is essentially a working prototype of this entire project.**

- **FRET** (github.com/NASA-SW-VnV/fret): GUI tool for eliciting requirements in structured English ("FRETish"), which it formalizes to past-time LTL and checks with NuSMV/Kind2. This is directly relevant to stages 1–3.
- **Ogma** (github.com/nasa/ogma): Haskell CLI, Apache 2.0, actively maintained (releases every 1–3 months). Wraps **Copilot** (a stream DSL compiling to hard-real-time C99). Takes FRET/Copilot/Lustre/SMV specs (not raw LTL text directly — the practical path is FRETish → pmLTL → Ogma). Has a documented `ogma ros` subcommand that generates a self-contained ROS2 package: a node that subscribes to the topics its input variables need, re-evaluates monitors on new data, and publishes violations to separate topics. Example templates: `ogma-cli/examples/ros-copilot/`.
- **Paper**: "Monitoring ROS2: from Requirements to Autonomous Robots" (Dutle et al., [arXiv:2209.14030](https://arxiv.org/abs/2209.14030)) — documents this exact end-to-end FRET→LTL→Copilot→ROS2-monitor workflow, treating the generated monitor as a pluggable "black box" node. **Read this paper first.**
- **ROSMonitoring** (github.com/autonomy-and-verification-uol/ROSMonitoring, Liverpool) — an alternative runtime-verification framework generating message-passing monitors for ROS1/ROS2, with its own dashboard. Worth a comparison pass against Ogma.
- **SpeAR v2.0** (loonwerks.com, NASA/Loonwerks) — closest prior art for stage 4 specifically: a Past-LTL requirements DSL with a "Logical Consistency Checker" for a *set* of requirements (satisfiability/vacuity against a state model) — directly matches the r1.1 ∧ r1.2 ⇒ R1 conjunction-checking need.
- **Bendík (ISSTA 2017)**, "Consistency Checking in Requirements Analysis" — algorithm for enumerating Minimal Inconsistent Subsets (MISes), i.e. when the consistency check fails, this pinpoints *which* requirements conflict rather than just reporting "inconsistent." Worth adopting for good UX in stage 4.

**LTLsplitter's likely value-add over existing tools**: Ogma and FRET are GUI-thin or CLI-only and don't do live ROS2 monitor deployment + visualization in one integrated app. That integration (stages 2, 4, 6 wrapped around the FRET/Ogma core) is the actual novel surface area here.

## 4. Stage-by-stage findings

### Stage 1 — LLM requirement splitting
Recognized, active research area, not a novel technique:
- **NL2TL** (MIT, ACL 2023, [arXiv:2305.07766](https://arxiv.org/abs/2305.07766)): T5 fine-tuned with a "lifting" trick (abstract atomic propositions, translate, re-ground) — >95% accuracy.
- **Lang2LTL** (Brown, [arXiv:2302.11649](https://arxiv.org/pdf/2302.11649)): NER → grounding to a *fixed symbol set* via embedding similarity → lifted LTL translation, 93.5% accuracy, open code. Directly applicable to grounding LLM output in our declared-variable vocabulary (stage 2 output).
- **Hierarchical Semantics Decomposition** (2025, [arXiv:2512.17334](https://arxiv.org/pdf/2512.17334)): decomposes compound requirements into sub-requirements before translating each to LTL and composing — essentially the r1.1/r1.2 ⇒ R1 pattern already in the pipeline spec.
- **nl2spec** ([Springer](https://link.springer.com/chapter/10.1007/978-3-031-37703-7_18)): interactive human-in-the-loop tool mapping LTL sub-formulas back to NL fragments so a human can catch mistranslations. **Recommend this pattern for stage 1's UI** — show the user the LLM's split and let them correct it before it's locked in, since a known failure mode is the LLM hallucinating logical structure (AND/OR/temporal ordering) not actually present in the source text.
- Constrained generation to enforce "only reference declared variables": grammar-constrained decoding, or the newer **Decode-Time Grammars** ([arXiv:2607.18357](https://arxiv.org/abs/2607.18357)) with proven "No-Ghost" soundness against undefined symbols.
- **Safety caution** (consistent across sources): never trust single-shot LLM output for a spec that will drive a live robot monitor. Pair with the stage 4 formal check, and prefer a human-in-the-loop review step, not full automation.

### Stage 2 — Variable declaration
No dedicated tooling gap — this is a straightforward form-based GUI screen. Its output (typed variable + range + ROS node) is what stage 1's grounding step and stage 3's authoring step both constrain against.

### Stage 3 — Spec authoring (LTL or behavior tree)
- For LTL: FRETish (FRET's structured-English format) is a strong candidate input format since it's exactly what feeds Ogma via FRET's pmLTL translation — reusing it avoids inventing a new spec language.
- For behavior trees: **BTGenBot/BTGenBot-2** ([arXiv:2602.01870](https://arxiv.org/html/2602.01870v1)) and **LLM-as-BT-Planner** ([arXiv:2409.10444](https://arxiv.org/abs/2409.10444)) show LLM-assisted BT generation with XML output and validator-based error recovery — relevant if stage 1's LLM is also used to help draft the BT/LTL, not just split the requirement.

### Stage 4 — Consistency / realizability check
Two genuinely different checks, worth keeping conceptually separate in the UI:
- **Consistency (satisfiability)**: "can all requirements hold simultaneously" — use **nuXmv** (`check_ltlspec_sat`), the cross-platform-friendly option. Report Minimal Inconsistent Subsets (Bendík's method) when it fails, not just pass/fail.
- **Realizability**: "does a reactive strategy exist against an adversarial environment" — a strictly harder, two-player-game question (2EXPTIME in general LTL; polynomial for the GR(1) fragment). Use **Strix** or Spot's **ltlsynt** for GR(1)-style specs; both are Linux/macOS-only, reinforcing the WSL2/backend decision in §2.
- **Behavior trees**: no mature equivalent tooling exists. Options: transpile to nuXmv via **BehaVerify** ([github.com/verivital/behaverify](https://github.com/verivital/behaverify)), or implement our own structural check (no overlapping activation conditions across Selector/Fallback children) — treat as a known gap, not a solved problem.

### Stage 5 — Monitor generation (Ogma)
See §3. Key integration facts:
- Input path: FRETish → pmLTL → Ogma (not raw LTL text as first-class CLI input).
- Output: full ROS2 package (C99 monitor via Copilot, subscribes to input topics, publishes violations).
- Must run where GHC/Cabal/Z3 are available — Linux or WSL2, not bare Windows.

### Stage 6 — Deployment & live visualization
- Closest architectural analogs: **rqt** (Qt-plugin host, PyQt5/PySide2, each panel a plugin sharing one Qt app), **PlotJuggler** (C++/Qt, keeps ROS-specific code in separate plugin repos — decouples core viz from ROS), **Foxglove Studio** (Electron, talks to ROS2 only via a WebSocket bridge, never links rclpy in-process).
- **Recommended GUI stack: PySide6/PyQt6**, specifically *because* rclpy is Python — the GUI can `import rclpy` and hold node objects in-process, unlike a Tauri/Electron frontend which would need a subprocess/IPC or WebSocket bridge (Foxglove's approach) to reach ROS2.
- Non-blocking rclpy-in-GUI pattern: run `rclpy.spin()` on a background `QThread`, marshal results to the UI via Qt signals — or merge event loops with **qasync** (asyncio-in-Qt) calling `spin_once()` with a short timeout inside the merged loop. Reference: [libros2qt](https://github.com/1r0b1n0/libros2qt).
- Packaging rclpy into a standalone exe is **not clean "zero deps"**: PyInstaller can bundle rclpy/rosidl/rcl_interfaces via `--collect-all`, but you must also ship the ROS2 install tree's shared libraries and typically the RMW/DDS middleware — effectively vendoring a chunk of a ROS2 install per-distro/per-RMW, not a universal binary ([ros2/ros2#1514](https://github.com/ros2/ros2/issues/1514)).

## 5. Open decisions to make before scaffolding

1. ~~Backend architecture (WSL2/container vs native)~~ — **resolved**: Linux-only target, so everything runs as native local processes (§2).
2. **Spec language for stage 3**: adopt FRETish (reuse FRET's translation machinery) vs. design a custom LTL/BT authoring UI. Reusing FRETish is lower-risk given it's the direct path to Ogma.
3. **How much of stage 1 is LLM vs. human-reviewed**: given the "hallucinated logical structure" failure mode, decide upfront whether the LLM split is auto-applied or always presented for human confirmation (nl2spec-style) before feeding stage 3/4.
4. **Behavior-tree track scope**: LTL has a mature toolchain end-to-end (FRET/Ogma/nuXmv/Strix); the BT track has real gaps at stage 4 (no realizability equivalent) and a less direct path into Ogma. Consider whether v1 should focus on LTL-only and treat BT support as a stretch goal.
5. **Packaging format**: with Windows out of scope, decide the Linux distribution mechanism — plain PyInstaller binary, AppImage, or a Debian package — likely lower priority than the above.
