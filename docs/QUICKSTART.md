# 使用指南｜安装、模型配置与候选生成

Rank2Story 通过三个 Agent Skills 组织市场研究和候选生成流程，安装后可以直接用自然语言指定作品定位。

## 第一步：交给 Agent 安装

> 请阅读 https://raw.githubusercontent.com/Wlove2/rank2story/main/docs/INSTALL_FOR_AGENTS.md ，按说明为我安装 Rank2Story 的三个 Skills，检查环境，指导我安全配置候选生成模型，并完成离线自检。安装完成后告诉我哪些功能可用、哪些数据源还需授权。

[查看给 Agent 的安装文档](INSTALL_FOR_AGENTS.md) · [Skills 使用方式](AGENT_INTEGRATION.md)

安装文档包含项目下载、三个 Skills 接入、模型配置和环境验证。第一次进行实时扫榜前，按[首次运行准备与网站授权](INSTALL_FOR_AGENTS.md#首次运行准备与网站授权)检查 Agent Reach、OpenCLI、浏览器及各来源的访问条件。

## 第二步：填写自己模型的信息

在项目根目录中填写模型 API 地址、模型名称以及服务需要的 Key。项目提供 `.env.example` 配置模板，可以复制为 `.env` 后编辑，也可以由 Agent 创建个人配置文件：

```dotenv
MODEL_BASE_URL=https://your-endpoint.example/v1
MODEL_ID=your-model-id
MODEL_API_KEY=
```

`MODEL_BASE_URL` 填自己的模型 API 地址，`MODEL_ID` 填模型名，`MODEL_API_KEY` 填模型服务要求的密钥（无需鉴权可留空）。上述地址和模型名只是占位，不能直接使用。

Key 应通过本机编辑器或安全凭据管理输入，避免在聊天记录、运行日志和公开文件中暴露。`.env` 是个人本机配置；完成一次配置后，后续候选任务会自动读取。

Agent 聊天模型与项目的候选生成接口是不同的调用途径。当前项目需要可供脚本访问的 OpenAI 兼容模型 API；不能保证仅凭安装 Skills 就能直接复用聊天模型。

## 第三步：直接提出候选任务

候选任务由三个维度构成：**篇幅（长篇/短篇）、目标平台（番茄/七猫）、受众频道（男频/女频）**。篇幅决定故事体量与节奏，目标平台决定内容定位，受众频道决定主要读者群体。

> 使用 Rank2Story，为**番茄 · 男频 · 长篇**生成一批小说选题。优先使用符合条件的已有市场证据包，需要更新时再采集，并按 A/B/C 路线完成构思、编辑、审核和交付。

**市场资料来源与作品目标平台不同。** 项目综合七个平台的市场信号开展研究；目前候选作品定位支持番茄与七猫，其他平台提供研究参考。[查看来源与目标平台说明](AGENT_INTEGRATION.md)。

### 扫一次，生成多次

扫描后保存的“市场证据包”是有日期、来源和校验结果的**固定版本市场资料**。只要它仍满足同一篇幅、来源覆盖和时效要求，你就能说：

> 沿用上次的市场证据包，**再生成一批七猫女频短篇候选**，不要自动重复扫榜。

Agent 应先检查该证据包是否确实适用于**新指定的篇幅与目标**；不适用时应明确告知并按需重新扫描。每批候选都建立独立任务，不覆盖上一批；旧包不等于实时榜单，重复生成也可能有跨批撞梗。

## 第四步：手动使用（可选）

手动创建个人模型配置时，可通过以下命令复制模板：

- Windows PowerShell：`Copy-Item .env.example .env`，然后运行 `notepad .env` 编辑。
- macOS / Linux：`cp .env.example .env`，然后用本机编辑器打开 `.env`。

通过 Agent 接入时，配置文件创建由安装流程完成。

不使用 Agent 的高级用户，可在**已经安装依赖的仓库根目录**运行：

```bash
# 用合成数据体验流程：不发真实模型请求，不抓实时网页
python examples/run_synthetic_scan_to_candidate.py

# 仅检查有无模型配置，不显示 Key
python scripts/model.py status

# 配置好模型后，可选择发起一次真实模型连通性请求
python scripts/model.py check
```

真实候选需要合规扫描并得到 `evidence_packet.json`，然后：

```bash
python scripts/candidate.py run --base-root ./data/runs --packet "<evidence_packet.json路径>" --lane long --platform fanqie --channel male
python scripts/candidate.py execute --claim "<run 返回的 claim 路径>"
python scripts/candidate.py status --claim "<run 返回的 claim 路径>"
python scripts/candidate.py verify --claim "<run 返回的 claim 路径>"
```

**同一个证据包能重复创建新任务**：每次重新 `run`，指定相同 `--packet` 文件路径，但任务和审核结果独立保存。`execute` 会发出模型调用；`verify` 只有在候选审查通过时才会显示 `passed`。高级用户也可以通过 `--base-url`、`--model`、`--api-key-env` 显式指定模型连接参数；使用项目配置时无需这些参数。

若要求近期社交证据且指定天数，可在**新任务的扫描初始化**时添加 `--max-social-age-days 30`（示例为以 UTC 日期计算的 30 天窗口）。过期记录不能凑社交来源配额；默认扫描和旧证据包不受影响。详见 [数据源接入](CONNECTORS.md)。

市场扫描的 `python skills/novel-market-scan/scripts/start.py --profile short_production` **只做扫描初始化和环境预检**，不代表一条命令完成全部网页抓取。实际采集还需合法权限、浏览器及可能的外部适配器。详见 [数据源接入](CONNECTORS.md) 和 [模型连接](MODEL_CONNECTIVITY.md)。

[Agent 安装文档](INSTALL_FOR_AGENTS.md) · [策略配置](POLICY_CONFIGURATION.md) · [中断恢复](CANDIDATE_RUN_RECOVERY.md)。
