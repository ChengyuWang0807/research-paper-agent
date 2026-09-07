"""Readable top-level driver for the complete Research-Paper-Agent workflow.

Run ``python workflow.py overview`` to see the stage map.
Run ``python workflow.py demo ...`` to create a task and run it to the first gate.
Run ``python workflow.py run ...`` to resume a task after approval.

01 研究启动 -> 02 文献处理 -> 03 知识整合 -> 05 写作 -> 05 审计
                         \-> 04 实验闭环 (future conditional branch)
06 系统可靠性 runs underneath every stage.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research_paper_agent.cli import main  # noqa: E402
from research_paper_agent.workflow import ResearchWorkflow  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
