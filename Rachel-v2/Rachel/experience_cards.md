# Rachel Experience Cards

Discovery projects every card that passes the current activation, event, tag,
and relevance checks. Roughly five cards is an ordinary-context recommendation,
not a fill target, maximum, or test threshold. Audit contexts remain capped at
4 by default; terminal, advanced-terminal rescue, and topology Audit contexts
remain capped at 5.

本文件是 `experience.md` 的可执行短卡层，用于后续按 tag 检索并挂载到
`context(compact)`、`reaction_sites()`、`explore_site(site_id)`、`try_action()` 和
`commit()` 的 LLM 上下文中。

机器可读版本见 `experience_cards.json`；运行时代码应读取 JSON，本文件用于人工维护和审查。

## 使用契约

- Discovery 挂载所有通过结构化 activation、event、tag 与相关性筛选的卡片，不设置固定数量上限，也允许没有匹配卡片；“通常约 5 张”只是观察建议，不是填充目标或测试阈值；不全文注入 `experience.md`。
- Audit 默认仍最多 4 张；terminal、advanced-terminal rescue 和 topology Audit 场景最多 5 张。高风险 topology / atom-source 场景的 5 张预算仍是保留槽位，优先保证 topology gate、proof obligation、template evidence、custom precursor 和 atom-source 提醒共存。
- 卡片只作为排序、怀疑和审计提醒；不能覆盖明确底物事实、机理事实或用户约束。
- 卡片不选择反应，也不代替 LLM 判断；其作用是指出当前最值得重新思考、补证或审计的问题。
- 若卡片与当前底物不匹配，LLM 必须在 reasoning 中说明弃用原因。
- commit audit 记录卡片 `id` 即可，普通 LLM 上下文不重复长正文。
- 检索优先使用结构化上下文：functional group、selected site/action、risk tag、canonical validation、action source。反应名可激活反应专用卡，但不能单独生成 topology signal。

## 卡片字段

- `id`: 稳定引用 ID。
- `tags`: 用于检索的短标签。
- `activation`: 仅供选择器使用的结构化准入条件，不进入 `prompt_brief`。
- `one_line`: 可直接挂载到 prompt 的一句话提醒。
- `action_prompt`: LLM 当前必须执行的具体检查。
- `avoid`: 需要避免的常见错误。

## Core Cards

### exp_topology_first

- tags: `topology`, `ring_size`, `fused_ring`, `scaffold`, `commit`, `proof_obligation`, `reaction_topology`
- activation: structured `topology_signal`
- one_line: Check ring size, fusion pattern, scaffold atoms, and topology deltas before trusting a reaction label.
- action_prompt: Before commit, state preserved scaffold, changed site, ring atom count, and whether topology findings are evidence challenges rather than reaction-name verdicts.
- avoid: Do not let a template name skip topology audit, and do not treat topology warnings as name-based disproof without reading the evidence.

### exp_site_fidelity_fused_heteroaryl

- tags: `site_fidelity`, `fused_heteroaryl`, `heteroaryl`, `site_shift`, `commit`, `site_mapping`, `changed_site_count`, `site_fidelity_observation`
- activation: `fused_heteroaryl`, `site_shift`, `changed_site_count`, or `site_fidelity_observation`
- one_line: In fused heteroaryl systems, same scaffold is not enough; changed-site fidelity must be audited explicitly.
- action_prompt: Compare target and precursor positions using `validation.observations.site_fidelity`, `changed_site_count`, and any mapped `changed_sites` before claiming site retention.
- avoid: Do not substitute scaffold similarity or execution success for site fidelity, and do not invent site mapping when the observation is unavailable.

### exp_custom_topology_audit_gate

- tags: `custom_precursor`, `route_sketch`, `annulation`, `ring_construction`, `fused_ring`, `scaffold_edit`, `site_fidelity`, `site_shift`, `proof_required`, `proof_obligation`, `reaction_topology`, `family_evidence`, `validation_observations`, `declared_action`, `commit`, `decision_gate`, `proof_obligations`, `atom_mapping`, `declared_mechanism`, `atom_source`
- one_line: Custom scaffold or ring-editing actions need positional chemistry proof; templates and reaction-family names are only scaffolds.
- action_prompt: In `propose_action`, fill `intended_deltas`, `expected_ring_change`, `changed_bonds`, `preserved_anchors`, `mechanistic_evidence`, and optional `family_evidence`. If validation is `proof_required`, reconcile observations, `declared_action`, `proof_obligations`, atom source, tether, and anchors; use `mechanism_interpretation` only as optional support before override or commit.
- avoid: Do not reject only because the reaction name is unregistered, and do not deepen a route through annulation, rearrangement, or ring construction unless the atom-source and site-fidelity proof closes.

### exp_preserve_mature_heteroaryl

