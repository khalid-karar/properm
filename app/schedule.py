"""Read a project schedule from Primavera P6 (.xer text export) or MS Project XML (MSPDI) into one neutral shape.

Returned dict: source, project (name), projects (names found), tasks [{code, name, hours, start, end, milestone, hours_from_duration}],
links [(predecessor_code, successor_code, type)] with type FS/SS/FF/SF, warnings [text]. Nothing here touches the database."""
import re
from collections import defaultdict
from datetime import date
from xml.etree import ElementTree as ET

MAX_TASKS = 20000


class ScheduleError(ValueError):
    pass


def _d(v):
    v = (v or "").strip()[:10]
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


# ---------------- Primavera P6 .xer ----------------
def read_xer(data: bytes, project: str | None = None) -> dict:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    if not text.lstrip().startswith("ERMHDR"):
        raise ScheduleError("This does not look like a Primavera XER file (it should start with ERMHDR)")
    tables: dict[str, list[dict]] = defaultdict(list)
    cur, fields = None, []
    for line in text.splitlines():
        parts = line.split("\t")
        tag = parts[0]
        if tag == "%T":
            cur, fields = (parts[1].strip() if len(parts) > 1 else None), []
        elif tag == "%F":
            fields = [f.strip() for f in parts[1:]]
        elif tag == "%R" and cur:
            vals = parts[1:] + [""] * (len(fields) - len(parts[1:]))
            tables[cur].append(dict(zip(fields, vals)))
    tasks_all = tables.get("TASK", [])
    if not tasks_all:
        raise ScheduleError("No activities (TASK table) found in the XER file")
    projs = {p.get("proj_id"): (p.get("proj_short_name") or p.get("proj_id") or "").strip() for p in tables.get("PROJECT", [])}
    with_tasks = []
    for t in tasks_all:
        if t.get("proj_id") not in with_tasks:
            with_tasks.append(t.get("proj_id"))
    names = [projs.get(i) or str(i) for i in with_tasks]
    chosen = None
    if project:
        chosen = next((i for i in with_tasks if (projs.get(i) or str(i)).lower() == project.strip().lower()), None)
        if chosen is None:
            raise ScheduleError(f"Project '{project}' is not in this file. It contains: {', '.join(names)}")
    else:
        chosen = with_tasks[0]
    warnings = []
    if len(with_tasks) > 1 and not project:
        warnings.append(f"The file holds {len(with_tasks)} projects ({', '.join(names)}). Only '{projs.get(chosen) or chosen}' was read. Choose another with the project name field.")
    work = defaultdict(float)
    for r in tables.get("TASKRSRC", []):
        try:
            work[r.get("task_id")] += float(r.get("target_qty") or 0)
        except ValueError:
            pass
    tasks, by_id, skipped_wbs, skipped_loe = [], {}, 0, 0
    for t in tasks_all:
        if t.get("proj_id") != chosen:
            continue
        kind = (t.get("task_type") or "").strip()
        if kind == "TT_WBS":
            skipped_wbs += 1
            continue
        if kind == "TT_LOE":
            skipped_loe += 1
            continue
        code, name = (t.get("task_code") or "").strip(), (t.get("task_name") or "").strip()
        start = _d(t.get("target_start_date")) or _d(t.get("early_start_date")) or _d(t.get("act_start_date"))
        end = _d(t.get("target_end_date")) or _d(t.get("early_end_date")) or _d(t.get("act_end_date"))
        milestone = kind in ("TT_Mile", "TT_FinMile")
        hrs, from_dur = work.get(t.get("task_id"), 0.0), False
        if hrs <= 0 and not milestone:
            try:
                hrs, from_dur = float(t.get("target_drtn_hr_cnt") or 0), True
            except ValueError:
                hrs = 0.0
        tasks.append({"code": code, "name": name, "hours": round(hrs, 1), "start": start, "end": end, "milestone": milestone, "hours_from_duration": from_dur})
        by_id[t.get("task_id")] = code
    if skipped_wbs:
        warnings.append(f"{skipped_wbs} WBS summary rows were not imported (they only group activities)")
    if skipped_loe:
        warnings.append(f"{skipped_loe} level-of-effort activities were not imported (they carry no discrete work)")
    kinds = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}
    links = [(by_id[r.get("pred_task_id")], by_id[r.get("task_id")], kinds.get(r.get("pred_type"), "FS")) for r in tables.get("TASKPRED", [])
             if r.get("pred_task_id") in by_id and r.get("task_id") in by_id]
    return _done("xer", projs.get(chosen) or str(chosen), names, tasks, links, warnings)


