import json

from sqlalchemy import create_engine, text, bindparam, Engine
from modelforge_common.enums import JobStatus
from worker.config import settings


def build_engine() -> Engine:
    """Create and return a SQLAlchemy engine."""
    return create_engine(settings.database_url, pool_pre_ping=True)


def set_job_status(engine: Engine, job_id: int, status: JobStatus,
                   mlflow_run_id: str | None = None, error: str | None = None) -> None:
    """Update job status in the database with optional mlflow_run_id and error."""
    sets = ["status = :status"]
    params = {"status": status.value, "id": job_id}
    if mlflow_run_id is not None:
        sets.append("mlflow_run_id = :mrid")
        params["mrid"] = mlflow_run_id
    if error is not None:
        sets.append("error = :err")
        params["err"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id = :id"), params)


def set_job_progress(engine: Engine, job_id: int, progress: float) -> None:
    """Update live training progress (0~1) for a job."""
    with engine.begin() as c:
        c.execute(text("UPDATE training_jobs SET progress = :p WHERE id = :id"),
                  {"p": max(0.0, min(1.0, float(progress))), "id": job_id})


def _as_id_list(raw) -> list[int]:
    """JSON column comes back as a python list (PG) or a JSON string (sqlite); normalize."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    return [int(x) for x in raw] if isinstance(raw, list) else []


def _storage_uris(c, ids: list[int]) -> list[str]:
    """Resolve dataset_version ids -> storage_uris, preserving the given order."""
    if not ids:
        return []
    rows = c.execute(text("SELECT id, storage_uri FROM dataset_versions WHERE id IN :ids")
                     .bindparams(bindparam("ids", expanding=True)),
                     {"ids": ids}).mappings().all()
    by = {r["id"]: r["storage_uri"] for r in rows}
    return [by[i] for i in ids if i in by]


def load_job(engine: Engine, job_id: int) -> dict:
    """Load job details, resolving the merged train/eval snapshot URIs."""
    with engine.connect() as c:
        row = dict(c.execute(text(
            "SELECT j.id, j.base_model, j.task_type, j.hyperparams, j.name, "
            "j.dataset_version_id, j.eval_dataset_version_id, "
            "j.dataset_version_ids, j.eval_dataset_version_ids, "
            "m.name AS model_name, v.storage_uri, ev.storage_uri AS eval_storage_uri "
            "FROM training_jobs j "
            "JOIN dataset_versions v ON v.id = j.dataset_version_id "
            "LEFT JOIN dataset_versions ev ON ev.id = j.eval_dataset_version_id "
            "LEFT JOIN models m ON m.id = j.model_id "
            "WHERE j.id = :id"), {"id": job_id}).mappings().one())

        train_ids = _as_id_list(row.get("dataset_version_ids")) or [row["dataset_version_id"]]
        eval_ids = _as_id_list(row.get("eval_dataset_version_ids"))
        if not eval_ids and row.get("eval_dataset_version_id"):
            eval_ids = [row["eval_dataset_version_id"]]
        row["storage_uris"] = _storage_uris(c, train_ids) or [row["storage_uri"]]
        row["eval_storage_uris"] = _storage_uris(c, eval_ids)
        row["train_version_ids"] = train_ids
        return row


def set_eval_status(engine: Engine, eval_run_id: int, status: JobStatus,
                    results: dict | None = None, error: str | None = None) -> None:
    """Update eval run status in the database with optional results and error."""
    sets = ["status = :status"]
    params = {"status": status.value, "id": eval_run_id}
    if results is not None:
        sets.append("results = :res")
        params["res"] = json.dumps(results)
    if error is not None:
        sets.append("error = :err")
        params["err"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE eval_runs SET {', '.join(sets)} WHERE id = :id"), params)


def set_eval_progress(engine: Engine, eval_run_id: int, progress: float) -> None:
    """Update live eval/test progress (0~1)."""
    with engine.begin() as c:
        c.execute(text("UPDATE eval_runs SET progress = :p WHERE id = :id"),
                  {"p": max(0.0, min(1.0, float(progress))), "id": eval_run_id})


def _as_json(v):
    if isinstance(v, (dict, list)) or v is None:
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


def load_trained_badcases(engine: Engine, version_ids: list[int]) -> list[dict]:
    """Annotated badcases whose dataset_version is in `version_ids` (i.e. were in this
    training set). Returns [{id, input, annotation}] with JSON parsed."""
    if not version_ids:
        return []
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, input, annotation FROM badcases "
            "WHERE dataset_version_id IN :ids AND annotation IS NOT NULL"
        ).bindparams(bindparam("ids", expanding=True)), {"ids": version_ids}).mappings().all()
    out = []
    for r in rows:
        out.append({"id": r["id"],
                    "input": _as_json(r["input"]),
                    "annotation": _as_json(r["annotation"])})
    return out


def load_eval_run(engine: Engine, eval_run_id: int) -> dict:
    """Load eval run details from the database."""
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT r.id, m.mlflow_model_name, m.mlflow_version, m.task_type, "
            "v.storage_uri, r.metric_config FROM eval_runs r "
            "JOIN model_versions m ON m.id = r.model_version_id "
            "JOIN dataset_versions v ON v.id = r.dataset_version_id "
            "WHERE r.id = :id"), {"id": eval_run_id}).mappings().one()
        return dict(row)


def set_prompt_eval_status(engine: Engine, run_id: int, status: JobStatus,
                           error: str | None = None) -> None:
    sets = ["status = :s"]
    params = {"s": status.value, "id": run_id}
    if error is not None:
        sets.append("error = :e")
        params["e"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE prompt_eval_runs SET {', '.join(sets)} WHERE id = :id"), params)


def set_prompt_eval_progress(engine: Engine, run_id: int, progress: float) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE prompt_eval_runs SET progress = :p WHERE id = :id"),
                  {"p": max(0.0, min(1.0, float(progress))), "id": run_id})


def load_prompt_eval_run(engine: Engine, run_id: int) -> dict:
    with engine.connect() as c:
        run = c.execute(text(
            "SELECT id, eval_type, dataset_version_ids FROM prompt_eval_runs WHERE id = :id"),
            {"id": run_id}).mappings().one()
        arms = c.execute(text(
            "SELECT a.id, a.arm_index, a.prompt_version_id, a.model_id, "
            "pv.system_prompt, pv.user_prompt, lp.base_url, lp.api_key, lm.model_id AS model_str "
            "FROM prompt_eval_arms a "
            "JOIN prompt_versions pv ON pv.id = a.prompt_version_id "
            "JOIN llm_models lm ON lm.id = a.model_id "
            "JOIN llm_providers lp ON lp.id = lm.provider_id "
            "WHERE a.run_id = :id ORDER BY a.arm_index"), {"id": run_id}).mappings().all()
        dv_ids = _as_json(run["dataset_version_ids"]) or []
        datasets = []
        if dv_ids:
            rows = c.execute(text("SELECT id, storage_uri FROM dataset_versions WHERE id IN :ids")
                             .bindparams(bindparam("ids", expanding=True)),
                             {"ids": dv_ids}).mappings().all()
            datasets = [(r["id"], r["storage_uri"]) for r in rows]
    return {"id": run["id"], "eval_type": run["eval_type"],
            "arms": [dict(a) for a in arms], "datasets": datasets}


def insert_eval_item(engine: Engine, run_id: int, item_index: int,
                     dataset_version_id: int, row_index: int, inputs: dict) -> int:
    with engine.begin() as c:
        return c.execute(text(
            "INSERT INTO prompt_eval_items (run_id, item_index, dataset_version_id, row_index, inputs) "
            "VALUES (:r, :i, :d, :ri, :inp) RETURNING id"),
            {"r": run_id, "i": item_index, "d": dataset_version_id, "ri": row_index,
             "inp": json.dumps(inputs, ensure_ascii=False)}).scalar_one()


def insert_eval_output(engine: Engine, item_id: int, arm_id: int) -> int:
    with engine.begin() as c:
        return c.execute(text(
            "INSERT INTO prompt_eval_outputs (item_id, arm_id, status) VALUES (:it, :a, 'pending') "
            "RETURNING id"), {"it": item_id, "a": arm_id}).scalar_one()


def set_output_result(engine: Engine, output_id: int, *, status: str,
                      output_text: str = "", error: str | None = None, latency_ms: int = 0) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE prompt_eval_outputs SET status = :s, output_text = :t, "
                       "error = :e, latency_ms = :l WHERE id = :id"),
                  {"s": status, "t": output_text, "e": error, "l": latency_ms, "id": output_id})


def load_ai_eval_context(engine: Engine, run_id: int, model_id: int) -> dict:
    with engine.connect() as c:
        run = c.execute(text("SELECT eval_type FROM prompt_eval_runs WHERE id = :id"),
                        {"id": run_id}).mappings().one()
        model = c.execute(text(
            "SELECT lm.model_id AS model_str, lp.base_url, lp.api_key "
            "FROM llm_models lm JOIN llm_providers lp ON lp.id = lm.provider_id "
            "WHERE lm.id = :id"), {"id": model_id}).mappings().one()
        arms = c.execute(text("SELECT id, arm_index FROM prompt_eval_arms "
                              "WHERE run_id = :id ORDER BY arm_index"), {"id": run_id}).mappings().all()
    return {"eval_type": run["eval_type"], "base_url": model["base_url"],
            "api_key": model["api_key"], "model_str": model["model_str"],
            "arms": [dict(a) for a in arms]}


def pending_ai_items(engine: Engine, run_id: int) -> list[dict]:
    with engine.connect() as c:
        items = c.execute(text("SELECT id, inputs FROM prompt_eval_items "
                               "WHERE run_id = :id AND ai_evaluated_at IS NULL ORDER BY id"),
                          {"id": run_id}).mappings().all()
        out = []
        for it in items:
            outs = c.execute(text("SELECT arm_id, output_text FROM prompt_eval_outputs WHERE item_id = :i"),
                             {"i": it["id"]}).mappings().all()
            out.append({"id": it["id"], "inputs": _as_json(it["inputs"]) or {},
                        "outputs": [dict(o) for o in outs]})
    return out


def set_ai_verdict(engine: Engine, item_id: int, *, ai_winner_arm_id, ai_all_bad, ai_is_good,
                   ai_model_id, ai_reasoning, evaluated_at) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE prompt_eval_items SET ai_winner_arm_id = :w, ai_all_bad = :ab, "
                       "ai_is_good = :ig, ai_model_id = :m, ai_reasoning = :r, ai_evaluated_at = :at "
                       "WHERE id = :id"),
                  {"w": ai_winner_arm_id, "ab": ai_all_bad, "ig": ai_is_good, "m": ai_model_id,
                   "r": ai_reasoning, "at": evaluated_at, "id": item_id})
