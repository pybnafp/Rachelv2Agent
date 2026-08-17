# Rachel-v2 Release Manifest

## Purpose

This manifest defines the recommended distribution boundary for Rachel-v2 when it is shared with another user or another agent environment for de novo retrosynthesis planning.

This file is a planning and packaging guide only. It does not imply that the current workspace has already been copied into a clean release directory.

## Release Principle

Distribute the runtime skill package, not the research workspace.

Rachel-v2 currently contains runnable code, migration notes, archived research material, validation assets, and many historical walkthrough runs. A direct copy of the whole workspace would expose unnecessary files, stale experiment scripts, local paths, caches, and token-heavy context to downstream users.

The preferred distribution model is:

```text
Rachel-v2-release/
  environment.yml
  release_manifest.md
  Rachel/
    ...
```

The existing `Rachel/SKILL.md` is already the operational skill entry for current users. Do not add a second workflow entry unless the target agent system requires a root-level `SKILL.md`.

## Include

Required runtime package:

```text
Rachel/main/
Rachel/chem_tools/
Rachel/chem_tools/templates/
Rachel/tools/__init__.py
Rachel/tools/atom_bond_map.py
Rachel/tools/llm_retro_platform.py
Rachel/tools/pubchem_terminal_audit.py
Rachel/tools/audit_terminal_buyability_batch.py
Rachel/chem_tools/terminal_allowlist.json
Rachel/SKILL.md
Rachel/experience.md
Rachel/experience_cards.md
Rachel/experience_cards.json
Rachel/README.md
Rachel/README.zh-CN.md
Rachel/workflow.md
Rachel/refs.md
```

Optional but useful:

```text
Rachel/tools/visualize_reaction.py
Rachel/tools/audit_n1_terminal_buyability.py
Rachel/targets/
docs/action_space_case_record_n1_1391.md
docs/chemist_guided_prompt_injection_plan.md
docs/strategic_rescue_route_sketch_plan.md
MIGRATION_SCOPE.md
```

Rationale:

- `Rachel/main/` contains the state machine, command interface, route tree, report, export, and visualization orchestration.
- `Rachel/chem_tools/` and `Rachel/chem_tools/templates/` define the chemistry action space, molecule facts, FGI, bond actions, smart capping, validation, and site audit.
- The runtime validation dependency closure includes precursor normalization,
  atom mapping, functional-group delta, graph delta, reaction-family,
  ring-topology, validation findings, validation policy, and evidence-packet
  modules.
- `Rachel/tools/llm_retro_platform.py` is still imported by `Rachel/main/retro_session.py` and `Rachel/main/retro_orchestrator.py`; it is runtime-relevant even though some CLI dataset modes inside it are experiment-facing.
- `Rachel/tools/atom_bond_map.py` is the supported standalone compatibility
  projection for indexed atom/bond inspection and now shares
  `chem_tools.mol_info.analyze_molecule` as its fact source.
- `Rachel/tools/pubchem_terminal_audit.py` and `Rachel/chem_tools/terminal_allowlist.json` provide the optional PubChem CID / vendor terminal closure audit.
- `Rachel/tools/audit_terminal_buyability_batch.py` is the dataset-parameterized batch implementation for local run/export terminal-closure analysis. `Rachel/tools/audit_n1_terminal_buyability.py` remains a compatibility wrapper that supplies `--dataset n1`.
- `Rachel/SKILL.md` is the compact operational contract for LLM/agent use.
- `experience_cards.*` and `experience.md` support dynamic prompt mounting and short experience prompts.
- `workflow.md` and `refs.md` are reference material for maintenance and debugging, not default LLM context.

## Exclude

Do not distribute these by default:

```text
.git/
.agents/
.codex/
.pytest_cache/
__pycache__/
*.pyc
Rachel/.rachel/
walkthrough_runs/
archive/
analysis/
validation/
moledata/
```

Also exclude runtime-adjacent test and experiment scripts unless a developer specifically asks for them:

