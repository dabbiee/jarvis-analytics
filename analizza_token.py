"""Analizza i transcript di Claude Code (~/.claude/projects) e genera dashboard_token.html.

Uso:  python analizza_token.py        (poi apri dashboard_token.html)
"""
import json, re, sys, webbrowser, zipfile, shutil
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
OUT = Path(__file__).with_name("dashboard_token.html")
TEMPLATE = Path(__file__).with_name("dashboard_template.html")

CONFIG_FILE = Path(__file__).with_name("config.json")


def carica_config() -> dict:
    """config.json e' facoltativo (vedi config.example.json). Resta sul tuo PC: e' in .gitignore."""
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


CONFIG = carica_config()

# Nomi leggibili dei server MCP. I connettori di claude.ai hanno un UUID diverso per ogni account:
# aggiungi i tuoi in config.json -> "nomi_mcp" (prime 8 cifre dell'UUID -> nome).
MCP_NAMES = {
    "claude-in-chrome": "Chrome", "Claude_Browser": "Browser integrato",
    "computer-use": "Computer use", "visualize": "Visualize", "ccd_session": "Sessioni app",
    "ccd_turn": "Task list app", "scheduled-tasks": "Attività pianificate",
    **CONFIG.get("nomi_mcp", {}),
}


def project_name(cwd: str) -> str:
    """Nome del progetto dalla cartella di lavoro.

    config.json -> "progetti": {"pezzo di percorso": "Nome"} rinomina o raggruppa le cartelle;
    config.json -> "cartelle_radice": ["progetti", ...] usa la sottocartella subito sotto una di queste.
    Senza configurazione si usa il nome dell'ultima cartella.
    """
    if not cwd:
        return "Sconosciuto"
    p = cwd.replace("/", "\\")
    for pezzo, nome in CONFIG.get("progetti", {}).items():
        if pezzo.lower() in p.lower():
            return nome
    if "scratch-workspaces" in p or "\\scratch" in p.lower():
        return "Chat Claude (scratch)"
    parts = [x for x in p.split("\\") if x]
    low = [x.lower() for x in parts]
    for anchor in (a.lower() for a in CONFIG.get("cartelle_radice", [])):
        if anchor in low:
            rest = parts[low.index(anchor) + 1:]
            if rest:
                return rest[0]
    return parts[-1] if parts else cwd


def tool_label(name: str, inp: dict):
    """Ritorna (categoria, etichetta)."""
    if name.startswith("mcp__"):
        srv = name.split("__")[1]
        key = srv.split("-")[0] if re.match(r"^[0-9a-f]{8}-", srv) else srv
        key = key.replace("plugin_", "")
        if key.startswith("ccd_"):          # funzioni interne dell'app desktop, non estensioni
            return "Tool", "App: " + key[4:]
        return "MCP", MCP_NAMES.get(key, key)
    if name == "Skill":
        return "Skill", str(inp.get("skill", "?"))
    if name in ("Agent", "Task"):
        return "Subagent", str(inp.get("subagent_type") or "general-purpose")
    return "Tool", name


def first_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                return c.get("text", "")
    return ""


