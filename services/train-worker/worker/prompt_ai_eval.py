import json
import re
from datetime import datetime, timezone
from modelforge_common.llm_client import chat as llm_chat, LLMError
from worker.db import load_ai_eval_context, pending_ai_items, set_ai_verdict

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _parse(content: str) -> dict | None:
    m = _JSON_RE.search(content or "")
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except (ValueError, TypeError):
        return None


def _build_user(eval_type: str, inputs: dict, candidates: list[str]) -> str:
    lines = ["【任务输入】", json.dumps(inputs, ensure_ascii=False), "【候选回答】"]
    if eval_type == "single_prompt":
        lines.append(candidates[0] if candidates else "")
    else:
        for i, c in enumerate(candidates, 1):
            lines.append(f"候选{i}: {c}")
    return "\n".join(lines)


def run_prompt_ai_eval(engine, run_id: int, model_id: int, judge_prompt: str) -> None:
    ctx = load_ai_eval_context(engine, run_id, model_id)
    eval_type = ctx["eval_type"]
    arms = ctx["arms"]   # ordered by arm_index
    for item in pending_ai_items(engine, run_id):
        by_arm = {o["arm_id"]: o["output_text"] for o in item["outputs"]}
        candidates = [by_arm.get(a["id"], "") for a in arms]
        verdict = {"ai_winner_arm_id": None, "ai_all_bad": False, "ai_is_good": None,
                   "ai_model_id": model_id, "ai_reasoning": ""}
        try:
            res = llm_chat(ctx["base_url"], ctx["api_key"], ctx["model_str"],
                           [{"role": "system", "content": judge_prompt},
                            {"role": "user", "content": _build_user(eval_type, item["inputs"], candidates)}])
            verdict["ai_reasoning"] = res.content
            parsed = _parse(res.content)
            if parsed:
                if eval_type == "single_prompt":
                    if isinstance(parsed.get("good"), bool):
                        verdict["ai_is_good"] = parsed["good"]
                else:
                    if parsed.get("all_bad") is True:
                        verdict["ai_all_bad"] = True
                    elif isinstance(parsed.get("winner"), int) and 1 <= parsed["winner"] <= len(arms):
                        verdict["ai_winner_arm_id"] = arms[parsed["winner"] - 1]["id"]
        except LLMError as e:
            verdict["ai_reasoning"] = f"调用失败:{e.message}"
        set_ai_verdict(engine, item["id"], evaluated_at=datetime.now(timezone.utc), **verdict)
