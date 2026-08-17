---
name: Rachel
description: >
  Rachel is an information-grounded, LLM-directed multi-step retrosynthesis
  workflow. Rachel supplies chemical facts, candidate scaffolds, validation
  findings, and audit state; you remain the chemistry decision engine. Design
  boldly, then validate strictly against mechanism, topology, atom source, site
  fidelity, compatibility, convergence, stereochemistry, and honest terminal
  boundaries. Use for de novo or high-quality route construction, debugging,
  validation, reporting, or maintenance inside Rachel-v2.
---

# Rachel

## 1. Core Philosophy And Operating Contract

Rachel does not replace chemical reasoning. Its job is to provide structured
information that makes reasoning harder to fake and easier to audit:

- molecular, functional-group, site, topology, and complexity facts;
- system-template and Smart CAP search-space hints;
- atom-source, electronic-state, compatibility, and mapping observations;
- contradictions, proof obligations, warnings, and tool limits;
- persistent route state, sandbox attempts, decisions, and exports.

The LLM or chemist owns:

- the global route thesis and its revision;
- reaction and disconnection design, including unlisted chemistry;
- precursor/reagent completion and mechanistic explanation;
- reconciliation of gate findings with chemical facts;
- commit, override, continuation, and terminal decisions.

Non-negotiable principles:

1. **Chemistry first.** Chemical truth and route quality outrank templates,
   family names, scores, confidence, convenience, and route depth.
2. **Bold design, strict proof.** Explore unconventional or de novo strategies
   when they are better, but validate mechanism, atom source, site, topology,
   selectivity, compatibility, and stereochemistry before commit.
3. **Actions are peer hypotheses.** Listed Rachel actions, Smart CAP hints, and
   complete LLM-designed one-step actions are candidate chemistry sources; none
   bounds retrosynthesis or proves a reaction. The LLM may choose a listed
   action, design a different reaction at the same site, propose an unlisted
   disconnection, or revise the route thesis. When an LLM-designed action looks
   stronger, lead with its positive chemical case: complete precursors/reagents,
   reaction/site, mechanism, atom sources, selectivity, topology/site fidelity,
   and route-plan alignment. Compare listed actions only as secondary selection
   provenance, and record rejected IDs only for actual rejections. A `*` dummy
   atom in a system precursor preview is an intentional attachment-site cue, not
   a real reagent or evidence that the template is incomplete; complete the same
   disconnection with real precursors before validation.
4. **Gates inform and classify.** `blocked`, `proof_required`, `inconclusive`,
   `warning`, and `clear` describe evidence state. They do not choose the route.
   True chemical contradictions are chemical hard stops. Validator/system
   failure is an execution stop until repaired, not chemical disproof.
5. **One real event per commit.** Multi-step ideas belong in `route_plan`,
   `route_sketch`, and strategy continuation; each tree edge remains one
   chemically coherent event.
6. **Audit every decision.** Preserve evidence, reagent roles, uncertainty,
   overrides, and the reason to continue or stop. Record rejected alternatives
   only when they are actually rejected.
7. **Depth must add value.** Continue toward simpler credible precursors, but
   prefer an honest terminal over speculative or compressed fake chemistry.

Document authority:

- `SKILL.md`: default executable contract and normal command loop.
- command output plus `prompt_brief`: current dynamic facts and obligations.
- `workflow.md`: design rationale, state transitions, and maintenance behavior.
- `refs.md`: exact command fields, schemas, and export structures.
- `experience_cards.json`: runtime dynamic reminders; cards inform judgment but
  never override substrate facts or mechanism.
- `experience.md`: long-form empirical priors, not default runtime context.
- `README.md` / `README.zh-CN.md`: project overview, not command protocol.

Use this file, Rachel command outputs, and `prompt_brief` as the default runtime
contract. Do not read long project documents by default.

Rachel already allocates molecular information in layers: compact provides
formula, average molecular weight, ring/stereocenter counts, rotatable bonds,
functional groups, and reaction-opportunity summaries; `reaction_sites()`
provides the complete site menu; `explore_site(site_id)` provides selected-site
atoms, the real bond index, endpoint roles, bond type, ring flag, and local FG
context. When ring members, stereocenter locations, or the whole indexed
atom/bond graph are specifically needed, call `context(detail="structure")`
rather than expanding compact.

