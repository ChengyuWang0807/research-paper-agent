"""Local debugging dashboard for Research-Paper-Agent."""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from research_paper_agent.workflow import ResearchWorkflow  # noqa: E402

PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Research-Paper-Agent 调试面板</title><style>
:root{font-family:Inter,'Segoe UI',sans-serif;color:#17202a;background:#f4f6f8}*{box-sizing:border-box}body{margin:0}header{background:#152536;color:#fff;padding:20px 28px;display:flex;justify-content:space-between}header h1{font-size:20px;margin:0}header span{font-size:12px;color:#a9bdcf}.layout{display:grid;grid-template-columns:270px 1fr;min-height:calc(100vh - 64px)}aside{background:#fff;border-right:1px solid #dce3e8;padding:18px;overflow:auto}main{padding:22px;max-width:1400px;width:100%}.task{padding:12px;border:1px solid #e1e7eb;border-radius:7px;margin-bottom:9px;cursor:pointer}.task:hover,.task.active{border-color:#3b82c4;background:#f0f7ff}.task strong{display:block;font-size:13px}.task small{display:block;color:#71808d;margin-top:5px}.badge{display:inline-block;border-radius:10px;padding:3px 8px;font-size:11px;background:#e8edf2;color:#40505d}.ok{background:#dff4e6;color:#17633a}.wait{background:#fff0d0;color:#855b00}.fail{background:#ffe1e1;color:#982d2d}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.card,.section{background:#fff;border:1px solid #e1e7eb;border-radius:8px;padding:16px}.card h3{font-size:12px;margin:0 0 8px;color:#5b6b77}.metric{font-size:21px;font-weight:650}.section{margin-bottom:15px}.section h2{font-size:15px;margin:0 0 14px}.timeline{display:flex;gap:7px;overflow:auto}.stage{min-width:140px;border-top:4px solid #b8c3cc;padding:10px;background:#f7f9fa}.stage.done{border-color:#36a269;background:#effaf3}.stage.current{border-color:#e0a426;background:#fff8e8}.stage .name{font-weight:600;font-size:12px}.stage .status{font-size:11px;margin-top:7px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:8px;border-bottom:1px solid #edf0f2;vertical-align:top}th{color:#697986}.mono{font-family:Consolas,monospace;font-size:11px;word-break:break-all}pre{background:#111b25;color:#d8e5ef;border-radius:6px;padding:14px;overflow:auto;max-height:500px;font-size:11px}button{border:0;border-radius:5px;padding:8px 12px;cursor:pointer;background:#2e79b7;color:#fff}.secondary{background:#e7edf2;color:#31424f}.empty{color:#82909a;font-size:13px;padding:18px 0}@media(max-width:800px){.layout{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid #dce3e8}.grid{grid-template-columns:repeat(2,1fr)}main{padding:14px}}
</style></head><body><header><h1>Research-Paper-Agent 调试面板</h1><span>本地观测与审核</span></header><div class='layout'><aside><h3>任务</h3><div id='tasks' class='empty'>加载中...</div></aside><main id='app'><div class='empty'>请选择一个任务</div></main></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let selected='';async function get(p){let r=await fetch(p);if(!r.ok)throw Error(await r.text());return r.json()}function badge(s){let c=s==='SUCCEEDED'||s==='COMPLETED'?'ok':s==='AWAITING_REVIEW'?'wait':s==='FAILED'?'fail':'';return `<span class='badge ${c}'>${esc(s)}</span>`}async function loadTasks(){let d=await get('/api/tasks'),e=document.querySelector('#tasks');e.innerHTML=d.tasks.length?d.tasks.map(t=>`<div class='task ${t.task_id===selected?'active':''}' onclick="selectTask('${esc(t.task_id)}')"><strong>${esc(t.task_id)}</strong><small>${esc(t.topic)}</small><small>${badge(t.status)} · stage ${t.stage_index}</small></div>`).join(''):'<div class="empty">暂无任务，请先运行 workflow.py demo。</div>'}async function selectTask(id){selected=id;await loadTasks();await renderTask()}async function renderTask(){if(!selected)return;let d=await get('/api/tasks/'+encodeURIComponent(selected)),t=d.task,runs=d.stage_runs,stages=['01_research_start','02_literature','03_synthesis','05_writing','05_audit'];document.querySelector('#app').innerHTML=`<div class='grid'><div class='card'><h3>任务状态</h3><div class='metric'>${badge(t.status)}</div></div><div class='card'><h3>当前阶段</h3><div class='metric'>${esc(stages[t.stage_index]||'完成')}</div></div><div class='card'><h3>Stage Runs</h3><div class='metric'>${runs.length}</div></div><div class='card'><h3>Sessions / Artifacts</h3><div class='metric'>${d.sessions.length} / ${d.artifacts.length}</div></div></div><div class='section'><h2>Workflow 时间线</h2><div class='timeline'>${stages.map((s,i)=>{let r=runs.find(x=>x.stage_id===s),cl=r?(r.status==='SUCCEEDED'?'done':'current'):(i===t.stage_index?'current':'');return `<div class='stage ${cl}'><div class='name'>${esc(s)}</div><div class='status'>${r?badge(r.status):(i===t.stage_index?'等待执行':'未执行')}</div></div>`}).join('')}</div></div>${t.pending_approval?`<div class='section'><h2>待人工审核：${esc(t.pending_approval.stage_id)}</h2><button onclick='approve(true)'>批准继续</button> <button class='secondary' onclick='approve(false)'>拒绝</button></div>`:''}<div class='section'><h2>Agent Runs</h2>${runs.length?`<table><tr><th>阶段</th><th>Agent</th><th>状态</th><th>Session</th><th></th></tr>${runs.map(r=>`<tr><td>${esc(r.stage_id)}</td><td>${esc(r.agent_id)}</td><td>${badge(r.status)}</td><td class='mono'>${esc(r.session_id)}</td><td><button class='secondary' onclick="replay('${esc(r.run_id)}')">查看 Trace</button></td></tr>`).join('')}</table>`:'<div class="empty">暂无运行记录</div>'}</div><div class='section'><h2>Sessions</h2><table><tr><th>Agent</th><th>模式</th><th>状态</th><th>Session ID</th></tr>${d.sessions.map(s=>`<tr><td>${esc(s.agent_id)}</td><td>${esc(s.session_mode)}</td><td>${badge(s.status)}</td><td class='mono'>${esc(s.session_id)}</td></tr>`).join('')}</table></div><div class='section'><h2>Artifacts & Handoffs</h2><table><tr><th>类型</th><th>阶段</th><th>路径</th></tr>${d.artifacts.map(a=>`<tr><td>Artifact</td><td>${esc(a.stage_id)}</td><td class='mono'>${esc(a.path)}</td></tr>`).join('')}${d.handoffs.map(h=>`<tr><td>Handoff</td><td>-</td><td class='mono'>${esc(h)}</td></tr>`).join('')}</table></div>`}async function replay(run){let d=await get('/api/tasks/'+encodeURIComponent(selected)+'/runs/'+encodeURIComponent(run));document.querySelector('#app').insertAdjacentHTML('beforeend',`<div class='section'><h2>Trace · ${esc(run)}</h2><pre>${esc(JSON.stringify(d,null,2))}</pre></div>`);window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})}async function approve(ok){let c=prompt(ok?'审核意见':'拒绝原因','');if(c===null)return;await fetch('/api/tasks/'+encodeURIComponent(selected)+'/approval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:ok,comment:c})});await loadTasks();await renderTask()}loadTasks();setInterval(()=>{loadTasks();if(selected)renderTask()},5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, workflow: ResearchWorkflow, **kwargs):
        self.workflow = workflow
        super().__init__(*args, **kwargs)

    def _json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/tasks":
                conn = self.workflow.orchestrator.store._connect()
                try:
                    rows = conn.execute("SELECT task_id, topic, status, stage_index, updated_at FROM tasks ORDER BY updated_at DESC").fetchall()
                finally:
                    conn.close()
                self._json({"tasks": [dict(row) for row in rows]})
                return
            parts = [unquote(x) for x in path.split("/") if x]
            if len(parts) == 3 and parts[:2] == ["api", "tasks"]:
                self._json(self.workflow.inspect(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "tasks"] and parts[3] == "runs":
                self._json(self.workflow.replay(parts[2], parts[4]))
                return
            self._json({"error": "not found"}, 404)
        except KeyError as error:
            self._json({"error": str(error)}, 404)
        except Exception as error:
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        parts = [unquote(x) for x in urlparse(self.path).path.split("/") if x]
        if len(parts) != 4 or parts[:2] != ["api", "tasks"] or parts[3] != "approval":
            self._json({"error": "not found"}, 404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(size) or b"{}")
            if data.get("approved", True):
                result = self.workflow.approve(parts[2], comment=str(data.get("comment", "")))
            else:
                result = self.workflow.reject(parts[2], comment=str(data.get("comment", "")))
            self._json(result)
        except Exception as error:
            self._json({"error": str(error)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-Paper-Agent local dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    workflow = ResearchWorkflow(args.root.resolve(), runner="mock")
    server = ThreadingHTTPServer((args.host, args.port), lambda *a, **kw: Handler(*a, workflow=workflow, **kw))
    print(f"Dashboard: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
