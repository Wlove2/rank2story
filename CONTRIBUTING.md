# 参与贡献

感谢关注 Rank2Story！这个项目由 3 个 Agent Skills 和 Python 工作流组成，主要解决**中文网文市场研究与故事选题**中的证据采集、结构化分析和候选审核问题。

## 从哪里开始

- **发现问题**：通过 GitHub Issue 报告可复现的异常；请填写运行环境、复现步骤、预期结果和实际结果。
- **改进功能**：先提交简要的功能建议，说明适用平台、业务用途和可以验证的结果。
- **贡献代码**：建议一次 PR 聚焦一个问题；不要在修复采集逻辑时顺便修改故事生成和审核规则。

## 本地验证

要求 Python 3.11+：

```bash
python -m pip install -r requirements.txt
python examples/verify_source_manifest.py
python examples/run_synthetic_scan_to_candidate.py
python -m pytest -q
python -m unittest discover -s examples -p "test_*.py" -q
```

源码包含冻结的历史基线及可选 A/B/C 控制器。**不要直接改写冻结核心文件后仍沿用旧版源码哈希**；若需要变更运行规则，请讨论版本兼容性、运行状态和源文件校验的更新方式。

## 数据与版权

**请勿提交：** Cookie、API Key、浏览器登录态、账号资料、未脱敏的本地路径、原始小说全文、付费内容、笔记或视频全文，以及未经许可复制的外部采集器源码。

欢迎用人工构造的离线样本或少量有来源的公开元数据复现问题。真实平台的榜单、动态字体、权限和页面结构可能变化；反馈时请说明日期及实际环境，不要把站点拒绝访问伪装为程序错误。

相关说明：[第三方许可](THIRD_PARTY.md) · [数据与隐私](docs/DATA_AND_RIGHTS.md) · [安全说明](SECURITY.md)。

## 提交要求

PR 请至少包含：改动目的、涉及文件、运行的测试、兼容性影响和必要的截图或日志（务必脱敏）。开源贡献应遵循项目 MIT License 和涉及的第三方许可。
