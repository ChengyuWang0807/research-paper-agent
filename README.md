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

### 先看完整工作流

根目录的 `workflow.py` 现在是面向用户的统一入口。它内部保留清晰的 01～06 阶段说明，底层状态、并发和持久化由 `Orchestrator` 负责。

```powershell
python workflow.py overview
```

### 一条命令启动调试任务

`demo` 会创建任务并运行到下一个人工审核门，输出中会直接告诉你下一条命令：

```powershell
python workflow.py demo `
  --task-id debug-001 `
  --topic "测试科研论文工作流"
```

带真实 PDF：

```powershell
python workflow.py demo `
  --task-id debug-paper-001 `
  --topic "测试文献处理和证据召回" `
  --paper "D:\papers\paper-a.pdf"
```

审核后继续：

```powershell
python workflow.py approve --task-id debug-001 --comment "批准研究边界"
python workflow.py run --task-id debug-001
python workflow.py status --task-id debug-001
```

因此调试时只需要记住四个入口：

```text
overview  查看完整阶段图
demo      创建任务并跑到审核门
approve   通过当前审核门
run       从当前 stage_index 继续
status    查看当前状态
```

查看一条任务的完整运行映射（stage run、session、工作区、handoff）：

```powershell
python workflow.py inspect --task-id debug-001
```

这会把 DSH 风格的 `Task -> Workspace -> Stage Run -> Session -> Artifact` 关系一次打印出来。

按不同视角调试同一任务：

```powershell
python workflow.py sessions --task-id debug-001
python workflow.py artifacts --task-id debug-001
python workflow.py stage-runs --task-id debug-001 --stage 02_literature
python workflow.py replay --task-id debug-001 --run-id <run-id>
```

`sessions` 用于检查多轮会话是否被复用；`artifacts` 用于检查阶段交付；`stage-runs` 用于检查某个大模块的所有执行记录；`replay` 用于复盘一次 Agent Run 的输入、输出和 DSH 日志。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

python workflow.py init --task-id demo-001 --topic "Agent Harness 可靠性综述"
python workflow.py run --task-id demo-001
python workflow.py approve --task-id demo-001 --comment "研究边界确认"
python workflow.py run --task-id demo-001
```

安装 DSH 适配器并运行真实模型（需要 `DEEPSEEK_API_KEY`）：

```powershell
pip install -e ".[dsh]"
$env:DEEPSEEK_API_KEY = "你的密钥"
python workflow.py --runner dsh run --task-id demo-001
```

`--runner dsh` 使用 DeepSeek Harness Python SDK，通过 JSON-RPC stdio 启动运行时；每次 Agent Run 使用自己的 `cwd`、`session_root` 和日志目录。默认的 `mock` 模式不需要 SDK 或密钥。

### 使用其他 OpenAI-compatible 模型

DSH 的 Harness 与模型 Provider 解耦。对于当前 PyPI `deepseek-harness-sdk 0.1.2a3`，最兼容的方式是使用内置 `deepseek-official` 适配器，将 `DEEPSEEK_BASE_URL` 指向你的 Qwen/vLLM OpenAI-compatible endpoint：

```powershell
pip install -e ".[dsh]"
$env:DEEPSEEK_API_KEY = "vllm-local"
$env:DEEPSEEK_BASE_URL = "https://ai-platform-service-deploy.agentsocean.com/innova-gateway/image-deployment/jiaosc1/qwen36-35b-a3b/v1"
$env:RPA_DSH_PROVIDER = "deepseek-official"
$env:RPA_DSH_MODEL = "qwen36-35b-a3b"
$env:RPA_DSH_MAX_TOKENS = "8192"
Remove-Item Env:RPA_DSH_CORDIS -ErrorAction SilentlyContinue
python workflow.py --runner dsh run --task-id demo-001
```

这里的 `deepseek-official` 只是 DSH 内置的协议适配器，实际请求会发送到 Qwen endpoint；`DEEPSEEK_API_KEY` 的值可以是 vLLM 服务要求的占位 token。`8192` 用于避免 DSH 默认输出上限超过该服务的 `262144` 上下文窗口。

仓库中的 [qwen-vllm.cordis.yml](config/dsh/qwen-vllm.cordis.yml) 是 `dsh-llm-pi-ai` 自定义 Provider 方案，适用于包含该插件的 DSH 源码/runtime；当前 PyPI runtime 未加载该插件时会报 `no adapter registered for provider "qwen-vllm"`。

加入本地 PDF 时可以重复使用 `--paper`：

