我需要你以**独立架构审查者**的身份，重新审视并优化 `hermes-dev-flow` 开源项目。

## 项目定位
AI 驱动的软件开发流水线框架：Hermes 编排 Claude Code/Codex/OpenCode 三种 CLI agent 执行编码任务。当前状态见 docs/HANDOFF.md。

## 两个对标项目（先看代码）

| | dev-flow | Paseo (11k⭐) | HomeRail (659⭐) |
|---|---|---|---|
| 编排 | 单路流水线 | 4模式 (Handoff/Loop/Committee/Advisor) | DAG引擎 + 节点 |
| 质量 | 三契约+六闸门(人工拍板) | Verifier循环 | Scorecard(打分制) |
| 执行面 | Pod热池+Redis | Worker子进程 | Docker Worker容器 |
| 协议 | 无 | ACP/MCP | 自研 DAG 合约 |
| 许可证 | MIT | AGPL-3.0 ⚠️ | MIT |

Paseo 强在多厂商控制面和跨设备。HomeRail 强在 DAG 引擎和把人的参与降到最低。Dev-Flow 强在结构化闸门和容器化执行面——但编排引擎是短板。

## 审查重点
1. 线性流水线→DAG节点图，引入可回放的workspace隔离
2. 六项人工闸门→Scorecard自动打分+Verifier循环
3. 单Pod热池→Manager/Node/Worker三层架构
4. 硬编码worker选择→编排偏好路由表
5. 哪些过度设计应该砍掉（三契约+逃生舱是否真的必要？）
6. 代码质量/目录结构的硬伤

## 约束
- 简体中文交流
- 追根因不打补丁
- 如果我的设计错了直接说
- 确认方案后再动手

先读 docs/HANDOFF.md、Paseo 报告（~/Desktop/paseo-research-report.html）和 HomeRail README。给我独立审查结论 + 融合优化方案。
