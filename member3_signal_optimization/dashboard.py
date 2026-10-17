from __future__ import annotations
import json, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_STATE = {
    "status":"Waiting to start","controller":"—","source":"—","time_s":0,"step":0,
    "vehicles_passed":0,"vehicles_departed":0,"vehicles_in_network":0,"decision_count":0,
    "predicted_count":0,"predicted_level":"LOW","phase":"—","active_direction":"—","green_remaining":0,
    "directions":{d:{"vehicles":0,"queue":0,"signal":"RED","passed":0} for d in ("NORTH","SOUTH","EAST","WEST")},
    "events":[],"history":[]
}
_LOCK=threading.Lock()
_SERVER=None
PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Adaptive Traffic Management</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#142138;--line:#2a3b56;--muted:#9aabc3;--text:#edf4ff;--green:#28d17c;--red:#ff5b67;--yellow:#ffd166;--blue:#68a8ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#1a2b49,#0b1220 60%);font:14px/1.45 Segoe UI,Arial,sans-serif;color:var(--text)}main{max-width:1400px;margin:auto;padding:25px}
.top{display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:22px}h1{font-size:clamp(22px,3vw,32px);margin:0}.sub,.hint{color:var(--muted)}.sub{margin-top:5px}.status{border:1px solid #246746;background:#102d25;color:#80f0b4;padding:8px 12px;border-radius:999px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{background:linear-gradient(145deg,#17263d,#111a2a);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 12px 30px #0002}.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}.value{font-size:30px;font-weight:800;margin:7px 0 3px}.hint{font-size:12px}.section{margin:24px 0 12px;font-size:17px;font-weight:750}
.directions{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.dirhead{display:flex;align-items:center;justify-content:space-between;font-weight:800;font-size:15px}.arrow{font-size:21px;color:var(--blue)}.metrics{display:flex;gap:22px;margin:19px 0}.metrics b{font-size:23px;display:block}.metrics span{color:var(--muted);font-size:12px}.signal{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:999px;background:#263247;font-weight:800;font-size:11px}.dot{width:8px;height:8px;border-radius:50%;background:var(--red)}.signal.GREEN .dot{background:var(--green)}.signal.YELLOW .dot{background:var(--yellow)}.signal.RED .dot{background:var(--red)}
.twocol{display:grid;grid-template-columns:1.1fr .9fr;gap:14px}.tablewrap{overflow:auto;max-height:560px}table{width:100%;border-collapse:collapse;min-width:520px}th,td{text-align:left;padding:11px 9px;border-bottom:1px solid var(--line);font-size:12px}th{color:var(--muted)}.tag{border-radius:6px;background:#20314b;padding:4px 7px;color:#a8cbff;font-weight:700}.bar{height:7px;border-radius:99px;background:#25344b;overflow:hidden;margin-top:10px}.bar i{display:block;height:100%;background:linear-gradient(90deg,#4f8dff,#28d17c)}.empty{color:var(--muted);padding:16px 0}.footer{color:var(--muted);font-size:11px;margin-top:20px}
@media(max-width:950px){.grid,.directions{grid-template-columns:repeat(2,minmax(0,1fr))}.twocol{grid-template-columns:1fr}}@media(max-width:560px){main{padding:14px}.grid,.directions{grid-template-columns:1fr}.value{font-size:26px}}
</style></head><body><main>
<div class="top"><div><h1>AI Adaptive Traffic Management</h1><div class="sub">Live SUMO intersection monitor · automatic updates</div></div><div class="status" id="status">● CONNECTING</div></div>
<div class="grid">
<div class="card"><div class="label">Simulation elapsed</div><div class="value" id="elapsed">00:00</div><div class="hint">SUMO simulation clock</div></div>
<div class="card"><div class="label">Vehicles passed / arrived</div><div class="value" id="passed">0</div><div class="hint">Exited network (not intersection-only count)</div></div>
<div class="card"><div class="label">Vehicles in network</div><div class="value" id="network">0</div><div class="hint">Currently active vehicles</div></div>
<div class="card"><div class="label">Signal decisions</div><div class="value" id="decisions">0</div><div class="hint">Logged controller decisions</div></div></div>
<div class="section">Live traffic by direction</div><div class="directions" id="directions"></div>
<div class="section">Controller & prediction</div><div class="grid">
<div class="card"><div class="label">Controller</div><div class="value" style="font-size:22px" id="controller">—</div><div class="hint" id="source">Input: —</div></div>
<div class="card"><div class="label">Predicted traffic</div><div class="value" id="prediction">0</div><div class="hint" id="level">Level: LOW</div></div>
<div class="card"><div class="label">Current phase</div><div class="value" style="font-size:22px" id="phase">—</div><div class="hint" id="active">Active approach: —</div></div>
<div class="card"><div class="label">Green remaining</div><div class="value"><span id="remaining">0</span><span style="font-size:15px"> sec</span></div><div class="hint">Controller phase timer</div></div></div>
<div class="twocol"><div><div class="section">Latest 100 Signal Decisions</div><div class="card tablewrap"><table><thead><tr><th>Time</th><th>Direction</th><th>Green</th><th>Demand</th><th>Reason / flags</th></tr></thead><tbody id="events"><tr><td colspan="5" class="empty">Waiting for first decision…</td></tr></tbody></table></div></div>
<div><div class="section">Queue history</div><div class="card"><div class="hint">Total inbound queue trend</div><div id="chart" style="height:170px;display:flex;align-items:end;gap:3px;margin-top:18px"></div><div class="hint" id="chartnote" style="margin-top:12px">Waiting for data…</div></div><div class="section">Session</div><div class="card"><div class="label">Simulation status</div><div class="value" style="font-size:20px" id="session">Waiting</div><div class="hint">Fixed-time and adaptive runs execute sequentially.</div></div></div></div>
<div class="footer">“Vehicles passed” means vehicles that arrived at their final SUMO destination. Dashboard values are live simulation data.</div></main>
<script>
const names={NORTH:'North',SOUTH:'South',EAST:'East',WEST:'West'},arrows={NORTH:'↑',SOUTH:'↓',EAST:'→',WEST:'←'};
function fmt(t){t=Math.max(0,Math.floor(Number(t)||0));let h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function refresh(){try{let r=await fetch('/data',{cache:'no-store'}),d=await r.json();
for(let [id,v] of Object.entries({status:'● '+String(d.status||'RUNNING').toUpperCase(),elapsed:fmt(d.time_s),passed:d.vehicles_passed??0,network:d.vehicles_in_network??0,decisions:d.decision_count??0,controller:String(d.controller||'—').toUpperCase(),source:'Input: '+String(d.source||'—').toUpperCase(),prediction:d.predicted_count??0,level:'Level: '+(d.predicted_level||'LOW'),phase:String(d.phase||'—').toUpperCase(),active:'Active approach: '+(names[d.active_direction]||d.active_direction||'—'),remaining:d.green_remaining??0,session:d.status||'Waiting'}))document.getElementById(id).textContent=v;
let html='';for(let k of ['NORTH','SOUTH','EAST','WEST']){let x=(d.directions||{})[k]||{},sig=String(x.signal||'RED').toUpperCase();html+=`<div class="card"><div class="dirhead"><span>${names[k]} <span class="arrow">${arrows[k]}</span></span><span class="signal ${esc(sig)}"><i class="dot"></i>${esc(sig)}</span></div><div class="metrics"><div><b>${x.vehicles??0}</b><span>Vehicles now</span></div><div><b>${x.queue??0}</b><span>Current queue</span></div></div><div class="hint">Exited network: ${x.passed??0}</div><div class="bar"><i style="width:${Math.min(100,(Number(x.queue)||0)*5)}%"></i></div></div>`}document.getElementById('directions').innerHTML=html;
let ev=(d.events||[]).slice(-100).reverse();document.getElementById('events').innerHTML=ev.length?ev.map(e=>`<tr><td>${fmt(e.time_s)}</td><td><span class="tag">${esc(names[e.approach]||e.approach)}</span></td><td>${e.green_s??0}s</td><td>${e.demand??0}</td><td>${esc(e.reason||'Demand-based')}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">Waiting for first decision…</td></tr>';
let hist=(d.history||[]).slice(-55);document.getElementById('chart').innerHTML=hist.length?hist.map(h=>`<div title="t=${fmt(h.time_s)} · queue=${h.queue}" style="flex:1;min-width:2px;height:${Math.max(3,Math.min(100,(Number(h.queue)||0)*5))}%;background:#4f8dff;border-radius:3px 3px 0 0"></div>`).join(''):'<div class="empty">No samples yet</div>';document.getElementById('chartnote').textContent=hist.length?`Latest total inbound queue: ${hist[hist.length-1].queue} vehicles`:'Waiting for simulation data…';
}catch(e){document.getElementById('status').textContent='● RECONNECTING'}}setInterval(refresh,700);refresh();
</script></body></html>'''

def update_dashboard(data):
    with _LOCK:
        for key, value in data.items():
            if key in ("events","history"):
                _STATE[key] = list(value)[-180:]
            else:
                _STATE[key] = value

def start_dashboard(open_browser=True, port=8765):
    global _SERVER
    if _SERVER is not None:
        return f"http://127.0.0.1:{port}"
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/data":
                with _LOCK: body=json.dumps(_STATE).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8")
                self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(body)
            else:
                body=PAGE.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(body)
        def log_message(self, format, *args): return
    _SERVER=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    threading.Thread(target=_SERVER.serve_forever,daemon=True).start()
    url=f"http://127.0.0.1:{port}"
    if open_browser: threading.Timer(0.8,lambda:webbrowser.open(url)).start()
    return url