- tags: `heteroaryl`, `indole`, `azaindole`, `quinoline`, `benzofuran`, `fused_ring`, `deep_disconnection`, `scaffold_assembly`, `route_plan`
- activation: `heteroaryl`, `indole`, `azaindole`, `quinoline`, `benzofuran`, or `fused_ring`
- one_line: Mature medicinal heteroaryl scaffolds are usually preserved, unless `route_plan` explicitly chooses scaffold assembly with proof.
- action_prompt: If breaking a mature heteroaryl core, first compare late editing against scaffold assembly; proceed only when `route_plan` records ring-construction logic and the action has topology/atom-source proof.
- avoid: Do not force low-confidence ring construction just to reduce CS; also do not over-preserve a core when a proved scaffold-assembly route is the stated plan.

### exp_paal_knorr_deep_ring_warning

- tags: `Paal-Knorr`, `pyrrole`, `indole`, `azaindole`, `ring_construction`, `template_risk`
- one_line: 对成熟杂芳骨架的 Paal-Knorr 深拆默认高风险，常是模板驱动的假深拆信号。
- action_prompt: 先问“这个杂环是否应作为 advanced terminal 保留”，再决定是否尝试 Paal-Knorr。
- avoid: 不要把 `[NH2]` 或不完整小分子表示当作高质量 terminal。

### exp_convergent_sp2_sp2_suzuki

- tags: `convergent`, `sp2_sp2`, `Suzuki`, `biaryl`, `heteroaryl`, `top_level`
- activation: `suzuki`, `sp2_sp2`, or `biaryl`
- one_line: When one sp2-sp2 bond naturally joins two substantial fragments, treat that natural convergence as a reason to compare a Suzuki disconnection before choosing a deeper or less balanced split.
- action_prompt: Compare coupling polarity, site selectivity, and whether the halide/triflate and boron handles are real, stable, and timed appropriately on each fragment.
- avoid: When candidate disconnections are otherwise comparably credible, prefer not to sacrifice a route-coherent convergent bond merely to obtain smaller but less credible precursors.

### exp_snar_electron_poor_heteroaryl

- tags: `SNAr`, `heteroaryl_fluoride`, `electron_poor`, `N_nucleophile`, `late_stage`, `competition`
- one_line: 电子贫化杂芳氟与合适 N-亲核体匹配时，SNAr 可优先于金属 C-N 偶联。
- action_prompt: 检查离去基、邻/对位活化、N-亲核体位阻和竞争亲核位点。
- avoid: 不要在 SNAr 明显匹配时机械转向 Buchwald、Ullmann 或 Chan-Lam。

### exp_reactive_handle_late_install

- tags: `handle_timing`, `halogenation`, `acid_chloride`, `benzyl_bromide`, `organotin`, `compatibility`
- one_line: Distinguish a permanent convergence handle from a temporary high-reactivity handle before deciding when it belongs in the route.
- action_prompt: For halides, organoboron/organotin groups, acid chlorides, benzyl halides, and related handles, compare installation timing against downstream compatibility and the planned convergent event.
- avoid: Prefer not to carry a temporary reactive handle through unnecessary steps; do not remove a permanent coupling handle before its planned use.

### exp_organometallic_precursor_normalization

- tags: `custom_precursor`, `precursor_normalization`, `organometallic_source_obligation`, `organometallic`, `metal_source`, `audit`
- activation: `precursor_normalization`, `organometallic_source_obligation`, or `action.precursor_normalization`
- triggers: `action.precursor_normalization`
- one_line: 有机金属试剂保留在当前反应；其来源提示应另建真实上游步骤，而不是替换当前试剂。
- action_prompt: 看到 precursor_normalization 时，保留 current_reagent 参与当前反应，并把 upstream_source_precursors 当作来源候选；比较直接金属插入、转金属或其他更真实的一步来源后再决定是否建立 continuation。
- avoid: 不要把当前反应所需的 C-metal 试剂替换成有机卤化物和金属后继续提交同一步，不要把来源提示当成唯一机制，也不要把反应性有机金属当作最终简单原料。

### exp_carbon_atom_accounting

- tags: `atom_accounting`, `carbon_source`, `mesyl`, `amide`, `oxidation`, `commit`, `new_c_c_bond`, `atom_source`, `fused_ring`
- one_line: Key atom sources matter more than template names; every new C/N/S/halogen/protecting-group atom needs a source.
- action_prompt: Before commit, state where key C/N/S/halogen/protecting-group atoms come from. For fused-ring rescue, explicitly identify the source of any new C-C bond and whether it comes from tethered atoms, a small molecule, or a named fragment.
- avoid: Do not submit a route where the product gains carbon or a ring bond without a precursor or reagent source.

### exp_multicomponent_complete_precursors

