from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.prompt import PromptVersion
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem


def _evaluated_items(db: Session, run_id: int) -> list[PromptEvalItem]:
    return list(db.execute(select(PromptEvalItem).where(
        PromptEvalItem.run_id == run_id,
        PromptEvalItem.evaluated_at.is_not(None))).scalars())


def _all_items(db: Session, run_id: int) -> list[PromptEvalItem]:
    return list(db.execute(select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)).scalars())


def _comparison(db: Session, run: PromptEvalRun) -> dict | None:
    if not run.compare_to_version_id:
        return None
    prev_ids = db.execute(
        select(PromptEvalRun.id)
        .join(PromptEvalArm, PromptEvalArm.run_id == PromptEvalRun.id)
        .where(PromptEvalRun.eval_type == "single_prompt",
               PromptEvalArm.prompt_version_id == run.compare_to_version_id,
               PromptEvalRun.id != run.id)
        .order_by(PromptEvalRun.id.desc())).scalars().all()
    cur = {(i.dataset_version_id, i.row_index): i.is_good for i in _evaluated_items(db, run.id)}
    # 候选上一版本运行按 id 降序;取第一个与本 run 有「同 (测试集版本, 行号)」已评交集的运行
    # ——更近但零行重叠的运行会被跳过(没有重叠就无从对比)。
    for prev_id in prev_ids:
        prev = {(i.dataset_version_id, i.row_index): i.is_good for i in _evaluated_items(db, prev_id)}
        keys = set(cur) & set(prev)
        if not keys:
            continue
        improved = sum(1 for k in keys if prev[k] is False and cur[k] is True)
        regressed = sum(1 for k in keys if prev[k] is True and cur[k] is False)
        comparable = len(keys)
        pv = db.get(PromptVersion, run.compare_to_version_id)
        label = f"{pv.prompt.name} V{pv.version_no}" if pv else None
        return {"compare_run_id": prev_id, "compare_version_label": label,
                "comparable": comparable, "improved": improved, "regressed": regressed,
                "improved_rate": improved / comparable, "regressed_rate": regressed / comparable}
    return None


def stats(db: Session, run_id: int) -> dict | None:
    run = db.get(PromptEvalRun, run_id)
    if run is None:
        return None
    evaluated = _evaluated_items(db, run_id)
    total = len(_all_items(db, run_id))
    base = {"eval_type": run.eval_type, "evaluated": len(evaluated), "total": total}
    if run.eval_type == "single_prompt":
        good = sum(1 for i in evaluated if i.is_good is True)
        bad = sum(1 for i in evaluated if i.is_good is False)
        good_rate = good / len(evaluated) if evaluated else 0.0
        return {**base, "good": good, "bad": bad, "good_rate": good_rate,
                "comparison": _comparison(db, run)}
    wins = {a.id: 0 for a in run.arms}
    all_bad = 0
    for i in evaluated:
        if i.all_bad:
            all_bad += 1
        elif i.winner_arm_id in wins:
            wins[i.winner_arm_id] += 1
    n = len(evaluated)
    arms = [{"arm_id": a.id, "label": a.label, "prompt_version_id": a.prompt_version_id,
             "model_id": a.model_id, "wins": wins[a.id],
             "win_rate": wins[a.id] / n if n else 0.0} for a in run.arms]
    best = max(run.arms, key=lambda a: (wins[a.id], -a.arm_index)) if run.arms else None
    best_id = best.id if (best and wins.get(best.id, 0) > 0) else None
    return {**base, "arms": arms, "all_bad": all_bad, "best_arm_id": best_id}