Do not read these unless the user explicitly asks for maintenance/debugging, or
a command output is missing necessary fields:

- `README.md`, `README.zh-CN.md`, `workflow.md`, `refs.md`, `experience.md`
- `context(full)`, `context(detail="diagnostic")`
- full `session.json`, full exports, historical walkthroughs, test scripts, or
  Rachel source code

If a field/protocol ambiguity blocks execution, read only the smallest relevant
fragment and say why.

## 2. Preferred Invocation

Use Python `RetroCmd` directly. Avoid inline JSON in PowerShell.

```python
from pathlib import Path
import json
from Rachel.main import RetroCmd

workspace = Path.cwd()
run = workspace / "walkthrough_runs" / "YYYYMMDD_target_slug"
run.mkdir(parents=True, exist_ok=True)
cmd = RetroCmd(str(run / "session.json"))

def save(name, payload):
    (run / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

save("00_init.json", cmd.execute("init", {
    "target": "TARGET_SMILES",
    "name": "target_slug",
    "max_depth": 15,
    "max_steps": 50,
    "terminal_cs_threshold": 2.25,
}))
node = cmd.execute("next", {})
save("01_next.json", node)
sites = cmd.execute("reaction_sites", {})
save("02_reaction_sites.json", sites)
```

If multi-line Python must be launched from PowerShell, use a here-string pipe
and set UTF-8 output before sending Chinese reasoning into Python:

```powershell
conda activate rachel-v2
$env:PYTHONIOENCODING='utf-8'
$OutputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
@'
from Rachel.main import RetroCmd
print("ok")
'@ | python -
```

Do not use Bash heredoc syntax such as `python - <<'PY'` in PowerShell. Use the
Python interpreter from the active `rachel-v2` environment.

When Rachel is installed as a Codex Skill, the default Windows location is
`$HOME\.codex\skills\Rachel`; if `CODEX_HOME` is set, use
`$CODEX_HOME\skills\Rachel`. When commands run outside the parent `skills`
directory, add that parent directory to `PYTHONPATH` before importing
`Rachel.main`.

## 3. Route Strategy Model

Rachel is stateful route construction, not one-shot route writing.

For a complex target without an active `route_plan_brief`, normally call
`route_plan(...)` early to record a short revision-0 provisional thesis seed
from the target, `molecule_brief`, and `functional_group_brief`. If the target
is simple, or those molecule-level facts cannot yet support a useful seed,
`reaction_sites()` may come first. If a seed was recorded, call
`route_plan(...)` again after the relevant site map and selected `explore_site`
evidence to restate the evidence-enriched complete structured plan as revision
1. If site evidence came first and no seed exists, the first `route_plan(...)`
call records the complete plan directly as revision 0. A seed is a chemical
hypothesis, not a proven route, and the complete plan is bounded structured
context rather than an unbounded route essay.

Use later Rachel molecule/site/action evidence to support, falsify, enrich, or
revise the active plan. Revise whenever evidence changes a recorded substantive
claim, including a key disconnection, precursor family, sequence, handle
timing, preserve/build decision, selectivity strategy, strategic risk, or
revision trigger. A local reaction choice can therefore require revision even
when the broad route mode remains unchanged. Catalyst, reagent, solvent, or
template-only changes within the same planned event normally do not. Every
revision must restate the complete current plan because `route_plan(...)`
replaces rather than merges omitted fields. Rachel-listed actions and complete
LLM actions remain peer executable evidence, not the global plan itself.

Compare:

- `late_fgi`: preserve mature core; edit handles late.
- `scaffold_assembly`: build the core/ring system from simpler fragments.
- `electronic_state_strategy`: build through a non-final electronic state, then
  aromatize, halogenate, oxidize/reduce, or otherwise convert.
- `hybrid`: explicitly combine these modes.

Use `route_sketch` when an idea changes the route thesis, needs local
strategy-to-action translation, spans more than one real event, or supports
bounded terminal review. A complete one-step LLM peer action may go directly to
`propose_action(...)`; `route_sketch` is not a permission gate for custom
chemistry. Neither path mutates the route tree or bypasses sandbox validation.

Use it to complete wildcard/open-action strategy, execute a global
`route_plan` locally, or define one next event from a multi-event idea. A `*`
dummy atom remains an intentional attachment-site cue rather than an
incomplete-template verdict. Convert only one next real chemical event into
`propose_action(...)` or a listed `try_action(action_id)`.

