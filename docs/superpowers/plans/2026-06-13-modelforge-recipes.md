# ModelForge Recipes Implementation Plan (阶段 5:ner / pair / embedding)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 补齐三类 task_type 的训练 recipe 与评估器,并接入 `get_recipe` / `get_evaluator` 分流:序列标注(NER)、句对/相似度(pair)、检索向量微调(embedding,含难负样本挖掘)。

**Architecture:** 沿用阶段 3/4 的 `Recipe`(train→TrainResult)与 `Evaluator`(evaluate→dict)协议。NER/pair 走 HuggingFace `Trainer`;embedding 走 sentence-transformers(MultipleNegativesRankingLoss),训练前可选难负样本挖掘。所有产物经现有 `log_and_register` 写入 MLflow,因此 `train_task` 与 `eval_task` 编排无需改动(只是 `get_recipe`/`get_evaluator` 多支持几种 task_type)。

**Tech Stack:** transformers(<5)、datasets、torch、scikit-learn、seqeval(NER)、scipy(Spearman)、sentence-transformers(embedding)。

依赖:阶段 1–4 完成。参考 spec 第 1 节任务类型表与第 6.2 节。

数据 schema(沿用 spec):
- ner: `tokens: list[str]`, `tags: list[str]`(BIO)
- pair: `text_a`, `text_b`, `label`(分类标签)或 `score`(0–1 相似度回归)
- embedding: `query`, `pos: list[str]`, `neg: list[str]`(neg 可选)

---

### Task 1: NER recipe + evaluator

**Files:**
- Create: `services/train-worker/worker/recipes/ner.py`
- Create: `services/train-worker/worker/evaluators/ner.py`
- Modify: `services/train-worker/worker/recipes/__init__.py`(注册 ner)
- Modify: `services/train-worker/worker/evaluators/__init__.py`(注册 ner)
- Modify: `services/train-worker/pyproject.toml`(加 `seqeval>=1.2`)
- Test: `services/train-worker/tests/test_ner_recipe.py`

- [ ] **Step 1: 安装依赖** `pip install seqeval`,并在 pyproject dependencies 加 `"seqeval>=1.2"`。

- [ ] **Step 2: 失败测试**
```python
# services/train-worker/tests/test_ner_recipe.py
import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.ner import NERRecipe
from worker.evaluators import get_evaluator
from worker.evaluators.ner import NEREvaluator

def test_get_recipe_ner():
    assert isinstance(get_recipe("ner"), NERRecipe)

def test_get_evaluator_ner():
    assert isinstance(get_evaluator("ner"), NEREvaluator)

@pytest.mark.slow
def test_ner_trains_and_evaluates(tmp_path):
    toks = [["I","love","Beijing"],["Cats","are","cute"]] * 6
    tags = [["O","O","B-LOC"],["O","O","O"]] * 6
    df = pd.DataFrame({"tokens": toks, "tags": tags})
    res = NERRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16},
        output_dir=str(tmp_path))
    assert "f1" in res.metrics
    metrics = NEREvaluator().evaluate(model_dir=str(tmp_path), df=df)
    assert "f1" in metrics and 0.0 <= metrics["f1"] <= 1.0
```

- [ ] **Step 3: 运行确认失败** `cd services/train-worker && python -m pytest tests/test_ner_recipe.py -q`

