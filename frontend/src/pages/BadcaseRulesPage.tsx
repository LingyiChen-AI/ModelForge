import { useEffect, useState } from "react";
import { listBadcaseRules } from "../api/client";
import { Badge, PageHeader } from "../ui";
import { toastError } from "../toast";

const TASK_LABEL: Record<string, string> = {
  classification: "分类",
  ner: "序列标注",
  pair: "句对",
  embedding: "向量检索",
};

export function BadcaseRulesPage() {
  const [rules, setRules] = useState<any[]>([]);

  useEffect(() => {
    listBadcaseRules()
      .then(setRules)
      .catch(() => toastError("加载失败"));
  }, []);

  return (
    <>
      <PageHeader
        title="上报规则"
        subtitle="每种模型类型的 Badcase 上报契约;外部业务用带 badcase:report 的 API Key 调用 POST /badcase/report。"
      />
      <div className="flex flex-col gap-4">
        {rules.map(r => (
          <div key={r.task_type} className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-3 flex items-center gap-2">
              <Badge tone="blue">{TASK_LABEL[r.task_type] ?? r.task_type}</Badge>
              <span className="font-mono text-[12px] text-slate-500">{r.task_type}</span>
            </div>
            <div className="grid grid-cols-2 gap-4 text-[12.5px]">
              <div>
                <div className="label mb-1">input 字段</div>
                <div className="font-mono text-slate-600">{(r.input_keys ?? []).join(", ")}</div>
              </div>
              <div>
                <div className="label mb-1">annotation 字段(系统内标注)</div>
                <div className="font-mono text-slate-600">{(r.annotation_keys ?? []).join(", ")}</div>
              </div>
            </div>
            <div className="mt-3">
              <div className="label mb-1">上报示例</div>
              <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11.5px] text-slate-100">
                {`curl -X POST '$API/badcase/report' \\
  -H 'Content-Type: application/json' \\
  -H 'X-Api-Key: <badcase:report key>' \\
  -d '${JSON.stringify({
    model_version_id: 1,
    input: r.example?.input ?? {},
    inference: r.example?.inference ?? {},
  })}'`}
              </pre>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