# ---------------- MS Project XML (MSPDI) ----------------
def read_mspdi(data: bytes) -> dict:
    if b"<!doctype" in data[:8192].lower() or b"<!entity" in data.lower():
        raise ScheduleError("The file contains entity declarations and was refused for safety")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise ScheduleError("Not a valid MS Project XML file. In MS Project use File, Save As, XML Format.")
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    f = lambda el, tag: (el.findtext(ns + tag) or "").strip()
    all_tasks = root.findall(f".//{ns}Tasks/{ns}Task") or root.findall(f".//{ns}Task")
    parents = {f(t, "OutlineNumber").rsplit(".", 1)[0] for t in all_tasks if "." in f(t, "OutlineNumber")}
    tasks, by_uid, skipped_summary = [], {}, 0
    for t in all_tasks:
        uid, name, outline = f(t, "UID"), f(t, "Name"), f(t, "OutlineNumber")
        if uid == "0" or not name:
            continue
        if f(t, "Summary") == "1" or outline in parents:
            skipped_summary += 1
            continue
        dur = f(t, "Work") or f(t, "Duration")
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", dur)
        hrs = round(int(m.group(1) or 0) + int(m.group(2) or 0) / 60, 1) if m else 0.0
        from_dur = not f(t, "Work") or hrs == 0
        if f(t, "Work") and hrs == 0:                                   # zero work: fall back to duration (e.g. a fixed-duration task)
            m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", f(t, "Duration"))
            hrs = round(int(m.group(1) or 0) + int(m.group(2) or 0) / 60, 1) if m else 0.0
        milestone = f(t, "Milestone") == "1"
        code = f(t, "WBS") or outline or f(t, "ID")
        tasks.append({"code": code, "name": name, "hours": 0.0 if milestone else hrs, "start": _d(f(t, "Start")), "end": _d(f(t, "Finish")),
                      "milestone": milestone, "hours_from_duration": (from_dur and not milestone)})
        by_uid[uid] = code
    if not tasks:
        raise ScheduleError("No tasks found in the project file")
    types = {"0": "FF", "1": "FS", "2": "SF", "3": "SS"}
    links = []
    for t in all_tasks:
        succ = by_uid.get(f(t, "UID"))
        for pl in t.findall(f"{ns}PredecessorLink"):
            pred = by_uid.get(f(pl, "PredecessorUID"))
            if succ and pred:
                links.append((pred, succ, types.get(f(pl, "Type"), "FS")))
    warnings = [f"{skipped_summary} summary tasks were not imported (they only group tasks)"] if skipped_summary else []
    name = f(root, "Name") or f(root, "Title") or ""
    return _done("msp", name, [name] if name else [], tasks, links, warnings)


def _done(source, project, projects, tasks, links, warnings):
    if not tasks:
        raise ScheduleError("No activities found in the file")
    if len(tasks) > MAX_TASKS:
        raise ScheduleError(f"The file has {len(tasks)} activities. The limit is {MAX_TASKS}. Split the schedule and import in parts.")
    return {"source": source, "project": project, "projects": projects, "tasks": tasks, "links": links, "warnings": warnings}


def read_schedule(filename: str, data: bytes, project: str | None = None) -> dict:
    n = (filename or "").lower()
    if n.endswith(".xer"):
        return read_xer(data, project)
    if n.endswith(".xml"):
        return read_mspdi(data)
    if n.endswith(".mpp"):
        raise ScheduleError("Binary .mpp files cannot be read. In MS Project use File, Save As, XML Format, then upload the .xml file.")
    raise ScheduleError("Use a Primavera .xer file or an MS Project .xml file")
