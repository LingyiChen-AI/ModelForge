import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Database } from "lucide-react";
import {
  listBadcases, listBadcaseSummary, annotateBadcase, buildBadcaseDataset,
  type Badcase, type BadcaseSummary,
} from "../api/client";
import { Button, PageHeader, EmptyState } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";
import { BadcaseAnnotateForm, annotationValid } from "./BadcaseAnnotateForm";

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索",
};

export function BadcaseAnnotateWorkbench({ modelVersionId }: { modelVersionId: number }) {
  const [queue, setQueue] = useState<Badcase[]>([]);
  const [sum, setSum] = useState<BadcaseSummary | null>(null);
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const reloadSummary = () =>
    listBadcaseSummary().then(s => setSum(s.find(x => x.model_version_id === modelVersionId) ?? null));

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listBadcases({ model_version_id: modelVersionId, status: "reported" }),
      reloadSummary(),
    ]).then(([q]) => setQueue(q)).finally(() => setLoading(false));
  }, [modelVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = queue[0] ?? null;
  useEffect(() => { setVal(current?.annotation ?? {}); }, [current]);

  const valid = current ? annotationValid(current.task_type, val) : false;

  const save = () => {
    if (!current) return;
    setBusy(true);
    annotateBadcase(current.id, val)
      .then(() => {
        toastSuccess("已标注");
        setQueue(q => q.slice(1));
        reloadSummary();
      })
      .catch(() => toastError("标注失败"))
      .finally(() => setBusy(false));
  };

  const build = async () => {
    setBusy(true);
    try {
      const cases = await listBadcases({ model_version_id: modelVersionId, status: "annotated" });
      if (cases.length === 0) { toastError("没有已标注未生成的 badcase"); return; }
      const res = await buildBadcaseDataset(cases.map(c => c.id));
      toastSuccess(`已生成训练集 ${res.dataset_name}`);
      reloadSummary();
    } catch {
      toastError("生成训练集失败");
    } finally {
      setBusy(false);
    }
  };

  const title = useMemo(
    () => sum ? `${sum.model_name ?? sum.model_version_id} · V${sum.model_version_label ?? "?"}` : "标注工作台",
    [sum],
  );

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={sum ? `${TASK_LABEL[sum.task_type] ?? sum.task_type} · 已标注 ${sum.annotated} / 待标注 ${sum.pending}` : "标注工作台"}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="subtle" onClick={() => navigate("/badcase")}><ArrowLeft size={16} /> 返回</Button>
            <Button variant="primary" disabled={busy || !(sum && sum.annotated > sum.used)} onClick={build}>
              <Database size={16} /> 生成 badcase- 训练集
            </Button>
          </div>
        }
      />
      {loading ? null : current ? (
        <div className="max-w-3xl rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-3 text-[13px] text-slate-500">
            Badcase #{current.id} · 剩余待标注 {queue.length}
          </div>
          <BadcaseAnnotateForm badcase={current} val={val} onChange={setVal} />
          <div className="mt-5 flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setQueue(q => [...q.slice(1), q[0]])}>
              跳过
            </Button>
            <Button variant="primary" disabled={!valid} loading={busy} onClick={save}>
              <Check size={16} /> 保存并下一条
            </Button>
          </div>
        </div>
      ) : (
        <EmptyState icon={<Check size={20} />} title="全部标注完成" hint="该模型暂无待标注 badcase。" />
      )}
    </div>
  );
}