```text
Rachel/main/_test*.py
Rachel/main/test_*.py
Rachel/tools/_near_miss.py
Rachel/tools/_show_mid.py
Rachel/tools/run_validation.py
Rachel/tools/retro_accuracy.py
Rachel/tools/build_e4_session_dataset.py
Rachel/tools/benchmark_multistep.py
Rachel/tools/template_quality_audit.py
Rachel/tools/test_capping.py
Rachel/tools/llm_bond_test.py
Rachel/tools/multistep_retro.py
Rachel/tools/failure_taxonomy.py
Rachel/tools/reaction_analysis.html
```

Rationale:

- `walkthrough_runs/` are historical run artifacts and can be large or target-specific.
- `moledata/` contains independently sourced benchmark/reference data and route visualizations. It is intentionally distributed as a separate companion package so the runtime skill remains small and does not imply that the imported routes are Rachel outputs.
- `archive/`, `analysis/`, and `validation/` are research, experiment, or maintenance material rather than core runtime.
- Several tools under `Rachel/tools/` still reference migrated test/data paths such as `Rachel.tests...`; including them in a user-facing release will create avoidable confusion.
- Cache and local state folders are machine-specific and should never be part of a clean distribution.

## Environment

The clean release should include:

```text
environment.yml
```

Recommended install command:

```powershell
conda env create -f environment.yml
conda activate rachel-v2
```

If the user already has a compatible environment, they can verify it instead of recreating it:

```powershell
python -c "import sys, rdkit; print(sys.version); print(rdkit.__version__)"
python -c "from Rachel.main import RetroCmd; print(RetroCmd)"
```

For Windows PowerShell, avoid Bash heredoc syntax such as:

```text
python - <<'PY'
```

Use a `.py` file or PowerShell here-string piped to Python if a multi-line smoke command is needed.

## Current Verified Local Baseline

The current local baseline used during Rachel-v2 development was:

```text
Python 3.11.5
RDKit 2025.09.3
pytest 7.4.0
pandas 2.0.3
numpy 1.24.3
matplotlib 3.7.2
Pillow 9.4.0
networkx 3.1
```

This baseline is evidence from the current machine, not a strict lower-bound guarantee.

## Root Skill Entry Decision

Current decision: do not add a new root-level `SKILL.md` in this planning step.

Reason:

- The existing `Rachel/SKILL.md` already contains the operational contract, command loop, PowerShell warnings, context-budget rules, chemistry quality rules, and failure recovery guidance.
- Adding a second skill entry now risks duplicated instructions.
- If a future target platform requires a root-level `SKILL.md`, create it as a thin pointer or curated copy of `Rachel/SKILL.md` during the actual release packaging step.

## Smoke Verification Plan

After a clean release copy is created, verify from the release root:

```powershell
python -c "from Rachel.main import RetroCmd; print('RetroCmd OK')"
```

Then run a minimal session with `RetroCmd`:

```python
from pathlib import Path
from Rachel.main import RetroCmd

run = Path("smoke_run")
run.mkdir(exist_ok=True)
cmd = RetroCmd(str(run / "session.json"))

print(cmd.execute("init", {
    "target": "CC(=O)Nc1ccc(O)cc1",
    "name": "paracetamol_smoke",
    "terminal_cs_threshold": 1.5,
}))
print(cmd.execute("next", {}))
print(cmd.execute("reaction_sites", {}))
```

This verification must pass without referencing a development-machine path.

## Repeatable Release Build

Build the current Codex Skill release from the project root:

```powershell
conda activate rachel-v2
python scripts\build_codex_skill_release.py
```

The builder uses an explicit runtime allowlist, generates installation and
release metadata, creates file and ZIP SHA-256 records, extracts the temporary
ZIP into a clean directory, runs the packaged verifier, and publishes the final
ZIP only after verification succeeds. It does not overwrite an existing
release.

The generated `Rachel/` directory remains the only Skill entry. Do not add a
second root-level `SKILL.md`.

## USPTO-190 Companion Data Package

When distributing the Retro* USPTO-190 hard reference routes, create a separate
data package from `moledata/retro_star_190_hard/`. Include the source pickle,
the deterministic reconstruction scripts and outputs, the 190 standalone HTML
route views, and provenance/verification metadata. Exclude `__pycache__/`.

Do not add this directory to the runtime skill package. The source data are
external benchmark/reference route sequences and are not Rachel predictions or
literature-validated synthetic procedures.

Those steps can be done later after the release boundary in this manifest is accepted.
