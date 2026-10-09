from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable


CONFIG_REL = Path(".research/config.yaml")
GLOBAL_FILES = ("profile.md", "preferences.md", "misconceptions.md", "projects.md")
ALLOWED_PROPOSAL_TARGETS = set(GLOBAL_FILES)
INTENT_TERMS = (
    "$research-teach",
    "research-teach",
    "文献",
    "论文",
    "科研",
    "研究计划",
    "知识图谱",
    "知识库",
    "教学",
    "教我",
    "学习资料",
    "literature",
    "paper",
    "research",
    "knowledge graph",
    "teach me",
    "$dote-tutor",
    "dote-tutor",
    "dft",
    "dote",
    "vasp",
    "scf",
    "relax",
    "phonon",
    "band structure",
    "density of states",
    "收敛",
    "能带",
    "声子",
    "电子结构",
    "计算任务",
)

DFT_INTENT_TERMS = (
    "$dote-tutor",
    "dote-tutor",
    "dft",
    "dote",
    "vasp",
    "scf",
    "phonon",
    "band structure",
    "density of states",
    "收敛",
    "能带",
    "声子",
    "电子结构",
    "计算任务",
)


class ResearchTeachError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_if_missing(path: Path, text: str) -> bool:
    if path.exists():
        return False
    atomic_write(path, text)
    return True


def slugify(value: str, fallback: str = "item") -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "-", normalized, flags=re.UNICODE)
    normalized = re.sub(r"-+", "-", normalized).strip("-_")
    return normalized[:96] or fallback


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def find_project_root(start: str | Path | None = None) -> Path | None:
    current = Path(start or os.getcwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_REL).is_file():
            return candidate
    return None