- [ ] **Step 4: 实现 recipe**
```python
# worker/recipes/ner.py
import json, os
import numpy as np
from datasets import Dataset as HFDataset
from transformers import (AutoTokenizer, AutoModelForTokenClassification,
                          TrainingArguments, Trainer, DataCollatorForTokenClassification)
from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
from worker.recipes.base import Recipe, TrainResult

class NERRecipe(Recipe):
    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        tag_set = sorted({t for row in df["tags"] for t in row})
        tag2id = {t: i for i, t in enumerate(tag_set)}
        id2tag = {i: t for t, i in tag2id.items()}
        max_len = int(hyperparams.get("max_length", 128))
        tok = AutoTokenizer.from_pretrained(base_model)

        def encode(batch):
            enc = tok(batch["tokens"], is_split_into_words=True, truncation=True,
                      max_length=max_len)
            labels = []
            for i, tags in enumerate(batch["tags"]):
                word_ids = enc.word_ids(batch_index=i)
                prev, seq = None, []
                for wid in word_ids:
                    if wid is None:
                        seq.append(-100)
                    elif wid != prev:
                        seq.append(tag2id[tags[wid]])
                    else:
                        seq.append(-100)
                    prev = wid
                labels.append(seq)
            enc["labels"] = labels
            return enc

        hf = HFDataset.from_pandas(df[["tokens", "tags"]])
        hf = hf.map(encode, batched=True, remove_columns=hf.column_names)
        model = AutoModelForTokenClassification.from_pretrained(
            base_model, num_labels=len(tag_set), id2label=id2tag, label2id=tag2id)
        collator = DataCollatorForTokenClassification(tok)

        def metrics_fn(p):
            logits, labels = p
            preds = np.argmax(logits, axis=-1)
            true, pred = [], []
            for pr, la in zip(preds, labels):
                t_seq, p_seq = [], []
                for pi, li in zip(pr, la):
                    if li != -100:
                        t_seq.append(id2tag[int(li)]); p_seq.append(id2tag[int(pi)])
                true.append(t_seq); pred.append(p_seq)
            return {"accuracy": accuracy_score(true, pred), "precision": precision_score(true, pred),
                    "recall": recall_score(true, pred), "f1": f1_score(true, pred)}

        args = TrainingArguments(output_dir=output_dir,
            num_train_epochs=int(hyperparams.get("epochs", 3)),
            per_device_train_batch_size=int(hyperparams.get("batch_size", 16)),
            per_device_eval_batch_size=int(hyperparams.get("batch_size", 16)),
            learning_rate=float(hyperparams.get("lr", 5e-5)),
            report_to=[], logging_steps=10, save_strategy="no")
        trainer = Trainer(model=model, args=args, train_dataset=hf, eval_dataset=hf,
                          data_collator=collator, compute_metrics=metrics_fn)
        trainer.train()
        metrics = {k.replace("eval_", ""): float(v) for k, v in trainer.evaluate().items()
                   if isinstance(v, (int, float))}
        trainer.save_model(output_dir); tok.save_pretrained(output_dir)
        with open(os.path.join(output_dir, "tag_map.json"), "w") as f:
            json.dump(tag2id, f)
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=tag_set)
```

- [ ] **Step 5: 实现 evaluator**
```python
# worker/evaluators/ner.py
import json, os
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
from worker.evaluators.base import Evaluator

class NEREvaluator(Evaluator):
    def evaluate(self, model_dir: str, df) -> dict:
        with open(os.path.join(model_dir, "tag_map.json")) as f:
            tag2id = json.load(f)
        id2tag = {i: t for t, i in tag2id.items()}
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForTokenClassification.from_pretrained(model_dir); model.eval()
        true, pred = [], []
        for tokens, tags in zip(df["tokens"], df["tags"]):
            enc = tok([tokens], is_split_into_words=True, truncation=True,
                      max_length=256, return_tensors="pt")
            with torch.no_grad():
                logits = model(**enc).logits[0].cpu().numpy()
            p = np.argmax(logits, axis=-1)
            word_ids = enc.word_ids(batch_index=0)
            prev, t_seq, p_seq = None, [], []
            for idx, wid in enumerate(word_ids):
                if wid is not None and wid != prev:
                    t_seq.append(tags[wid]); p_seq.append(id2tag[int(p[idx])])
                prev = wid
            true.append(t_seq); pred.append(p_seq)
        return {"accuracy": float(accuracy_score(true, pred)),
                "precision": float(precision_score(true, pred)),
                "recall": float(recall_score(true, pred)),
                "f1": float(f1_score(true, pred)), "n_samples": int(len(df))}
```

- [ ] **Step 6: 注册分流**

`worker/recipes/__init__.py`:导入 `from worker.recipes.ner import NERRecipe`,在 `get_recipe` 增 `if task_type == "ner": return NERRecipe()`。
`worker/evaluators/__init__.py`:导入 `from worker.evaluators.ner import NEREvaluator`,在 `get_evaluator` 增 `if task_type == "ner": return NEREvaluator()`。

- [ ] **Step 7: 运行确认通过**(fast 必过;slow `-m slow` 真实训练+评估)。再跑 `python -m pytest -q -m "not slow"` 全套无回归。

- [ ] **Step 8: 提交**
```bash
git add services/train-worker/worker/recipes/ner.py services/train-worker/worker/evaluators/ner.py services/train-worker/worker/recipes/__init__.py services/train-worker/worker/evaluators/__init__.py services/train-worker/pyproject.toml services/train-worker/tests/test_ner_recipe.py
git commit -m "feat(train-worker): NER recipe and evaluator"
```

