#!/usr/bin/env python3
"""Build a private, dependency-free HTML dashboard from the local DFT ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vwm_ledger import connect, init_db, provenance_graph, row_dict


def safe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def dashboard_data(ledger: Path, project: str | None = None) -> dict[str, Any]:
    init_db(ledger)
    with connect(ledger) as conn:
        params: list[Any] = []
        where = ""
        if project:
            where = "WHERE p.name = ?"
            params.append(project)
        tasks = [
            row_dict(row)
            for row in conn.execute(
                f"""
                SELECT t.*, p.name AS project_name
                FROM tasks t JOIN projects p ON p.id = t.project_id
                {where} ORDER BY p.name, t.name
                """,
                params,
            )
        ]
        ids = [int(task["id"]) for task in tasks]
        events: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        if ids:
            marks = ",".join("?" for _ in ids)
            events = [
                row_dict(row)
                for row in conn.execute(
                    f"SELECT * FROM events WHERE task_id IN ({marks}) ORDER BY id DESC", ids
                )
            ]
            files = [
                row_dict(row)
                for row in conn.execute(
                    f"SELECT * FROM file_records WHERE task_id IN ({marks}) ORDER BY task_id, relpath", ids
                )
            ]
        graph = provenance_graph(conn, project)
    claims: list[dict[str, Any]] = []
    for task in tasks:
        result = safe_json(task.get("result_json") or "{}")
        if not isinstance(result, dict):
            continue
        values = result.get("claims", [])
        if isinstance(values, list):
            for value in values:
                claim = value if isinstance(value, dict) else {"statement": str(value)}
                claims.append({**claim, "task_id": task["id"], "task": task["name"]})
    return {
        "generated_from": str(ledger.resolve()),
        "project": project,
        "tasks": tasks,
        "events": events,
        "files": files,
        "claims": claims,
        "graph": graph,
    }


HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DFT Research Dashboard</title>
<style>
:root{color-scheme:dark;--bg:#07111f;--panel:#0d1b2d;--line:#213753;--text:#eaf1fb;--muted:#93a6bd;--cyan:#4fd1c5;--gold:#f2c14e;--red:#ff7b72}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#102a43 0,var(--bg) 45%);color:var(--text);font:14px/1.45 ui-sans-serif,system-ui,-apple-system,sans-serif}
main{max-width:1500px;margin:auto;padding:28px}.eyebrow{color:var(--cyan);letter-spacing:.16em;text-transform:uppercase;font-size:12px}h1{font-size:34px;margin:.25rem 0 1.2rem}h2{font-size:17px;margin:0 0 14px}.toolbar{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}input,select{background:#081523;border:1px solid var(--line);color:var(--text);padding:10px 12px;border-radius:8px;min-width:210px}.cards{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;margin-bottom:18px}.card,.panel{background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:12px;box-shadow:0 14px 38px #0004}.card{padding:15px}.metric{font-size:26px;font-weight:750}.label,.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,.85fr);gap:16px}.panel{padding:16px;margin-bottom:16px;overflow:auto}table{width:100%;border-collapse:collapse;min-width:780px}th{text-align:left;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line)}td,th{padding:10px 8px;vertical-align:top}tr+tr td{border-top:1px solid #162a40}.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#18334a;color:#bfeae5;font-size:12px}.finger{font-family:ui-monospace,monospace;color:var(--gold)}#graph{width:100%;height:440px;background:#081523;border:1px solid var(--line);border-radius:9px}.empty{color:var(--muted);padding:20px}.claim{border-left:3px solid var(--gold);padding:8px 10px;margin:8px 0;background:#0a1727}.trace{font-size:12px;color:var(--muted)}@media(max-width:900px){.cards{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}
</style>
</head>
<body><main>
<div class="eyebrow">Local · Private · Offline</div><h1>DFT Research Dashboard</h1>
<div class="toolbar"><input id="search" placeholder="筛选任务、引擎、状态…"><select id="engine"><option value="">全部引擎</option></select><select id="review"><option value="">全部审核状态</option></select></div>
<section class="cards"><div class="card"><div class="metric" id="mTasks">0</div><div class="label">计算任务</div></div><div class="card"><div class="metric" id="mAccepted">0</div><div class="label">已审核接受</div></div><div class="card"><div class="metric" id="mNodes">0</div><div class="label">溯源节点</div></div><div class="card"><div class="metric" id="mFiles">0</div><div class="label">归档文件</div></div></section>
<div class="grid"><div><section class="panel"><h2>任务总览</h2><div id="tasks"></div></section><section class="panel"><h2>主张 → 证据反向追踪</h2><div id="claims"></div></section></div><div><section class="panel"><h2>计算依赖与知识溯源图</h2><svg id="graph" role="img" aria-label="calculation provenance graph"></svg><div class="muted">节点颜色表示审核状态；连线表示 depends_on。</div></section><section class="panel"><h2>最近事件</h2><div id="events"></div></section></div></div>
</main><script src="data.js"></script><script>
const D=window.DFT_DASHBOARD_DATA||{tasks:[],events:[],files:[],claims:[],graph:{nodes:[],edges:[]}};
const $=s=>document.querySelector(s), esc=s=>String(s??'');
const uniq=a=>[...new Set(a.filter(Boolean))].sort();
function options(el,values){values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.append(o)})}
options($('#engine'),uniq(D.tasks.map(x=>x.engine)));options($('#review'),uniq(D.tasks.map(x=>x.review_status)));
function filtered(){const q=$('#search').value.toLowerCase(),e=$('#engine').value,r=$('#review').value;return D.tasks.filter(t=>(!e||t.engine===e)&&(!r||t.review_status===r)&&JSON.stringify(t).toLowerCase().includes(q))}
function renderTasks(){const rows=filtered();$('#mTasks').textContent=rows.length;$('#mAccepted').textContent=rows.filter(x=>x.review_status==='ACCEPTED').length;$('#mNodes').textContent=D.graph.nodes.length;$('#mFiles').textContent=D.files.length;if(!rows.length){$('#tasks').innerHTML='<div class="empty">没有匹配任务</div>';return}const table=document.createElement('table');table.innerHTML='<thead><tr><th>项目 / 任务</th><th>引擎</th><th>类型</th><th>状态</th><th>审核</th><th>设计来源</th><th>归档</th></tr></thead>';const b=document.createElement('tbody');rows.forEach(t=>{const tr=document.createElement('tr');[`${t.project_name} / ${t.name}`,t.engine,t.task_type,t.task_state,t.review_status,[t.design_id,t.design_revision,t.design_matrix_id].filter(Boolean).join(' · '),t.archive_path].forEach((v,i)=>{const td=document.createElement('td');td.textContent=esc(v||'—');if(i===1||i===3||i===4)td.className='pill';tr.append(td)});b.append(tr)});table.append(b);$('#tasks').replaceChildren(table)}
function renderClaims(){const box=$('#claims');box.replaceChildren();if(!D.claims.length){box.innerHTML='<div class="empty">尚无结构化 claims；分析结果可在 result.json 的 claims 数组中登记。</div>';return}D.claims.forEach(c=>{const d=document.createElement('div');d.className='claim';const s=document.createElement('div');s.textContent=c.statement||c.claim||'未命名主张';const t=document.createElement('div');t.className='trace';t.textContent=`来源任务：${c.task} · 证据：${c.evidence||c.source||'待登记'}`;d.append(s,t);box.append(d)})}
function renderEvents(){const box=$('#events');box.replaceChildren();D.events.slice(0,12).forEach(e=>{const d=document.createElement('div');d.className='claim';const s=document.createElement('div');s.textContent=e.message||e.event_type;const t=document.createElement('div');t.className='trace';t.textContent=`${e.event_type} · ${e.created_at}`;d.append(s,t);box.append(d)});if(!box.children.length)box.innerHTML='<div class="empty">暂无事件</div>'}
function renderGraph(){const svg=$('#graph'),ns='http://www.w3.org/2000/svg',nodes=D.graph.nodes,edges=D.graph.edges;svg.replaceChildren();if(!nodes.length){const t=document.createElementNS(ns,'text');t.setAttribute('x','24');t.setAttribute('y','42');t.setAttribute('fill','#93a6bd');t.textContent='归档或 register fingerprint 后显示溯源图';svg.append(t);return}const W=760,H=420,cx=W/2,cy=H/2,R=Math.min(W,H)*.36;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);const pos=new Map(nodes.map((n,i)=>[n.id,{x:cx+R*Math.cos((i/nodes.length)*Math.PI*2-Math.PI/2),y:cy+R*Math.sin((i/nodes.length)*Math.PI*2-Math.PI/2)}]));edges.forEach(e=>{const a=pos.get(e.parent_node_id),b=pos.get(e.child_node_id);if(!a||!b)return;const l=document.createElementNS(ns,'line');for(const [k,v] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:'#395875','stroke-width':2}))l.setAttribute(k,v);svg.append(l)});nodes.forEach(n=>{const p=pos.get(n.id),g=document.createElementNS(ns,'g'),c=document.createElementNS(ns,'circle'),t=document.createElementNS(ns,'text');c.setAttribute('cx',p.x);c.setAttribute('cy',p.y);c.setAttribute('r','25');c.setAttribute('fill','#123b4a');c.setAttribute('stroke','#4fd1c5');c.setAttribute('stroke-width','2');t.setAttribute('x',p.x);t.setAttribute('y',p.y+42);t.setAttribute('text-anchor','middle');t.setAttribute('fill','#eaf1fb');t.setAttribute('font-size','12');t.textContent=(n.task_name||n.label).slice(0,22);const title=document.createElementNS(ns,'title');title.textContent=`${n.task_name}\n${n.fingerprint}`;g.append(c,t,title);svg.append(g)})}
['input','change'].forEach(ev=>{$('#search').addEventListener(ev,renderTasks);$('#engine').addEventListener(ev,renderTasks);$('#review').addEventListener(ev,renderTasks)});renderTasks();renderClaims();renderEvents();renderGraph();
</script></body></html>
"""


def build_dashboard(ledger: Path, output: Path, project: str | None = None, overwrite: bool = False) -> None:
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory is not empty; pass --overwrite: {output}")
    output.mkdir(parents=True, exist_ok=True)
    data = dashboard_data(ledger, project)
    (output / "data.js").write_text(
        "window.DFT_DASHBOARD_DATA = " + json.dumps(data, ensure_ascii=False, sort_keys=True) + ";\n",
        encoding="utf-8",
    )
    (output / "index.html").write_text(HTML, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vwm_dashboard.py")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    build_dashboard(args.ledger, args.output, args.project, args.overwrite)
    print(f"[ok] offline dashboard: {(args.output / 'index.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
