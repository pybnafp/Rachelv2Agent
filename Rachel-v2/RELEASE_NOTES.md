# Rachel-v2 Release Notes

Release: `Rachel-v2-20260721_142758-codex-skill`
Date: 2026-07-21T14:30:31+08:00

## Highlights

This update rebalances Rachel around LLM-owned chemistry without weakening its
sandbox, validation, commit, topology, continuation, or terminal gates. It
restores the useful strategic coverage of the earlier broad-prompt releases,
retains the evidence and representation improvements introduced later, and
repairs terminal re-entry as a real route-tree lifecycle transition.

## Restored Historical Strengths

- Route-level strategy remains visible during Discovery instead of being
  displaced by generic validation language.
- Convergence, mature-scaffold preservation, electronic-state strategy,
  reactive-handle timing, and bounded route rescue are again available at the
  design boundary.
- Relevant experience cards can follow the active route plan through local
  Discovery stages without restoring unrelated cards at every command.
- The restoration is semantic rather than a return to the repetitive 07-17
  full-catalog projection.

## New Behavior

1. **Peer chemical hypotheses.** Listed Rachel actions and complete
   LLM-designed one-step actions are peers. A custom proposal leads with its
   positive chemical case; comparison and rejection provenance are secondary
   and conditional.
2. **Discovery and Audit separation.** Discovery exposes positive route-design
   guidance and complete stage self-prompts. Audit projects validation guidance
   only for the active evidence state.
3. **Two-path route planning.** A complex target can start with a short
   revision-0 provisional thesis and later receive a complete evidence-enriched
   revision-1 plan, or it can inspect sites first and record an evidence-first
   complete revision-0 plan.
4. **Dynamic relevant experience.** Discovery exposes every card that passes
   structured activation and relevance checks. Roughly five is an ordinary
   context recommendation, not a fill target or hard ceiling; specialized
   Audit/Terminal capacities remain bounded.
5. **Hard versus advisory language.** State invariants and chemical
   contradictions remain hard. Route search uses conditional comparison and
   focuses the LLM on proving its proposed chemistry rather than disproving
   every alternative.
6. **State-specific validation disclosure.** Clear, warning, inconclusive,
   proof-required, chemically blocked, and system-error blocked states receive
   distinct guidance without repeating validation philosophy at every stage.
7. **Terminal reopen lifecycle.** `review_terminal(..., additional_steps=0)`
   revokes stale completion, preserves the original molecule node and route
   history, requeues the leaf into the standard retrosynthesis loop, supports
   explicit finite step-budget extension, and requires a later explicit
   `finalize`.

## Preserved Gates

- One real chemical event per committed tree edge.
- Complete precursor/reagent handling and selected-attempt provenance.
- Forward validation, atom accounting, site fidelity, and topology evidence.
- Chemical contradictions remain no-commit results.
- Validator/system failure remains a procedural execution stop, not chemical
  disproof.
- Strategy continuation and advanced-terminal rescue remain enforceable.
- `finalize` remains the only completion boundary.

## Documentation Alignment

- `Rachel/SKILL.md` remains the executable LLM contract.
- Dynamic command output and `prompt_brief` remain the current-stage authority.
- `Rachel/workflow.md` remains the design and maintenance explanation.
- `Rachel/refs.md` now documents both route-plan paths and a peer custom-action
  example with conditional rejection provenance.
- Both READMEs now summarize the current planning contract, peer-action branch,
  and terminal reopen loop without copying the full Skill rules.

## Verification

Supported runtime and release checks:

```powershell
python -m pytest -q Rachel/main validation/tests/test_codex_skill_release.py validation/tests/core/unit/test_terminal_review_threshold.py
# 164 passed

python -m compileall -q Rachel
# passed
```

Documentation checks include UTF-8 decoding, English/Chinese section and flow
parity, local Markdown link validation, removal of the obsolete usage-notes
link, and protected-source hash comparison.

## Known Limits

- Historical walkthroughs used different model versions and are not controlled
  causal evidence for prompt quality.
- No same-model, same-target, same-tool A/B evaluation has yet established
  cross-model route-quality gains.
- Full-repository pytest is not a valid completion signal because collection
  has pre-existing duplicate test-module names and missing optional
  dependencies such as `hypothesis`, `torch`, and legacy E7 imports.
- Dense Discovery contexts can produce longer card payloads; relevance and
  activation precision, rather than a fixed card ceiling, are the control.
