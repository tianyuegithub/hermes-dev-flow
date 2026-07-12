# DeerFlow 调用总览 · 设计文档 · 2026-07-06

## 目标

为 deer-flow 新增 `/overview` 调用总览页面，按智能体维度展示平台整体运行情况。

## 数据源

基于 deer-flow 现有的 LangGraph API：

| 端点 | 用途 | 关键字段 |
|------|------|---------|
| `POST /threads/search` | 获取所有线程 | `thread_id`, `assistant_id`, `status`, `created_at`, `updated_at` |
| `GET /threads/{id}/runs` | 获取线程的运行记录 | `run_id`, `status` |
| `GET /assistants/{id}` | 获取智能体名称 | `name` |

## 可直接计算的指标（数据已就绪）

| 指标 | 计算方式 | 数据来源 |
|------|---------|---------|
| 智能体数量 | `COUNT(DISTINCT assistant_id)` | threads 列表 |
| 今日调用数 | `COUNT(threads WHERE created_at >= TODAY)` | threads 列表 |
| 活跃线程数 | `COUNT(threads WHERE status IN ('busy','running'))` | threads 列表 |
| 按智能体分组 | `GROUP BY assistant_id` | threads 列表 |
| 状态分布 | idle / busy / error 计数 | threads[].status |
| 最后活跃时间 | `MAX(updated_at)` per agent | threads 列表 |
| 每日趋势 | `GROUP BY DATE(created_at)` 近 7 天 | threads 列表 |

## 不可直接计算的指标（Run/Thread 模型缺少字段）

| 指标 | 缺失字段 | 替代方案 |
|------|---------|---------|
| 响应时长 | 无 `duration_ms` | 需在 Run 模型添加 `completed_at` - 已实现计算差值 |
| Token 消耗 | 无 `token_count` 或 `usage` | 需在 LangGraph 中间件注入 usage 字段 |
| 成功率 | status 不是二元 success/fail | 可用 error 占比近似替代 |

## 页面设计

```
┌─────────────────────────────────────────────────────┐
│  灵境 · Multi-Agent Platform     [平台简介][工作模式][调用总览] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │ 智能体数 │  │ 今日调用 │  │ 活跃线程 │   ← 3 张概览卡│
│  │   5     │  │   42    │  │   3     │              │
│  └─────────┘  └─────────┘  └─────────┘              │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  智能体        线程数 运行数 Idle Busy Err 活跃│   │
│  │  ├─ lead_agent   12    45    8    3   1   今  │   │
│  │  ├─ bpa-ic        8    32    5    2   1   昨  │   │
│  │  ├─ vdl-ops       5    18    4    1   0   2天 │   │
│  │  └─ ...                                        │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  近 7 天调用趋势（折线图）                             │
│  ▁▂▃▅▃▄▆                                            │
└─────────────────────────────────────────────────────┘
```

## 文件清单

| 文件 | 用途 |
|------|------|
| `backend/app/gateway/routers/overview.py` | GET /api/overview 统计 API |
| `backend/app/gateway/app.py` | 注册 overview router |
| `frontend/src/app/overview/page.tsx` | 调用总览页面 |
| `frontend/src/core/branding/lingjing-platform.ts` | 导航入口「调用总览」 |

## 技术栈

- 后端: FastAPI + LangGraph Client
- 前端: Next.js 16 + React + NumberTicker + ShineBorder
- 品牌系统: 复用 lingjing 品牌组件（LingjingPerspectiveHeader）