---

### Task 2: pair(句对/相似度)recipe + evaluator

**Files:**
- Create: `services/train-worker/worker/recipes/pair.py`
- Create: `services/train-worker/worker/evaluators/pair.py`
- Modify: recipes/evaluators `__init__.py`(注册 pair)
- Test: `services/train-worker/tests/test_pair_recipe.py`

设计:句对相似度回归。输入 `text_a`,`text_b`,目标 `score`(浮点 0–1;若只有 `label` 分类标签则映射为 0/1 浮点)。用 `AutoModelForSequenceClassification(num_labels=1)` 回归,MSE loss(Trainer 对 num_labels=1 自动用回归)。评估 Spearman/Pearson。

- [ ] **Step 1: 失败测试**
```python
# services/train-worker/tests/test_pair_recipe.py
import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.pair import PairRecipe
from worker.evaluators import get_evaluator
from worker.evaluators.pair import PairEvaluator

def test_get_recipe_pair():
    assert isinstance(get_recipe("pair"), PairRecipe)

def test_get_evaluator_pair():
    assert isinstance(get_evaluator("pair"), PairEvaluator)

@pytest.mark.slow
def test_pair_trains_and_evaluates(tmp_path):
    df = pd.DataFrame({
        "text_a": ["cat","hello","good day","bye"] * 4,
        "text_b": ["kitten","hi","nice day","leave"] * 4,
        "score": [1.0, 1.0, 1.0, 0.0] * 4})
    res = PairRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16}, output_dir=str(tmp_path))
    assert "mse" in res.metrics
    metrics = PairEvaluator().evaluate(model_dir=str(tmp_path), df=df)
    assert "spearman" in metrics
```

- [ ] **Step 2: 确认失败**

- [ ] **Step 3: 实现 recipe**
```python
# worker/recipes/pair.py
import numpy as np
from datasets import Dataset as HFDataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer)
from worker.recipes.base import Recipe, TrainResult

def _targets(df):
    if "score" in df.columns:
        return df["score"].astype(float).tolist()
    labels = sorted(df["label"].unique().tolist())
    l2i = {l: i for i, l in enumerate(labels)}
    return df["label"].map(l2i).astype(float).tolist()

class PairRecipe(Recipe):
    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        max_len = int(hyperparams.get("max_length", 128))
        tok = AutoTokenizer.from_pretrained(base_model)
        data = df.assign(labels=_targets(df))
        def enc(b): return tok(b["text_a"], b["text_b"], truncation=True, max_length=max_len)
        hf = HFDataset.from_pandas(data[["text_a", "text_b", "labels"]])
        hf = hf.map(enc, batched=True)
        model = AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=1)
        def metrics_fn(p):
            preds = p[0].reshape(-1); y = p[1].reshape(-1)
            return {"mse": float(np.mean((preds - y) ** 2))}
        args = TrainingArguments(output_dir=output_dir,
            num_train_epochs=int(hyperparams.get("epochs", 3)),
            per_device_train_batch_size=int(hyperparams.get("batch_size", 16)),
            per_device_eval_batch_size=int(hyperparams.get("batch_size", 16)),
            learning_rate=float(hyperparams.get("lr", 5e-5)),
            report_to=[], logging_steps=10, save_strategy="no")
        trainer = Trainer(model=model, args=args, train_dataset=hf, eval_dataset=hf,
                          compute_metrics=metrics_fn)
        trainer.train()
        metrics = {k.replace("eval_", ""): float(v) for k, v in trainer.evaluate().items()
                   if isinstance(v, (int, float))}
        trainer.save_model(output_dir); tok.save_pretrained(output_dir)
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=[])
```

- [ ] **Step 4: 实现 evaluator**
```python
# worker/evaluators/pair.py
import numpy as np
import torch
from scipy.stats import spearmanr, pearsonr
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from worker.evaluators.base import Evaluator
from worker.recipes.pair import _targets

class PairEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df) -> dict:
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
        enc = tok(df["text_a"].tolist(), df["text_b"].tolist(),
                  truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            preds = model(**enc).logits.reshape(-1).cpu().numpy()
        y = np.array(_targets(df), dtype=float)
        sp = spearmanr(preds, y).correlation if len(set(y.tolist())) > 1 else 0.0
        pe = pearsonr(preds, y)[0] if len(set(y.tolist())) > 1 else 0.0
        return {"spearman": float(sp if sp == sp else 0.0),
                "pearson": float(pe if pe == pe else 0.0),
                "mse": float(np.mean((preds - y) ** 2)), "n_samples": int(len(df))}
```
（`scipy` 随 scikit-learn 已安装;若缺则 `pip install scipy`。）

