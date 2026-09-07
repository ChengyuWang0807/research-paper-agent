# DSH 对齐说明

## DSH 的核心边界

公开源码把运行时拆成三层：

```text
Harness -> Runtime process -> Session -> Workspace
```

- Harness 持有 runtime，runtime 可以服务多个 session。
- Session 是追加式事件日志，同一个 `session_id` 可以继续多轮。
- Workspace 由规范化目录路径标识，并维护属于自己的 session id 列表；session header 的 canonical cwd 必须和 workspace 一致。
- Subagent 还有 parent/child session 关系，并区分 one-shot 与 continuable。

公开源码参考：

- `packages/workspace/workspace/src/paths.ts`
- `packages/workspace/workspace/src/types.ts`
- `packages/workspace/workspace/src/entity.ts`
- `packages/api/session-controller/src/client/sessions/session.ts`
- `packages/subagent`
- `docs/subsystems/session.md`

## 本项目的对应关系

```text
Research Task
  └── runs/<task-id>/                         Research Workspace
       ├── <stage>/<run-id>/                  Stage Run
       │    ├── input/                        输入快照
       │    ├── scratch/                      临时文件
       │    ├── output/                       契约产物
       │    ├── logs/                         DSH 事件和运行日志
       │    ├── dsh_session/                  本次运行目录
       │    └── run_manifest.json              run/session 映射
       ├── handoffs/                          版本化阶段交接
       ├── task.json                          任务元数据
       ├── session_manifest.json              应用层 session 注册表
       └── dsh/home/                          任务级 DSH_HOME
```

当前保留原有 `runs/<task>/<stage>/<run-id>/` 布局，只增加任务级元数据，不破坏已有任务和产物。

## Session 策略

| 场景 | 模式 | 设计理由 |
| --- | --- | --- |
| `01_research_start` | `continuable` | 边界确认和用户反馈需要多轮复用 |
| `03_synthesis` | `continuable` | 证据不足时可以继续修订召回和比较 |
| `05_writing` | `continuable` | 写作返修需要保留大纲上下文 |
| `02` 论文 Worker | `one_shot` | 每篇论文隔离，避免上下文污染 |
| `02` supervisor、`05_audit` | `one_shot` | 依赖结构化 handoff，便于重放和审计 |

`session_manifest.json` 只负责记录任务、阶段、Agent、session id、`dsh_home` 和最近 run；它不替代 DSH 的事件日志。

## 可观察入口

```powershell
python workflow.py overview
python workflow.py demo --task-id inspect-demo --topic "测试工作流"
python workflow.py inspect --task-id inspect-demo
```

`inspect` 会一次列出任务状态、stage runs、session 模式、工作区、任务级 DSH_HOME 和 handoff 文件。

## 当前边界

本次改造已经实现持久 session id 和任务级 DSH_HOME；DSH runtime 进程仍按一次 CLI 调用启动和关闭。跨 CLI 调用通过同一个 `dsh_home` 与 session id 恢复持久会话。若后续需要一个长任务内持续持有 runtime，再增加 task-level `DshRuntimeManager`，不改变 handoff 与目录契约。
