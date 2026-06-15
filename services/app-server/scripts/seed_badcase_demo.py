"""Seed ~200 ALREADY-ANNOTATED badcases per task type for exercising the repair flow.

Deletes existing badcases (the manual test reports) first, then inserts annotated demo
data attached to one real model version per task type. Run from services/app-server:

    python scripts/seed_badcase_demo.py
"""
import random
from datetime import datetime, timezone

from sqlalchemy import select, delete
from app.db import SessionLocal
from app.models.badcase import Badcase
from app.models.training import ModelVersion
from app.models.user import User

random.seed(42)
N = 200
NOW = datetime.now(timezone.utc)

# ---------------- classification ----------------
CLS = {
    "物流查询": ["我的快递到哪了", "包裹什么时候能到", "怎么还没发货", "物流信息一直不更新",
                "下单后多久能发货", "可以加急配送吗", "运费怎么算", "支持次日达吗",
                "快递停在中转站了", "能修改收货地址吗"],
    "售后服务": ["我要退货怎么操作", "这个怎么申请退款", "商品坏了能换货吗", "支持七天无理由退货吗",
                "退款一般多久到账", "发票怎么开具", "保修期是多久", "去哪里维修",
                "少发了一件商品", "收到的商品是坏的"],
    "售前咨询": ["这款和那款有什么区别", "现在有现货吗", "尺码应该怎么选", "可以再便宜点吗",
                "有优惠券可以用吗", "什么时候有活动", "这个是什么材质", "适合送人吗",
                "还有其他颜色吗", "支持定制吗"],
    "投诉建议": ["客服态度太差了", "等了好久都没人回复", "我要投诉你们", "你们处理也太慢了",
                "这就是欺骗消费者", "我要给差评", "对处理结果很不满意", "希望改进配送速度",
                "建议多增加点客服", "整体体验很糟糕"],
    "账户问题": ["登录不上去了", "密码忘了该怎么办", "怎么修改绑定的手机号", "我的账号好像被盗了",
                "怎么注销账户", "实名认证一直失败", "收不到短信验证码", "怎么绑定银行卡",
                "我的积分怎么没了", "会员怎么开通"],
}
CLS_PREFIX = ["", "你好,", "请问", "麻烦问一下,", "客服在吗,"]
CLS_SUFFIX = ["", "?", ",谢谢", ",急", ",在线等回复"]


def gen_classification():
    labels = list(CLS)
    rows = []
    for label in labels:
        combos = [(p, b, s) for b in CLS[label] for p in CLS_PREFIX for s in CLS_SUFFIX]
        random.shuffle(combos)
        for p, b, s in combos[: N // len(labels)]:
            wrong = random.choice([x for x in labels if x != label])
            rows.append(dict(
                input={"text": f"{p}{b}{s}"},
                inference={"label": wrong, "score": round(random.uniform(0.45, 0.7), 3)},
                annotation={"label": label},
                category=wrong))
    random.shuffle(rows)
    return rows[:N]


# ---------------- ner ----------------
PER = ["小明", "李华", "王芳", "张伟", "赵敏", "陈静", "刘洋", "周杰伦", "吴磊", "郑爽"]
LOC = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "重庆"]
ORG = ["阿里巴巴", "腾讯", "百度", "字节跳动", "华为", "美团", "京东", "小米", "网易", "滴滴"]
NER_TEMPLATES = [
    [("E", "PER"), ("O", "在"), ("E", "LOC"), ("O", "的"), ("E", "ORG"), ("O", "上班")],
    [("E", "PER"), ("O", "和"), ("E", "PER"), ("O", "一起去"), ("E", "LOC"), ("O", "出差")],
    [("E", "ORG"), ("O", "总部位于"), ("E", "LOC")],
    [("E", "PER"), ("O", "毕业后加入了"), ("E", "ORG")],
    [("O", "昨天"), ("E", "PER"), ("O", "从"), ("E", "LOC"), ("O", "飞往"), ("E", "LOC")],
    [("E", "LOC"), ("O", "的"), ("E", "ORG"), ("O", "招聘了"), ("E", "PER")],
    [("E", "PER"), ("O", "正在"), ("E", "ORG"), ("O", "参加面试")],
]
POOL = {"PER": PER, "LOC": LOC, "ORG": ORG}


def gen_ner():
    rows = []
    for i in range(N):
        tmpl = random.choice(NER_TEMPLATES)
        tokens, tags = [], []
        for kind, payload in tmpl:
            if kind == "E":
                word = random.choice(POOL[payload])
                for j, ch in enumerate(word):
                    tokens.append(ch)
                    tags.append(("B-" if j == 0 else "I-") + payload)
            else:
                for ch in payload:
                    tokens.append(ch)
                    tags.append("O")
        rows.append(dict(
            input={"tokens": tokens},
            inference={"tags": ["O"] * len(tokens)},   # model missed all entities
            annotation={"tags": tags},
            category=None))
    return rows