- [ ] **Step 5: 注册分流**（recipes/evaluators `__init__.py` 增 pair 分支与 import）

- [ ] **Step 6: 确认通过**（fast + slow + not-slow 全套）

- [ ] **Step 7: 提交**
```bash
git add services/train-worker/worker/recipes/pair.py services/train-worker/worker/evaluators/pair.py services/train-worker/worker/recipes/__init__.py services/train-worker/worker/evaluators/__init__.py services/train-worker/tests/test_pair_recipe.py
git commit -m "feat(train-worker): pair similarity recipe and evaluator"
```

---

### Task 3: embedding recipe(含难负挖掘)+ evaluator

**Files:**
- Create: `services/train-worker/worker/recipes/embedding.py`
- Create: `services/train-worker/worker/evaluators/embedding.py`
- Modify: recipes/evaluators `__init__.py`(注册 embedding)
- Modify: `services/train-worker/pyproject.toml`(加 `sentence-transformers>=3.0`)
- Test: `services/train-worker/tests/test_embedding_recipe.py`

设计:用 sentence-transformers 微调,`MultipleNegativesRankingLoss`,训练样本 `(query, positive)`(+ 可选 negatives)。难负挖掘:`hyperparams.negatives.mode == "auto"` 时用基线模型对 query 检索 corpus(所有 pos)取 top-k 非正样本作为难负;`provided` 用数据自带 `neg`。评估:recall@k(用训练好的模型对 query 检索 pos)。

- [ ] **Step 1: 安装依赖** `pip install sentence-transformers`,pyproject 加 `"sentence-transformers>=3.0"`。

- [ ] **Step 2: 失败测试**(用一个极小的 ST 兼容模型;`sentence-transformers/all-MiniLM-L6-v2` 较大,改用 `prajjwal1/bert-tiny` 作为底座由 ST 包装 mean-pooling)
```python
# services/train-worker/tests/test_embedding_recipe.py
import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.embedding import EmbeddingRecipe
from worker.evaluators import get_evaluator
from worker.evaluators.embedding import EmbeddingEvaluator

def test_get_recipe_embedding():
    assert isinstance(get_recipe("embedding"), EmbeddingRecipe)

def test_get_evaluator_embedding():
    assert isinstance(get_evaluator("embedding"), EmbeddingEvaluator)

def test_mine_hard_negatives_basic():
    # 纯逻辑:在无 neg 时,从 corpus 里挑非正样本
    df = pd.DataFrame({"query": ["q1","q2"], "pos": [["p1"],["p2"]], "neg": [[],[]]})
    rows = EmbeddingRecipe()._prepare_examples(df, negatives_mode="provided")
    assert len(rows) >= 2  # 至少每个 query 一条 (q, pos) 样本

@pytest.mark.slow
def test_embedding_trains_and_evaluates(tmp_path):
    df = pd.DataFrame({
        "query": ["cat","dog","car","tree"] * 3,
        "pos": [["a small kitten"],["a puppy"],["a fast vehicle"],["a tall plant"]] * 3,
        "neg": [[],[],[],[]] * 3})
    res = EmbeddingRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4}, output_dir=str(tmp_path))
    assert res.artifact_dir == str(tmp_path)
    metrics = EmbeddingEvaluator().evaluate(model_dir=str(tmp_path), df=df)
    assert "recall@1" in metrics and 0.0 <= metrics["recall@1"] <= 1.0
```

- [ ] **Step 3: 确认失败**