## 4. Default Route Loop

```text
init
-> next / context(compact)
-> for a complex target without a plan: normally route_plan(...) with a short revision-0 seed
   or reaction_sites() first when the target is simple or site evidence is needed
-> optional guide(...)
-> reaction_sites()
-> explore_site(site_id)
-> if a seed is active: route_plan(...) with the evidence-enriched complete revision-1 plan
   if site evidence came first with no plan: route_plan(...) with a complete revision-0 plan
   or revise later whenever a recorded substantive plan claim changes
-> choose one next real event:
   - listed action -> try_action(action_id)
   - complete one-step LLM action -> propose_action -> try_action
   - route-level or multi-event idea -> route_sketch -> one listed/custom action -> try_action
-> sandbox_list
-> commit(...) or accept(...)
-> next
-> finalize
-> report
-> export
```

State rules:

- Commands must follow session state. Do not run `next`, `reaction_sites`,
  `explore_site`, and `try_action` in parallel.
- `reaction_sites()` requires an active context. If there is no active context,
  call `next` first.
- `explore_site(site_id)` must use a current `site_id` from `reaction_sites`.
- `try_action(action_id)` must use an action from `explore_site` or
  `propose_action`.
- `propose_action` only registers an action; it is not validation.
- `commit` only commits a sandbox attempt.
- After `commit` or `accept`, call `next` before trying more actions.

## 5. Public Payload Schema

Do not guess field names.

Important fields:

- `next`: read `result["current"]` for current SMILES, compact cognition, and
  `prompt_brief`.
- `context(detail="structure")`: read
  `result["current"]["molecule_structure"]` for the active molecule's canonical
  SMILES, formula, average `mw`, descriptors, indexed atoms and bonds, ring
  members, stereo locations, symmetry, and scaffold topology. This view is
  read-only and is not persisted into compact session state.
- `reaction_sites`: first-layer field is `site_reaction_map`, not `sites`,
  `items`, or `reaction_sites`.
- Each site: `site_id`, `site_type`, `site_hint`, `action_count`,
  `reaction_count`, `competition_hint`, `risk_hint`, `reactions`.
- Each reaction row: `reaction_id`, `reaction_name`, `action_count`,
  `source_summary`, `risk_hint`.
- `explore_site(site_id)`: second-layer field is `actions`.
- Each action: `action_id`, `site_id`, `reaction.id`, `reaction.name`,
  `source`, `precursors_preview`, `risk_tags`, `bond_idx`, `alt_idx`,
  `actual_bond_idx`, `fgi_idx`.
- Local site identity is usually available from `atoms`, `actual_bond_idx`,
  `role_pair`, `bond_type`, `in_ring`, and `bond_fg_context`.
- `sandbox_list`: comparison field is `attempts`; `by_site` and `by_reaction`
  only hold attempt indexes.
- Each public attempt: `idx`, `action_id`, `precursors`, `reaction_type`, and
  canonical `validation` (`rachel.validation.v2`). Read `validation.execution`,
  `decision_gate`, `contradictions`, `proof_obligations`, `evidence_gaps`,
  `tool_limits`, `observations`, and `declared_action`.
- `mechanism_interpretation` is optional and omitted when no registered
  mechanism adds useful evidence; an unregistered reaction name is not itself
  a public warning.
- Legacy `forward_validation`, `validation_micro`, `evidence_packet`,
  `override_allowed`, and `site_rows` remain only in session/diagnostic payloads
  for historical compatibility. Do not use them as the normal LLM protocol.
- Internal session snapshots may also retain legacy continuation keys so older
  runs remain resumable. Public commands, `prompt_brief`, and `tree.json` use
  `continuation_*` / `strategy_continuation_*`; do not send `rescue_steps`,
  `rescue_step_idx`, `rescue_id`, `rescue_status`, or `rescue_abort`. The
  terminal-review escape fields `force_accept_without_rescue` and
  `rescue_not_actionable_reason` are separate existing gate inputs.
- `prompt_brief` is the default dynamic prompt projection. Read short
  `route_plan_brief`, `route_strategy_brief`, `chemist_guidance`, and
  `experience_prompts`; do not load full prompt state unless debugging.
