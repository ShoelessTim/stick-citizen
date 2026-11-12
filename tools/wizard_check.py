"""Walk the Set up wizard end to end: the real Api with fake sticks behind a local HTTP bridge, the real
screen in Chromium, and a simulated hand that presses whatever each step asks for.

  python tools/wizard_check.py . shots/wizard          # left: 8-way mini-stick + analog; right: plain
  SCEN=pairs python tools/wizard_check.py . shots/w2   # left: diagonals sent as two directions, no analog mode

Prints every step, the learned map check, and any page/API errors."""
import json, os, shutil, sys, tempfile, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
work = Path(tempfile.mkdtemp()); os.environ["STICK_CITIZEN_HOME"] = str(work / "home")
from stick_citizen.webapi import Api, FakeHub
hub = FakeHub([{"uid": "L", "name": "VKBsim Gladiator EVO L", "axes": 8, "buttons": 128, "hats": 1},
               {"uid": "R", "name": "VKBsim Gladiator EVO R", "axes": 8, "buttons": 128, "hats": 1}])
hub.axes = {"L": [0.0] * 8, "R": [0.0] * 8}
api = Api(hub, actionmaps=str(ROOT / "samples" / "demo_actionmaps.xml"))
lock = threading.Lock()
site = work / "site"; shutil.copytree(ROOT / "stick_citizen" / "web", site)
(site / "bridge.js").write_text("""window.MOCK_API = new Proxy({}, { get: (_, name) => (...args) =>
  fetch('/api/' + name, {method: 'POST', body: JSON.stringify(args)}).then(r => r.json()) });""")
html = (site / "index.html").read_text()
(site / "index.html").write_text(html.replace('<script src="app.js', '<script src="bridge.js"></script>\n<script src="app.js'))

class H(SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=str(site), **k)
    def log_message(s, *a): pass
    def do_POST(s):
        name = s.path.split("/api/")[1]
        args = json.loads(s.rfile.read(int(s.headers["Content-Length"])) or "[]")
        with lock:
            try: res = getattr(api, name)(*args)
            except Exception as e: res = {"ok": False, "error": repr(e)}; ERR.append(f"api.{name}{args}: {e!r}")
        body = json.dumps(res).encode(); s.send_response(200); s.send_header("Content-Type", "application/json")
        s.send_header("Content-Length", str(len(body))); s.end_headers(); s.wfile.write(body)
ERR = []
srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}/index.html"

# ---- the simulated hardware: every control gets its own number; axes by index
AXES = {"wheel-t1": 6, "mini-stick-a2-analog-x": 3, "mini-stick-a2-analog-y": 4}
NUM = {}
def key_for(side, cid):
    k = (side, cid)
    if k not in NUM: NUM[k] = f"b{20 + len([x for x in NUM if x[0] == side])}"
    return NUM[k]

def press(uid, keys, hold=0.12):
    with lock:
        for k in keys: hub.press(uid, k, True)
    time.sleep(hold)
    with lock:
        for k in keys: hub.press(uid, k, False)

def armed(want):
    return api._capture is not None and api._capture_want == want