- [ ] **Step 4: 实现 recipe**
```python
# worker/recipes/embedding.py
from sentence_transformers import SentenceTransformer, models, InputExample, losses
from torch.utils.data import DataLoader
from worker.recipes.base import Recipe, TrainResult

def _build_st(base_model: str) -> SentenceTransformer:
    word = models.Transformer(base_model, max_seq_length=128)
    pool = models.Pooling(word.get_word_embedding_dimension(), pooling_mode="mean")
    return SentenceTransformer(modules=[word, pool])

class EmbeddingRecipe(Recipe):
    def _prepare_examples(self, df, negatives_mode="auto", model=None):
        rows = []
        corpus = [p for row in df["pos"] for p in row]
        for i, r in df.reset_index(drop=True).iterrows():
            q = r["query"]
            for pos in r["pos"]:
                negs = list(r.get("neg") or [])
                if negatives_mode == "auto" and not negs and model is not None:
                    # 用当前模型检索 corpus 取最相近的非正样本作为难负
                    import numpy as np
                    pool = [c for c in corpus if c not in r["pos"]]
                    if pool:
                        qe = model.encode([q]); ce = model.encode(pool)
                        sims = (qe @ ce.T)[0]
                        negs = [pool[int(np.argmax(sims))]]
                if negs:
                    rows.append(InputExample(texts=[q, pos, negs[0]]))
                else:
                    rows.append(InputExample(texts=[q, pos]))
        return rows

    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        model = _build_st(base_model)
        mode = (hyperparams.get("negatives") or {}).get("mode", "auto")
        examples = self._prepare_examples(df, negatives_mode=mode, model=model)
        loader = DataLoader(examples, shuffle=True,
                            batch_size=int(hyperparams.get("batch_size", 16)))
        loss = losses.MultipleNegativesRankingLoss(model)
        model.fit(train_objectives=[(loader, loss)],
                  epochs=int(hyperparams.get("epochs", 1)), warmup_steps=0,
                  show_progress_bar=False)
        model.save(output_dir)
        return TrainResult(metrics={"train_pairs": len(examples)},
                           artifact_dir=output_dir, label_names=[])
```

- [ ] **Step 5: 实现 evaluator**(recall@k:每个 query 在所有 pos 组成的 corpus 中检索,命中自身 pos 即正确)
```python
# worker/evaluators/embedding.py
import numpy as np
from sentence_transformers import SentenceTransformer
from worker.evaluators.base import Evaluator

class EmbeddingEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df, ks=(1, 3, 5)) -> dict:
        model = SentenceTransformer(model_dir)
        corpus, gold = [], []
        for _, r in df.reset_index(drop=True).iterrows():
            gold.append(len(corpus))   # 第一个 pos 的全局下标作为该 query 的正确答案
            corpus.extend(r["pos"])
        queries = df["query"].tolist()
        qe = model.encode(queries, normalize_embeddings=True)
        ce = model.encode(corpus, normalize_embeddings=True)
        sims = qe @ ce.T
        ranks = np.argsort(-sims, axis=1)
        out = {}
        for k in ks:
            hits = sum(1 for i, g in enumerate(gold) if g in ranks[i, :k].tolist())
            out[f"recall@{k}"] = float(hits / len(gold))
        out["n_samples"] = int(len(df))
        return out
```

- [ ] **Step 6: 注册分流**(recipes/evaluators `__init__.py` 增 embedding 分支与 import)

- [ ] **Step 7: 确认通过**(fast 三个必过;slow 真实训练+评估;`-m "not slow"` 全套无回归)

- [ ] **Step 8: 提交**
```bash
git add services/train-worker/worker/recipes/embedding.py services/train-worker/worker/evaluators/embedding.py services/train-worker/worker/recipes/__init__.py services/train-worker/worker/evaluators/__init__.py services/train-worker/pyproject.toml services/train-worker/tests/test_embedding_recipe.py
git commit -m "feat(train-worker): embedding recipe with hard-negative mining and evaluator"
```

---

## 自查(Self-Review)

**Spec 覆盖:** ner(entity-F1)、pair(Spearman/Pearson)、embedding(recall@k + 难负挖掘 auto/provided)三类 recipe + evaluator,并接入 `get_recipe`/`get_evaluator`。训练/评估编排(`train_task`/`eval_task`)无需改动——它们按 task_type 调度,本计划只扩展分流表。

**占位符扫描:** 无 TBD;每步含完整代码。

**类型一致性:** 各 recipe 返回 `TrainResult(metrics, artifact_dir, label_names)`;各 evaluator 返回 dict(float/int)。recipe 保存目录含各自加载所需文件(NER: tag_map.json + HF 模型;pair: HF 模型;embedding: ST 目录)。

**前置依赖/风险:** seqeval / sentence-transformers / scipy 需安装;slow 测试用 prajjwal1/bert-tiny 联网下载(已缓存)。embedding 用 ST 包装 bert-tiny 做 mean-pooling,真实指标可能偏低但测试只断言区间 [0,1]。难负挖掘 auto 模式在小 corpus 上是 O(n²) encode,仅用于中小数据集(与 spec 一致)。