- `prompt_brief.required_audit_fields` is a stage/state-specific subset, not a
  fixed checklist repeated on every action.
- `prompt_brief.strategy_continuation_brief` means a multi-step route-sketch
  continuation is active. This is normal LLM strategy execution, not only a
  terminal rescue. Read focus molecule, next-step summary, and remaining count.

## 6. Strategy Commands

### `route_plan`

Use for a persistent global thesis. It does not mutate the tree.

```python
cmd.execute("route_plan", {
    "route_thesis": "short global synthesis thesis",
    "route_mode": "late_fgi | scaffold_assembly | electronic_state_strategy | hybrid",
    "mode_evidence": ["why this route paradigm is preferred"],
    "strategic_risks": ["what could make this thesis fail"],
    "revision_triggers": ["evidence that should force revision"],
    "key_disconnections": ["key bond or FG logic"],
    "preferred_precursor_logic": ["preferred precursor family or handle"],
    "protect_or_preserve": ["motifs/scaffolds to preserve"],
    "revision_reason": "initial | better route found | weak action-space | advanced terminal review",
})
```

The first call may contain only a concise thesis, provisional route mode, one or
two likely disconnections or preserve/build decisions, and a few risks or
revision triggers. Use the exact `revision_reason` value `initial` for this
revision-0 seed so it is not represented as an already-completed revision.
After relevant site/action evidence, the normal second call
should fill every applicable existing field and use a revision reason such as
`evidence-enriched refinement after site analysis`.

Revise `route_plan` whenever terminal review, sandbox evidence, chemist
guidance, action-space comparison, or a local reaction choice changes a
recorded substantive plan claim. Do not revise merely because the same planned
event uses another catalyst, reagent, solvent, or template. Each call replaces
the stored entry, so revision 1 and all later revisions must repeat unchanged
fields that remain part of the current plan.

### `route_sketch`

Use for local strategy-to-action translation.

```python
sketch = cmd.execute("route_sketch", {
    "problem": "why the visible action-space does not express the strongest route hypothesis",
    "macro_strategy": "short target-oriented synthesis idea",
    "key_disconnections": ["one or two key disconnections"],
    "rejected_action_space_reason": "only when specific listed actions are actually rejected",
    "next_executable_step": "propose_action",
})
```

For any bounded 1-3 step strategy, add a short ordered `continuation_steps`
list. Still register only the first real event as an action. Set
`terminal_review=True` only when reviewing an advanced terminal.

```python
cmd.execute("route_sketch", {
    "problem": "advanced terminal needs mini-route review",
    "macro_strategy": "first disconnect X, then continue tracing Y",
    "key_disconnections": ["first event", "follow-up event"],
    "next_executable_step": "propose_action",
    "terminal_review": True,
    "continuation_steps": [
        {
            "step_idx": 0,
            "target_smiles": "CURRENT_SMILES",
            "reaction_name": "first real event",
            "expected_precursors": ["PRECURSOR_A", "PRECURSOR_B"],
            "continuation_precursor": "PRECURSOR_A",
        },
        {
            "step_idx": 1,
            "target_smiles": "PRECURSOR_A",
            "reaction_name": "follow-up real event",
            "expected_precursors": ["SIMPLER_PRECURSOR"],
        },
    ],
})
```

Never set `next_executable_step="accept"` in `route_sketch`. `accept` is a
separate terminal command.

### `propose_action`

Register a complete LLM-designed one-step precursor set as a normal peer action.
Lead with its positive chemical case in `rationale_summary`; use comparison with
visible alternatives as secondary provenance.

```python
custom = cmd.execute("propose_action", {
    "precursors": ["SMILES1", "SMILES2"],
    "reagents": ["CURRENT_STEP_REAGENT"],
    "reaction_name": "one-step reaction name",
    "action_label": "short custom action label",
    "why_existing_actions_rejected": "only when specific listed actions are actually rejected",
    "rationale_summary": "positive chemical case: mechanism, site, atom sources, selectivity, and why this is one real chemical event",
    "risk_tags": ["site_fidelity_check"],
})
trial = cmd.execute("try_action", {"action_id": custom["action_id"]})
```

For a peer proposal that does not chemically reject the listed actions, leave
`why_existing_actions_rejected` empty. Put the positive chemical case first in
`rationale_summary`; add comparison only to explain why the candidate is worth
testing.