def load_config(project: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    root = find_project_root(project)
    if root is None:
        raise ResearchTeachError("No .research/config.yaml found in this directory or its parents.")
    try:
        data = json.loads((root / CONFIG_REL).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchTeachError(f"Invalid project config: {exc}") from exc
    if data.get("version") != 1:
        raise ResearchTeachError("Unsupported project config version.")
    return root, data


def config_path(root: Path, config: dict[str, Any], key: str) -> Path:
    raw = config.get("paths", {}).get(key)
    if not isinstance(raw, str) or not raw:
        raise ResearchTeachError(f"Missing paths.{key} in project config.")
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def init_global(agent_context: str | Path) -> dict[str, Any]:
    context = Path(agent_context).expanduser().resolve()
    context.mkdir(parents=True, exist_ok=True)
    (context / "proposals").mkdir(exist_ok=True)
    (context / "audit").mkdir(exist_ok=True)
    created: list[str] = []
    templates = {
        "profile.md": (
            "# Confirmed Learner Profile\n\n"
            "Store only user-confirmed background, capabilities, and learning constraints.\n"
        ),
        "preferences.md": (
            "# Confirmed Teaching Preferences\n\n"
            "Store only preferences the user explicitly confirmed.\n"
        ),
        "misconceptions.md": (
            "# Confirmed Cross-project Misconceptions\n\n"
            "Add an item only after repeated evidence and explicit user confirmation.\n"
        ),
        "projects.md": (
            "# Research and Learning Projects\n\n"
            "Project summaries may link to project locations but must not duplicate source documents.\n"
        ),
        "schema.yaml": json.dumps(
            {
                "version": 1,
                "privacy": "private",
                "confirmed_fields_only": True,
                "proposal_required": True,
                "allowed_project_reads": list(GLOBAL_FILES),
                "allowed_proposal_targets": sorted(ALLOWED_PROPOSAL_TARGETS),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    for name, text in templates.items():
        if write_if_missing(context / name, text):
            created.append(name)
    return {"agent_context": str(context), "created": created}


def _project_config(root: Path, global_context: Path, topic: str) -> dict[str, Any]:
    return {
        "version": 1,
        "project_id": str(uuid.uuid4()),
        "topic": topic,
        "privacy": "private",
        "global_context": str(global_context),
        "paths": {
            "papers": "papers",
            "references": "references",
            "knowledge": "knowledge",
            "learning": "knowledge/Learning",
            "dashboard": "dashboard",
            "cache": ".research/cache",
            "proposals": ".research/proposals",
            "state": ".research/state",
            "logs": ".research/logs",
        },
        "conversion": {
            "remote": {
                "reference": "allowed",
                "project_document": "confirm",
                "confidential": "forbidden",
            },
            "safe_upload_directories": [],
            "mineru_base_url": "https://mineru.net/api/v4",
            "opendataloader_environment": "~/.local/share/research-teach/opendataloader",
        },
        "screening": {
            "max_download_batch": 20,
            "core_journal_list": "knowledge/Maps/Core-Journals.md",
        },
    }


def _append_gitignore(root: Path, entries: Iterable[str]) -> list[str]:
    target = root / ".gitignore"
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    lines = existing.splitlines()
    added: list[str] = []
    if lines and lines[-1].strip():
        lines.append("")
    marker = "# research-teach private and generated data"
    if marker not in lines:
        lines.append(marker)
    for entry in entries:
        if entry not in lines:
            lines.append(entry)
            added.append(entry)
    atomic_write(target, "\n".join(lines).rstrip() + "\n")
    return added


def init_project(
    project: str | Path,
    global_context: str | Path,
    topic: str = "",
) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    context = Path(global_context).expanduser().resolve()
    if not context.is_dir():
        raise ResearchTeachError(
            f"Global AgentContext does not exist: {context}. Run init-global first."
        )

    directories = (
        "papers",
        "references",
        "knowledge/Sources/Inbox",
        "knowledge/Sources/Verified",
        "knowledge/Assets",
        "knowledge/Concepts",
        "knowledge/Maps/Controversies",
        "knowledge/Learning/01-foundations",
        "knowledge/Learning/02-core",
        "knowledge/Learning/03-deep-dive",
        "knowledge/Records",
        "dashboard",
        ".research/cache",
        ".research/proposals",
        ".research/state",
        ".research/logs",
    )
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=True)

    config_file = root / CONFIG_REL
    if config_file.exists():
        _, existing = load_config(root)
        configured = Path(str(existing.get("global_context", ""))).expanduser().resolve()
        if configured != context:
            raise ResearchTeachError(
                f"Project already points to a different AgentContext: {configured}"
            )
        config = existing
    else:
        config = _project_config(root, context, topic)
        atomic_write(config_file, json.dumps(config, ensure_ascii=False, indent=2) + "\n")

    link = root / ".research/global"
    if link.is_symlink():
        if link.resolve() != context:
            raise ResearchTeachError(f"Existing global link points to {link.resolve()}")
    elif link.exists():
        raise ResearchTeachError(f"{link} exists and is not a symbolic link.")
    else:
        link.symlink_to(context, target_is_directory=True)

    templates = {
        root / "references/library.bib": "% Project-local citation library.\n",
        root / "knowledge/Learning/00-overview.md": (
            "---\nnode_type: learning\nstatus: proposed\ntitle: Project learning overview\n---\n\n"
            "# Learning Overview\n\n"
            "## Mission\n\nPending confirmation.\n\n"
            "## Reading path\n\n"
            "1. [[01-foundations]]\n2. [[02-core]]\n3. [[03-deep-dive]]\n"
        ),
        root / "knowledge/Maps/Core-Journals.md": (
            "---\nnode_type: map\nstatus: proposed\ntitle: Core journals\nlast_reviewed: null\n---\n\n"
            "# Core Journals\n\n"
            "## Tier 1\n\nPending confirmation.\n\n"
            "## Tier 2\n\nPending confirmation.\n\n"
            "## Sources for the list\n\nPending authoritative sources.\n"
        ),
        root / "knowledge/Maps/Literature-Screening.md": (
            "---\nnode_type: map\nstatus: proposed\ntitle: Literature screening\n---\n\n"
            "# Literature Screening\n\n"
            "| Candidate | Journal tier | Abstract match | Use | Decision | Reason |\n"
            "|---|---|---|---|---|---|\n"
        ),
        root / ".research/state/research-plan.md": (
            "# Research Plan\n\n"
            "## Diagnosis\n\nPending.\n\n"
            "## Research question and scope\n\nPending confirmation gate 1.\n\n"
            "## Inclusion and exclusion criteria\n\nPending.\n"
        ),
    }
    created = [str(path.relative_to(root)) for path, text in templates.items() if write_if_missing(path, text)]

    ignored = _append_gitignore(
        root,
        (
            ".research/global",
            ".research/cache/",
            ".research/proposals/",
            ".research/state/",
            ".research/logs/",
            "papers/",
            "dashboard/",
            "knowledge/Learning/",
            "knowledge/Records/",
        ),
    )
    return {
        "project": str(root),
        "project_id": config["project_id"],
        "global_context": str(context),
        "created_templates": created,
        "gitignore_added": ignored,
    }


def project_status(project: str | Path | None = None) -> dict[str, Any]:
    root, config = load_config(project)
    paths: dict[str, Any] = {}
    for key in config.get("paths", {}):
        path = config_path(root, config, key)
        if path.is_dir():
            paths[key] = {"path": str(path), "files": sum(1 for item in path.rglob("*") if item.is_file())}
        else:
            paths[key] = {"path": str(path), "exists": path.exists()}
    link = root / ".research/global"
    return {
        "project": str(root),
        "project_id": config.get("project_id"),
        "topic": config.get("topic", ""),
        "global_link": str(link.resolve()) if link.is_symlink() else None,
        "paths": paths,
    }


def is_research_intent(prompt: str) -> bool:
    lowered = prompt.casefold()
    return any(term.casefold() in lowered for term in INTENT_TERMS)


def is_dft_intent(prompt: str) -> bool:
    lowered = prompt.casefold()
    return any(term.casefold() in lowered for term in DFT_INTENT_TERMS)


def load_approved_context(project: str | Path | None = None, max_chars: int = 24000) -> str:
    root, config = load_config(project)
    context = Path(str(config["global_context"])).expanduser().resolve()
    chunks: list[str] = []
    remaining = max_chars
    for name in GLOBAL_FILES:
        path = context / name
        if not path.is_file() or remaining <= 0:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        clipped = text[:remaining]
        chunks.append(f"## {name}\n{clipped}")
        remaining -= len(clipped)
    return (
        f"Research Teach project: {root}\n"
        "The following learner context is approved and read-only. Do not edit it directly.\n\n"
        + "\n\n".join(chunks)
    )


def create_proposal(
    target: str,
    title: str,
    content: str,
    rationale: str,
    project: str | Path | None = None,
) -> Path:
    root, config = load_config(project)
    if target not in ALLOWED_PROPOSAL_TARGETS:
        raise ResearchTeachError(f"Proposal target must be one of: {sorted(ALLOWED_PROPOSAL_TARGETS)}")
    proposal_dir = config_path(root, config, "proposals")
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = proposal_dir / f"{timestamp}-{slugify(title, 'proposal')}.json"
    payload = {
        "version": 1,
        "proposal_id": str(uuid.uuid4()),
        "project_id": config["project_id"],
        "created_at": now_iso(),
        "status": "pending",
        "target": target,
        "title": title.strip(),
        "content": content.strip(),
        "rationale": rationale.strip(),
    }
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def _load_proposal(path: str | Path) -> tuple[Path, dict[str, Any]]:
    proposal_path = Path(path).expanduser().resolve()
    try:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchTeachError(f"Invalid proposal: {exc}") from exc
    if proposal.get("target") not in ALLOWED_PROPOSAL_TARGETS:
        raise ResearchTeachError("Proposal contains an invalid target.")
    if proposal.get("status") not in {"pending", "accepted", "rejected"}:
        raise ResearchTeachError("Proposal contains an invalid status.")
    return proposal_path, proposal


def proposal_entry(proposal: dict[str, Any]) -> str:
    return (
        f"\n## {proposal['title']}\n\n"
        f"{proposal['content']}\n\n"
        f"_Rationale_: {proposal['rationale']}\n"
        f"_Source project_: {proposal['project_id']}\n"
        f"_Accepted_: {now_iso()}\n"
    )


def preview_proposal(path: str | Path, project: str | Path | None = None) -> str:
    _, proposal = _load_proposal(path)
    _, config = load_config(project)
    target = Path(str(config["global_context"])).expanduser().resolve() / proposal["target"]
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    after = before.rstrip() + "\n" + proposal_entry(proposal)
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(target),
            tofile=str(target),
        )
    )


def accept_proposal(path: str | Path, project: str | Path | None = None) -> dict[str, Any]:
    proposal_path, proposal = _load_proposal(path)
    if proposal["status"] != "pending":
        raise ResearchTeachError(f"Proposal is already {proposal['status']}.")
    root, config = load_config(project)
    context = Path(str(config["global_context"])).expanduser().resolve()
    target = context / proposal["target"]
    if target.parent.resolve() != context:
        raise ResearchTeachError("Proposal target escaped AgentContext.")
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    atomic_write(target, before.rstrip() + "\n" + proposal_entry(proposal))
    proposal["status"] = "accepted"
    proposal["accepted_at"] = now_iso()
    atomic_write(proposal_path, json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
    audit = context / "audit/proposals.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(proposal, ensure_ascii=False) + "\n")
    return {"proposal": str(proposal_path), "target": str(target), "status": "accepted"}


def reject_proposal(path: str | Path, reason: str) -> dict[str, Any]:
    proposal_path, proposal = _load_proposal(path)
    if proposal["status"] != "pending":
        raise ResearchTeachError(f"Proposal is already {proposal['status']}.")
    proposal["status"] = "rejected"
    proposal["rejected_at"] = now_iso()
    proposal["rejection_reason"] = reason.strip()
    atomic_write(proposal_path, json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
    return {"proposal": str(proposal_path), "status": "rejected"}


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value in {"null", "~"}:
            parsed: Any = None
        elif value.casefold() in {"true", "false"}:
            parsed = value.casefold() == "true"
        else:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value.strip("'\"")
        data[key.strip()] = parsed
    return data, body


def _note_title(path: Path, frontmatter: dict[str, Any], body: str) -> str:
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Teach Knowledge Graph</title>
<style>
:root{color-scheme:light dark;--bg:#f7f7f4;--panel:#fff;--ink:#1f2933;--muted:#64748b;--line:#d7dce2;--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#111418;--panel:#191d23;--ink:#eef2f7;--muted:#9ca8b8;--line:#343b46;--accent:#70a5ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}
header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center}
header h1{font-size:18px;margin:0}input,select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);height:calc(100vh - 66px)}
#graph{width:100%;height:100%;background:var(--panel)}aside{padding:18px;overflow:auto;border-left:1px solid var(--line)}
.node{cursor:pointer;stroke:var(--panel);stroke-width:2}.edge{stroke:var(--line);stroke-width:1.2}.edge.proposed{stroke-dasharray:5 4}
.label{font-size:10px;fill:var(--muted);pointer-events:none}.meta{color:var(--muted)}a{color:var(--accent)}
@media(max-width:800px){main{grid-template-columns:1fr;grid-template-rows:60vh auto}aside{border-left:0;border-top:1px solid var(--line)}}
</style>
</head>
<body>
<header><h1>Knowledge Graph</h1><input id="search" placeholder="Filter nodes"><select id="type"><option value="">All types</option></select></header>
<main><svg id="graph"></svg><aside id="details"><p class="meta">Select a node to inspect its evidence and links.</p></aside></main>
<script>
const colors={source:"#0f766e",concept:"#2563eb",map:"#9333ea",learning:"#d97706",note:"#64748b"};
Promise.all([fetch("data.json").then(r=>r.json())]).then(([data])=>{
 const svg=document.querySelector("#graph"),details=document.querySelector("#details"),search=document.querySelector("#search"),type=document.querySelector("#type");
 [...new Set(data.nodes.map(n=>n.type))].sort().forEach(t=>type.add(new Option(t,t)));
 let nodes=data.nodes.map((n,i)=>({...n,x:80+(i*97)%700,y:70+(i*53)%500,vx:0,vy:0})),edges=data.edges;
 const NS="http://www.w3.org/2000/svg"; const lineEls=[], nodeEls=[];
 edges.forEach(e=>{let l=document.createElementNS(NS,"line");l.setAttribute("class","edge "+e.status);svg.append(l);lineEls.push([l,e])});
 nodes.forEach(n=>{let g=document.createElementNS(NS,"g"),c=document.createElementNS(NS,"circle"),t=document.createElementNS(NS,"text");
 c.setAttribute("r",n.type==="source"?8:10);c.setAttribute("fill",colors[n.type]||colors.note);c.setAttribute("class","node");
 t.setAttribute("class","label");t.setAttribute("dx",12);t.setAttribute("dy",4);t.textContent=n.title.slice(0,42);
 g.append(c,t);g.addEventListener("click",()=>show(n));svg.append(g);nodeEls.push([g,n]);});
 function visible(n){let q=search.value.toLowerCase();return(!q||n.title.toLowerCase().includes(q))&&(!type.value||n.type===type.value)}
 function show(n){let linked=edges.filter(e=>e.source===n.id||e.target===n.id);details.innerHTML=`<h2>${esc(n.title)}</h2><p class=meta>${esc(n.type)} · ${esc(n.status||"")}</p><p><a href="${encodeURI(n.path)}">${esc(n.path)}</a></p><h3>Relations</h3>`+linked.map(e=>`<p>${esc(e.relation)} → ${esc((nodes.find(x=>x.id===(e.source===n.id?e.target:e.source))||{}).title||"missing")} <span class=meta>${esc(e.status)}</span></p>`).join("")}
 function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
 function frame(){let w=svg.clientWidth,h=svg.clientHeight;nodes.forEach((a,i)=>{if(!visible(a))return;for(let j=i+1;j<nodes.length;j++){let b=nodes[j];if(!visible(b))continue;let dx=a.x-b.x,dy=a.y-b.y,d2=Math.max(80,dx*dx+dy*dy),f=240/d2;a.vx+=dx*f;b.vx-=dx*f;a.vy+=dy*f;b.vy-=dy*f}});
 edges.forEach(e=>{let a=nodes.find(n=>n.id===e.source),b=nodes.find(n=>n.id===e.target);if(!a||!b)return;let dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=(d-110)*.0007;a.vx+=dx*f;b.vx-=dx*f;a.vy+=dy*f;b.vy-=dy*f});
 nodes.forEach(n=>{n.vx+=(w/2-n.x)*.0003;n.vy+=(h/2-n.y)*.0003;n.vx*=.88;n.vy*=.88;n.x=Math.max(15,Math.min(w-15,n.x+n.vx));n.y=Math.max(15,Math.min(h-15,n.y+n.vy))});
 lineEls.forEach(([l,e])=>{let a=nodes.find(n=>n.id===e.source),b=nodes.find(n=>n.id===e.target),v=a&&b&&visible(a)&&visible(b);l.style.display=v?"":"none";if(v){l.setAttribute("x1",a.x);l.setAttribute("y1",a.y);l.setAttribute("x2",b.x);l.setAttribute("y2",b.y)}});
 nodeEls.forEach(([g,n])=>{g.style.display=visible(n)?"":"none";g.setAttribute("transform",`translate(${n.x},${n.y})`)});
 requestAnimationFrame(frame)} frame(); search.oninput=()=>{};type.onchange=()=>{};
});
</script>
</body></html>
"""


def build_graph(project: str | Path | None = None) -> dict[str, Any]:
    root, config = load_config(project)
    knowledge = config_path(root, config, "knowledge")
    dashboard = config_path(root, config, "dashboard")
    note_paths = sorted(path for path in knowledge.rglob("*.md") if path.is_file())
    nodes: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    bodies: dict[str, str] = {}

    for path in note_paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        node_id = str(path.relative_to(root)).replace(os.sep, "/")
        title = _note_title(path, fm, body)
        node = {
            "id": node_id,
            "title": title,
            "type": str(fm.get("node_type", "note")),
            "status": str(fm.get("status", "")),
            "path": "../" + node_id,
        }
        nodes.append(node)
        bodies[node_id] = body
        for alias in {path.stem, title, node_id, str(path.relative_to(knowledge).with_suffix(""))}:
            aliases[alias.casefold()] = node_id

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    relation_re = re.compile(
        r"^-\s*([\w-]+)\s*->\s*\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]"
        r"(?:\s*\|\s*status:\s*(proposed|verified))?"
        r"(?:\s*\|\s*evidence:\s*(.+))?\s*$",
        flags=re.MULTILINE | re.IGNORECASE,
    )
    wiki_re = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")

    for source, body in bodies.items():
        explicit_spans: list[tuple[int, int]] = []
        for match in relation_re.finditer(body):
            target = aliases.get(match.group(2).strip().casefold())
            if not target or target == source:
                continue
            relation = match.group(1).casefold()
            status = (match.group(3) or "proposed").casefold()
            key = (source, target, relation, status)
            if key not in seen:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "relation": relation,
                        "status": status,
                        "evidence": (match.group(4) or "").strip(),
                    }
                )
                seen.add(key)
            explicit_spans.append(match.span())

        for match in wiki_re.finditer(body):
            if any(start <= match.start() < end for start, end in explicit_spans):
                continue
            target = aliases.get(match.group(1).strip().casefold())
            if not target or target == source:
                continue
            key = (source, target, "links-to", "proposed")
            if key not in seen:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "relation": "links-to",
                        "status": "proposed",
                        "evidence": "",
                    }
                )
                seen.add(key)

    dashboard.mkdir(parents=True, exist_ok=True)
    atomic_write(
        dashboard / "data.json",
        json.dumps(
            {"generated_at": now_iso(), "nodes": nodes, "edges": edges},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    atomic_write(dashboard / "index.html", _dashboard_html())
    return {
        "dashboard": str(dashboard / "index.html"),
        "nodes": len(nodes),
        "edges": len(edges),
    }


def cache_status(project: str | Path | None = None) -> dict[str, Any]:
    root, config = load_config(project)
    cache = config_path(root, config, "cache")
    files = [path for path in cache.rglob("*") if path.is_file()]
    return {"cache": str(cache), "files": len(files), "bytes": sum(path.stat().st_size for path in files)}


def clean_cache(project: str | Path | None = None) -> dict[str, Any]:
    root, config = load_config(project)
    cache = config_path(root, config, "cache")
    before = cache_status(root)
    if cache.exists():
        for child in cache.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    before["removed"] = before.pop("files")
    return before
