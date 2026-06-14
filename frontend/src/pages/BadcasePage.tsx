import { useEffect, useMemo, useState } from "react";
import { Bug, Database, BookText } from "lucide-react";
import { listBadcases, buildBadcaseDataset, listBadcaseRules, type Badcase } from "../api/client";
import { Badge, Button, Drawer, EmptyState, PageHeader, Select, StatusBadge, TableShell } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";
import { BadcaseAnnotateDrawer } from "./BadcaseAnnotateDrawer";

const STATUS_OPTIONS = [
  { v: "", l: "全部状态" },
  { v: "reported", l: "待标注" },
  { v: "annotated", l: "已标注" },
  { v: "used", l: "已用" },
];
const TASK_LABEL: Record<string, string> = { classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索" };

export function BadcasePage() {
  const [items, setItems] = useState<Badcase[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [sel, setSel] = useState<number[]>([]);
  const [anno, setAnno] = useState<Badcase | null>(null);
  const [busy, setBusy] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rules, setRules] = useState<any[]>([]);

  const openRules = () => {
    setRulesOpen(true);
    if (rules.length === 0) listBadcaseRules().then(setRules).catch(() => toastError("加载规则失败"));
  };

  const reload = () =>
    listBadcases(status ? { status } : undefined).then(setItems);

  useEffect(() => {
    setLoading(true);
    reload().finally(() => setLoading(false));
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const groups = useMemo(() => {
    const m = new Map<string, Badcase[]>();
    for (const b of items) {
      const k = `${b.model_name ?? b.model_version_id} · V${b.model_version_label ?? "?"}`;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(b);
    }
    return [...m.entries()];
  }, [items]);

  const toggle = (id: number) =>
    setSel(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]));

  const selected = items.filter(b => sel.includes(b.id));
  const canBuild =
    selected.length > 0 &&
    selected.every(b => b.status === "annotated" || b.annotation != null) &&
    new Set(selected.map(b => b.task_type)).size === 1;

  const build = () => {
    setBusy(true);
    buildBadcaseDataset(sel)
      .then(res => {
        toastSuccess(`已生成训练集 ${res.dataset_name}(${res.row_count} 行)`);
        setSel([]);
        reload();
        navigate(`/training?badcase_version=${res.version_id}`);
      })
      .catch(() => toastError("生成失败(需都已标注且同一类型)"))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <PageHeader
        title="Badcase"
        subtitle="外部上报的坏例按模型版本自动归类;标注后可一键生成 badcase- 训练集并去修复。"
        actions={
          <Button variant="primary" disabled={!canBuild} loading={busy} onClick={build}>
            <Database size={16} /> 生成训练集并去修复 ({sel.length})
          </Button>
        }
      />

      <div className="mb-4 flex items-center gap-2.5">
        <Button onClick={openRules}><BookText size={15} /> 查看上报规则</Button>
        <span className="ml-2 text-[13px] text-slate-500">状态</span>
        <Select
          className="h-9 w-40"
          value={status}
          onChange={e => setStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map(s => (
            <option key={s.v} value={s.v}>
              {s.l}
            </option>
          ))}
        </Select>
      </div>

      {items.length === 0 && !loading ? (
        <EmptyState
          icon={<Bug size={22} />}
          title="还没有 Badcase"
          hint="外部业务通过 API 上报后会自动出现在这里。"
        />
      ) : (
        groups.map(([title, rows]) => (
          <div key={title} className="mb-5">
            <div className="mb-2 flex items-center gap-2 text-[14px] font-medium text-slate-800">
              <Bug size={15} className="text-slate-400" />
              {title}
              <span className="text-slate-400">({rows.length})</span>
            </div>
            <TableShell
              head={
                <>
                  <th className="w-10"></th>
                  <th className="w-14">#</th>
                  <th>输入</th>
                  <th>模型推理</th>
                  <th>状态</th>
                  <th>标注</th>
                  <th className="w-24 text-right"></th>
                </>
              }
              empty={false}
              loading={false}
            >
              {rows.map(b => (
                <tr key={b.id}>
                  <td>
                    <input
                      type="checkbox"
                      className="accent-brand-500"
                      checked={sel.includes(b.id)}
                      onChange={() => toggle(b.id)}
                    />
                  </td>
                  <td className="font-mono text-slate-400">{b.id}</td>
                  <td className="max-w-xs truncate text-slate-700">
                    {JSON.stringify(b.input)}
                  </td>
                  <td className="max-w-xs truncate text-slate-500">
                    {JSON.stringify(b.inference)}
                  </td>
                  <td>
                    <StatusBadge status={b.status} />
                  </td>
                  <td className="max-w-[160px] truncate text-slate-500">
                    {b.annotation ? (
                      JSON.stringify(b.annotation)
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="text-right">
                    <Button size="sm" onClick={() => setAnno(b)}>
                      标注
                    </Button>
                  </td>
                </tr>
              ))}
            </TableShell>
          </div>
        ))
      )}

      <BadcaseAnnotateDrawer
        badcase={anno}
        onClose={() => setAnno(null)}
        onSaved={() => {
          setAnno(null);
          reload();
        }}
      />

      <Drawer
        open={rulesOpen}
        onClose={() => setRulesOpen(false)}
        title="上报规则"
        subtitle="每种模型类型的 Badcase 上报契约;外部业务用带 badcase:report 的 API Key 调用 POST /badcase/report。"
        width="max-w-2xl"
      >
        <div className="flex flex-col gap-4">
          {rules.map(r => (
            <div key={r.task_type} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2">
                <Badge tone="blue">{TASK_LABEL[r.task_type] ?? r.task_type}</Badge>
                <span className="font-mono text-[12px] text-slate-500">{r.task_type}</span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-[12.5px]">
                <div><div className="label mb-1">input 字段</div><div className="font-mono text-slate-600">{(r.input_keys ?? []).join(", ")}</div></div>
                <div><div className="label mb-1">annotation 字段(系统内标注)</div><div className="font-mono text-slate-600">{(r.annotation_keys ?? []).join(", ")}</div></div>
              </div>
              <div className="mt-3">
                <div className="label mb-1">上报示例</div>
                <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] text-slate-100">{`curl -X POST '$API/badcase/report' \\
  -H 'Content-Type: application/json' \\
  -H 'X-Api-Key: <badcase:report key>' \\
  -d '${JSON.stringify({ model_version_id: 1, input: r.example?.input, inference: r.example?.inference })}'`}</pre>
              </div>
            </div>
          ))}
        </div>
      </Drawer>
    </>
  );
}