Use `precursors` for route-bearing skeletons or synthons that should become tree
nodes. Use `reagents` for current-step catalysts, metals, donors, or other
components needed for validation and export but not intended as tree leaves.
Both lists participate in atom accounting; scaffold/topology/site audits use
only `precursors`.

If this is the first event of a multi-step mini-route, include
`route_sketch_id`, `continuation_step_idx`, and `continuation_precursor`.

## 7. Chemical Decision Rules

1. Commit one real chemical event at a time. Do not compress multi-step
   chemistry into one custom action.
2. Mechanism, scaffold topology, site fidelity, atom source, handle timing,
   functional-group compatibility, and convergence outrank template match.
3. Template pass is evidence, not proof. Template miss is not disproof.
4. Reaction names and family labels are hints, not verdicts.
5. Prefer preserving mature heteroaryl or rigid scaffolds when routes are
   comparably credible; scaffold assembly remains available when explicitly
   justified with mechanism and precursor evidence.
6. Prefer installing high-reactivity temporary handles late when compatible with
   the route. Protection and deprotection are real tree steps, not reasoning
   comments.
7. Account for key C/N/S/halogen/protecting-group atoms and missing small
   molecules before commit.
8. Preserve stoichiometric duplicates in the appropriate component list: if
   two identical route-bearing synthons or current-step reagents supply two
   product sites, repeat that SMILES in `precursors` or `reagents`. Do not rely
   on prose such as "two equivalents" for atom-balance validation.
9. Drive toward simple, stable, purchasable precursors when chemistry remains
   credible. Accept honest advanced terminals over fake deep disconnections.
   When two candidate disconnections are chemically comparably credible, prefer
   the one that moves route-bearing nodes toward simpler, stabler, and more
   purchasable precursors rather than preserving bespoke advanced fragments.
   A low CS score is not sufficient for automatic terminal acceptance when the
   molecule contains an assigned stereocenter; review its stereochemical source
   and any executable rollback before accepting it.
   Use `review_terminal(smiles, reason, additional_steps=0)` when a chemist asks
   to continue below an accepted terminal, including after `finalize`. A
   successful review revokes the current completion conclusion, keeps the
   original tree node and reaction history, and restores the normal standard
   Rachel loop without bypassing terminal-review or sandbox gates. If the total
   step budget is exhausted, supply a positive `additional_steps`; explicitly
   `finalize` again after the extended route closes.
10. Use LLM initiative: when a better chemical strategy exists, express it as a
   complete one-step `propose_action`, then sandbox it.
11. Treat detected carbene, radical, or radical-ion precursors as factual
   `proof_required` findings, not automatic chemical contradictions. Correct an
   unintended template placeholder to a closed-shell precursor, or provide its
   in-situ generation, lifetime, atom source, mechanistic role, and selectivity
   evidence. Independent atom-balance or topology contradictions still block.
   A single-atom `Li`, `Mg`, `Zn`, or `Cu` component is reported instead as an
   `elemental_metal_reagent` observation: RDKit radical electrons on elemental
   metal are a representation fact, not an unsupported molecular radical.

If `precursor_normalization` records an organometallic
`source_obligation`, keep `current_reagent` in the current action. Read
`upstream_source_precursors` only as a possible separate upstream preparation;
never substitute those source materials into the reaction being validated.
The source list is a planning hint, not a unique mechanistic verdict; the LLM
may replace it with a better explicit source sequence.

## 8. Custom Topology Audit Gate

For custom or route-sketch-derived actions that build, open, fuse, or rewrite a
ring/scaffold, a reaction-family name is not enough. Before commit, require:

- exact changed bond atoms;
- at least two preserved scaffold anchors;
- unchanged relative positions of retained substituents/handles unless movement
  is the intended event;
- clear atom source for new ring/scaffold atoms;
- mechanism/tether evidence for intramolecular events;
- explanation of major alternatives.

Put topology evidence in the action payload before sandboxing:

