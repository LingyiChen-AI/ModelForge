from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.prompt import PromptVersion
from app.models.dataset import DatasetVersion
from app.models.llm import LlmModel
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
from app.celery_client import send_prompt_eval_task   # module-level for monkeypatch


def _check_counts(eval_type: str, pv_ids: list, model_ids: list, dv_ids: list) -> None:
    if len(dv_ids) < 1:
        raise ValueError("至少选择一个测试集")
    if eval_type == "multi_prompt":
        if len(pv_ids) < 2:
            raise ValueError("多 prompt 评测需选择至少 2 个 prompt 版本")
        if len(model_ids) != 1:
            raise ValueError("多 prompt 评测需且仅选 1 个模型")
    elif eval_type == "multi_model":
        if len(model_ids) < 2:
            raise ValueError("多模型评测需选择至少 2 个模型")
        if len(pv_ids) != 1:
            raise ValueError("多模型评测需且仅选 1 个 prompt 版本")
    elif eval_type == "single_prompt":
        if len(pv_ids) != 1 or len(model_ids) != 1:
            raise ValueError("单 prompt 评测需且仅选 1 个 prompt 版本和 1 个模型")
    else:
        raise ValueError(f"未知评测类型:{eval_type}")


def _check_params(db: Session, pv_ids: list, dv_ids: list) -> None:
    needed: set[str] = set()
    for pv_id in pv_ids:
        pv = db.get(PromptVersion, pv_id)
        if pv is None:
            raise ValueError("存在无效的 prompt 版本")
        needed.update(pv.params or [])
    for dv_id in dv_ids:
        dv = db.get(DatasetVersion, dv_id)
        if dv is None:
            raise ValueError("存在无效的测试集版本")
        cols = set((dv.stats or {}).get("columns", []))
        missing = [p for p in needed if p not in cols]
        if missing:
            raise ValueError(f"测试集〈{dv.dataset.name} V{dv.version_no}〉缺少参数 {', '.join(missing)}")


def _label(db: Session, pv_id: int, model_id: int, eval_type: str) -> str:
    if eval_type == "multi_model":
        m = db.get(LlmModel, model_id)
        return m.model_id if m else f"model#{model_id}"
    pv = db.get(PromptVersion, pv_id)
    return f"{pv.prompt.name} V{pv.version_no}" if pv else f"pv#{pv_id}"


def _arm_specs(eval_type: str, pv_ids: list, model_ids: list) -> list[tuple]:
    if eval_type == "multi_prompt":
        return [(i, pv, model_ids[0]) for i, pv in enumerate(pv_ids)]
    if eval_type == "multi_model":
        return [(i, pv_ids[0], m) for i, m in enumerate(model_ids)]
    return [(0, pv_ids[0], model_ids[0])]   # single_prompt


def create_and_dispatch(db: Session, body, created_by=None) -> PromptEvalRun:
    _check_counts(body.eval_type, body.prompt_version_ids, body.model_ids, body.dataset_version_ids)
    _check_params(db, body.prompt_version_ids, body.dataset_version_ids)
    for m_id in body.model_ids:
        if db.get(LlmModel, m_id) is None:
            raise ValueError("存在无效的模型")
    compare_to = None
    if body.eval_type == "single_prompt":
        cur = db.get(PromptVersion, body.prompt_version_ids[0])
        prev = db.execute(select(PromptVersion).where(
            PromptVersion.prompt_id == cur.prompt_id,
            PromptVersion.version_no < cur.version_no
        ).order_by(PromptVersion.version_no.desc())).scalars().first()
        compare_to = prev.id if prev else None
    run = PromptEvalRun(
        name=body.name, eval_type=body.eval_type,
        prompt_version_ids=list(body.prompt_version_ids),
        model_ids=list(body.model_ids),
        dataset_version_ids=list(body.dataset_version_ids),
        compare_to_version_id=compare_to, created_by=created_by)
    for idx, pv_id, m_id in _arm_specs(body.eval_type, body.prompt_version_ids, body.model_ids):
        run.arms.append(PromptEvalArm(arm_index=idx, prompt_version_id=pv_id, model_id=m_id,
                                      label=_label(db, pv_id, m_id, body.eval_type)))
    db.add(run); db.commit(); db.refresh(run)
    run.celery_task_id = send_prompt_eval_task(run.id)
    db.commit(); db.refresh(run)
    return run


def submit_verdict(db: Session, item_id: int, body, user_id: int | None) -> PromptEvalItem | None:
    item = db.get(PromptEvalItem, item_id)
    if item is None:
        return None
    run = db.get(PromptEvalRun, item.run_id)
    if run.eval_type == "single_prompt":
        if body.is_good is None:
            raise ValueError("单 prompt 评测需提交 好 / 坏")
        item.is_good = body.is_good
        item.winner_arm_id = None
        item.all_bad = False
    else:
        if body.all_bad:
            item.all_bad = True
            item.winner_arm_id = None
        elif body.winner_arm_id is not None:
            arm = db.get(PromptEvalArm, body.winner_arm_id)
            if arm is None or arm.run_id != run.id:
                raise ValueError("winner_arm_id 不属于该评测")
            item.winner_arm_id = body.winner_arm_id
            item.all_bad = False
        else:
            raise ValueError("多臂评测需选择获胜方或『都一样坏』")
        item.is_good = None
    item.evaluated_by = user_id
    item.evaluated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(item)
    return item
