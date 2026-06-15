import { type Badcase } from "../api/client";
import { Button, Field, Input, Select } from "../ui";

export function annotationValid(t: string, val: Record<string, any>): boolean {
  return Boolean(
    (t === "classification" && val.label) ||
    (t === "pair" && (val.label === "0" || val.label === "1")) ||
    (t === "ner" && Array.isArray(val.tags) && val.tags.length > 0) ||
    (t === "embedding" && Array.isArray(val.pos) && val.pos.length > 0),
  );
}

export function BadcaseAnnotateForm({
  badcase,
  val,
  onChange,
  labelOptions = [],
}: {
  badcase: Badcase;
  val: Record<string, any>;
  onChange: (v: Record<string, any>) => void;
  labelOptions?: string[];   // model's label space; classification renders these as a dropdown
}) {
  const t = badcase.task_type;
  const set = (k: string, v: any) => onChange({ ...val, [k]: v });
  const candidates: string[] = badcase.input?.candidates ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Field label="模型输入">
        <pre className="rounded-lg bg-slate-50 p-2 font-mono text-[12px] text-slate-600 whitespace-pre-wrap break-all">
          {JSON.stringify(badcase.input, null, 2)}
        </pre>
      </Field>
      <Field label="模型推理(错误)">
        <pre className="rounded-lg bg-slate-50 p-2 font-mono text-[12px] text-slate-500 whitespace-pre-wrap break-all">
          {JSON.stringify(badcase.inference, null, 2)}
        </pre>
      </Field>

      {t === "classification" && (
        <Field label="正确标签 label">
          {labelOptions.length > 0 ? (
            <Select value={val.label ?? ""} onChange={e => set("label", e.target.value)}>
              <option value="">选择标签…</option>
              {labelOptions.map(l => <option key={l} value={l}>{l}</option>)}
            </Select>
          ) : (
            <Input value={val.label ?? ""} onChange={e => set("label", e.target.value)} placeholder="如 售后服务" />
          )}
        </Field>
      )}

      {t === "pair" && (
        <Field label="正确标签(相似 / 不相似)">
          <Select value={val.label ?? ""} onChange={e => set("label", e.target.value)}>
            <option value="">选择…</option>
            <option value="1">1 · 相似</option>
            <option value="0">0 · 不相似</option>
          </Select>
        </Field>
      )}

      {t === "ner" && (
        <Field label="正确 tags(逗号分隔,与 tokens 等长)">
          <Input
            value={(val.tags ?? []).join(",")}
            onChange={e => set("tags", e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean))}
            placeholder="B-PER,I-PER,O,B-LOC,I-LOC"
          />
        </Field>
      )}

      {t === "embedding" && (
        <Field label="逐个标注候选(pos=相关 / neg=不相关)">
          <div className="flex flex-col gap-1.5">
            {candidates.map(cand => {
              const inPos = ((val.pos ?? []) as string[]).includes(cand);
              const inNeg = ((val.neg ?? []) as string[]).includes(cand);
              const mark = (key: "pos" | "neg") => {
                const other = key === "pos" ? "neg" : "pos";
                onChange({
                  ...val,
                  [key]: [...new Set([...((val[key] ?? []) as string[]), cand])],
                  [other]: ((val[other] ?? []) as string[]).filter(x => x !== cand),
                });
              };
              return (
                <div key={cand} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
                  <span className="flex-1 truncate text-[13px] text-slate-700">{cand}</span>
                  <Button size="sm" variant={inPos ? "primary" : "subtle"} onClick={() => mark("pos")}>相关</Button>
                  <Button size="sm" variant={inNeg ? "danger" : "subtle"} onClick={() => mark("neg")}>不相关</Button>
                </div>
              );
            })}
          </div>
        </Field>
      )}
    </div>
  );
}