```python
cmd.execute("propose_action", {
    "precursors": ["..."],
    "reaction_name": "custom topology step",
    "action_label": "short label",
    "why_existing_actions_rejected": "only when specific listed actions fail the topology audit",
    "rationale_summary": "one real event with explicit atom-source evidence",
    "intended_deltas": ["ring_closure", "fg_installation"],
    "expected_ring_change": "fused_ring",
    "changed_bonds": [
        {"product_atoms": [0, 1], "precursor_atoms": [0, 1], "event": "formed"}
    ],
    "preserved_anchors": ["retained heteroatom position", "stable handle"],
    "mechanistic_evidence": ["why this is one plausible event"],
    "family_evidence": {
        "same_precursor_tether": "if intramolecular",
        "new_ring_bond_atom_source": "source of new bond atoms"
    },
    "risk_tags": ["ring_construction", "scaffold_edit"],
})
```

After `try_action`, read canonical `validation`. Reconcile:

```text
1. `observations`: graph / ring / FG / MCS atom-mapping facts
2. `declared_action` and optional `mechanism_interpretation`
3. `proof_obligations`, `evidence_gaps`, `contradictions`, and `tool_limits`
```

`atom_mapping` is an MCS-derived atom-source audit, not a true reaction oracle.
Use it as a structured challenge.

## 9. Validation And Commit

Read `validation.decision_gate` first:

- `blocked`: do not commit. If `block_type=system_error`, rerun/fix validation;
  otherwise change the action or precursor.
- `proof_required`: pause-and-prove, not automatic
  chemical disproof. First add atom-source, tether, anchor, or mechanistic
  evidence, or revise the precursor. Commit only with explicit
  `validation_override`.
- `inconclusive`: review `evidence_gaps` separately from `tool_limits`.
  Template/tool absence is neither disproof nor positive proof.
- `warning`: can commit, but reasoning must address risk.
- `clear`: no gate objection; normal chemistry review is still required.

Commit reasoning must state:

- why the step is mechanistically real;
- which site changes and which scaffold/site features are preserved;
- key carbon/atom/small-molecule/protecting-group sources;
- functional-group and handle-timing compatibility;
- why major alternatives were rejected, when actual rejection occurred;
- if overriding validation, why the gate is a false positive and what evidence
  replaces it;
- if accepting an advanced terminal, why stopping is higher quality than deeper
  speculative disconnection.

Commit example:

```python
cmd.execute("commit", {
    "idx": idx,
    "expected_action_id": "the action_id shown at sandbox idx",
    "reasoning": "mechanism, site, scaffold, atom accounting, alternatives",
    "rejected": [{"action_id": "...", "reason": "..."}],
    "route_plan_alignment": "supports | revises | conflicts | not_applicable",
    "validation_override": {
        "allowed": True,
        "reason": "why gate is false positive",
        "evidence": "independent chemical evidence"
    },
})
```

Use `validation_override` only when required and chemically justified.
Always send `expected_action_id` in normal LLM commits. It is an index-safety
assertion: if sandbox ordering changed or reasoning targets another action,
commit fails before mutating the tree.

## 10. Terminal And Mini-Route Review

Before accepting a nontrivial advanced terminal, ask whether the molecule can be
made as a small target through a bounded 1-3 step mini-route from simpler,
stable, purchasable, or more rational building blocks.

Prefer considering:

- FG rollback;
- oxidation-state adjustment;
- protection/deprotection;
- regio/chemoselectivity source;
- physical organic reactivity differences;
- scaffold assembly or non-final electronic-state strategies when late FGI
  hides core construction.

If a credible mini-route step exists:

Executable rescue steps return to the normal validation and commit path:

1. `route_sketch(..., terminal_review=True)`
2. `propose_action(...)`
3. `try_action(custom_id)`
4. `commit(...)` if credible
5. `next` exposes continuation precursor when follow-up steps exist

If no credible executable mini-route step can be defined or repaired:

Tool or template failure alone is not terminal rationale; stopping requires a
chemical or route-quality reason that no credible event can be defined or
repaired.

```python
cmd.execute("accept", {
    "reason": "advanced-terminal rationale after review",
    "force_accept_without_rescue": True,
    "rescue_not_actionable_reason": "specific chemical/protocol reason no validated mini-route step is actionable",
})
```

If `strategy_continuation_brief` is active, resolve it before accepting or
finalizing. Continue with normal `reaction_sites/explore_site/try_action` or
`propose_action -> try_action -> commit`. If the continuation is not chemically
actionable, close it with:

