# 平台刮削记录

## 番茄小说 (fanqienovel.com)

- **可刮削**: 是
- **当前开源实现**: `scripts/fanqie_refresh.py` + Playwright + 原创基础文字解码器 `scripts/fanqie_decoder.py`；自定义字体未知映射时必须降级而非猜测。FanqieRankTracker 是历史参考项目，不是强制依赖，其源码不随仓库发布。
- **URL 模式**: `/rank/{gender}_{type}_{category}`
  - gender: 0=女频, 1=男频
  - type: 1=新书榜, 2=阅读榜
  - 仅 4 种榜：女频新书/男频新书/女频阅读/男频阅读
- **注意**: 页面有自定义字符编码，需要 decode_text 函数
- **交互式浏览器抓取方式**: 可加载页面但分类切换需要 30+秒/个，效率低

## 纵横中文网 (zongheng.com)

- **生产 collector**：`scripts/collect_paid_platform_ranks.py --platform zongheng`
- **固定 URL**：`https://www.zongheng.com/rank`
- **验收**：6 榜、57 席、33 本去重；两轮有序 ID 一致。

## 晋江文学城 (jjwxc.net)

- **生产 collector**：`scripts/collect_paid_platform_ranks.py --platform jjwxc`
- **固定 URL**：`https://www.jjwxc.net/topten.php?orderstr=4`
- **编码**：原始响应按 GB18030 解码。
- **验收**：当前季度榜 200 席；两轮有序 ID 一致。

## 起点中文网 (qidian.com)

- **生产 collector**：`scripts/collect_qidian_browser_ranks.ps1`
- **固定路径**：月票、畅销、阅读指数、推荐、签约作者新书 5 榜；不允许模型现场找 URL/selector。
- **获取方式**：`opencli` Chrome bridge；固定 `.book-img-text li` DOM 合同，每榜少于 20 席直接失败。
- **验收**：5 榜、100 席、59 本去重；两轮有序 ID 一致。动态字体数值可标 obfuscated，其他作品字段必须完整。
## 七猫小说 (qimao.com)

- **可刮削**: 是
- **方法**: `collect_qimao_web_ranks.py` 采集男女频 × 大热/新书/完结/收藏/更新 10 个公开频道；读者端另由 `collect_qimao_reader_ranks.py` 采集。
- **限制**: Web 10 频道缺一即降级；读者端大热接口当前只返回 8 条，不能代替 Web 完整度硬门。

## 小红书 / B站

- **生产要求**: 使用 agent-reach。小红书执行 search → note → download 全部图片并顺序读取；B站执行 search → video → subtitle，缺字幕时转写音频。
- **可评分字段**: 原 URL、发布时间、互动量、完整图文/字幕缺一不可。
- **摘要降级**: `automated_public_search_summary + metadata_only + signal_eligible_entries: 0`；摘要进入 manifest 说明做过搜索，但不进入 signal matrix。
- **数量与结构**: 每个平台发现至少 30 个 canonical URL、筛选至少 15 个、完整合格至少 8 个；至少 5 个账号，单账号最多 2 条，并满足登记内容类型配额。
- **账号与榜单转载**: watchlist 账号只提高发现召回；每个当前内容仍须验真。纯转载本轮已采官方榜单写 `official_rank_repost`，保留出处但热度增量为 0。
- **详细合同**: [social-source-policy.md](social-source-policy.md)。

## FanqieRankTracker

- **URL**: https://github.com/wen1701/FanqieRankTracker
- **覆盖**: 番茄全榜单（女频新书/男频新书/女频阅读/男频阅读）
- **已扩展**: scrape_fanqie_ranks.py v2.0 4 榜单自动循环 (2026-06-27)
- **运行**: Playwright + GitHub Actions 每日自动
