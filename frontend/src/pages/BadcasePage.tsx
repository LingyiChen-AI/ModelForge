import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { Bug, BookText, PencilLine } from "lucide-react";
import { listBadcaseSummaryPaged, listBadcaseRules, type BadcaseSummary } from "../api/client";
import { Badge, Button, EmptyState, PageHeader, Pagination, TableShell } from "../ui";
import { toastError } from "../toast";
import { navigate } from "../router";
import { BadcaseRulesDrawer } from "./BadcaseRulesDrawer";

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索",
};

export function BadcasePage() {
  const [rows, setRows] = useState<BadcaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rules, setRules] = useState<any[]>([]);

  const openRules = () => {
    setRulesOpen(true);
    if (rules.length === 0) listBadcaseRules().then(setRules).catch(() => toastError("加载规则失败"));
  };

  useEffect(() => {
    setLoading(true);
    listBadcaseSummaryPaged({ page, page_size: pageSize })
      .then(res => { setRows(res.items); setTotal(res.total); })
      .catch(() => toastError("加载失败")).finally(() => setLoading(false));
  }, [page, pageSize]);

  return (
    <div>
      <PageHeader
        title="Badcase"
        subtitle="按模型版本汇总上报的坏例;点「标注」进入工作台逐条标注,标注后可生成 badcase- 训练集修复。"
        actions={<Button variant="subtle" onClick={openRules}><BookText size={16} /> 查看上报规则</Button>}
      />

      <TableShell
        loading={loading}
        empty={rows.length === 0}
        head={
          <><th className="px-4 py-2.5 text-left font-medium">模型</th>
          <th className="px-4 py-2.5 text-left font-medium">类型</th>
          <th className="px-4 py-2.5 text-left font-medium">上报</th>
          <th className="px-4 py-2.5 text-left font-medium">已标注</th>
          <th className="px-4 py-2.5 text-left font-medium">已生成训练集</th>
          <th className="px-4 py-2.5 text-left font-medium">已修复</th>
          <th className="px-4 py-2.5 text-right font-medium">操作</th></>
        }
      >
        {rows.length === 0 ? (
          <EmptyState icon={<Bug size={20} />} title="暂无 badcase" hint="通过 API 上报后,这里按模型版本归类。" />
        ) : (
          rows.map(r => (
            <tr key={r.model_version_id} className="border-t border-slate-100">
              <td className="px-4 py-3">
                <span className="font-medium text-slate-800">{r.model_name ?? r.model_version_id}</span>
                <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">V{r.model_version_label ?? "?"}</span>
              </td>
              <td className="px-4 py-3"><Badge tone="gray">{TASK_LABEL[r.task_type] ?? r.task_type}</Badge></td>
              <td className="px-4 py-3 text-slate-700">{r.reported}</td>
              <td className="px-4 py-3 text-slate-700">{r.annotated}{r.pending > 0 && <span className="ml-1 text-[12px] text-amber-600">(待 {r.pending})</span>}</td>
              <td className="px-4 py-3 text-slate-700">{r.used}</td>
              <td className="px-4 py-3">
                {r.fixed > 0 ? (
                  <div className="flex flex-wrap items-center gap-1">
                    {r.fixed_versions.map(v => <Badge key={v.version_label} tone="green">V{v.version_label} 修复 {v.count} 条</Badge>)}
                    <span className="text-[12px] text-slate-500">共 {r.fixed}</span>
                  </div>
                ) : <span className="text-slate-400">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                <Button size="sm" variant="primary" onClick={() => navigate(`/badcase/annotate/${r.model_version_id}`)}>
                  <PencilLine size={14} /> 标注
                </Button>
              </td>
            </tr>
          ))
        )}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <BadcaseRulesDrawer open={rulesOpen} onClose={() => setRulesOpen(false)} rules={rules} />
    </div>
  );
}