```python
cmd.execute("continuation_abort", {
    "continuation_id": continuation_id,
    "reason": "specific chemical reason continuation is not actionable",
})
```

If the continuation focus was originally an auto-terminal leaf, aborting the
continuation restores that terminal state. Use `review_terminal(smiles,
reason, additional_steps=0)` to reopen the same tree leaf when replacing the
abandoned continuation with a better strategy.

## 11. Error Recovery

- `no active context`: call `next`.
- PowerShell JSON quoting errors: use Python `RetroCmd` dict calls.
- `Missing file specification after redirection operator`: you used Bash heredoc
  in PowerShell; use a PowerShell here-string pipe.
- Chinese reasoning becomes `????`: set `$OutputEncoding` and
  `[Console]::OutputEncoding` before piping to Python; do not only set
  `PYTHONIOENCODING`.
- Summary script cannot find `sites` or `items`: use `site_reaction_map`.
- `validation.decision_gate.state = inconclusive`: separate chemistry
  `evidence_gaps` from validator/template `tool_limits` before deciding.
- `precursors_preview` contains `*`: treat it as an intentional attachment-site
  cue from the same system disconnection, not a real precursor or template
  failure. Complete the real precursor/leaving group/reagent and use
  `propose_action -> try_action`. If an active strategy continuation supplies a
  complete precursor set, use that set as the sole executable realization for
  this action, not as a separate chemistry alternative.
- `source="smart_capping"`: the public reaction name is the generic
  `LLM-completed structural disconnection`; read the original rule label only
  from `execution.heuristic_reaction_hint`. Treat both label and fragments as
  structural hints only. Complete or correct the one-step
  precursors and chemical evidence with `propose_action`; a direct
  `try_action` returns `llm_completion_required` and does not create a sandbox
  attempt.
- `proof_obligations` contains `protecting_group_source_required`: the listed
  action omitted the reagent that contributes the protecting group. Add the
  complete donor (for example `TBSCl`, an acyl donor, benzyl donor, or sulfonyl
  donor) through `propose_action`, then revalidate atom balance and site
  selectivity. Do not override the missing atom source.
- `finalize` returns `strategy_continuation_pending`: call `next` to process the
  continuation or `continuation_abort` with a reason.
- A successful public `commit` returns `step_id`; do not test the removed
  legacy `success` field.
- If any command returns `{"error": ...}`, stop at that command. Fix command
  order or payload and rerun; do not continue by guessing fields.

## 12. Context Budget And Documents

- Default LLM input should include only current command output, `prompt_brief`,
  needed payload fields, and concise reasoning.
- Experience is mounted through `prompt_brief.experience_prompts`; do not read
  full `experience.md` or card files during normal execution.
- Discovery exposes every experience card that passes the current structured
  activation, event, tag, and relevance checks. Roughly five is an ordinary-
  context recommendation, not a fill target, maximum, or test threshold;
  sparse contexts may expose none. Audit remains capped at 4 by default, while
  terminal review and topology Audit remain capped at 5. Specialized cards are
  not mounted from broad scaffold text or reaction names alone.
- Large JSON outputs should be saved to disk and summarized, not pasted into
  chat.
- `context(detail="diagnostic")`, full `tree.json`, full reports, and source
  inspection are for debugging, tests, or user-requested maintenance only.

Escalation-only documents:

- `workflow.md`: protocol design and maintenance rationale.
- `refs.md`: command return fields and export structure.
- `README.md` / `README.zh-CN.md`: project overview.
- `experience.md`: long experience notes.
- `experience_cards.json`: card maintenance source; runtime reads
  `prompt_brief`.

## 13. Run Directory

Formal high-quality runs should use independent directories:

```text
<active-workspace>\walkthrough_runs\YYYYMMDD_<target_slug>\
```

Session file:

```text
...\session.json
```

Export explicitly:

```python
cmd.execute("export", {"output_dir": r"...\export", "name": "target_slug"})
```

If `session.json` already exists and the user did not request resume, create a
new timestamp/slug directory instead of mixing runs.

## Final Principle

Rachel informs, challenges, validates, and records; the LLM designs and decides.
Before every commit, ask whether the event is chemically real, fully sourced,
correctly located, compatible, strategically valuable, and honestly supported
by the available evidence. If not, revise the action rather than obeying a
template or forcing route depth.
