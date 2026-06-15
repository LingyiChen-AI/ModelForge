import { type Badcase } from "../api/client";
import { Button, Field, Input, Select } from "../ui";

// a labeled key→value row inside a panel
function KV({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 text-[13px]">
      <span className="w-16 shrink-0 text-slate-400">{k}</span>
      <span className="min-w-0 flex-1 break-words text-slate-700">{children}</span>
    </div>
  );
}
function Panel({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col gap-1.5 rounded-lg border border-slate-200 bg-slate-50/60 p-3">{children}</div>;
}
const PAIR_LABEL = (l: any) => (String(l) === "1" ? "相似" : String(l) === "0" ? "不相似" : String(l ?? "—"));

// parsed (non-JSON) display of the reported model input, per task type
function InputView({ b }: { b: Badcase }) {
  const i = b.input ?? {};
  if (b.task_type === "classification") return <Panel><KV k="样本">{i.text}</KV></Panel>;
  if (b.task_type === "pair") return <Panel><KV k="句子 A">{i.text_a}</KV><KV k="句子 B">{i.text_b}</KV></Panel>;
  if (b.task_type === "ner")
    return <Panel><KV k="样本">{(i.tokens ?? []).join("")}</KV></Panel>;
  if (b.task_type === "embedding")
    return (
      <Panel>
        <KV k="查询">{i.query}</KV>
        <KV k="候选">
          <div className="flex flex-col gap-1">
            {(i.candidates ?? []).map((c: string, idx: number) => (
              <span key={idx} className="rounded bg-white px-2 py-1 ring-1 ring-slate-200">{c}</span>
            ))}
          </div>
        </KV>
      </Panel>
    );
  return <Panel><pre className="whitespace-pre-wrap break-all font-mono text-[12px] text-slate-600">{JSON.stringify(i, null, 2)}</pre></Panel>;
}

// parsed display of the (wrong) model inference, per task type
function InferenceView({ b }: { b: Badcase }) {
  const f = b.inference ?? {};
  const score = f.score != null ? <span className="ml-2 text-slate-400">置信度 {Number(f.score).toFixed(3)}</span> : null;
  if (b.task_type === "classification")
    return <Panel><KV k="预测标签"><span className="font-medium text-rose-600">{f.label ?? "—"}</span>{score}</KV></Panel>;
  if (b.task_type === "pair")
    return <Panel><KV k="预测"><span className="font-medium text-rose-600">{PAIR_LABEL(f.label)}</span>{score}</KV></Panel>;
  if (b.task_type === "ner") {
    const tokens: string[] = b.input?.tokens ?? [];
    const tags: string[] = f.tags ?? [];
    return (
      <Panel>
        <div className="flex flex-wrap gap-1">
          {tokens.map((tok, idx) => {
            const tag = tags[idx] ?? "O";
            const ent = tag !== "O";
            return (
              <span key={idx} className={"rounded px-1 py-0.5 text-[13px] " + (ent ? "bg-rose-50 text-rose-600 ring-1 ring-rose-200" : "text-slate-600")}>
                {tok}{ent && <sub className="ml-0.5 text-[9px] text-rose-400">{tag}</sub>}
              </span>
            );
          })}
        </div>
      </Panel>
    );
  }
  if (b.task_type === "embedding") {
    const ranked: { text: string; score?: number }[] = f.ranked ?? [];
    return (
      <Panel>
        <KV k="排序">
          <div className="flex flex-col gap-1">
            {ranked.length === 0 ? <span className="text-slate-400">—</span> : ranked.map((r, idx) => (
              <span key={idx} className="flex items-center justify-between gap-2 rounded bg-white px-2 py-1 ring-1 ring-slate-200">
                <span className="min-w-0 truncate">{idx + 1}. {r.text}</span>
                {r.score != null && <span className="shrink-0 text-slate-400">{Number(r.score).toFixed(3)}</span>}
              </span>
            ))}
          </div>
        </KV>
      </Panel>
    );
  }
  return <Panel><pre className="whitespace-pre-wrap break-all font-mono text-[12px] text-slate-600">{JSON.stringify(f, null, 2)}</pre></Panel>;
}

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
      <Field label="模型输入"><InputView b={badcase} /></Field>
      <Field label="模型推理(错误)"><InferenceView b={badcase} /></Field>

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
