# Rank2Story · Agent 工作区使用说明

本项目以三个独立 Agent Skills 组织工作流。用户可以让支持 Skills、文件操作和脚本执行的 Agent 读取对应指令，再调用项目中的校验与候选执行脚本。

## 三个 Skills

- `skills/novel-market-scan/SKILL.md`：市场扫描、来源覆盖、采集记录和冻结证据包。
- `skills/novel-candidate-portfolio/SKILL.md`：基于已冻结证据的 A/B/C 候选创建、编辑、双审、筛选及最终校验。
- `skills/novel-analyzer/SKILL.md`：为“扫榜加候选”等综合请求选择正确的前两项能力；不重复实现工作流。

优先保留**完整仓库**，而不是只复制三个 `SKILL.md`；`scripts/`、`config/`、`variants/`、三个 `skills/` 下的引用文件和校验工具都参与实际执行。

## Agent 执行约定

1. 先阅读根目录 `README.md`、三个 `SKILL.md` 和 `docs/AGENT_INTEGRATION.md`；仅在所用 Agent 具备 Skills 发现功能时，按照其自己的说明登记三个 Skill 目录。
2. **完整候选任务优先解析三个维度：篇幅（长/短）、目标平台（番茄/七猫）、受众频道（男/女）**。例如“生成番茄男频长篇选题”应执行扫描→冻结证据→A/B/C 候选→审核与校验，而不是只给市场调研结果；目标平台仅限定候选定位，市场扫描仍按多来源配置进行。若用户只要求扫榜或复用冻结证据，则仅执行相应阶段。不擅自生成小说正文或公开候选。
3. 在决定是否采集之前，先检查是否已有**篇幅适用、来源覆盖达标且时效合适的市场证据包**（`evidence_packet.json`）。有合格证据时询问用户复用还是更新，而不是每批候选都自动重扫；没有合格数据时才检查采集权限、浏览器和外部适配器。预检不等于抓取，不允许伪造数据。
4. 采集或复用时都必须校验证据包完整性、记录原采集日期和哈希；候选阶段只接收合格证据包。**同一份证据包可用于多个独立新候选任务**，每次新建 run/claim，禁止覆盖已有任务或把旧榜单当成当天的新数据。
5. 生成任务用完整仓库的 `python scripts/candidate.py run`；模型执行用 `python scripts/candidate.py execute --claim ...`；最后必须 `verify`。各操作必须使用同一 claim 的冻结快照，不应手工修改审查回执。
6. Agent 的现有聊天模型**不自动等同于**这个执行器的 OpenAI 兼容 HTTP 端点。若 Agent 能提供受支持的模型接口，可在未提交的 `.env` 中配置或在执行时显式传参；否则需要独立接口或自行实现受验证的 Agent 原生任务执行适配。
7. 不把私有 Key、Cookie、完整第三方内容、个人路径、账号会话或未获许可的数据提交到 Git。不要在聊天回复中粘贴 Key。

## 快速开始

- 安装依赖和离线演示：[docs/QUICKSTART.md](docs/QUICKSTART.md)
- 给 Agent 的安装文件：[docs/INSTALL_FOR_AGENTS.md](docs/INSTALL_FOR_AGENTS.md)
- Agent/Skills 接入说明：[docs/AGENT_INTEGRATION.md](docs/AGENT_INTEGRATION.md)
- 模型设置：复制 `.env.example` 为根目录 `.env`（被 Git 忽略），按本机模型配置填写；`python scripts/model.py status` 只输出配置是否存在，不打印 Key。

项目的根目录包含 `AGENTS.md` 只表示有提供给支持此约定的 Agent 的工作说明，并**不代表所有 Agent 产品都可自动发现、加载三个 Skill 或复用自己的语言模型**。
