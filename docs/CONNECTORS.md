# 实时采集与连接器

`novel-market-scan` 是工作流 Skill。实时扫榜需要访问相应平台的合法权限、可用的浏览器和必要的外部采集适配器；**本项目不提供账号、Cookie 或第三方无再分发许可的字体映射代码**。

## 安装检查

```bash
python -m pip install -r requirements.txt
python examples/check_installation.py --json
python skills/novel-market-scan/scripts/start.py --help
```

**首次安装准备：** `pip install playwright` 不会自动安装 Chromium；按 `examples/check_installation.py --json` 检查，缺失时经用户同意执行 `python -m playwright install chromium`，或配置 `NOVEL_CHROMIUM_EXECUTABLE`。 `opencli`、`agent-reach` 不是 Python requirements 的一部分，需要从[其上游项目](../THIRD_PARTY.md)确认安装方式和合法授权。安装诊断退出 0 仅代表检查已完成，不代表浏览器启动、登录、真实采集或模型服务经过验证。

**系统限制：** 起点长篇采集器 `collect_qidian_browser_ranks.ps1` 使用 Windows `System32/chcp.com`，当前没有验证过的非 Windows 替代采集器。正式长篇扫描在非 Windows 上预检报 `COLLECTOR_PLATFORM_UNSUPPORTED` 并停止；短篇流程没有这一依赖。番茄完整网页排名仍可能需要独立获得授权的字体解码器。

合成测试无需平台登录和模型请求，详见 [Quickstart](QUICKSTART.md)。实际网页采集前应核实目标平台最新使用条款、页面结构和请求频率，不要将本项目视为平台官方 API。

## 可选：近期社交证据时间窗口

常规市场扫描沿用原有来源配额，不额外排除较早发布的帖子或视频。如果用户**明确指定近期读者反馈的时间范围**，可在新建扫描任务时启用时效门槛：

```bash
python skills/novel-market-scan/scripts/start.py --profile short_production --max-social-age-days 30
```

此例表示从扫描初始化时锁定的 **UTC 日期**向前最多 30 天。该限制只作用于小红书和 Bilibili 的独立有效社交信号，不改变小说榜单的采集时间、完整内容要求或其他来源规则。过期、日期无法解析及未来日期的内容不计入合格社交配额；不足时来源覆盖验证失败，正式证据包不可冻结。被标记为非独立信号的转载仍可保留溯源，但不能凑配额。

未传此选项时默认扫描行为不变。此门槛随新扫描的 `run_manifest.json` 冻结，在覆盖验证和证据包冻结时复核；不会追溯改变已冻结的旧证据包，也不能把过时内容冒充为新采集记录。扫描初始化依然不代表实际已抓取网站。

## 平台访问与授权检查