# ---------------- pair ----------------
PAIR_POS = [
    ("今天天气怎么样", "今天的天气如何"), ("怎么申请退货", "退货流程是什么"),
    ("订单什么时候发货", "我的订单何时能发出"), ("怎么修改收货地址", "如何更改收件地址"),
    ("会员怎么开通", "如何开通会员服务"), ("密码忘记了怎么办", "忘记密码如何找回"),
    ("运费是多少", "邮费怎么收"), ("支持货到付款吗", "可以到付吗"),
    ("这个有保修吗", "是否提供保修服务"), ("发票怎么开", "如何开具发票"),
]
PAIR_NEG = [
    ("今天天气怎么样", "我想订一张去上海的机票"), ("怎么申请退货", "附近有什么好吃的餐厅"),
    ("订单什么时候发货", "推荐一部好看的电影"), ("怎么修改收货地址", "明天的会议几点开始"),
    ("会员怎么开通", "这只股票还能买吗"), ("密码忘记了怎么办", "周末去爬山怎么样"),
    ("运费是多少", "帮我查一下英语单词"), ("支持货到付款吗", "今晚的球赛谁赢了"),
    ("这个有保修吗", "怎么煮一碗好吃的面"), ("发票怎么开", "最近有什么新游戏"),
]
PAIR_TAIL = ["", "呢", "啊", "?", ",谢谢", ",麻烦了"]


def gen_pair():
    rows, half = [], N // 2
    for i in range(half):
        a, b = random.choice(PAIR_POS)
        rows.append(dict(
            input={"text_a": a + random.choice(PAIR_TAIL), "text_b": b + random.choice(PAIR_TAIL)},
            inference={"label": "0", "score": round(random.uniform(0.2, 0.45), 3)},
            annotation={"label": "1"}, category=None))
    for i in range(N - half):
        a, b = random.choice(PAIR_NEG)
        rows.append(dict(
            input={"text_a": a + random.choice(PAIR_TAIL), "text_b": b + random.choice(PAIR_TAIL)},
            inference={"label": "1", "score": round(random.uniform(0.55, 0.8), 3)},
            annotation={"label": "0"}, category=None))
    random.shuffle(rows)
    return rows


# ---------------- embedding ----------------
EMB = [
    ("怎么重置密码", "在设置页点击忘记密码即可重置"),
    ("如何申请退货", "在订单详情里点击申请退货并填写原因"),
    ("运费怎么算", "满99元包邮,未满收取10元运费"),
    ("会员有什么权益", "会员享受专属折扣和免费配送"),
    ("怎么修改收货地址", "在我的-地址管理里编辑收货地址"),
    ("发票怎么开", "在订单完成后点击申请发票并填写抬头"),
    ("多久能发货", "付款后48小时内安排发货"),
    ("支持哪些支付方式", "支持微信、支付宝和银行卡支付"),
    ("怎么联系人工客服", "在帮助中心点击在线客服转人工"),
    ("积分怎么使用", "下单时可在结算页勾选使用积分抵扣"),
]


def gen_embedding():
    answers = [a for _, a in EMB]
    rows = []
    for i in range(N):
        q, correct = EMB[i % len(EMB)]
        distractors = random.sample([a for a in answers if a != correct], 3)
        cands = distractors + [correct]
        random.shuffle(cands)
        rows.append(dict(
            input={"query": q, "candidates": cands},
            inference={"ranked": [{"text": distractors[0], "score": 0.62},
                                  {"text": correct, "score": 0.41}]},
            annotation={"pos": [correct], "neg": distractors},
            category=None))
    return rows


GENERATORS = {
    "classification": gen_classification,
    "ner": gen_ner,
    "pair": gen_pair,
    "embedding": gen_embedding,
}


def main():
    db = SessionLocal()
    try:
        admin = db.execute(select(User).order_by(User.id)).scalars().first()
        if not admin:
            raise SystemExit("no user found to attribute annotations to")

        # pick one model version per task type
        mv_by_task = {}
        for task in GENERATORS:
            mv = db.execute(select(ModelVersion).where(ModelVersion.task_type == task)
                            .order_by(ModelVersion.id)).scalars().first()
            if not mv:
                print(f"!! no model version for task '{task}', skipping")
                continue
            mv_by_task[task] = mv

        # clean slate: remove all existing badcases (the manual test reports)
        n_del = db.execute(select(Badcase)).scalars().all()
        db.execute(delete(Badcase))
        db.commit()
        print(f"deleted {len(n_del)} existing badcases")

        total = 0
        for task, mv in mv_by_task.items():
            rows = GENERATORS[task]()
            for i, r in enumerate(rows):
                db.add(Badcase(
                    model_version_id=mv.id, task_type=task,
                    input=r["input"], inference=r["inference"], category=r["category"],
                    source="seed-batch", source_ref=f"seed-{task}-{i}",
                    status="annotated", annotation=r["annotation"],
                    annotated_by=admin.id, annotated_at=NOW, fixed_by=[]))
            db.commit()
            print(f"seeded {len(rows):>3} annotated {task} badcases  -> {mv.name} V{mv.mlflow_version} (mv {mv.id})")
            total += len(rows)
        print(f"done. {total} annotated badcases inserted.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
