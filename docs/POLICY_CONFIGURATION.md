# 候选策略配置

Rank2Story 提供两种可选的候选生成策略，通过完整仓库根目录的 `scripts/candidate.py` 统一使用。两种策略均需要真实来源证据、独立审核和最终交付校验。

## 配置默认策略

`config/candidate.json` 示例：

```json
{
  "candidate": {
    "policy": "abc_branch_one"
  }
}
```

| 策略名 | 说明 |
| --- | --- |
| `abc_branch_one`（默认） | 优先确保 A/B/C 各路线的结构多样性；最终每条路线需要至少一张独立审核通过的候选 |
| `quality_strict` | 独立的历史严格策略，中间阶段要求更多候选存活；最终交付规则以该策略的冻结控制器为准 |

## 常用命令

```bash
# 查看当前配置
python scripts/candidate.py config

# 用默认策略创建新的候选任务（需要真实、已验证的冻结证据包）
python scripts/candidate.py run --base-root ./data/runs --packet "<evidence_packet.json路径>" --lane long --platform fanqie --channel male

# 仅为本次新任务选择另一种策略
python scripts/candidate.py run --policy quality_strict --base-root ./data/runs --packet "<evidence_packet.json路径>" --lane long --platform fanqie --channel male

# 下列操作仅作用于该任务创建时保存的代码快照
python scripts/candidate.py status --claim "<claim.json路径>"
python scripts/candidate.py resume --claim "<claim.json路径>"
python scripts/candidate.py verify --claim "<claim.json路径>"
```

`run` 和 `config` **不调用模型**。真实执行需要另外使用 `execute --claim`，并提供模型 API 地址、模型 ID 和（需要时）Key 所在环境变量。完整操作见 [使用指南](QUICKSTART.md)。

策略选择优先级：`run --policy` 高于 `run --config` 指定的配置文件，高于默认 `config/candidate.json`。只有新建任务时能够选择策略。执行中的任务始终沿用自己的冻结代码，修改配置不会偷换已有任务的审核规则。

## 与 Agent Skills 集成

当三个 Skills 与根目录的 `scripts/`、`config/`、`variants/` 一起安装时，推荐由外部 Agent 或用户调用根目录的统一入口。若仅单独复制 Skills 子目录，目录内的候选脚本是独立兼容入口，**不会自动读取根目录不存在的策略配置**。

质量审查未通过时会如实返回失败结果，不会为了凑齐候选自动跳过市场评审、原创性审查或结构去重。证据输入与用户隐私应留在操作者本地。