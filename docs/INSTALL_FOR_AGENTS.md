# Rank2Story — 给 Agent 阅读的安装与接入说明

> **阅读对象：**被用户授权安装 Rank2Story 的 Agent。本文是安装与配置指令，不是让用户逐条执行的命令清单。
> **项目来源：**`https://github.com/Wlove2/rank2story`（核对仓库所有者与项目名称再继续）。

## 任务目标

在用户授权的电脑或工作区中，安装**完整的 Rank2Story 项目**，识别/接入三个 Skills，并协助用户一次性配置候选生成所使用的模型。优先让用户之后只需说“生成番茄男频长篇候选”即可由 Agent 完成流程；不要要求用户自己记住命令。

**权限边界：**安装/配置不等于允许自动购买服务、公开数据、保存账号口令或抓取未获授权的内容。没有终端、文件或浏览器权限时，报告实际缺口，不能声称已安装成功。若项目地址无法访问，应报告网络或访问权限问题，不从未经核验的镜像替代安装。

## 安装和配置步骤（由 Agent 执行）

1. **检查环境和权限。**确定用户允许操作的项目目录，确认 Python 3.11+、Git 或安全的 GitHub ZIP 下载方式、必要的终端/文件读写能力。不在已有目录中强制覆盖用户文件；如需额外软件、浏览器扩展或系统权限，先询问。
2. **获取完整项目。**从 `https://github.com/Wlove2/rank2story` 下载到用户同意的目录；需要时在可执行命令的环境里运行：

   ```bash
   git clone https://github.com/Wlove2/rank2story.git
   cd rank2story
   python -m pip install -r requirements.txt
   ```

   如果用户环境中不适合使用 Git，可通过 GitHub 页面下载代码 ZIP 再解压。不要把远程下载的脚本通过“下载即执行”的管道运行。安装依赖时优先使用隔离的 Python 虚拟环境。Playwright 的 pip 包不包含浏览器二进制；如检查发现缺少 Chromium，须征得用户同意后运行 `python -m playwright install chromium`，或使用经授权的 `NOVEL_CHROMIUM_EXECUTABLE`。
3. **读取并接入 Skills。**依次阅读仓库根目录 `AGENTS.md` 与三个文件：
   - `skills/novel-market-scan/SKILL.md`：市场信息收集、来源核验、证据包生成。
   - `skills/novel-candidate-portfolio/SKILL.md`：依据证据包创建和评审候选。
   - `skills/novel-analyzer/SKILL.md`：根据请求决定调用哪些 Skills。

   如果你的 Agent 产品支持 Skills 注册，请按照**当前 Agent 产品自身的规则**登记这些 Skill 目录（不是仅复制三个 `SKILL.md`）。确保所有 Skill 可以访问完整仓库的 `scripts/`、`config/` 和 `variants/`；必要时让项目目录保持为工作区。若该 Agent 不支持自动技能发现，应明确说明并采用工作区指令 + 工具编排方式，而不是假装已安装为原生 Skill。
4. **模型配置由 Agent 引导完成。**当前候选生成、故事编辑与审核代码需要一个可供程序访问的 **OpenAI 兼容模型接口**。检查 `python scripts/model.py status` 的结果；如果缺少配置，引导用户提供 `MODEL_BASE_URL`（API 地址）、`MODEL_ID`（模型名），以及需要鉴权时的 `MODEL_API_KEY`。
   - 优先使用 Agent 平台的**安全凭据管理或受控本机输入方式**，不要要求用户把 Key 粘贴到聊天消息中。
   - 如果没有安全凭据管理能力，让用户**在本机编辑器**中填写项目根目录的 `.env`；可以由你创建该文件和其中**非敏感的模板字段**，但不要在对话、终端输出或共享日志中显示真实 Key。
   - `.env` 应位于项目根目录，与 `.env.example` 同级，内容格式如下（值都只是占位符）：

     ```dotenv
     MODEL_BASE_URL=https://your-endpoint.example/v1
     MODEL_ID=your-model-id
     MODEL_API_KEY=
     ```

   - `.env` 已被项目排除在源代码提交之外。若用户已配置有效的环境变量，保留现有设置；不要覆盖用户的原有密钥。
   - 提醒用户：这里配置的是 Rank2Story 候选生成流程使用的模型。Agent 自身的聊天模型**不会自动成为此接口**；只有 Agent 提供可供脚本访问的兼容 API 时才可能直接复用。
