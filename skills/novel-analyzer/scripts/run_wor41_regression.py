#!/usr/bin/env python3
"""Reproduce WOR-41's July 9 re-gate and a current 16-concept short pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import short_candidate_pool as pooler


FANQIE_ACTIVITY = {
    "kind": "official_activity",
    "source": "https://fanqienovel.com/writer/zone/solicit-activity",
    "date": "2026-07-16",
    "current": True,
    "content_status": "complete",
    "manifest_id": "fanqie-short-activity-20260716",
}


def scores(**overrides):
    result = {name: 4 for name in pooler.WEIGHTS}
    result["revision_cost"] = 2
    result.update(overrides)
    return result


def concept(title, genre, emotion, premise, **overrides):
    item = {
        "title": title,
        "audience_bucket": overrides.pop("audience", "general"),
        "genre_bucket": genre,
        "emotion_bucket": emotion,
        "platform_targets": ["番茄短故事"],
        "premise": premise,
        "promise_300": f"前300字建立限时问题：{premise}",
        "desire": "主角必须在当晚拿到可验证的结果",
        "setup": "异常规则与人物关系同时落地",
        "risk": "失败会失去最重要的关系或生存机会",
        "obstacle": "对手控制信息并迫使主角做不可逆选择",
        "payoff": "主角以行动完成核心承诺并改变公开结果",
        "aftermath": {
            "opponent_reaction": "对手的利益与立场当场改变",
            "relationship_or_cost": "关键关系回应，主角同时付出代价",
            "protagonist_choice": "主角做出不能撤回的新选择",
            "next_state": "人物关系和生存状态进入新的稳定态",
        },
        "scene_chain": ["承诺落地", "风险显形", "第一次受阻", "代价升级", "兑现", "四项后效"],
        "market_evidence": [dict(FANQIE_ACTIVITY)],
        "verification": {"title_status": "passed", "concept_status": "passed", "ip_status": "passed", "safety_status": "passed"},
        "scores": scores(),
        "risks": {"direct_ip": False, "unauthorized_ip": False, "sensitive_risk": 1, "hotspot_stacking": False},
    }
    for key, value in overrides.items():
        if key == "score_overrides":
            item["scores"].update(value)
        elif key == "risk_overrides":
            item["risks"].update(value)
        else:
            item[key] = value
    return item


def july9_concepts():
    psychology = concept(
        "诡异副本里，我给 Boss 当心理咨询师", "悬疑惊悚+职场反差", "恐惧转治愈",
        "咨询师必须在副本关闭前让五个怪物说出真正诉求",
        score_overrides={"reaction_chain": 3, "revision_cost": 3},
    )
    anticorruption = concept(
        "重生后，我把渣爹的贪腐证据寄给了纪委", "年代重生+反腐", "复仇",
        "女主重生后举报亲属并承受家庭瓦解",
        score_overrides={"aftermath": 2, "reaction_chain": 2, "revision_cost": 5},
        risk_overrides={"sensitive_risk": 4},
    )
    journey = concept(
        "国运直播：我的西游答题把外网吓傻了", "国运+西游+答题", "民族爽感",
        "主角靠西游知识赢下国运直播",
        score_overrides={"closure": 2, "scene_capacity": 2},
        risk_overrides={"hotspot_stacking": True},
    )
    milk = concept(
        "当奶嗝文学入侵了末日战场", "科幻末世+反差脑洞", "喜剧爽感",
        "被当成累赘的女战士把奶嗝变成可控声波武器",
        score_overrides={"core_promise": 5, "emotional_compensation": 5, "reaction_chain": 5},
    )
    zhang = concept(
        "我的室友是盗笔里的张起灵", "校园+盗墓衍生", "反差喜剧",
        "室友发现转校生就是知名盗墓角色",
        risk_overrides={"direct_ip": True, "unauthorized_ip": True},
    )
    return [psychology, anticorruption, journey, milk, zhang]


def current_concepts():
    ready = [
        ("月球养老院的最后一封家书", "未来科幻", "治愈", "护工在月球断联前替十二位老人送出最后的家书"),
        ("狼人律师只接离婚案", "西方狼人+都市职业", "反差喜剧", "狼人律师发现每宗离婚案都指向同一个月圆契约"),
        ("第七码头不收活人的快递", "悬疑惊悚", "恐惧", "夜班快递员必须在天亮前退回一件写着自己死期的包裹"),
        ("她把族谱改成了创业名单", "女性成长+历史古代", "自我实现", "被除名的族女用族谱空页记录被埋没的女工匠"),
        ("停电后，全楼只有我家冰箱在说话", "女频脑洞+都市日常", "家庭治愈", "冰箱每说出一件过期食物就揭开一段家庭隐瞒"),
        ("民国照相馆只拍明天", "民国旧影+悬疑", "遗憾补偿", "照相师拍出的不是客人现在，而是他们明天必须阻止的瞬间"),
        ("八十年代，我替妈妈拒绝了第二次婚礼", "年代+女性成长", "亲情补偿", "女儿回到母亲再婚前夜，阻止她再次牺牲人生"),
        ("王府账房今天也在劝王爷分家", "历史古代+都市日常", "打脸", "账房用一夜账本逼王府承认被吃绝户的寡嫂"),
        ("我在太空站给地球人做临终客服", "未来科幻+都市职业", "治愈", "客服必须在通讯断开前完成陌生人的最后一个小愿望"),
        ("小区业委会来了个失忆判官", "男频脑洞+都市日常", "现实爽感", "失忆判官用凡人证据解决一桩无法靠神力裁决的侵占案"),
    ]
    concepts = [concept(*row) for row in ready]
    concepts.extend([
        concept("哈利波特在番茄当编辑", "知名IP同人", "喜剧", "知名角色来平台审稿", risk_overrides={"direct_ip": True, "unauthorized_ip": True}),
        concept("国运直播：狼人答题震惊全球", "国运+狼人+答题", "民族爽感", "多个热点标签组合赢比赛", risk_overrides={"hotspot_stacking": True}),
        concept("醒来后所有人都说我是凶手", "悬疑", "恐惧", "主角醒来后被所有人指认", payoff="", score_overrides={"closure": 2}),
        concept("重生后我给现实领导当秘书", "现实人物+重生", "权力爽感", "主角利用现实政治身份翻盘", risk_overrides={"sensitive_risk": 5}),
        concept("三界外卖单", "玄幻脑洞", "喜剧", "外卖员收到三界订单", market_evidence=[]),
        concept("她赢了以后", "女性成长", "打脸", "女主赢下比赛却没有产生任何后果", aftermath={"opponent_reaction": "", "relationship_or_cost": "", "protagonist_choice": "", "next_state": ""}, score_overrides={"aftermath": 2}),
    ])
    return concepts


def render_list(candidates, status):
    lines = [f"# {status} candidates", ""]
    for item in candidates:
        if item["status"] != status:
            continue
        lines.extend([
            f"## {item['id']} 《{item['title']}》",
            "",
            f"- 题材：{item['genre_bucket']}",
            f"- 情绪：{item['emotion_bucket']}",
            f"- 总分：{item['score']}",
            f"- 判定：{', '.join(item['gate_reasons']) or '通过硬门'}",
            f"- 核心承诺：{item['premise']}",
            "",
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    old_pool = pooler.empty_pool()
    pooler.ingest(old_pool, july9_concepts())
    current_pool = pooler.empty_pool()
    pooler.ingest(current_pool, current_concepts())

    old_summary = pooler.summarize(old_pool)
    current_summary = pooler.summarize(current_pool)
    pooler.save_pool(args.outdir / "short_candidate_pool_20260709_regated.json", old_pool)
    pooler.save_pool(args.outdir / "short_candidate_pool_20260716.json", current_pool)
    (args.outdir / "short_ready_20260716.md").write_text(render_list(current_pool["candidates"], "ready"), encoding="utf-8")
    (args.outdir / "short_provisional_20260716.md").write_text(render_list(current_pool["candidates"], "provisional"), encoding="utf-8")
    (args.outdir / "short_rejected_20260716.md").write_text(render_list(current_pool["candidates"], "rejected"), encoding="utf-8")

    signals = """# 2026-07-16 短篇专属信号\n\n- 番茄官方创作活动页：西方题材“哥伦布计划”（07.01–07.31）；短故事 IP 金品共创计划列出男/女频脑洞、悬疑惊悚、历史古代、都市日常、民国旧影、年代、女性成长等 14 类（06.21–09.30）。\n  - https://fanqienovel.com/writer/zone/solicit-activity\n- 番茄官方公告页：2026-07-14 有短故事极端违规治理公告；风险门应独立于热度评分。\n  - https://fanqienovel.com/writer/zone/notice\n- 七猫作家助手当前页显示 2026 第 7 期女频快闪方向“不完美的她”，但页面未证明其为短篇专属，故只作弱编辑方向，不支撑 ready。\n  - https://zhushou.qimao.com/become-author\n- 七猫原创登载规则要求原创、独立权利并禁止侵权/违法内容；页面未给当前短篇投稿次数。\n  - https://m.qm989.com/publish.html\n\n限制：未找到可公开核验的七猫当前短篇榜/样稿页；没有用户真实投稿/退稿记录，投稿率与过稿率均为 unknown。\n"""
    (args.outdir / "short_signals_20260716.md").write_text(signals, encoding="utf-8")

    report = f"""# WOR-41 同批回归与当前候选池\n\n## 20260709 同批重门禁\n\n- 旧版展示：5/5。\n- 新门禁：ready {old_summary['counts']['ready']}，provisional {old_summary['counts']['provisional']}，rejected {old_summary['counts']['rejected']}。\n- provisional：《诡异副本里，我给 Boss 当心理咨询师》《当奶嗝文学入侵了末日战场》；两者只有活动方向，没有独立作品/读者需求证据。\n- rejected：反腐候选命中 HIGH_SENSITIVE_RISK/MISSING_AFTERMATH；西游答题命中 HOTSPOT_STACKING/WEAK_CLOSURE/WEAK_SCENE_CAPACITY；张起灵候选命中 DIRECT_IP/UNAUTHORIZED_IP。\n- ready 库存为 0，需要补货 {old_summary['replenish_gap']} 个到目标 10。\n\n## 20260716 当前短篇信号批次\n\n- raw 16，ready {current_summary['counts']['ready']}，provisional {current_summary['counts']['provisional']}，rejected {current_summary['counts']['rejected']}。\n- 原 10 个 ready 全部降为 provisional；原“缺短篇证据”的《三界外卖单》也从 rejected 改为 provisional，因此 provisional 共 11 个。\n- ready 库存为 0；在补齐“当期短篇方向 + 独立作品/读者需求信号”之前不得交付投稿。\n- 五个 rejected 分别覆盖直接 IP、热点拼接、闭环不足、高敏感风险和四项后效缺失；纯证据不足不再冒充结构淘汰。\n\n## 对比边界\n\n旧版没有短篇专属数值评分，因此无法检验“候选评分是否与成稿质量一致”。结构评分只能证明概念字段完整，不能替代市场证据；本次修正后没有候选达到 market-ready。旧盲评结果只能作为结构可执行性参考，不再作为可投稿性结论。没有新的真实用户选择或投稿结果，尚不能证明真实愿写率、投稿率或过稿率提升。\n"""
    (args.outdir / "regression_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"old": old_summary, "current": current_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


