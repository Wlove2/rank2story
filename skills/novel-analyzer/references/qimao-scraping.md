# 七猫排行榜数据抓取指南

## URL结构

| 榜单 | URL |
|------|-----|
| 大热榜月榜 | `https://www.qimao.com/paihang/boy/hot/month/` |
| 新书榜月榜 | `https://www.qimao.com/paihang/boy/new/month/` |

## 操作流程

1. `browser_navigate https://www.qimao.com/paihang`
2. 等待页面加载完毕（约3-5秒），排行榜默认显示大热榜月榜
3. 用 `browser_snapshot` 获取榜单数据
4. 若要新书榜：点击"新书榜"Tab → "月榜" → 等待3秒 → `browser_snapshot`

## 数据结构

每条item包含：
- 排名（1-20的数字）
- 书名（a链接）
- 作者名
- 分类标签（都市/玄幻/历史/N次元等）
- 子分类（都市高武/东方玄幻/架空历史等）
- 简介（StaticText，约100-200字）
- 最近更新章节（a链接）

## 七猫 Web `qimao_web_ranks.json` 数据结构（20260720 实测）

`collect_qimao_web_ranks.py` 输出的 `qimao_web_ranks.json` 结构：

```json
{
  "source": "qimao_public_web_ranks",
  "surface": "public_web",
  "retrieved_at": "...",
  "entries": [...],   // ← 200 本书在顶层，不在 channels 内
  "channels": [...]   // ← channels 内是元数据（valid_entries, status），entries 为空
}
```

**解析时读 `data['entries']`**，不要读 `data['channels'][i]['entries']`（那是空的）。

每本书结构：
```json
{
  "gender": "male",
  "rank_type": "hot",
  "rank": 1,
  "title": "盖世神医",
  "author": "狐颜乱语",
  "category": "都市 / 都市高武",
  "status": "连载中",
  "word_count": "881.66万字",
  "heat": "139.4万"
}
```

## 常见坑

- `web_extract` 对七猫返回504超时
- 页面JS加载慢，点击榜单一Tab后需等3-5秒
- 女频榜单url结构可能不同（`/paihang/girl/`），如需女频数据需额外探索
