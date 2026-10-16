# 第三方项目与许可说明

本项目自有且有权许可的代码采用 [MIT License](LICENSE)。**MIT 不自动覆盖他人的源码、平台数据、书籍内容、笔记、视频、封面或第三方软件。** 如发现需要补充的授权或署名，请通过 GitHub Issues 联系维护者。

## 特别致谢：番茄榜单采集参考

感谢 [wen1701/FanqieRankTracker](https://github.com/wen1701/FanqieRankTracker) 提供的番茄排行榜 Playwright 采集实践与技术参考。本项目早期的番茄榜单研究参考了其思路，并在独立运行环境中扩展了男/女频、新榜及阅读榜的覆盖。

**许可状态（2026-10-12 核对）：**

- 上游仓库 [README](https://github.com/wen1701/FanqieRankTracker#-license) 明示“MIT”。
- GitHub 仓库的 `license` 元数据为 `null`；当前主分支根目录没有独立 `LICENSE` 文件。因此不能仅凭 README 的一行声明，替上游补写法律授权条款或假定所有代码均可任意再许可。
- **本仓库未打包该上游的 `scrape_fanqie_ranks.py` 或原字体映射实现**。当前的 `fanqie_decoder.py` 是保守的 Unicode 解码方案；真实历史扫榜曾在操作者本机使用**另外提供的外部解码器**，该外部源码并未附带分发。
- `fanqie_refresh.py` 支持操作者通过 `--legacy-script` / `NOVEL_FANQIE_COLLECTOR` 自行接入有权使用的实现。**允许用户自主接入，并不意味着本项目替用户获得了该脚本的许可。**
- 如果未来计划复制、修改或重新分发上游任何源文件，应先核对适用版本的许可正文，必要时向原作者确认，并保留版权声明；在此之前不要把外部脚本纳入仓库。

这是**技术参考与致谢**，并不表示上游作者审核、认可、赞助或参与维护本项目。

## 其他外部项目

| 项目 | 上游地址 | 核对的上游许可 | 本仓库中的使用 |
| --- | --- | --- | --- |
| [Agent Reach](https://github.com/Panniantong/Agent-Reach) | Panniantong/Agent-Reach | MIT | 可选外部采集工具，不打包 |
| [OpenCLI](https://github.com/jackwener/OpenCLI) | jackwener/OpenCLI；[相关分支](https://github.com/qiaozhishuo/opencli) | Apache-2.0 | 可选命令行工具，不打包 |
| [Playwright Python](https://github.com/microsoft/playwright-python) | microsoft/playwright-python | Apache-2.0 | 通过包管理器安装 |
| [lxml](https://github.com/lxml/lxml) | lxml/lxml | BSD-3-Clause | 通过包管理器安装 |
| [pytest](https://github.com/pytest-dev/pytest) | pytest-dev/pytest | MIT | 测试依赖 |

表格中的许可证依据各仓库截至 2026-10-12 的公开 GitHub 元数据；**这不是项目代码被整体重新授权**。依赖通过正常方式安装时，应保留其随包提供的许可证及声明。若日后直接复制第三方代码，必须另行检查来源、版本、许可证条件并更新此页。

## 平台内容与用户输出

番茄小说、七猫小说、起点中文网、晋江文学城、纵横中文网、小红书和 Bilibili 均为各自平台运营者所有。本项目不隶属于这些平台，平台名称仅用于来源说明。

项目内公开的历史成果仅使用精选书名、笔名、榜位、公开统计及对应来源链接等可核对的元数据，未附带作品完整正文、笔记全文或视频字幕。即便是元数据，使用者仍应遵守平台条款、访问权限及相关法律，不得将本仓库的 MIT 许可视为第三方内容的再利用授权。

关于运行日志、用户个人资料、模型端点与数据发布，请见 [数据与隐私](docs/DATA_AND_RIGHTS.md)。