```powershell
python workflow.py init --task-id demo-002 --topic "科研 Agent 综述" `
  --paper "D:\papers\paper-a.pdf" `
  --paper "D:\papers\paper-b.pdf"
```

当 `--paper` 指向真实 PDF 时，02 文献处理会在每个隔离 Worker 中执行本地解析：

```text
PDF -> DocumentIR -> 类型感知 Chunk -> SQLite FTS5 -> literature_handoff
```

正文按约 450 词切块并保留约 80 词 overlap；表格、图片和公式标记为独立 Chunk，并保留页码、原文和元素编号。索引文件位于 `data/literature/literature.db`，不会由 Worker 直接共享写入之外的状态。安装 `pip install -e ".[retrieval]"` 后可使用 `ZvecIndex` 接入语义向量索引；Embedding endpoint 需要单独提供 `/v1/embeddings`，不会把生成模型 endpoint 当作向量模型。

可以直接测试 03 的本地关键词召回和 RRF 输出：

```powershell
python workflow.py retrieve --query "accuracy" --limit 5
python workflow.py retrieve --query "workflow" --content-type figure
python workflow.py retrieve --query "实验结果" --year 2026
```

输出中的 `retrieval_sources`、`retrieval_ranks` 和 `rrf_score` 用于复盘证据是由哪一路召回的。Reranker 默认关闭，接入可用的排序模型后再通过 `Reranker` 接口注入。

03 阶段的 `knowledge_pack.json` 还会包含：

```text
query_plan             每个研究问题的查询词、过滤条件和 Top-K
subquestion_results    每个子问题命中的 evidence_id
evidence_set           通过 paper_id、page、source_text 校验的证据
retrieval_trace        BM25/semantic/RRF/reranker 的数量和排名轨迹
coverage               子问题覆盖率、论文覆盖数和充分性判断
feedback_actions       expand_query / manual_review 等结构化反馈
```

当 `coverage.sufficient` 为 `false` 时，系统只产生反馈动作，不自动修改研究边界；上层 workflow 可以据此决定扩展查询、请求 02 补充解析，或返回 01 重新确认。

第一次 `run` 会在研究启动审核门暂停；批准后再次 `run` 会并发执行论文 Worker，并继续到最终审计审核门。

## 语义索引开关

`ZvecIndex` 和 OpenAI-compatible Embedding 客户端是可选适配器。只有设置 `RPA_ENABLE_SEMANTIC_INDEX=true`、`RPA_EMBEDDING_BASE_URL` 和 `RPA_ZVEC_ROOT`，02 阶段才会调用 `/v1/embeddings` 并建立 Zvec 索引；解析产物和 FTS5 不依赖该服务。03 阶段的 `HybridRetriever` 会合并 BM25、语义召回（可用时）和元数据过滤，并用 RRF 生成带来源与排名轨迹的 `evidence_set`。

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
- DSH 适配器已接入，但必须显式使用 `--runner dsh`；未配置 SDK 或 API Key 时会把错误记录为该 Run 的失败，而不会静默生成成功结果。
- 当前 PyMuPDF Worker 已支持真实 PDF 解析、类型感知 Chunk 和 SQLite FTS5 关键词索引；复杂版面（OCR、复杂表格、公式识别）仍由后续 Docling/MinerU 适配器增强。
- `ZvecIndex` 和 OpenAI-compatible Embedding 客户端已提供为可选适配器；语义召回、重排和实验闭环将在后续里程碑接入。

## LangGraph 首阶段验收

LangGraph 版本只负责图级状态、节点、人工中断和恢复；论文业务产物、隔离工作区和 DSH Session 仍由现有 Orchestrator 管理。当前图覆盖：

```text
research_start -> review_scope (interrupt) -> literature_init
```

安装图运行依赖并执行本地验收：

```powershell
pip install -e ".[graph]"
python scripts/smoke_langgraph.py
```

smoke 脚本会打印审核中断 payload，然后用同一 `thread_id` 提交批准并打印恢复后的状态、Artifact、Handoff 和 DSH Session 引用。

启动 LangGraph Studio（可选）：

```powershell
pip install -e ".[studio]"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
langgraph dev --host 127.0.0.1 --port 2024 --no-browser
```

打开 `https://smith.langchain.com/studio/?baseUrl=http%3A%2F%2F127.0.0.1%3A2024`，选择 `research_graph`。本地 Studio 不需要 `LANGSMITH_API_KEY`；没有该变量时不会同步云端 Trace，但本地 Graph、Interrupt、Memory 和 Trace 仍可查看。图入口配置位于 [langgraph.json](langgraph.json)，实现位于 [graph_app.py](src/research_paper_agent/graph_app.py)。
