import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { annotateBadcase, type Badcase } from "../api/client";
import { Button, Drawer } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { BadcaseAnnotateForm, annotationValid } from "./BadcaseAnnotateForm";

export function BadcaseAnnotateDrawer({
  badcase, onClose, onSaved,
}: { badcase: Badcase | null; onClose: () => void; onSaved: () => void }) {
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => { setVal(badcase?.annotation ?? {}); }, [badcase]);

  const valid = badcase ? annotationValid(badcase.task_type, val) : false;

  const save = () => {
    if (!badcase) return;
    setBusy(true);
    annotateBadcase(badcase.id, val)
      .then(() => { toastSuccess("已标注"); onSaved(); })
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
          <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!valid} loading={busy} onClick={save}>
            <Check size={16} /> 保存标注
          </Button>
        </div>
      }
    >
      {badcase && <BadcaseAnnotateForm badcase={badcase} val={val} onChange={setVal} />}
    </Drawer>
  );
}
