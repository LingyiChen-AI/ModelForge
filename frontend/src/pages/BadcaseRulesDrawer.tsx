import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Drawer } from "../ui";
import { toastSuccess } from "../toast";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索",
};

// input sub-fields per task type (for the request-parameter table)
const INPUT_FIELDS: Record<string, { name: string; type: string; desc: string }[]> = {
  classification: [{ name: "text", type: "string", desc: "待分类文本" }],
  ner: [{ name: "tokens", type: "string[]", desc: "分词/分字后的 token 序列" }],
  pair: [{ name: "text_a", type: "string", desc: "句子 A" }, { name: "text_b", type: "string", desc: "句子 B" }],
  embedding: [{ name: "query", type: "string", desc: "查询文本" }, { name: "candidates", type: "string[]", desc: "候选文本列表(非空)" }],
};

const RESPONSE_FIELDS: { name: string; type: string; desc: string }[] = [
  { name: "id", type: "int", desc: "badcase ID" },
  { name: "model_version_id", type: "int", desc: "所属模型版本" },
  { name: "task_type", type: "string", desc: "任务类型(由模型版本决定)" },
  { name: "input", type: "object", desc: "上报的模型输入" },
  { name: "inference", type: "object", desc: "上报的模型推理结果" },
  { name: "category", type: "string | null", desc: "自动归类(分类任务=推理标签)" },
  { name: "status", type: "string", desc: "reported(待标注)/ annotated / used" },
  { name: "source", type: "string", desc: "上报来源(API Key 名称)" },
  { name: "source_ref", type: "string | null", desc: "业务侧唯一标识" },
  { name: "fixed_by", type: "array", desc: "已修复的模型版本列表" },
  { name: "created_at", type: "string", desc: "上报时间" },
];

function reqBody(rule: any) {
  return {
    model_version_id: 1,
    input: rule?.example?.input ?? {},
    inference: rule?.example?.inference ?? {},
    source_ref: "your-business-id-001",
  };
}
function curlOf(rule: any) {
  const body = JSON.stringify(reqBody(rule), null, 2);
  return `curl -X POST ${API_BASE}/badcase/report \\
  -H "Content-Type: application/json" \\
  -H "X-Api-Key: <your-api-key>" \\
  -d '${body}'`;
}
function pyOf(rule: any) {
  const body = JSON.stringify(reqBody(rule), null, 4).replace(/\n/g, "\n    ");
  return `import requests

resp = requests.post(
    "${API_BASE}/badcase/report",
    headers={"X-Api-Key": "<your-api-key>"},
    json=${body},
)
resp.raise_for_status()
print(resp.json())`;
}

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
    toastSuccess("已复制");
  };
  return (
    <div className="relative">
      <button
        onClick={copy}
        className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md bg-slate-700/80 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-600 cursor-pointer"
      >
        {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "已复制" : "复制"}
      </button>
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 pr-16 font-mono text-[12px] leading-relaxed text-slate-100">{code}</pre>
    </div>
  );
}

function FieldTable({ rows, firstCol }: { rows: { name: string; type: string; desc: string; required?: string }[]; firstCol: string }) {
  const showReq = rows.some(r => r.required != null);
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full text-[12.5px]">
        <thead>
          <tr className="bg-slate-50/70 text-left text-slate-500">
            <th className="px-3 py-2 font-medium">{firstCol}</th>
            <th className="px-3 py-2 font-medium">类型</th>
            {showReq && <th className="px-3 py-2 font-medium">必填</th>}
            <th className="px-3 py-2 font-medium">说明</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.name} className="border-t border-slate-100">
              <td className="px-3 py-1.5 font-mono text-slate-700">{r.name}</td>
              <td className="px-3 py-1.5 font-mono text-slate-500">{r.type}</td>
              {showReq && <td className="px-3 py-1.5 text-slate-600">{r.required}</td>}
              <td className="px-3 py-1.5 text-slate-600">{r.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[12px] font-medium text-slate-500">{title}</div>
      {children}
    </div>
  );
}

function CodeTabs({ tabs }: { tabs: { key: string; label: string; code: string }[] }) {
  const [active, setActive] = useState(tabs[0]?.key);
  const current = tabs.find(t => t.key === active) ?? tabs[0];
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            className={`rounded-md px-2.5 py-1 text-[12px] font-medium cursor-pointer transition-colors ${
              t.key === current.key
                ? "bg-slate-800 text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <CodeBlock code={current.code} />
    </div>
  );
}

function RuleCard({ rule }: { rule: any }) {
  const t: string = rule.task_type;
  const inputRows = (INPUT_FIELDS[t] ?? []).map(f => ({
    name: `input.${f.name}`, type: f.type, required: "是", desc: f.desc,
  }));
  const paramRows = [
    { name: "model_version_id", type: "int", required: "是", desc: "目标模型版本 ID(决定任务类型)" },
    { name: "input", type: "object", required: "是", desc: "模型输入,字段见下" },
    ...inputRows,
    { name: "inference", type: "object", required: "否", desc: "模型推理结果,用于留存对照" },
    { name: "source_ref", type: "string", required: "否", desc: "业务侧唯一标识,(source, source_ref) 去重" },
  ];
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-[15px] font-semibold text-slate-800">{TASK_LABEL[t] ?? t}</span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">{t}</span>
      </div>
      <div className="flex flex-col gap-4">
        <Section title="请求参数"><FieldTable rows={paramRows} firstCol="字段" /></Section>
        <CodeTabs tabs={[
          { key: "curl", label: "cURL", code: curlOf(rule) },
          { key: "python", label: "Python", code: pyOf(rule) },
        ]} />
        <Section title="响应字段(data)"><FieldTable rows={RESPONSE_FIELDS} firstCol="字段" /></Section>
      </div>
    </div>
  );
}

export function BadcaseRulesDrawer({ open, onClose, rules }: { open: boolean; onClose: () => void; rules: any[] }) {
  return (
    <Drawer
      open={open} onClose={onClose} width="max-w-[70vw]"
      title="上报规则与接入文档"
      subtitle="各任务类型的上报参数、cURL / Python 示例与响应字段。统一接口 POST /badcase/report,需 X-Api-Key(badcase:report 权限)。"
    >
      <div className="flex flex-col gap-5">
        {rules.map(r => <RuleCard key={r.task_type} rule={r} />)}
      </div>
    </Drawer>
  );
}
