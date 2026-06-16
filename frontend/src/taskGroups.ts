// Shared task-type labels + a helper to group flat dropdown lists (model versions,
// dataset versions) into sorted <optgroup>s so the selects don't look like a jumble.

export const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量",
};

// the order task groups appear in
const TASK_ORDER = ["classification", "ner", "pair", "embedding"];

export type TaskGroup<T> = { task: string; label: string; items: T[] };

/**
 * Group items by task type, with groups ordered by TASK_ORDER and items sorted
 * within each group (by name asc, then version desc when provided).
 */
export function groupByTask<T>(
  items: T[],
  getTask: (x: T) => string,
  getName?: (x: T) => string,
  getVersion?: (x: T) => number | string | undefined,
): TaskGroup<T>[] {
  const groups = new Map<string, T[]>();
  for (const it of items) {
    const t = getTask(it);
    if (!groups.has(t)) groups.set(t, []);
    groups.get(t)!.push(it);
  }
  for (const arr of groups.values()) {
    arr.sort((a, b) => {
      if (getName) {
        const c = getName(a).localeCompare(getName(b), "zh");
        if (c !== 0) return c;
      }
      if (getVersion) return Number(getVersion(b) ?? 0) - Number(getVersion(a) ?? 0);
      return 0;
    });
  }
  const rank = (t: string) => { const i = TASK_ORDER.indexOf(t); return i < 0 ? 99 : i; };
  return [...groups.keys()]
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map(t => ({ task: t, label: TASK_LABEL[t] ?? t, items: groups.get(t)! }));
}
