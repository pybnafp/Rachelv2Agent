export type StageKey = "init" | "planning" | "strategy" | "finalizing" | "exporting" | "done";

export const STAGES: { key: StageKey; label: string }[] = [
  { key: "init", label: "初始化" },
  { key: "planning", label: "路线规划" },
  { key: "strategy", label: "策略调整" },
  { key: "finalizing", label: "收尾" },
  { key: "exporting", label: "导出" },
  { key: "done", label: "完成" },
];

const COMMAND_STAGE: Record<string, StageKey> = {
  init: "init",
  next: "planning",
  reaction_sites: "planning",
  explore_site: "planning",
  try_action: "planning",
  propose_action: "planning",
  sandbox_list: "planning",
  sandbox_clear: "planning",
  select: "planning",
  commit: "planning",
  accept: "planning",
  review_terminal: "planning",
  skip: "planning",
  route_plan: "strategy",
  route_sketch: "strategy",
  guide: "strategy",
  finalize: "finalizing",
  export: "exporting",
  report: "exporting",
  finish: "done",
};

/** 按「最后一条可识别命令」判定当前阶段；空/全部未知 → init */
export function stageOf(commands: string[]): StageKey {
  let stage: StageKey = "init";
  for (const c of commands) {
    const s = COMMAND_STAGE[c];
    if (s) stage = s;
  }
  return stage;
}
