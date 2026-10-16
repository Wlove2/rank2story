# 候选运行：状态、续跑与重跑

Rank2Story 把软件运行状态和候选内容审核结果分开管理。**市场或原创性审查拒绝作品，是正常的候选质量结果，不应自动当作系统故障或触发无上限重试。**

## 状态与原则

| 状态 | 含义 | 推荐操作 |
| --- | --- | --- |
| `paused` | 有效任务等待操作 | 查看 `status`、租约和下一步动作，确认无并发后再明确运行 `execute` |
| `running` | 正在执行或等待响应 | 先核对租约/进程，不重复启动 |
| `candidate_generation_failed` | 任务终止（可能是内容质量未通过，需看 `failures`） | 保留全部否决与回执；确需再试则创建新 claim |
| `awaiting_user_choice` | 候选集合已准备进行最终确认 | 必须执行 `verify`，仅 `passed` 才可交付 |

## 操作命令

```bash
# 查看具体失败分类、模型调用和接受回执
python examples/candidate_run_recovery.py inspect --claim "<claim.json>"

# 终态新建任务之前先预检（只读）
python examples/candidate_run_recovery.py restart \
  --claim "<old-claim.json>" \
  --new-scripts "./variants/abc-branch-one/skills/novel-analyzer/scripts" \
  --base-root "./data/restarts"

# 显式允许新建独立暂停任务；不会采集来源或调用模型
python examples/candidate_run_recovery.py restart \
  --claim "<old-claim.json>" \
  --new-scripts "./variants/abc-branch-one/skills/novel-analyzer/scripts" \
  --base-root "./data/restarts" --create

# 对暂停而未终止的原任务，直接沿用冻结源码
python scripts/candidate.py status --claim "<claim.json>"
python scripts/candidate.py resume --claim "<claim.json>"
python scripts/candidate.py execute --claim "<claim.json>" --base-url "<model-url>" --model "<model-id>"
python scripts/candidate.py verify --claim "<claim.json>"
```

`run` 和 `restart --create` 只创建独立状态，不自动调模型。`execute` 由操作者单独授权模型端点与权限。旧 claim 无论仓库当前选择了 `abc_branch_one` 还是 `quality_strict`，都**必须使用自己冻结的 `_bundle_snapshot`**；不能把过去不合格的审核记录替换为想要的新结论。

## 保护机制

- 新 claim 会记录父子溯源关系；成功验证过的证据包和 S1 原子可按规则复用，原任务不可覆盖。
- 对中断后已保存、未接受的模型响应，冻结执行器可恢复接受，防止同一 job 重复计入。
- 市场适配、原创性、结构多样性与独立审查的否决不会因为预算耗尽、分支不足或恢复操作而自动失效。
- 只对已经停止或没有活跃执行器租约的任务操作；生产凭据和私人输出均由操作者存放在 Git 之外。

历史离线故障注入覆盖了“响应已写磁盘、接受回执前异常退出、同一 claim 恢复”的场景；**这并非真实第三方模型网络断线的完整演练**。相关测试在 `examples/test_candidate_run_recovery.py`。真实生产和历史候选交付的独立结论见 [RESULTS.md](RESULTS.md)。