def clean_prompt(t: str) -> str:
    t = re.sub(r"<[^>]+>.*?</[^>]+>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:140]


CLAUDE = Path.home() / ".claude"
SHARE = Path(__file__).with_name("condivisioni")
# .claude-plugin/types pesa MB ed e' rigenerabile: non va negli zip
README = r"""MOD DI CLAUDE CODE: {name}
{desc}

INSTALLAZIONE (Windows)
1. Estrai la cartella "{name}" in %USERPROFILE%\.claude\mods\
2. Aggiungila al catalogo locale delle mod (%USERPROFILE%\.claude\mods\.claude-plugin\marketplace.json):
   {{ "name": "{name}", "source": "./{name}", "description": "..." }}
3. In Claude Code (Mod / plugin) abilitala, oppure chiedi a Claude: "installa la mod {name}".
Se manca la cartella types/ rigenerala chiedendo a Claude di ricostruire i tipi della mod.
"""


def mod_files(root: Path):
    for f in root.rglob("*"):
        parts = f.relative_to(root).parts[:-1]
        if f.is_file() and "node_modules" not in parts and not (".claude-plugin" in parts and "types" in parts) and f.name != "trace.log":
            yield f


def collect_mods():
    enabled = {}
    try:
        enabled = json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8")).get("enabledPlugins", {})
    except Exception:
        pass
    found = {}
    cands = [(d, "installed") for d in (CLAUDE / "mods").glob("*") if (d / ".claude-plugin" / "plugin.json").exists()]
    cands += [(d, "dev:" + d.parent.name[:8]) for d in (CLAUDE / "dev-mods").glob("*/*") if (d / ".claude-plugin" / "plugin.json").exists()]
    for d, kind in cands:
        if d.name in found and kind != "installed":
            continue
        try:
            man = json.loads((d / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        files = list(mod_files(d))
        src = [f for f in files if f.suffix in (".ts", ".tsx") and not f.name.endswith((".d.ts", ".test.ts", ".test.tsx"))]
        lines = sum(len(f.read_text(encoding="utf-8", errors="replace").splitlines()) for f in src)
        hooks = set()
        for f in src:
            hooks |= set(re.findall(r"['\"](prompt\.submit|session\.start|turn\.start|turn\.step|turn\.end|tool\.[a-z]+)['\"]", f.read_text(encoding="utf-8", errors="replace")))
        name = man.get("name", d.name)
        status = "attiva" if any(v and k.split("@")[0] == name for k, v in enabled.items()) else ("installata" if kind == "installed" else "in sviluppo")
        SHARE.mkdir(exist_ok=True)
        zp = SHARE / f"{name}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, Path(name) / f.relative_to(d))
            z.writestr(f"{name}/LEGGIMI_INSTALLAZIONE.txt", README.format(name=name, desc=man.get("description", "")))
        mt = max((f.stat().st_mtime for f in files), default=0)
        info = {"name": name, "version": man.get("version", "?"), "desc": man.get("description", ""), "status": status,
                "where": kind, "files": len(files), "lines": lines, "src": [f.name for f in src], "hooks": sorted(hooks),
                "mod": datetime.fromtimestamp(mt).strftime("%Y-%m-%d"), "zip": f"condivisioni/{name}.zip",
                "kb": round(zp.stat().st_size / 1024, 1), "stats": {}}
        # smistatore: statistiche di instradamento dal trace
        traces = list((CLAUDE / "dev-mods").glob(f"*/{name}/trace.log")) + list((CLAUDE / "mods").glob(f"{name}/trace.log")) \
            + list((CLAUDE / "plugins").glob(f"**/{name}/**/trace.log"))
        if traces:
            txt = "\n".join(t.read_text(encoding="utf-8", errors="replace") for t in traces)
            c = Counter(re.findall(r"livello=(\w+)", txt))
            info["stats"] = {**dict(c), "deviate": len(re.findall(r"-> (haiku|sonnet)", txt)),
                             "cache_tenuta": txt.count("cache tenuta")}
        found[name] = info
    return sorted(found.values(), key=lambda m: m["mod"], reverse=True)


# Data da cui confrontare "prima" e "dopo" (es. quando hai cambiato CLAUDE.md o attivato una mod).
# Si imposta in config.json -> "data_confronto": "2026-01-31T12:00". Senza, lo studio non viene calcolato.
DATA_CONFRONTO = CONFIG.get("data_confronto")


def result_chars(content):
    """Caratteri di testo di un tool_result (le immagini base64 non contano)."""
    if isinstance(content, str):
        return len(content)
    n = 0
    for c in content or []:
        if isinstance(c, dict) and c.get("type") == "text":
            n += len(c.get("text", ""))
    return n


def studio(files, mods):
    """Confronto prima/dopo le regole di risparmio token e le mod."""
    cut = DATA_CONFRONTO
    if not cut:
        return None
    per = {k: Counter() for k in ("prima", "dopo")}
    giorni = defaultdict(Counter)
    seen, pending = set(), {}
    for f in files:
        sub = "subagents" in f.parts
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            rows = []
            for line in fh:
                if '"type":"assistant"' not in line and '"type":"user"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("timestamp"):
                    rows.append((d, line))
        for d, _ in rows:
            ts = d["timestamp"]
            p = "prima" if ts < cut else "dopo"
            s = per[p]
            m = d.get("message") or {}
            c = m.get("content")
            if d["type"] == "user":
                if not sub and not d.get("isMeta"):
                    txt = first_text(c)
                    if txt and not txt.startswith("<"):
                        s["prompt"] += 1
                for x in c if isinstance(c, list) else []:
                    if isinstance(x, dict) and x.get("type") == "tool_result" and x.get("tool_use_id") in pending:
                        nm = pending.pop(x["tool_use_id"])
                        s["res_" + nm] += result_chars(x.get("content"))
                continue
            for x in c or []:
                if isinstance(x, dict) and x.get("type") == "tool_use":
                    nm = x.get("name", "")
                    if nm in ("Read", "Grep", "Glob"):
                        s["n_" + nm] += 1
                        pending[x.get("id")] = nm
            u, mid = m.get("usage"), m.get("id")
            if not u or not mid or mid in seen or m.get("model") == "<synthetic>":
                continue
            seen.add(mid)
            cr = u.get("cache_read_input_tokens", 0) or 0
            cw = u.get("cache_creation_input_tokens", 0) or 0
            out = u.get("output_tokens", 0) or 0
            new = u.get("input_tokens", 0) or 0
            s["turni"] += 1; s["cr"] += cr; s["cw"] += cw; s["out"] += out; s["new"] += new
            mod = m.get("model", "")
            fam = "haiku" if "haiku" in mod else "sonnet" if "sonnet" in mod else "opus" if "opus" in mod else "altro"
            s["m_" + fam] += 1
            g = giorni[datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")]
            g["turni"] += 1; g["cr"] += cr; g["tot"] += cr + cw + out + new

    def riassunto(s):
        t = max(1, s["turni"]); pr = max(1, s["prompt"])
        tot = s["cr"] + s["cw"] + s["out"] + s["new"]
        return {"prompt": s["prompt"], "turni": s["turni"], "tot": tot,
                "turni_prompt": round(s["turni"] / pr, 1), "tok_prompt": round(tot / pr),
                "cr_turno": round(s["cr"] / t), "cw_turno": round(s["cw"] / t), "out_turno": round(s["out"] / t),
                "quota_cache": round(100 * s["cr"] / max(1, tot), 1),
                "read_prompt": round(s["n_Read"] / pr, 2), "grep_prompt": round((s["n_Grep"] + s["n_Glob"]) / pr, 2),
                "read_tok": round(s["res_Read"] / 4 / max(1, s["n_Read"])),
                "grep_tok": round((s["res_Grep"] + s["res_Glob"]) / 4 / max(1, s["n_Grep"] + s["n_Glob"])),
                "modelli": {k: round(100 * s["m_" + k] / t, 1) for k in ("haiku", "sonnet", "opus")}}

    tappe = [{"data": cut[:10],
              "cosa": CONFIG.get("descrizione_confronto", "Data di confronto"), "attiva": True}]
    tappe += [{"data": m["mod"], "cosa": "Mod " + m["name"], "attiva": m["status"] == "attiva"} for m in mods]
    return {"cut": cut[:16].replace("T", " "), "prima": riassunto(per["prima"]), "dopo": riassunto(per["dopo"]),
            "giorni": [[k, v["turni"], round(v["cr"] / max(1, v["turni"])), v["tot"]] for k, v in sorted(giorni.items())],
            "tappe": sorted(tappe, key=lambda x: x["data"])}


def main():
    files = list(ROOT.rglob("*.jsonl"))
    msgs = {}                      # message.id -> record (dedup dello streaming)
    sess = {}                      # sessionId -> info
    titles, relocated = {}, {}
    stamps = defaultdict(list)     # sessionId -> timestamp per tempo attivo
    for f in files:
        is_sub = "subagents" in f.parts
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"type":"custom-title"' in line or '"type":"relocated"' in line:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("customTitle"):
                        titles[d["sessionId"]] = d["customTitle"]
                    if d.get("relocatedCwd"):
                        relocated[d["sessionId"]] = d["relocatedCwd"]
                    continue
                if '"type":"assistant"' not in line and '"type":"user"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = d.get("sessionId") or f.stem
                ts = d.get("timestamp")
                if not ts:
                    continue
                s = sess.setdefault(sid, {"cwd": "", "title": "", "start": ts, "end": ts,
                                          "prompts": 0, "entry": d.get("entrypoint", "")})
                if d.get("cwd") and not s["cwd"]:
                    s["cwd"] = d["cwd"]
                stamps[sid].append(ts)
                s["start"] = min(s["start"], ts)
                s["end"] = max(s["end"], ts)
                m = d.get("message") or {}
                if d["type"] == "user" and not is_sub and not d.get("isMeta"):
                    txt = first_text(m.get("content"))
                    if txt and not txt.startswith("<") or (txt and "<command-" in txt):
                        c = clean_prompt(txt)
                        if c:
                            s["prompts"] += 1
                            if not s["title"]:
                                s["title"] = c
                elif d["type"] == "assistant":
                    u = m.get("usage")
                    mid = m.get("id") or d.get("requestId") or d.get("uuid")
                    if not u or not mid:
                        continue
                    rec = msgs.get(mid)
                    if rec is None:
                        rec = msgs[mid] = {"sid": sid, "ts": ts, "model": m.get("model", "?"),
                                           "sub": is_sub, "tools": [], "u": u}
                    rec["u"] = u
                    for c in m.get("content") or []:
                        if isinstance(c, dict) and c.get("type") == "tool_use":
                            rec["tools"].append(tool_label(c.get("name", "?"), c.get("input") or {}))

    projects, sessions, events = [], [], defaultdict(lambda: [0, 0, 0, 0, 0])
    pidx, sidx = {}, {}
    sess_tok = defaultdict(lambda: [0, 0, 0, 0])
    sess_tools = defaultdict(Counter)
    sess_models = defaultdict(Counter)
    sess_turns = Counter()
    sess_sub = Counter()

    for rec in msgs.values():
        if rec["model"] == "<synthetic>":
            continue
        sid = rec["sid"]
        u = rec["u"]
        t = [u.get("input_tokens", 0) or 0, u.get("cache_creation_input_tokens", 0) or 0,
             u.get("cache_read_input_tokens", 0) or 0, u.get("output_tokens", 0) or 0]
        if sid not in sidx:
            info = sess.get(sid, {"cwd": "", "title": "", "start": rec["ts"], "end": rec["ts"], "prompts": 0, "entry": ""})
            pn = project_name(relocated.get(sid) or info["cwd"])
            if pn not in pidx:
                pidx[pn] = len(projects); projects.append(pn)
            sidx[sid] = len(sessions)
            sessions.append({"sid": sid, "id": sid[:8], "p": pidx[pn], "title": titles.get(sid) or info["title"] or "(senza prompt)",
                             "start": info["start"], "end": info["end"], "prompts": info["prompts"]})
        si = sidx[sid]
        dt = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00")).astimezone()
        key = (si, dt.strftime("%Y-%m-%d"), dt.hour)
        ev = events[key]
        for i in range(4):
            ev[i] += t[i]; sess_tok[si][i] += t[i]
        ev[4] += 1
        sess_turns[si] += 1
        if rec["sub"]:
            sess_sub[si] += sum(t)
        sess_models[si][rec["model"]] += t[3]
        for cat, lab in rec["tools"]:
            sess_tools[si][cat + "|" + lab] += 1

    for i, s in enumerate(sessions):
        a = datetime.fromisoformat(s["start"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(s["end"].replace("Z", "+00:00"))
        s["start"] = a.astimezone().strftime("%Y-%m-%d %H:%M")
        s["span"] = round((b - a).total_seconds() / 60)
        st = sorted(datetime.fromisoformat(x.replace("Z", "+00:00")) for x in stamps.get(s.pop("sid"), []))
        act = sum((y - x).total_seconds() for x, y in zip(st, st[1:]) if (y - x).total_seconds() < 1800)
        s["min"] = round(act / 60)
        s["t"] = sess_tok[i]
        s["turns"] = sess_turns[i]
        s["sub"] = sess_sub[i]
        s["model"] = sess_models[i].most_common(1)[0][0] if sess_models[i] else "?"
        s["tools"] = dict(sess_tools[i])

    mods = collect_mods()
    data = {
        "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "files": len(files),
        "mods": mods,
        "studio": studio(files, mods),
        "projects": projects,
        "sessions": sessions,
        "events": [[k[0], k[1], k[2], *v] for k, v in sorted(events.items(), key=lambda x: (x[0][1], x[0][2]))],
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    global ULTIMI
    ULTIMI = data   # usati da crea_versione_protetta.py per il file da condividere
    tot = sum(sum(v) for v in sess_tok.values())
    print(f"{len(files)} file, {len(sessions)} sessioni, {len(projects)} progetti, {tot:,} token -> {OUT}")
    if "--open" in sys.argv:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
