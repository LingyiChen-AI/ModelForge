# Badcase 上报 — curl 测试命令

通过 API 向系统上报坏例(badcase)。`task_type` 不用传,后端根据 `model_version_id` 自动判定;
`source` 取 API Key 的名字;`source_ref` 是业务侧唯一标识(同一 `model_version_id` + `source_ref` 会去重)。

## 准备

```bash
export MF_KEY="mf_QFRSRCk41ylj8GTzQdqdI1Pp0cDSj5Rq"   # 带 badcase:report 权限的 Key
export MF_URL="http://localhost:8000"                  # app-server
```

> Key 在「API Key」页面创建后**只在创建时返回一次明文**,请妥善保存。
> 上面这把是测试用 Key(名称 `badcase测试`,权限 `badcase:report` + `inference`)。

## 模型版本对照

| task_type | model_version_id | 模型 |
|---|---|---|
| classification 分类 | `1`(V3)/ `5`(V4) | 客服意图分类 |
| ner 序列标注 | `3`(V1) | 序列标注 |
| pair 句对 | `2`(V1) | 句对 |
| embedding 向量 | `4`(V1)/ `6`(V2) | 向量 |

---

## 1. 分类 (classification) — model_version_id=1

```bash
curl -s -X POST $MF_URL/badcase/report \
  -H "Content-Type: application/json" -H "X-Api-Key: $MF_KEY" \
  -d '{
    "model_version_id": 1,
    "input": {"text": "下单后多久能发货"},
    "inference": {"label": "售后服务", "score": 0.61},
    "source_ref": "ticket-2001"
  }'
```

- `input.text` 必填;`inference.label` 用于**自动归类**(分类任务按推理标签归桶)。

## 2. 序列标注 (ner) — model_version_id=3

```bash
curl -s -X POST $MF_URL/badcase/report \
  -H "Content-Type: application/json" -H "X-Api-Key: $MF_KEY" \
  -d '{
    "model_version_id": 3,
    "input": {"tokens": ["小", "明", "去", "上", "海", "出", "差"]},
    "inference": {"tags": ["O","O","O","O","O","O","O"]},
    "source_ref": "doc-3001"
  }'
```

- `input.tokens` 必填(字/词数组);`inference.tags` 是模型预测的标签序列。

## 3. 句对 (pair) — model_version_id=2

```bash
curl -s -X POST $MF_URL/badcase/report \
  -H "Content-Type: application/json" -H "X-Api-Key: $MF_KEY" \
  -d '{
    "model_version_id": 2,
    "input": {"text_a": "今天天气怎么样", "text_b": "明天会不会下雨"},
    "inference": {"label": "1", "score": 0.88},
    "source_ref": "pair-4001"
  }'
```

- `input.text_a` / `input.text_b` 必填。

## 4. 向量 (embedding) — model_version_id=4

```bash
curl -s -X POST $MF_URL/badcase/report \
  -H "Content-Type: application/json" -H "X-Api-Key: $MF_KEY" \
  -d '{
    "model_version_id": 4,
    "input": {"query": "怎么修改收货地址", "candidates": ["在我的-地址管理里修改", "拨打客服电话"]},
    "inference": {"ranked": [{"text": "拨打客服电话", "score": 0.72}, {"text": "在我的-地址管理里修改", "score": 0.55}]},
    "source_ref": "emb-5001"
  }'
```

- `input.query` 必填;`input.candidates` 必填且非空数组。

---

## 验证 / 排错

- 提交后到 **Badcase 页面**(部署菜单下方)查看按模型版本自动归类的记录。
- 缺字段 → `422`(如 embedding 不给 `candidates`)。
- Key 无效 / 无 `badcase:report` 权限 → `401`。
- 标注、生成「badcase-」训练集是在系统页面里完成(需登录权限),不走这个 Key。

返回示例(201):

```json
{
  "id": 1,
  "model_version_id": 1,
  "model_name": "客服意图分类",
  "model_version_label": "3",
  "task_type": "classification",
  "input": {"text": "我要退货怎么操作"},
  "inference": {"label": "物流查询", "score": 0.82},
  "category": "物流查询",
  "source": "badcase测试",
  "source_ref": "ticket-1001",
  "status": "reported",
  "annotation": null,
  "dataset_version_id": null,
  "created_at": "2026-06-15T10:02:21"
}
```