from playwright.sync_api import sync_playwright
log, shots = [], set()
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 940})
    pg.on("pageerror", lambda e: ERR.append("page: " + str(e)))
    pg.on("console", lambda m: m.type == "error" and ERR.append("console: " + m.text))
    pg.set_default_timeout(8000); pg.goto(url); pg.wait_for_timeout(1500)

    def run_side(side, scenario):
        uid = side
        pg.evaluate(f"setTimeout(() => setupFlow(S.state.sticks.find(s => s.side === '{side}')), 0)"); pg.wait_for_timeout(500)
        did = set(); steps = 0
        while steps < 120:
            steps += 1
            info = pg.evaluate("""(() => { const W = S.wiz; if (!W) return null; const t = W.todo[W.i]; if (!t) return {done:true};
                const st = stickBySlot(W.slot); const m = st.controls.find(c => c.id === t.id);
                return {id: t.id, kind: m && m.kind, dir: m && m.dir, group: m && m.group,
                        title: (document.querySelector('#wizard .wz-do')||{}).textContent,
                        btns: [...document.querySelectorAll('#wizard .wz-btns .btn')].map(b => b.textContent)}; })()""")

            if not info or info.get("done"): break
            cid, kind = info["id"], info["kind"]
            log.append(f"{side} {cid:28s} | {info['title']!s:34s} | {' / '.join(info['btns'])}")
            tag = (kind or "") + ("diag" if "-" in (info["dir"] or "") else "") + ("hat" if info["dir"] else "")
            if tag not in shots or cid in ("mini-stick-a2-analog-x", "rapid-trigger-down"):
                shots.add(tag); pg.screenshot(path=str(OUT / f"{side}-{cid}.png"))
            if "warn" in (pg.evaluate("(document.querySelector('#wizard .wz-do')||{}).className") or ""):
                log.append("   !! unexpected prompt: " + pg.evaluate("document.querySelector('#wizard .wz-how').textContent")); return
            # scenario hooks
            if scenario == "pairs" and info["group"].startswith("Mini-stick") and "-" in (info["dir"] or ""):
                a, c = info["dir"].split("-")
                g = info["group"].lower().replace(" ", "-")
                press(uid, [key_for(side, f"{g}-{a}"), key_for(side, f"{g}-{c}")]); pg.wait_for_timeout(400); continue
            if scenario == "pairs" and kind == "axis" and "analog" in cid:
                pg.click("#wizard .wz-btns .btn:has-text('No analog mode')"); pg.wait_for_timeout(400); continue
            if scenario == "happy" and cid == "hat-a3-down" and "dup" not in did:     # press the wrong one once
                did.add("dup"); press(uid, [key_for(side, "hat-a3-up")]); pg.wait_for_timeout(500)
                t = pg.evaluate("document.querySelector('#wizard .wz-do').textContent"); log.append("   duplicate prompt: " + t)
                pg.screenshot(path=str(OUT / f"{side}-duplicate.png"))
                pg.click("#wizard .wz-btns .btn:has-text('Try again')"); pg.wait_for_timeout(400); continue
            if scenario == "happy" and cid == "hat-a4-down" and "back" not in did:       # go Back once
                did.add("back"); pg.click("#wizard .wz-btns .btn:has-text('Back')"); pg.wait_for_timeout(400)
                log.append("   back -> " + pg.evaluate("S.wiz.todo[S.wiz.i].id")); continue
            want = "axis" if kind == "axis" else "button"
            for _ in range(50):
                if armed(want): break
                time.sleep(0.05)
            else: log.append(f"   !! never armed for {want}"); return
            if kind == "axis":
                i = AXES.get(cid, 5)
                with lock: hub.axes[uid][i] = 0.95
                pg.wait_for_timeout(400)
                with lock: hub.axes[uid][i] = 0.0
            else:
                press(uid, [key_for(side, cid)])
            pg.wait_for_timeout(350)
        pg.wait_for_timeout(500)
        end = pg.evaluate("(document.querySelector('#wizard .wz-name')||{}).textContent")
        log.append(f"== {side} end screen: {end}")
        pg.screenshot(path=str(OUT / f"{side}-end.png"))
        pg.click("#wizard .wz-btns .btn:has-text('Done')"); pg.wait_for_timeout(400)

    run_side("L", os.environ.get("SCEN", "happy"))
    run_side("R", "pairs")
    # what got learned
    st = api.get_state()
    for s in st["sticks"]:
        inputs = {c["id"]: c["inputs"].get("base") for c in s["controls"]}
        dupes = {}
        for cid, k in inputs.items():
            if k: dupes.setdefault(k, []).append(cid)
        log.append(f"== {s['side']}: {sum(1 for v in inputs.values() if v)} learned, {len(s['unassigned'])} unassigned {s['unassigned']}, "
                   f"shared inputs: {[v for v in dupes.values() if len(v) > 1]}")
        wrong = [cid for cid, k in inputs.items() if k and cid in AXES and k != f"a{AXES[cid]}"]
        wrong += [cid for cid, k in inputs.items() if k and (s['side'], cid) in NUM and k != NUM[(s['side'], cid)]]
        log.append(f"   wrong numbers: {wrong}")
    # Sublight lands?
    with lock: r = api.apply_layout("sublight")
    log.append("== Sublight: " + str(r.get("msg")))
    b.close()
print("\n".join(log)); print("ERRORS:", ERR or "none")