首次使用时，先完成[安装环境与工具检查](INSTALL_FOR_AGENTS.md#首次运行准备与网站授权)，再逐个验证扫描所依赖的来源。**需要授权的是实际受限制的站点访问或浏览器操作，并非必须同时登录七个平台。** 按当前采集适配器与网站的可访问情况决定。

| 平台 / 来源 | 初次验证的内容 | 什么时候需要使用者操作 |
| --- | --- | --- |
| 番茄公开排行榜、阅读榜 | 榜单可打开，分类、作品 ID、标题等关键字段可可靠提取 | 若特殊字体无法解析，另行接入有权使用的外置解码器；并非通过登录解决 |
| 番茄作者端短篇热榜、活动及公告 | 作者端指定来源可以访问并返回预期内容 | 需要身份验证时，由使用者登录自己的作者端账号 |
| 七猫公开排行、阅读端短篇榜 | 所需榜单/API 有效，并取得完整的实际榜单记录 | 出现限制或需要身份验证时，再使用已获授权的访问途径 |
| 起点、晋江、纵横 | 指定公开榜单内容可访问并解析；起点长篇还检查 Windows 采集条件 | 只有实际遇到账号限制时才需本人登录，不预设全部要账号 |
| 小红书 | 可用的采集渠道确实能搜索、读取笔记正文及所需图片；多图笔记逐张完整读取 | 浏览器会话或适配器要求登录时，由使用者在自己的浏览器完成；不能把仅有搜索摘要算作有效笔记 |
| Bilibili | 搜索和视频信息可以读取，所需字幕、评论等内容可实际获取 | 部分数据受访问限制时，由使用者登录或提供获授权的可用访问方式 |

**Agent Reach 与 OpenCLI 的实际检查：**

```bash
agent-reach doctor
opencli --version
opencli list
opencli doctor
```

OpenCLI 使用浏览器会话的功能依赖其 Browser Bridge 扩展和使用者已登录的对应网站；`opencli doctor` 连通不代表小红书笔记、B 站字幕或具体排行榜一定可读。安装与授权方式参考 [Agent Reach](https://github.com/Panniantong/Agent-Reach/blob/main/docs/install.md) 和 [OpenCLI](https://github.com/jackwener/OpenCLI/blob/main/docs/guide/installation.md) 的上游文档，优先复用现有工具，不重复安装。

短篇正式采集的五个必需来源为番茄作者端短篇热榜、番茄阅读端短篇榜、七猫阅读端短篇榜、小红书读者需求和 Bilibili 读者需求；完整长篇采集要求番茄与七猫的网页榜和阅读端榜、纵横、晋江、起点、小红书及 Bilibili 九类来源。实际名称、范围、配额及是否通过，以 [source-registry.json](../skills/novel-analyzer/references/source-registry.json) 和当次运行校验为准。

只有每个必需来源的真实采集结果经过完整性检查，才能计入正式覆盖；无法访问或部分材料缺失应如实返回状态，不以模拟数据或其他平台的结果替代。

## 平台与能力

| 来源类别 | 工作流用途 | 使用前提 |
| --- | --- | --- |
| 番茄网页排行榜 | 男女频、分类、新榜/阅读榜与阅读者趋势 | 浏览器、合规访问、可能需要外置专用字体解码器 |
| 番茄作者侧动态 | 作者活动、投稿规则、站内作者信号 | 有效的访问权限，部分入口可能需要本人授权登录 |
| 七猫网页与阅读榜 | 市场对比、短篇/长篇排行与受众信号 | 对应公开页面/API 当前仍可访问 |
| 纵横、晋江、起点相关公开页面 | 长篇付费/题材趋势交叉核实 | 各站授权与网页兼容性，不保证全网稳定 |
| Bilibili | 读者反馈、小说推荐与题材讨论 | 公共搜索、去重和来源配额 |
| 小红书 | 图文读者需求证据 | 合法可访问的公开笔记；**多图笔记必须完整读取全部图片**才可作为完整证据 |

某平台失败或只有部分图片读取成功时，工作流应**保留失败状态**并阻止将其算入覆盖配额，不能凭猜测凑满样本。各来源配额及其版本见 `skills/novel-analyzer/references/source-registry.json` 与 Skill 文档。

## 番茄采集的第三方参考

本项目早期参考了 [wen1701/FanqieRankTracker](https://github.com/wen1701/FanqieRankTracker) 的 Playwright 榜单采集实践，感谢原作者。上游 README 声明 MIT，但当前仓库不提供独立 LICENSE 文件或可识别的 GitHub License 元数据。我们没有打包上游脚本或字形映射；可选外部解码器须由操作者自行确认使用权。具体见 [第三方项目与许可](../THIRD_PARTY.md)。

## 番茄字体：已跑通的路径

2026-10-09 操作者本机使用**本地已有的外置字形解码器**收集 4 组榜单，74/74 分类、740 条记录有效：

```bash
# 这里是接口示意：传入你自己有权使用的本机解码脚本
python skills/novel-analyzer/scripts/fanqie_refresh.py --help
# 独立的接入配置项为 --legacy-script 或 NOVEL_FANQIE_COLLECTOR
```

- 外部模块必须兼容采集器期望的 `decode_text` 接口；**仅将路径作为参数使用，不将第三方源码复制进入 Git**。
- 内置 `fanqie_decoder.py` 可处理正常 Unicode，并在无法可靠解码特殊字体时保守报错。
- `fanqie_detail_metadata.py` 提供基于真实作品 ID 的官方详情页标题核对/回退；已做小规模验证，**没有宣称不使用外置解码器也能在全新机器上稳定获取 740 条**。
- 操作者历史成功 ≠ 公开仓库保证今日榜单随时可用。对网站权限和字体版权必须独立核实。

## 社交多媒体和证据完整性

Bilibili 扫描可复用既有筛查进度并对视频 ID 去重；同一作者占比受配额限制。小红书笔记的图片读取可选在操作者本地调用视觉模型，结果记录实际读取图片数和完整性标记；无法下载的图片不能隐式视为已读。

**不要提交**原始短视频/笔记文本、账号登录态、签名 CDN URL 或未获授权的小说内容。每条合格的抽象证据都必须能追溯到它的来源标识，但完整源材料由操作者本地自行保存。

## 真实结果与边界

[查看 2026-10-09 已验证的 9/9 来源和 74/740 榜单汇总](RESULTS.md)。该页不再分发第三方书籍原始内容。模型连接、恢复机制分别见 [MODEL_CONNECTIVITY.md](MODEL_CONNECTIVITY.md)、[CANDIDATE_RUN_RECOVERY.md](CANDIDATE_RUN_RECOVERY.md)。
