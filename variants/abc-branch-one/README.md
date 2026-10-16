# A/B/C 选题策略（`abc_branch_one`，4.4.2）

该目录提供 Rank2Story 的 A/B/C 多路线候选控制器。仓库根目录 `scripts/candidate.py` 默认使用此策略；若希望使用另一种初筛规则，可以选择 `quality_strict`。策略名称在 `config/candidate.json` 中配置。

## 主要规则

- A/B/C 各自生成结构不同的故事内核，经故事创作、编辑、候选映射后进入独立审查。
- 市场适配与原创性审核均可否决候选，不能通过跳过审核强制交付。
- A/B/C 最终各需至少一张审核合格且机制独立的候选，整体还需满足结构多样性与交付数量要求。
- 支持有界的替补生成、结构去重、Pareto 组合选择；当条件无法满足时如实返回 `candidate_generation_failed`。
- 已创建的任务保留自身冻结的源码与证据，不会被修改后的默认策略覆盖。

## 调用方式

推荐在**仓库根目录**使用：

```bash
python scripts/candidate.py config
python scripts/candidate.py run --base-root ./data/runs --packet "<证据包路径>" --lane long --platform fanqie --channel male
python scripts/candidate.py status --claim "<claim.json路径>"
```

`run` 不请求模型。要继续真实模型生成，请阅读 [Quickstart](../../docs/QUICKSTART.md) 完成模型地址与 Key 配置，并在同一 claim 上运行 `execute` 和 `verify`。

## 测试与局限

版本化文件通过 `V442_POLICY_MANIFEST.json` 的 SHA-256 校验；本策略具有确定性回归、恢复机制与合成数据集成测试。真实候选的市场与原创性审核仍可能拒绝整个批次，这属于正常的内容质量结果，不能冒充成功交付。