- tags: `multicomponent`, `reductive_amination`, `condensation`, `ring_closure`, `skeleton_imbalance`, `custom_precursor`, `new_c_c_bond`, `atom_source`, `fused_ring`
- activation: `multicomponent`, `reductive_amination`, `condensation`, `ring_closure`, or `skeleton_imbalance`
- one_line: Multicomponent, one-pot, reductive amination, condensation, and ring-closure proposals often omit key small molecules.
- action_prompt: If `skeleton_imbalance` appears, check for missing aldehyde, imine, acid, ylide, metal partner, or other small molecule. For fused-ring rescue, verify the new C-C bond source and whether a single event really accounts for all added atoms.
- avoid: Do not submit a multicomponent or ring-closing step with only the main scaffold precursor when a required small molecule or atom source is missing.

### exp_protection_is_tree_node

- tags: `protection`, `deprotection`, `free_amine`, `phenol`, `acid`, `compatibility`, `commit`
- activation: `protection`, `deprotection`, `free_amine`, `phenol`, or `acid` fact
- one_line: 保护/脱保护是真实路线节点，不是 reasoning 注释。
- action_prompt: 若条件与裸官能团冲突，必须把保护或脱保护作为独立动作/步骤处理。
- avoid: 不要在 commit reasoning 里写“默认已保护”却不进树。

### exp_template_pass_not_enough

- tags: `template_evidence`, `clear`, `forward_validation`, `commit_gate`, `sandbox`
- activation: `sandbox.success`, `sandbox.failure`, or any `validation.*` event
- one_line: Template pass is not proof, and template miss is not disproof; both require chemical audit.
- action_prompt: Before commit, audit mechanism, topology, carbon/atom source, site fidelity, handle timing, and alternatives. If a template misses plausible chemistry, use `route_sketch`/`propose_action` with evidence rather than treating the miss as a verdict.
- avoid: Do not treat template product similarity as a commit reason, and do not treat forward-template tool limits as chemical disproof.

### exp_forward_fail_requires_override

- tags: `forward_validation`, `blocked`, `hard_fail`, `chemical_contradiction`, `system_error`, `commit_gate`, `sandbox`
- one_line: A blocked decision gate is a commit barrier; first distinguish a chemical contradiction from a validator/system error.
- action_prompt: For chemical contradictions, revise the precursor or action. For validator/system errors, rerun or repair validation; do not use `validation_override` to conceal unavailable validation.
- avoid: Do not treat execution completion as chemistry approval, and do not collapse proof_required into blocked.

### exp_advanced_terminal_over_fake_deep

- tags: `advanced_terminal`, `terminal`, `deep_disconnection`, `template_risk`, `buyability`, `proof_obligation`, `terminal_rescue`
- activation: `stage.terminal`, `decision.accept_terminal`, `action.terminal_acceptance`, or `strategy.advanced_terminal_rescue_requested`
- one_line: An honest advanced terminal is better than fake deep disconnection, but only after credible rescue attempts cannot be repaired into a real step.
- action_prompt: Before accepting, state which bounded rescue was tried or considered, why no credible next chemical event can be defined or repaired, and why stopping is higher quality than further speculative disconnection.
- avoid: Do not use tool or template failure alone as terminal rationale; terminal is justified only when deeper chemistry is speculative or no credible event can be repaired.

### exp_custom_precursor_after_rejection

- tags: `custom_precursor`, `propose_action`, `action_rejection`, `LLM_proposed`, `intentional_attachment_placeholder`, `audit`
- activation: `custom_precursor`, `llm_proposed`, or `intentional_attachment_placeholder`
- one_line: A complete LLM-designed one-step action is a peer hypothesis, not only a fallback after system-action failure; it must pass the same sandbox audit.
- action_prompt: Use `propose_action` for a stronger different same-site reaction, an unlisted disconnection, or completion of an intentional `'*'` system preview. Completing that preview realizes the same system disconnection and is not template rejection. Lead with the positive chemical case: complete precursors and reagents, reaction/site, mechanism, atom sources, selectivity, topology/site fidelity, route coherence, and why the proposal is one real chemical event. Use concise comparison rationale only to explain why this candidate is worth testing; cite rejected action ids and reasons only when actually rejecting those actions.
- avoid: Do not use custom precursors to bypass action comparison, `try_action`, commit audit, or multi-step strategy continuation. Do not compare a placeholder preview and its completed realization as separate chemistry alternatives.

### exp_route_sketch_for_weak_action_space

