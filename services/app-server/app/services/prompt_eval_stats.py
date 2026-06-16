from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.prompt import PromptVersion
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem


def _all_items(db: Session, run_id: int) -> list[PromptEvalItem]:
    return list(db.execute(select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)).scalars())


def _comparison(db: Session, run: PromptEvalRun, cur_good: dict) -> dict | None:
    """单 prompt 人工 is_good 对上一版本(compare_to_version_id)最近一次已评运行的变好/变坏。"""
    if not run.compare_to_version_id:
        return None
    prev_ids = db.execute(
        select(PromptEvalRun.id)
        .join(PromptEvalArm, PromptEvalArm.run_id == PromptEvalRun.id)
        .where(PromptEvalRun.eval_type == "single_prompt",
               PromptEvalArm.prompt_version_id == run.compare_to_version_id,
               PromptEvalRun.id != run.id)
        .order_by(PromptEvalRun.id.desc())).scalars().all()
    for prev_id in prev_ids:
        prev = {(i.dataset_version_id, i.row_index): i.is_good
                for i in _all_items(db, prev_id) if i.evaluated_at is not None}
        keys = set(cur_good) & set(prev)
        if not keys:
            continue
        improved = sum(1 for k in keys if prev[k] is False and cur_good[k] is True)
        regressed = sum(1 for k in keys if prev[k] is True and cur_good[k] is False)
        comparable = len(keys)
        pv = db.get(PromptVersion, run.compare_to_version_id)
        label = f"{pv.prompt.name} V{pv.version_no}" if pv else None
        return {"compare_run_id": prev_id, "compare_version_label": label,
                "comparable": comparable, "improved": improved, "regressed": regressed,
                "improved_rate": improved / comparable, "regressed_rate": regressed / comparable}
    return None


def _metrics(run: PromptEvalRun, items: list[PromptEvalItem],
             get_winner, get_all_bad, get_is_good) -> dict:
    """从一组「已评 item」(人工或 AI)算指标。"""
    n = len(items)
    if run.eval_type == "single_prompt":
        good = sum(1 for i in items if get_is_good(i) is True)
        bad = sum(1 for i in items if get_is_good(i) is False)
        return {"evaluated": n, "good": good, "bad": bad,
                "good_rate": good / n if n else 0.0}
    wins = {a.id: 0 for a in run.arms}
    all_bad = 0
    for i in items:
        if get_all_bad(i):
            all_bad += 1
        elif get_winner(i) in wins:
            wins[get_winner(i)] += 1
    arms = [{"arm_id": a.id, "label": a.label, "prompt_version_id": a.prompt_version_id,
             "model_id": a.model_id, "wins": wins[a.id],
             "win_rate": wins[a.id] / n if n else 0.0} for a in run.arms]
    best = max(run.arms, key=lambda a: (wins[a.id], -a.arm_index)) if run.arms else None
    best_id = best.id if (best and wins.get(best.id, 0) > 0) else None
    return {"evaluated": n, "arms": arms, "all_bad": all_bad, "best_arm_id": best_id}


def stats(db: Session, run_id: int) -> dict | None:
    run = db.get(PromptEvalRun, run_id)
    if run is None:
        return None
    items = _all_items(db, run_id)
    human_items = [i for i in items if i.evaluated_at is not None]
    ai_items = [i for i in items if i.ai_evaluated_at is not None]

    human = _metrics(run, human_items,
                     lambda i: i.winner_arm_id, lambda i: i.all_bad, lambda i: i.is_good)
    ai = _metrics(run, ai_items,
                  lambda i: i.ai_winner_arm_id, lambda i: i.ai_all_bad, lambda i: i.ai_is_good)

    if run.eval_type == "single_prompt":
        cur_good = {(i.dataset_version_id, i.row_index): i.is_good for i in human_items}
        human["comparison"] = _comparison(db, run, cur_good)

    return {"eval_type": run.eval_type, "total": len(items), "human": human, "ai": ai}
