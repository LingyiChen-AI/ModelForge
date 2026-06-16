import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from modelforge_common.llm_client import chat as llm_chat, LLMError
from modelforge_common.prompt_template import render
from worker.storage import read_snapshot
from worker.db import (JobStatus, load_prompt_eval_run, set_prompt_eval_status,
                       set_prompt_eval_progress, insert_eval_item, insert_eval_output,
                       set_output_result)


def _clean(v):
    """空单元格在 parquet 里是 float NaN —— 转成 None,避免 json.dumps 产出非法的 NaN
    导致 PostgreSQL JSON 列插入失败、整轮中断;渲染时 None→空串。"""
    return None if isinstance(v, float) and v != v else v


def run_prompt_eval(engine, run_id: int, concurrency: int = 20) -> None:
    set_prompt_eval_status(engine, run_id, JobStatus.RUNNING)
    set_prompt_eval_progress(engine, run_id, 0.02)
    run = load_prompt_eval_run(engine, run_id)
    arms = run["arms"]

    # 1) 读各测试集快照,展平成 items + 每臂 pending output
    work = []   # [(output_id, arm, inputs)]
    item_index = 0
    for dv_id, uri in run["datasets"]:
        df = read_snapshot(uri)
        cols = list(df.columns)
        for row_index, rec in enumerate(df.to_dict(orient="records")):
            inputs = {k: _clean(rec[k]) for k in cols}
            item_id = insert_eval_item(engine, run_id, item_index, dv_id, row_index, inputs)
            item_index += 1
            for arm in arms:
                out_id = insert_eval_output(engine, item_id, arm["id"])
                work.append((out_id, arm, inputs))

    # 2) 并发调 LLM —— IO 密集,用线程池;并发数发起评测时填入(5–100)。
    #    LLM 调用在子线程,DB 写(结果 + 进度)统一回主线程串行,避免连接池压力;单条失败隔离不影响其余。
    concurrency = max(5, min(100, int(concurrency or 20)))
    total = len(work) or 1

    def _call(out_id, arm, inputs):
        t0 = time.monotonic()
        try:
            messages = []
            sys_text = render(arm["system_prompt"] or "", inputs)
            if sys_text.strip():
                messages.append({"role": "system", "content": sys_text})
            messages.append({"role": "user", "content": render(arm["user_prompt"] or "", inputs)})
            # 超时/网络/429/5xx 自动重试(指数退避),timeout 放宽到 60s(推理模型生成慢)
            res = llm_chat(arm["base_url"], arm["api_key"], arm["model_str"], messages,
                           timeout=60.0, retries=2)
            return out_id, "done", res.content, None, int((time.monotonic() - t0) * 1000)
        except LLMError as e:
            return out_id, "error", "", e.message, int((time.monotonic() - t0) * 1000)

    done = 0
    with ThreadPoolExecutor(max_workers=min(concurrency, total)) as ex:
        futures = [ex.submit(_call, o, a, i) for (o, a, i) in work]
        for fut in as_completed(futures):
            out_id, status, text, err, latency = fut.result()
            set_output_result(engine, out_id, status=status, output_text=text or "",
                              error=err, latency_ms=latency)
            done += 1
            set_prompt_eval_progress(engine, run_id, 0.05 + 0.93 * (done / total))

    set_prompt_eval_progress(engine, run_id, 1.0)
    set_prompt_eval_status(engine, run_id, JobStatus.SUCCEEDED)
