import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { annotateBadcase, type Badcase } from "../api/client";
import { Button, Drawer, Field, Input } from "../ui";
import { toastError, toastSuccess } from "../toast";

export function BadcaseAnnotateDrawer({
  badcase,
  onClose,
  onSaved,
}: {
  badcase: Badcase | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setVal(badcase?.annotation ?? {});
  }, [badcase]);

  const t = badcase?.task_type ?? "";
  const set = (k: string, v: any) => setVal(s => ({ ...s, [k]: v }));
  const candidates: string[] = badcase?.input?.candidates ?? [];

  const valid =
    (t === "classification" && val.label) ||
    (t === "pair" && (val.label === "0" || val.label === "1")) ||
    (t === "ner" && Array.isArray(val.tags) && val.tags.length > 0) ||
    (t === "embedding" && Array.isArray(val.pos) && val.pos.length > 0);

  const save = () => {
    if (!badcase) return;
    setBusy(true);
    annotateBadcase(badcase.id, val)
      .then(() => {
        toastSuccess("已标注");
        onSaved();
      })
      .catch(() => toastError("标注失败"))
      .finally(() => setBusy(false));
  };

  return (
    <Drawer
      open={badcase !== null}
      onClose={onClose}
      title={badcase ? `标注 Badcase #${badcase.id}` : "标注"}
      subtitle="补充正确答案;标注后可被选入 badcase- 训练集。"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" disabled={!valid} loading={busy} onClick={save}>
            <Check size={16} /> 保存标注
          </Button>
        </div>
      }
    >
      {badcase && (
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
              <Input
                value={val.label ?? ""}
                onChange={e => set("label", e.target.value)}
                placeholder="如 售后服务"
              />
            </Field>
          )}

          {t === "pair" && (
            <Field label="正确标签(1=相似 / 0=不相似)">
              <Input
                value={val.label ?? ""}
                onChange={e => set("label", e.target.value.trim())}
                placeholder="0 或 1"
              />
            </Field>
          )}

          {t === "ner" && (
            <Field label="正确 tags(逗号分隔,与 tokens 等长)">
              <Input
                value={(val.tags ?? []).join(",")}
                onChange={e =>
                  set(
                    "tags",
                    e.target.value
                      .split(",")
                      .map((x: string) => x.trim())
                      .filter(Boolean),
                  )
                }
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
                    set(key, [...new Set([...((val[key] ?? []) as string[]), cand])]);
                    set(
                      other,
                      ((val[other] ?? []) as string[]).filter(x => x !== cand),
                    );
                  };
                  return (
                    <div
                      key={cand}
                      className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2"
                    >
                      <span className="flex-1 truncate text-[13px] text-slate-700">{cand}</span>
                      <Button
                        size="sm"
                        variant={inPos ? "primary" : "subtle"}
                        onClick={() => mark("pos")}
                      >
                        相关
                      </Button>
                      <Button
                        size="sm"
                        variant={inNeg ? "danger" : "subtle"}
                        onClick={() => mark("neg")}
                      >
                        不相关
                      </Button>
                    </div>
                  );
                })}
              </div>
            </Field>
          )}
        </div>
      )}
    </Drawer>
  );
}
