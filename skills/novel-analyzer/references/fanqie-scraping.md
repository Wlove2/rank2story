# 番茄小说排行榜刮削技术记录

> **开源版 2026-10-09 更新：** 以下为历史研发记录，并非当前站点的实时可用性保证。公开仓库已用原创 `scripts/fanqie_decoder.py` 替代对无明确许可证 FanqieRankTracker 解码函数的强制依赖。默认仅处理普通 Unicode，遇自定义私用区字形明确失败而不猜测。必要时使用 `NOVEL_FANQIE_COLLECTOR` 加载使用权明确的可选解码器；可用 `NOVEL_CHROMIUM_EXECUTABLE` 选择已有 Chrome。真实站点访问及版权授权须另行验证。

## 发现过程

尝试了三种方式刮削番茄排行榜：
1. `requests` + BeautifulSoup → 失败（页面内容编码防爬）
2. 交互式浏览器快照 → 能加载页面但无法从 accessibility tree 提取书卡
3. FanqieRankTracker 的 Playwright 方案 → 可行

## FanqieRankTracker 原理

```
技术栈: Playwright (真实浏览器) + 自定义字符映射解码

URL 结构: https://fanqienovel.com/rank/{性别}_{类型}_{分类ID}
  性别: 0=女频, 1=男频
  类型: 1=新书榜, 2=阅读榜（实测确认，不是 0！）
  分类ID: 1139 等

关键发现（2026-06-27）:
  男频种子页 (/rank/1_1_1139) 只出分类菜单，不出书列表。
  女频种子页 (/rank/0_2_1139) 直接出书列表。
  脚本必须：先点击分类链接 → 等待加载 → 提取书籍。

流程:
  1. 从种子 URL 打开页面
  2. 等待 menu / rank / category 选择器出现（不是 /page/ 链接）
  3. JS 动态提取所有分类标签 (a[href^="/rank/X_Y_"])
  4. 逐一点击每个分类 → 等待加载 → scroll 3次 → 提取前30本书
  5. 自定义字符映射解码文本（番茄将文字编码防爬）
  6. 增量写入 JSON（支持中断恢复）
  7. 分类间 sleep 5秒
```

## Playwright 配置要点

**当前独立仓库：** 使用本项目的 Python 3.11+ 虚拟环境（按 `docs/QUICKSTART.md` 安装）。不需要安装特定 Agent 平台的专用 Python 环境。

正确命令：
```bash
"$PY" scripts/fanqie_refresh.py --output-root "$RUN_ROOT/raw/fanqie_public_web_ranks" --date "$DATE"
```

`$PY` 应指向当前项目虚拟环境；`$RUN_ROOT` 来自 `scan_start.py` 创建的当前 run。真实采集输出必须在该 run 的隔离目录下，不得改写到 Desktop、旧 `source_snapshots` 或共享日期根。

验证：
```bash
"python" -c "from playwright.sync_api import sync_playwright; print('playwright OK')"
```

## 进程监控

Playwright 脚本运行时：
- `process poll` 可能长时间返回空 output_preview
- 验证方法：`tasklist | grep chrome`（应看到多个 chrome.exe 进程）
- 如果 chrome 进程数 > 0 且状态为 running，说明在正常运行

## 验证结果

- 女频新书榜: `/rank/0_1_*` ✅ 已验证（FanqieRankTracker 默认）
- 男频新书榜: `/rank/1_1_*` ✅ 已验证（19个分类）
- 女频阅读榜: `/rank/0_2_*` ✅ 已验证（18个分类）
- 男频阅读榜: `/rank/1_2_*` ✅ 已验证（19个分类）

## 已完成修复 (2026-06-27)

历史生产环境曾使用独立 FanqieRankTracker v3.0 外部脚本完成四类榜单循环（源代码不在本开源仓库内，也不是当前默认依赖）。
- 修复男频种子页只出菜单不出书的问题
- 修复 wait_until="load" 超时问题
- 仅 4 种榜单类型，无热搜榜/口碑榜等其他类型。

## 运行时坑与修复 (2026-06-27 实测)

**坑1：西方奇幻分类提取为0本**
- 现象：男频新书榜/阅读榜的"西方奇幻"分类，脚本JS提取器返回0本书
- 根因：该分类页面DOM结构与提取器假设不匹配（container.innerText.includes('在读') 判定失败）
- 规避：直接访问分类URL（如 `/rank/1_1_1141`）验证；若实际有书，在最终分析中标注该分类数据缺失，不纳入统计
- 临时补抓脚本：访问直接URL后用相同extract_js提取，覆盖JSON中对应分类的books字段

**坑2：点击分类后等待时间不足**
- 现象：page.locator().click() 后立即提取，books=0
- 修复：`time.sleep(2)` → `time.sleep(8)`，并增加 `page.wait_for_selector('a[href^="/page/"]', timeout=5000)`

**坑3：task_state_*.json 导致跳过逻辑**
- 现象：重新跑脚本时所有分类都显示"跳过"
- 根因：task_state文件记录已完成分类，即使数据文件不存在也跳过
- 修复：重跑前删除 `data/task_state_*.json`

**坑4：await 在同步函数中导致 SyntaxError**
- 现象：patch时加了await报错 `SyntaxError: 'await' outside async function`
- 根因：scrape_fanqie_ranks.py 使用同步playwright API，不是async
- 修复：去掉await，保持 `page.locator().click()` 和 `page.wait_for_selector()` 同步调用

## 数据产出验证 (2026-06-27)

成功产出4个JSON文件：
- `fanqie_male_new_ranks_20260627.json`: 380 books (19 categories × 20)
- `fanqie_male_read_ranks_20260627.json`: 380 books (19 categories × 20)
- `fanqie_female_new_ranks_20260627.json`: 360 books (18 categories × 20)
- `fanqie_female_read_ranks_20260627.json`: 360 books (18 categories × 20)

总计约1500本书，可用于选题分析。