5. **仅做低风险自检。**在工作区运行：

   ```bash
   python examples/verify_source_manifest.py
   python examples/check_installation.py --json
   python scripts/model.py status
   python examples/run_synthetic_scan_to_candidate.py
   ```

   源码哈希检查、配置状态检查和合成数据演示**不需要真实模型 Key 或实时网页采集**。如果模型已配好并且用户同意发起真实请求，可以使用 `python scripts/model.py check` 验证连通性；它会产生一次模型调用。不要把合成数据通过等同于真实采集或真实模型候选交付。
6. **检查真实采集前提。**按下方[首次运行准备与网站授权](#首次运行准备与网站授权)逐项检查 Agent Reach、OpenCLI、浏览器、模型和各平台访问情况；具体采集来源见 [连接器说明](CONNECTORS.md)。安装完成不代表所有实时来源均已就绪。
7. **交付安装结果。**报告项目所在路径、三个 Skills 是否成功发现、依赖及离线自检结论、模型是否已配置（只报告是/否，不暴露 URL 中可能含有的敏感参数或 Key），以及真实采集还缺哪些权限/工具。安装完毕**不要擅自开启真实大规模扫榜或多轮付费模型调用**；等用户提出具体选题任务。


## 首次运行准备与网站授权

完成 Skills 安装后，依次确认**本机环境、模型接口、采集工具、平台访问**。首次安装只需进行检查和少量必要的连通性验证；网站登录由使用者在自己控制的浏览器中完成。可以先运行离线示例，待真实采集条件具备后再执行扫榜。

### 1. 核对安装状态

在项目根目录执行：

```bash
python examples/check_installation.py --json
python scripts/model.py status
```

重点核对安装报告：

| 检查项 | 就绪条件 | 不满足时 |
| --- | --- | --- |
| `python.supported`、`packages`、`skills` | Python 3.11+、依赖可导入且三个 Skill 说明文件存在；不代表 Agent 已注册 Skills | 按安装步骤补全本地文件和 Python 环境 |
| `commands.opencli`、`commands.agent-reach` | 两个命令均可调用 | 按下一节的上游文档安装或修复 |
| `browser.executable_exists` | Playwright 对应的 Chromium 已安装，或已指定可用浏览器路径 | 安装 Chromium 或配置 `NOVEL_CHROMIUM_EXECUTABLE` |
| `fanqie_decoder.custom_font_support` | 按所选番茄网页榜单决定是否还需要外置解码器 | 如遇特殊字体，用有权使用的适配器配置 `NOVEL_FANQIE_COLLECTOR` |
| `long_scan_os_supported` | 当前完整长篇采集使用 Windows | 非 Windows 环境先使用短篇扫描，或等待适配的长篇采集器 |

报告中的 `agent_skill_registration: not_checked_by_this_script` 表示脚本**不检查 Agent 产品是否真正发现或注册了 Skills**，这一步由安装 Agent 按自身平台实际确认。`offline_ready` 只涉及本地基础环境；`local_collection_dependencies_present` 也不表示站点已登录、内容读取完整。程序本身不验证登录状态，须继续完成下列检查。

### 2. 接入 Agent Reach 与 OpenCLI

两者不是 `requirements.txt` 的一部分。当前短篇和完整长篇的生产扫描预检都检查 `agent-reach`、`opencli` 命令。若系统已有可用安装，直接复用，不重复部署。

- **Agent Reach**：按[官方安装指南](https://github.com/Panniantong/Agent-Reach/blob/main/docs/install.md)配置；运行 `agent-reach install --env=auto` 进行基础依赖检查，随后运行 `agent-reach doctor` 查看需要启用的来源及连接状态。涉及安装其他系统软件时再取得授权。
- **OpenCLI**：按[官方安装指南](https://github.com/jackwener/OpenCLI/blob/main/docs/guide/installation.md)准备 CLI 和 Chrome/Chromium Browser Bridge 扩展。运行 `opencli --version`、`opencli list`、`opencli doctor`；使用浏览器登录态的适配器还需确认扩展正常连接。安装命令、Node 版本要求和扩展获取方式以所安装版本的上游说明为准。
- **Playwright**：如本机缺少 Chromium，取得授权后执行 `python -m playwright install chromium`；已有兼容浏览器也可通过 `NOVEL_CHROMIUM_EXECUTABLE` 指定。

`agent-reach doctor`、`opencli doctor` 和 `check_installation.py` 都是连接/环境检查，**不能代替对具体来源读取结果的验证**。OpenCLI 的浏览器扩展连接正常，也不代表所有网站都有有效登录态。

### 3. 逐来源检查访问与登录

按照 [平台访问与授权检查](CONNECTORS.md#平台访问与授权检查) 核对所需来源：

- **番茄、七猫、起点、晋江、纵横**：先检查指定的公开排行榜和接口能否访问。部分番茄作者侧来源需要使用者自己的有效登录会话；公开榜单不要求一律登录。
- **小红书**：如采集渠道需要登录，由使用者在自己的浏览器中完成，并通过已连接的 OpenCLI 或合法接入的适配器读取具体笔记；多图笔记必须逐张实际读取。
- **Bilibili**：检查公开搜索、视频资料以及任务需要的字幕、评论能否读取；遇到需要登录的内容，再由使用者授权。
- **番茄网页特殊字体**：不属于登录问题。若榜单文字无法可靠解析，需要单独接入有使用权的解码器。

当前短篇扫描要求 5 类来源，完整长篇扫描要求 9 类来源，具体清单由 `skills/novel-analyzer/references/source-registry.json` 决定。**不能因为某个平台已有公开网页可看，就把未获取的必需来源标记为已完成。**

### 4. 区分三种就绪状态

| 计划使用的功能 | 要完成的检查 |
| --- | --- |
| 离线演示 | Python、依赖、三个 Skills、合成示例执行成功 |
| 利用已有证据包生成候选 | 已有证据包适用于目标篇幅且校验通过；模型接口已配置并可用 |
| 新一轮真实市场扫描及候选生成 | 上述条件，加上所选扫描配置要求的工具、浏览器、网站访问、采集结果完整性检查 |

模型配置完成后，可经使用者同意执行 `python scripts/model.py check`，该命令会发出一次实际模型请求。真实扫描先按需要的 `short_production` 或 `comprehensive_long_production` 配置做预检；需要新增登录或缺少外置工具时，先完成配置再采集。

### 5. 安装完成后给出检查结果

以“**已就绪 / 需本人操作 / 尚未就绪**”区分以下内容：三个 Skills、本机 Python 与 Chromium、Agent Reach、OpenCLI、模型接口、各必需平台来源，以及是否具备复用现有证据包的条件。对尚未就绪的项目说明原因和下一步；不要把“已安装命令”“浏览器已连接”和“真实数据已采集”混成同一状态。

真实运行、文件恢复和中断续跑命令见 [使用指南](QUICKSTART.md) 及 [运行恢复](CANDIDATE_RUN_RECOVERY.md)。

## 用户之后怎样提出选题任务

通常只需三个维度：**篇幅（长篇/短篇）、目标平台（番茄/七猫）、受众（男频/女频）**。

例如：“使用 Rank2Story，生成一批**番茄男频长篇**选题。”或“生成**七猫女频短篇**候选。”

番茄和七猫是**候选作品的定位平台**，不意味着只能从这两个站点取数据。市场扫描可组合多个网文平台、视频和社区来源；详见 `docs/AGENT_INTEGRATION.md`。

## 复用已有市场数据（重要）

**市场证据包**（程序中称 `evidence_packet.json`，也称“已校验并固定版本的数据包”）是某次扫描后经来源覆盖、真实性与哈希校验的输入记录。

- 如果用户已经有**适用篇幅、来源完整且仍能满足任务时效性**的证据包，优先询问是复用还是重新扫描；**不要每次生成候选都自动重复扫榜**。
- 针对同一证据包，允许重复创建**不同的候选任务**：每次使用相同的 `--packet` 文件路径执行新的 `run`，各次任务都会有独立的运行 ID、候选生成、审核和结果，不覆盖旧任务。
- 必须核对证据包的 `lane`、内容来源与用户当前任务是否匹配。若长短篇要求不同，不能强行跨篇幅复用；如用户指定“最新市场”，应先考虑数据日期及刷新来源。
- 不把旧证据包冒充新榜单；同一批数据重复生成的候选也不保证每批都彼此不同，跨批重复仍需要检查。

详细使用方式和手动命令见 `docs/QUICKSTART.md`。实际候选流程不得省略模型调用、独立审核和 `verify` 校验。
