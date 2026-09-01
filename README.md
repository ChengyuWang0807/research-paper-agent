# Research-Paper-Agent

一个以结构化 Handoff 驱动的多 Agent 科研论文工作流最小框架。

当前 MVP 先验证框架本身，而不是直接承诺完整论文生成能力：

```text
01 研究启动 -> 02 文献处理 -> 03 知识整合 -> 05 写作与审计
                         06 系统可靠性全程支撑
```

核心约束：

- `workflow.py` 是统一流程入口，Agent 不自行推进全局状态。
- 每次 Agent Run 拥有独立的 `input/`、`scratch/`、`output/` 和 `logs/`。
- Agent 能看到的数据、工具、输出和人工审核策略由 `agent.yaml` 声明。
- 阶段之间只传版本化 Handoff 和正式产物引用，不传完整聊天历史。
- 文献 Worker 可以并发运行，但不能直接修改共享状态。
- 当前使用确定性的 Mock Harness，后续通过 `AgentRunner` 接口接入真实开源 Harness。

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

python workflow.py init --task-id demo-001 --topic "Agent Harness 可靠性综述"
python workflow.py run --task-id demo-001
python workflow.py approve --task-id demo-001 --comment "研究边界确认"
python workflow.py run --task-id demo-001
```

加入本地 PDF 时可以重复使用 `--paper`：

```powershell
python workflow.py init --task-id demo-002 --topic "科研 Agent 综述" `
  --paper "D:\papers\paper-a.pdf" `
  --paper "D:\papers\paper-b.pdf"
```

第一次 `run` 会在研究启动审核门暂停；批准后再次 `run` 会并发执行论文 Worker，并继续到最终审计审核门。

## 目录职责

```text
workflow.py                         CLI 入口
config/                             Workflow 和模型配置
src/research_paper_agent/core/      状态机、调度、隔离、Handoff、Trace
src/research_paper_agent/agents/    Agent 契约和系统提示词
src/research_paper_agent/tools/     工具白名单注册
src/research_paper_agent/schemas/   正式产物 JSON Schema
runs/                               隔离运行工作区（不提交）
artifacts/                          通过校验的正式产物（不提交）
data/app.db                         任务与审核状态（不提交）
```

## 当前边界

- Mock Harness 只用于验证编排，不调用真实大模型。
- PDF Worker 当前只登记文件信息，不做真实 PDF 解析。
- 检索、Embedding、Reranker、向量库和实验闭环将在后续里程碑接入。
