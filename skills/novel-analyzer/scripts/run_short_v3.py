#!/usr/bin/env python3
"""Regression fixture runner only; never use this script for production candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import short_candidate_pool as pooler


DIRECTION = {
    "kind": "official_activity",
    "source": "https://fanqienovel.com/writer/zone/solicit-activity",
    "date": "2026-07-17",
    "current": True,
    "content_status": "complete",
    "manifest_id": "fanqie-short-activity-20260717",
}


STRONG_RECORDS = [
    {
        "title": "遗物整理师收到一张活人清单", "genre": "都市悬疑", "emotion": "迟来的补偿",
        "premise": "遗物整理师发现死者清单上最后一个名字是仍在照顾自己的继父",
        "promise": "开场她正给骨灰盒贴标签，却从夹层抽出一张每天自动少一个名字的清单",
        "desire": "在继父名字消失前查明母亲死亡后的财产去向", "setup": "她靠整理遗物替家属保守秘密，却从不打开封死的夹层",
        "risk": "报警会让继父失去手术资格，沉默则下一位委托人会死", "obstacle": "养老机构财务主管用合法代签掩盖每笔转账",
        "payoff": "她在追思会现场拆开十二只同批骨灰盒，让家属逐一认领被藏起的存折",
        "anchors": ["骨灰盒夹层", "褪色存折", "养老院代签章"], "opening": "她用热风枪揭开骨灰盒底部的封蜡",
        "choice": "她把继父的手术押金转入受害者共同监管账户", "antagonist": "财务主管必须填平挪用缺口才能保住女儿的留学担保",
        "actions": ["直播拆封十二只骨灰盒", "逐笔核对存折暗号", "将代签章交给最先受骗的老人"],
        "reactions": ["继父", "受害老人家属", "养老机构董事"], "hooks": ["清单为什么每天少一个名字", "继父为何认识存折暗号", "第十二只骨灰盒是谁的"],
        "texture": ["她紧张时会把标签贴歪一毫米", "继父每次撒谎都先问她吃没吃饭"],
        "scenes": ["封蜡异响", "清单少名", "代签受阻", "押金选择", "追思会拆盒", "继父签下共同账户"],
        "aftermath": ["财务主管先抢章后求家属别报警", "继父失去手术便利却第一次交出旧账本", "她拒绝替母亲原谅任何人", "养老院改为双人签章并公开旧账"],
        "keywords": ["家庭", "悬疑", "打脸逆袭"], "difference": "把常见遗产反转改成职业流程、共同账户和照护伦理的两难",
    },
    {
        "title": "我把全家福挂进了失物招领处", "genre": "家庭现实", "emotion": "边界重建",
        "premise": "商场失物招领员收到一张被剪掉自己的全家福，认出送件人是失踪十年的姐姐",
        "promise": "她给无主照片编号时，发现照片背面写着今天下午四点来领走一个女儿",
        "desire": "在闭店前找回姐姐，并阻止父母再次用亲情替弟弟填债", "setup": "她能记住每件失物的主人，却一直假装不记得姐姐离家的原因",
        "risk": "公开旧事会让姐姐失去刚争取到的孩子抚养权", "obstacle": "父亲把招领广播改成家庭道歉会，逼姐妹在围观中和解",
        "payoff": "她把全家福挂上无主物墙，按编号归还房本、借条和姐姐当年的报警回执",
        "anchors": ["剪角全家福", "商场招领广播", "磨损的报警回执"], "opening": "她用镊子从钱包夹层取出被剪掉的人脸",
        "choice": "她关掉父亲的话筒并把自家房本交给法院保全窗口", "antagonist": "父亲相信牺牲女儿能换来儿子不坐牢和家庭表面完整",
        "actions": ["切断道歉直播音轨", "按失物编号展示借条日期", "陪姐姐把回执交给法官"],
        "reactions": ["父亲", "姐姐的女儿", "围观商户"], "hooks": ["四点要领走哪个女儿", "照片是谁剪的", "报警回执为何从未立案"],
        "texture": ["她会给每件失物喷不同味道的消毒水", "姐姐见面先问招领柜押金退不退"],
        "scenes": ["照片入柜", "广播寻人", "父亲抢麦", "房本保全", "无主物墙对账", "姐妹各自回家"],
        "aftermath": ["父亲当众撕照片却不敢碰报警回执", "外甥女第一次叫出母亲名字", "她拒绝做新的家庭调解人", "姐妹建立不经父母的探视安排"],
        "keywords": ["婚姻家庭", "家庭", "救赎"], "difference": "不靠跪求和原谅收尾，而用失物流程拆分财产、责任与关系边界",
    },
    {
        "title": "婚礼司仪念错了第三份遗嘱", "genre": "婚姻反转", "emotion": "公开夺回",
        "premise": "兼职司仪在前夫婚礼上发现提词器混入三份互相冲突的遗嘱",
        "promise": "她念到新娘名字时，屏幕却跳出自己母亲留下的第三份受益人名单",
        "desire": "在宣誓前证明婚礼场地和公司股权都来自被调包的遗产", "setup": "她靠替陌生人维持体面谋生，最怕在台上失控",
        "risk": "停下婚礼会触发母亲遗嘱中的弃权条款", "obstacle": "前夫律师不断远程改提词器并诱导她念完错误版本",
        "payoff": "她故意继续主持，把三版遗嘱的修改时间投到大屏，让公证员在交换戒指前封存服务器",
        "anchors": ["婚礼提词器", "三枚不同骑缝章", "交换戒指倒计时"], "opening": "她在念新娘姓名前按下提词器回退键",
        "choice": "她放弃自己可继承的现金份额，换取服务器立即司法封存", "antagonist": "律师需要婚礼完成才能触发股权代持转正",
        "actions": ["并排投出三版遗嘱", "让乐队按修改时间奏三次停顿", "请公证员当场拔走服务器硬盘"],
        "reactions": ["前夫", "新娘父亲", "婚礼宾客"], "hooks": ["谁把第三份遗嘱塞进提词器", "母亲为何设置弃权条款", "新娘父亲为何提前带公证员"],
        "texture": ["她每次紧张都会把人名重音标成红色", "前夫只在撒谎时叫她全名"],
        "scenes": ["提词器错名", "律师远控", "弃权倒计时", "现金放弃", "大屏三遗嘱", "硬盘封存"],
        "aftermath": ["前夫拔电源反而触发云端备份", "新娘父亲取消联姻并追问代持款", "她主持完最后一句但拒收尾款", "婚礼场地进入遗产保全而非归她所有"],
        "keywords": ["婚姻家庭", "打脸逆袭", "大女主"], "difference": "把婚礼打脸写成程序证据与自我放弃，而非亲子鉴定或带娃归来",
    },
    {
        "title": "社区食堂只收旧欠条", "genre": "现实温情", "emotion": "尊严补偿",
        "premise": "社区食堂新店长取消免费餐，却宣布七十年前的手写欠条可以抵饭钱",
        "promise": "第一位老人递来的欠条上，债主竟是店长已经去世的母亲",
        "desire": "在食堂被收购前找齐母亲替人垫过的饭钱和被隐瞒的受助名单", "setup": "她讨厌母亲一辈子替别人吃亏，接手食堂只想先止损",
        "risk": "承认旧欠条会让她背上超出店面价值的债", "obstacle": "收购方煽动居民把善意伪造成无限赊账",
        "payoff": "她把欠条按年份贴满价目墙，只兑现能由两名见证人说出当年菜名的那一张",
        "anchors": ["油渍欠条", "搪瓷饭票盒", "价目墙粉笔"], "opening": "她把免费餐牌翻面写上第一道验证题",
        "choice": "她拒绝高价收购并用店面抵押设立有限救助金", "antagonist": "收购方需要制造坏账才能压低食堂估值并拿到街角地块",
        "actions": ["逐张核对菜名和见证人", "公开收购方伪造纸张的水印", "把真实欠条兑换成实名饭票"],
        "reactions": ["欠条老人", "普通付费居民", "收购方会计"], "hooks": ["母亲为何从不催债", "哪张欠条用了新纸", "最后一张为何写的是她名字"],
        "texture": ["她算账时会把豆子按七颗一组摆开", "老人明明饿却先把饭票塞给陌生孩子"],
        "scenes": ["翻牌止损", "首张母债", "假条泛滥", "水印查伪", "价目墙见证", "有限救助金开餐"],
        "aftermath": ["收购方会计承认造假但要求保护基层员工", "居民开始轮值见证而非只领免费餐", "她承认母亲善良也有边界错误", "食堂保留商业账和救助账两套公开账本"],
        "keywords": ["职场", "救赎", "现实题材"], "difference": "把泛善良改成有验证、有上限、有反利用成本的社区机制",
    },
    {
        "title": "她在族谱背面开了一间工厂", "genre": "年代女性成长", "emotion": "身份夺回",
        "premise": "被族谱除名的女焊工发现每页背面都画着母亲留下的零件图",
        "promise": "祠堂修谱当天，她把族谱贴上灯箱，背面的机床图在众人眼前亮起",
        "desire": "在老厂设备被当废铁卖掉前证明母亲才是核心工艺设计者", "setup": "她从小被说只会蛮力，最擅长的却是看反写图纸",
        "risk": "公开图纸会暴露母亲当年违规借用公章并连累退休工人", "obstacle": "族长兼厂长把女性署名改成家族集体成果",
        "payoff": "她用族谱背面图纸现场焊出缺失零件，让停摆十年的机床重新转动并拒绝挂家族牌匾",
        "anchors": ["反写族谱", "铜制缺口齿轮", "借用公章登记本"], "opening": "她把族谱举到焊接探伤灯前",
        "choice": "她主动提交母亲违规用章记录，换取工艺署名进入档案", "antagonist": "族长需要集体署名维持家族对厂房补偿款的控制",
        "actions": ["用探伤灯显出反写图", "按图焊出缺口齿轮", "在机床启动前递交用章记录"],
        "reactions": ["退休女工", "族长的儿子", "档案馆员"], "hooks": ["母亲为何把图画在族谱背面", "齿轮缺口是错误还是钥匙", "登记本最后一页被谁撕走"],
        "texture": ["她说紧张就会闻焊条辨批次", "族长每次讲祖训都把自己的名字念重一拍"],
        "scenes": ["灯下显图", "废铁竞价", "女工证词", "违规用章", "齿轮点火", "新档案署名"],
        "aftermath": ["族长先阻止开机后要求分署名", "退休女工拿出各自保存的零件", "她接受母亲犯错但拒绝抹去贡献", "厂房补偿改由全体工人按档案核算"],
        "keywords": ["古代", "女性成长", "打脸逆袭"], "difference": "爽点来自技术复现和承担违规代价，不靠现代知识碾压年代人物",
    },
    {
        "title": "凌晨两点，停尸房来了一份外卖", "genre": "职业悬疑", "emotion": "恐惧转正义",
        "premise": "医院夜班护工收到写着停尸柜编号的热粥，备注要求她在冷却前喂完",
        "promise": "她拉开柜门，里面的人手腕仍有输液针眼，外卖骑手却显示三年前已死亡",
        "desire": "在交班前证明柜中人被提前宣告死亡并找出下单者", "setup": "她靠记住每位病人的粥温判断吞咽情况，从不相信仪器单独结论",
        "risk": "擅自移动遗体会让她承担毁坏证据和停职责任", "obstacle": "值班医生用完整监控证明死者从未离开病房",
        "payoff": "她把粥分装进三个温度探头，重演转运路线，让监控时间差和仍在代谢的药物一起暴露",
        "anchors": ["停尸柜七码", "保温粥封签", "输液泵离线记录"], "opening": "她把外卖封签贴到柜门温度计旁",
        "choice": "她按下停尸房消防报警，主动留下违规开柜记录", "antagonist": "值班医生需要死亡时间提前两小时才能避开用药事故责任",
        "actions": ["用三支探头重演粥温下降", "调出输液泵离线秒数", "在消防到场时重新验生命体征"],
        "reactions": ["值班医生", "死者家属", "同班护工"], "hooks": ["死去骑手如何下单", "监控为何毫无断点", "柜中人是否还能被救回"],
        "texture": ["她记不住人名却能记住每个人喝粥的温度", "医生解释越快越爱擦已经干净的听诊器"],
        "scenes": ["亡者外卖", "违规开柜", "监控无缝", "消防选择", "温度重演", "重新抢救"],
        "aftermath": ["医生先否认后抢夺输液泵", "家属拒绝立即和解并要求独立鉴定", "她救回病人却被停职调查", "医院新增人工复核但公开本次误报"],
        "keywords": ["奇闻异事", "悬疑", "现实题材"], "difference": "灵异入口最终落在职业细节与责任链，保留救人代价而非纯反转",
    },
    {
        "title": "我替失忆的妈妈参加离婚调解", "genre": "婚姻家庭", "emotion": "亲情松绑",
        "premise": "女儿替失忆母亲参加离婚调解，却发现母亲每次见父亲都会准确忘掉同一件事",
        "promise": "调解员问结婚日期时，母亲答不出年份，却背出父亲藏私房钱的七码密码",
        "desire": "在冷静期结束前确认母亲是真失忆还是用失忆逃离控制", "setup": "她一直替父母记纪念日，以为记得就是爱",
        "risk": "揭穿母亲装病会让她失去监护资格，继续配合又可能构成骗保", "obstacle": "父亲提交完整照护日志证明自己是唯一可靠监护人",
        "payoff": "她让母亲独自重走三处调解路线，用每次故意留下的超市小票拼出一份逃离计划",
        "anchors": ["七码保险柜", "冷静期回执", "三张折叠超市小票"], "opening": "母亲把结婚证倒着递给调解员，却正着按出保险柜密码",
        "choice": "她撤回自己的监护申请，让母亲接受独立能力鉴定", "antagonist": "父亲需要监护身份继续处置母亲名下拆迁款，同时真心害怕被抛弃",
        "actions": ["核对三张小票路线", "公开撤回监护申请", "让母亲在无家属陪同下完成能力鉴定"],
        "reactions": ["父亲", "母亲的妹妹", "调解员"], "hooks": ["母亲为何只忘同一件事", "小票折痕组成什么路线", "父亲的照护日志是谁写的"],
        "texture": ["母亲装糊涂时会把糖包按颜色排齐", "父亲每页日志都漏写自己午睡的两小时"],
        "scenes": ["倒递结婚证", "七码记忆", "照护日志", "撤回监护", "小票路线", "独立鉴定"],
        "aftermath": ["父亲承认控制拆迁款却仍要求照顾她", "姨妈停止替姐姐解释改为提供住处", "女儿接受母亲也曾利用自己的愧疚", "母亲以限制民事能力评估通过开启单独账户"],
        "keywords": ["失忆", "婚姻家庭", "现实题材"], "difference": "不把失忆当万能反转，而把监护、能力鉴定和亲情操控拆开",
    },
    {
        "title": "返城表上，姐姐替我签了放弃", "genre": "年代家庭", "emotion": "迟到的选择",
        "premise": "下乡姐妹收到唯一返城名额，妹妹却发现放弃栏已有姐姐模仿她的签名",
        "promise": "欢送会名单念到她时，档案员拿出一张墨迹还没干的自愿放弃书",
        "desire": "在当天班车开走前夺回自己的选择，同时查清姐姐为何偷签", "setup": "妹妹从小替姐姐写作业，姐姐学会了她每一种笔迹",
        "risk": "撤销放弃会让姐姐刚确诊的孩子失去省城治疗机会", "obstacle": "姐夫利用家属表决逼所有知青证明妹妹早就口头同意",
        "payoff": "妹妹当众重写十年前的两份字迹，让档案员看见姐姐只会模仿字形、不会她受伤后的落笔停顿",
        "anchors": ["返城放弃书", "断尖英雄钢笔", "末班客车票"], "opening": "她用断尖钢笔在放弃书旁补写一个故意缺口的名字",
        "choice": "她拿走返城名额，却把省城接诊联系人和第一月工资留给外甥", "antagonist": "姐姐既想救孩子，也认为妹妹从小让过无数次就该再让一次",
        "actions": ["现场复写旧签名", "指出受伤后独有停顿", "在班车门口交出治疗联系人"],
        "reactions": ["姐姐", "同队知青", "档案员"], "hooks": ["墨迹为何没干", "姐姐从何学会笔迹", "妹妹会不会为孩子再让一次"],
        "texture": ["妹妹写自己的姓总会停半拍揉虎口", "姐姐求人时反而把声音压得像在下命令"],
        "scenes": ["名单宣读", "湿墨放弃", "家属表决", "笔迹复写", "班车取舍", "姐妹分路"],
        "aftermath": ["姐姐撕票后又把治疗地址捡起来", "知青们承认曾默认妹妹继续牺牲", "妹妹不原谅偷签但兑现对孩子的帮助", "两姐妹分别进城与留队，不以和解抹平选择"],
        "keywords": ["年代", "家庭", "重生"], "difference": "保留年代资源稀缺，把爽点落在选择权和有限互助，不走重生复仇",
    },
    {
        "title": "老宅拆迁前，奶奶改了门牌号", "genre": "家庭财产", "emotion": "公平重算",
        "premise": "拆迁测绘员发现奶奶把自家门牌从18号改成了已经注销的17号",
        "promise": "全家等着签千万补偿单时，测绘图显示17号住着一个法律上不存在的人",
        "desire": "在签约截止前确认奶奶想藏的是房间、住户还是一段未登记收养关系", "setup": "孙女最擅长画准确边界，却从没问过奶奶为什么睡在过道",
        "risk": "恢复真实门牌会使全家补偿面积缩水并暴露违规扩建", "obstacle": "伯父用全家投票要求按现状签字后再私下分配",
        "payoff": "孙女重画墙体年代，把补偿从房屋面积改成每位实际居住者的安置资格，并主动划掉自家违规厨房",
        "anchors": ["掉漆17号门牌", "蓝色测绘笔", "过道折叠床"], "opening": "她把激光测距仪对准门牌后那圈新鲜螺丝印",
        "choice": "她在全家签字前先提交自家违规面积", "antagonist": "伯父认为拿到总款后再照顾奶奶更灵活，也想控制所有人的安置房",
        "actions": ["按墙灰层次标出建造年份", "划掉违规厨房面积", "替未登记养女申请实际居住听证"],
        "reactions": ["伯父", "被隐藏的养女", "其他排队住户"], "hooks": ["17号原住户是谁", "奶奶为何睡过道", "划掉厨房后谁先反悔"],
        "texture": ["奶奶每晚把折叠床朝门口挪两厘米", "伯父谈孝顺时总先问补偿单复印了几份"],
        "scenes": ["门牌螺丝印", "测绘冲突", "过道旧住户", "违规自报", "居住听证", "分户安置"],
        "aftermath": ["伯父撤签威胁失败后改抢奶奶证件", "养女不认亲只接受独立安置", "孙女少拿面积并辞去家族分款代理", "全家从总款争夺转为逐户签约"],
        "keywords": ["婚姻家庭", "现代", "家庭"], "difference": "不靠隐藏遗嘱，爽点来自专业测绘、自损利益和实际居住权重算",
    },
    {
        "title": "全网等我认错时，我关掉了提词器", "genre": "娱乐职场", "emotion": "自证反击",
        "premise": "被指学术造假的主持人在直播道歉时发现提词器每句认错都对应同事的一笔奖金",
        "promise": "倒计时归零前，她删掉道歉稿第一行，屏幕立刻跳出一条内部结算通知",
        "desire": "在直播结束前证明节目组把她的资料错误包装成个人造假", "setup": "她靠严格念稿成名，也因此被所有人认定没有自己的判断",
        "risk": "脱稿会触发违约并让真正的研究助理失去署名机会", "obstacle": "制片人用实时舆情数据逼她每隔三分钟承认一项新指控",
        "payoff": "她关闭主提词器，改用现场道具逐页还原资料流转，让研究助理自己念出被删掉的署名",
        "anchors": ["直播提词器", "奖金结算弹窗", "贴错标签的资料箱"], "opening": "她在倒计时三秒时拔掉脚下的翻页踏板",
        "choice": "她主动承担脱稿违约金并放弃下一季主持席", "antagonist": "制片人需要她认错保住节目版权交易，也确信一个主持人不敢离开镜头",
        "actions": ["切断主提词器信号", "按标签时间搬出资料箱", "把最后一句交给研究助理念"],
        "reactions": ["制片人", "研究助理", "直播观众与品牌方"], "hooks": ["认错句为何对应奖金", "资料标签是谁换的", "助理会不会在镜头前改口"],
        "texture": ["她脱稿时会无意识摩挲旧翻页踏板", "助理拿到话筒先纠正了她一个术语"],
        "scenes": ["道歉倒计时", "奖金弹窗", "三分钟加罪", "违约选择", "资料箱还原", "助理念署名"],
        "aftermath": ["制片人抢回镜头却被品牌方暂停结算", "助理获得署名也承认曾沉默自保", "她自证后仍离开节目而非恢复原位", "观众争论转向节目流程审计"],
        "keywords": ["直播", "娱乐圈", "打脸逆袭"], "difference": "从万能录音打脸改为可追溯的资料流转、共同责任和职业退出",
    },
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_evidence(items: list[dict[str, Any]], keywords: list[str], used: dict[str, int]) -> dict[str, Any]:
    ranked = []
    for item in items:
        if item.get("platform_format") != "official_short":
            continue
        title = str(item.get("title") or "")
        categories = " ".join(item.get("categories", []))
        score = sum(2 if keyword in title else 1 if keyword in categories else 0 for keyword in keywords)
        ranked.append((score, -used.get(item["evidence_id"], 0), item))
    if not ranked:
        raise ValueError("no official short references")
    _, _, selected = max(ranked, key=lambda pair: (pair[0], pair[1], -items.index(pair[2])))
    used[selected["evidence_id"]] = used.get(selected["evidence_id"], 0) + 1
    return selected


def to_market_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "short_rank",
        "manifest_id": item["manifest_id"],
        "evidence_id": item["evidence_id"],
        "source_item_id": item["source_item_id"],
        "source": item["source"],
        "date": "2026-07-17",
        "current": True,
        "content_status": item["rank_status"],
        "platform_format": item["platform_format"],
        "lane_classification": item["lane_classification"],
        "classification_basis": item["classification_basis"],
        "reference_title": item["title"],
    }


def verification_for(title: str, verification_map: dict[str, Any]) -> dict[str, Any]:
    record = verification_map.get(title) if isinstance(verification_map, dict) else None
    if not isinstance(record, dict):
        return {"title_status": "not_run", "concept_status": "not_run", "ip_status": "not_run", "safety_status": "not_run"}
    return {key: record.get(key, "not_run") for key in ("title_status", "concept_status", "ip_status", "safety_status")}


def make_concept(record: dict[str, Any], evidence: dict[str, Any], verification_map: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": record["title"], "audience_bucket": "female", "genre_bucket": record["genre"], "emotion_bucket": record["emotion"],
        "platform_targets": ["番茄短故事", "七猫短故事"], "premise": record["premise"], "promise_300": record["promise"],
        "desire": record["desire"], "setup": record["setup"], "risk": record["risk"], "obstacle": record["obstacle"], "payoff": record["payoff"],
        "aftermath": dict(zip(("opponent_reaction", "relationship_or_cost", "protagonist_choice", "next_state"), record["aftermath"])),
        "craft": {
            "concrete_anchors": record["anchors"], "opening_action": record["opening"], "irreversible_choice": record["choice"],
            "antagonist_self_interest": record["antagonist"], "observable_payoff_actions": record["actions"],
            "reaction_parties": record["reactions"], "micro_hook_questions": record["hooks"], "human_texture": record["texture"],
        },
        "scene_chain": record["scenes"], "market_evidence": [dict(DIRECTION), to_market_evidence(evidence)],
        "market_basis": {"observed_reference": evidence["title"], "observed_categories": evidence["categories"], "essential_difference": record["difference"]},
        "verification": verification_for(record["title"], verification_map),
        "verification_records": list((verification_map.get(record["title"]) or {}).get("records", [])) if isinstance(verification_map, dict) else [],
        "scores": {name: (2 if name == "revision_cost" else 4) for name in pooler.WEIGHTS},
        "risks": {"direct_ip": False, "unauthorized_ip": False, "sensitive_risk": 1, "hotspot_stacking": False},
    }


def bad_concepts(base: list[dict[str, Any]], qimao_item: dict[str, Any], verification_map: dict[str, Any]) -> list[dict[str, Any]]:
    bad = []
    direct_ip = json.loads(json.dumps(base[0], ensure_ascii=False)); direct_ip["title"] = "华妃重生后改写甄嬛传"; direct_ip["risks"]["direct_ip"] = True; direct_ip["risks"]["unauthorized_ip"] = True; bad.append(direct_ip)
    generic = json.loads(json.dumps(base[1], ensure_ascii=False)); generic["title"] = "她赢了以后所有人都后悔"; generic["setup"] = "异常规则与人物关系同时落地"; generic["risk"] = "失败会失去最重要的关系或生存机会"; generic["payoff"] = "主角以行动完成核心承诺并改变公开结果"; bad.append(generic)
    explain = json.loads(json.dumps(base[2], ensure_ascii=False)); explain["title"] = "真相公开后婚礼取消"; explain["craft"]["observable_payoff_actions"] = []; bad.append(explain)
    sensitive = json.loads(json.dumps(base[3], ensure_ascii=False)); sensitive["title"] = "我替现实领导改了审判书"; sensitive["risks"]["sensitive_risk"] = 5; bad.append(sensitive)
    qimao_only = json.loads(json.dumps(base[4], ensure_ascii=False)); qimao_only["title"] = "停电那天所有人都忘了我"; qimao_only["market_evidence"] = [dict(DIRECTION), to_market_evidence(qimao_item)]; bad.append(qimao_only)
    missing_aftermath = json.loads(json.dumps(base[5], ensure_ascii=False)); missing_aftermath["title"] = "他认错以后故事结束了"; missing_aftermath["aftermath"]["next_state"] = ""; missing_aftermath["scores"]["aftermath"] = 2; bad.append(missing_aftermath)
    for item in bad:
        item["verification"] = verification_for(item["title"], verification_map)
    return bad


def render(items: list[dict[str, Any]], status: str) -> str:
    lines = [f"# short {status} v3", ""]
    for item in items:
        if item["status"] != status:
            continue
        lines.extend([
            f"## {item['id']} 《{item['title']}》", "",
            f"- 题材/情绪：{item['genre_bucket']} / {item['emotion_bucket']}",
            f"- 分数：{item['score']}；判定：{', '.join(item['gate_reasons']) or '通过'}",
            f"- 承诺：{item['promise_300']}", f"- 兑现：{item['payoff']}",
            f"- 具体锚点：{'；'.join(item['craft']['concrete_anchors'])}",
            f"- 不可逆选择：{item['craft']['irreversible_choice']}",
            f"- 市场参考：《{item['market_basis']['observed_reference']}》；差异：{item['market_basis']['essential_difference']}",
            f"- 最近骨架：{item['craft_audit']['closest_title']} / {item['craft_audit']['max_structural_similarity']}",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--regression-fixtures", action="store_true")
    args = parser.parse_args()
    if not args.regression_fixtures:
        raise SystemExit(
            "run_short_v3.py contains fixed regression fixtures and is forbidden in production; "
            "use short_candidate_batch.py --raw <fresh-raw.json> --evidence-packet <frozen.json>"
        )
    catalog = read_json(args.catalog)
    verification_map = read_json(args.verification).get("titles", {}) if args.verification and args.verification.exists() else {}
    verified = [item for item in catalog["items"] if item.get("platform_format") == "official_short"]
    qimao = next(item for item in catalog["items"] if item.get("platform") == "七猫")
    used: dict[str, int] = {}
    concepts = [make_concept(record, select_evidence(verified, record["keywords"], used), verification_map) for record in STRONG_RECORDS]
    concepts.extend(bad_concepts(concepts, qimao, verification_map))
    pool = pooler.empty_pool()
    pooler.ingest(pool, concepts)
    args.outdir.mkdir(parents=True, exist_ok=True)
    write_json(args.outdir / "short_raw_v3.json", concepts)
    pooler.save_pool(args.outdir / "short_candidate_pool_v3.json", pool)
    for status in ("ready", "provisional", "rejected"):
        (args.outdir / f"short_{status}_v3.md").write_text(render(pool["candidates"], status), encoding="utf-8")
    summary = pooler.summarize(pool)
    write_json(args.outdir / "short_v3_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