- tags: `strategic_rescue`, `action_space_weak`, `route_sketch`, `custom_precursor`, `advanced_terminal`
- activation: `action_space_weak`, `route_sketch`, or the listed strategy events
- triggers: `strategy.action_space_weak`, `strategy.route_sketch_requested`, `strategy.route_sketch_active`
- one_line: Use `route_sketch` when local actions do not express the best route hypothesis or when an LLM design changes strategy or spans multiple events.
- action_prompt: Lead with the positive chemical case for the route hypothesis: state the target core, usable handles, key disconnection, precursor/reagent logic, mechanism, atom sources, selectivity, and next executable step. Compare listed actions only as secondary selection provenance. A simple complete one-step peer action may go directly through `propose_action`; a multi-event or route-thesis change should use `route_sketch` before converting exactly one event to `propose_action` or `try_action`.
- avoid: Do not turn `route_sketch` into a permission gate for every custom action, bypass sandbox, or compress multiple real events into one action.

### exp_global_route_plan_persistence

- tags: `route_plan`, `strategic_rescue`, `audit`
- triggers: `strategy.route_plan_active`
- one_line: An active `route_plan` is the current synthesis thesis; local evidence should support, falsify, enrich, or materially revise it.
- action_prompt: Read `route_plan_brief` while comparing this site or action. State how the local choice preserves or changes the planned disconnection, precursor logic, sequence, handle timing, scaffold policy, or selectivity strategy.
- avoid: Do not let local template convenience silently replace the recorded route thesis.

### exp_route_plan_revision

- tags: `route_plan`, `strategic_rescue`, `action_space_weak`, `audit`
- triggers: `strategy.route_plan_revised`
- one_line: 发现更优路线或原 plan 与证据冲突时，应短修订 route_plan，而不是静默漂移。
- action_prompt: 用 route_plan(...) 记录 revision_reason、更新 thesis、关键断键和保留结构，再继续标准 action/sandbox loop。
- avoid: 不要把旧 plan 和新选择混在 reasoning 里却不更新状态。

### exp_route_mode_triage_before_first_plan

- tags: `route_mode`, `route_plan`, `top_level`, `late_functionalization`, `scaffold_assembly`, `electronic_state_strategy`, `strategic_rescue`
- triggers: `stage.context_compact`, `stage.route_plan`, `strategy.route_mode_triage`
- one_line: Before the first complex-target plan, classify the route hypothesis instead of jumping directly to a local disconnection.
- action_prompt: Compare late FGI/editing, scaffold assembly, electronic-state strategy, and hybrid routes; write the current choice plus evidence, risks, and revision triggers into route_plan.
- avoid: Do not treat the listed local action-space as the complete retrosynthesis space, and do not let a route-mode decision remain only in hidden reasoning.

### exp_electron_poor_pyridine_electronic_state_strategy

- tags: `electron_poor`, `electron_poor_pyridine`, `pyridine`, `heteroaryl`, `scaffold_assembly`, `electronic_state_strategy`
- triggers: `strategy.route_mode_triage`
- one_line: Highly substituted electron-poor pyridines may need scaffold assembly or non-final electronic-state strategy, not automatic late FGI.
- action_prompt: For fused or highly deactivated pyridyl cores, compare late FGI with scaffold assembly through pyridone/lactam, dihydropyridine, imine/enamine, or other non-final electronic states before final aromatization/halogenation; record the chosen rescue direction in `route_plan`.
- avoid: Do not accept an advanced pyridine terminal unless the route explains how the difficult pyridyl/fused core is actually constructed.

### exp_advanced_terminal_short_route_rescue

- tags: `advanced_terminal`, `terminal_rescue`, `strategic_rescue`, `route_sketch`, `custom_precursor`, `proof_required`, `proof_obligation`, `decision_gate`, `proof_obligations`
- triggers: `stage.terminal`, `decision.accept_terminal`, `action.terminal_acceptance`, `strategy.advanced_terminal_rescue_requested`
- one_line: Before accepting an advanced terminal, ask whether this small target has a bounded mini-route from simpler precursors.
- action_prompt: Look for 1-3 mechanistically selective steps from simpler precursors, FG rollback, oxidation-state adjustment, protection/deprotection, or regio/chemoselectivity sources, then identify one next executable event. If a mini-route has multiple steps, commit the first credible event and let `strategy_continuation` expose the next precursor.
- avoid: Do not accept after `terminal_review` just because the first mini-route step needs proof or one sandbox attempt exists; accept only when no credible mini-route step can be defined or repaired.

### exp_chemist_guidance_is_direction_not_evidence

- tags: `chemist_guidance`, `reaction_direction`, `site_fidelity`, `custom_precursor`, `audit`
- activation: any `chemist.*` event
- triggers: `chemist.directive`, `chemist.site_hint`, `chemist.reaction_hint`, `chemist.precursor_hint`, `chemist.terminal_hint`
- one_line: 合成人员指导是高优先级路线方向，但不是验证证据。
- action_prompt: 把自然语言指导转成 site/reaction/precursor 约束；若系统没有对应 action，propose_action 后再 try_action。
- avoid: 不要因为专家指定方向就跳过候选比较、sandbox 和 commit audit。
