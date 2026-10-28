# -*- coding: utf-8 -*-
"""
=============================================================================
IRLE TELEFON KONTROLCÜ — Bağımsız PWA Uygulaması
=============================================================================
Telefonuna gerçek bir uygulama olarak kur:
  iOS   → Safari → Paylaş → Ana Ekrana Ekle
  Android → Chrome → ⋮ → Uygulamayı Yükle

python kontrolcu_app.py  ile başlat.
=============================================================================
"""

import threading, logging, socket, os, io, sys, time, base64, json
import pyautogui, qrcode
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template_string, send_file, jsonify, Response
from flask_socketio import SocketIO

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("KontrolcuApp")

pyautogui.FAILSAFE = False
PORT = 5556

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        return ip
    except: return "127.0.0.1"

LOCAL_IP = get_local_ip()
BASE_URL = f"http://{LOCAL_IP}:{PORT}"

# ─────────────────────────────────────────────────────────────────────────────
# PWA İKONU — Programatik oluştur (Pillow)
# ─────────────────────────────────────────────────────────────────────────────
def make_icon(size: int) -> bytes:
    img = Image.new("RGB", (size, size), "#0f1117")
    d   = ImageDraw.Draw(img)
    # Gradient arka plan
    for i in range(size):
        ratio = i / size
        r = int(15  + ratio * 20)
        g = int(17  + ratio * 10)
        b = int(23  + ratio * 40)
        d.rectangle([(0, i), (size, i+1)], fill=(r, g, b))
    # Daire arka plan
    pad = int(size * 0.08)
    d.ellipse([pad, pad, size-pad, size-pad], fill="#1c2333", outline="#6366f1", width=max(2, size//48))
    # Gamepad şekli (basit ikonografik)
    cx, cy = size//2, size//2
    r = int(size * 0.28)
    # Sol çubuk
    d.rounded_rectangle([cx-r-int(r*.6), cy-int(r*.25), cx-int(r*.15), cy+int(r*.25)],
                         radius=int(r*.25), fill="#6366f1")
    # Sağ çubuk
    d.rounded_rectangle([cx+int(r*.15), cy-int(r*.25), cx+r+int(r*.6), cy+int(r*.25)],
                         radius=int(r*.25), fill="#6366f1")
    # Bağlantı köprüsü
    d.rounded_rectangle([cx-int(r*.15), cy-int(r*.15), cx+int(r*.15), cy+int(r*.15)],
                         radius=int(r*.15), fill="#a78bfa")
    # D-pad noktaları (sol)
    dp = int(r * .18)
    lx = cx - int(r * .55)
    d.ellipse([lx-dp, cy-dp, lx+dp, cy+dp], fill="#34d399")
    # ABXY noktaları (sağ)
    rx = cx + int(r * .55)
    colors = ["#f87171","#34d399","#60a5fa","#fbbf24"]
    offs   = [(0,-1),(1,0),(0,1),(-1,0)]
    sp     = int(r*.18)
    for (ox,oy),c in zip(offs,colors):
        d.ellipse([rx+ox*sp-dp, cy+oy*sp-dp, rx+ox*sp+dp, cy+oy*sp+dp], fill=c)
    buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()

ICON_192 = make_icon(192)
ICON_512 = make_icon(512)

# ─────────────────────────────────────────────────────────────────────────────
# PWA MANIFEST
# ─────────────────────────────────────────────────────────────────────────────
MANIFEST = {
    "name": "IRLE Kontrolcü",
    "short_name": "IRLE",
    "description": "PC Gamepad, Klavye ve Mouse kontrolcüsü",
    "start_url": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0f1117",
    "theme_color": "#6366f1",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
    "categories": ["utilities", "games"],
}

# ─────────────────────────────────────────────────────────────────────────────
# SERVICE WORKER — Offline desteği
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_WORKER_JS = r"""
const CACHE = 'irle-v1';
const OFFLINE_ASSETS = ['/'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE_ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))
  ));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  if(e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(res => { const c=res.clone(); caches.open(CACHE).then(ca=>ca.put(e.request,c)); return res; })
      .catch(() => caches.match(e.request))
  );
});
"""

# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">

<!-- PWA Tags -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="IRLE">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#6366f1">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon-192.png">

<title>IRLE Kontrolcü</title>
<style>
/* ─── TOKENS ─────────────────────────────────────────────────── */
:root{
  --bg:#0f1117;--surface:#161d2e;--card:#1c2535;--border:#253350;
  --accent:#6366f1;--ag:rgba(99,102,241,.2);
  --purple:#a78bfa;--green:#34d399;--red:#f87171;
  --yellow:#fbbf24;--blue:#60a5fa;
  --text:#e2e8f0;--muted:#4b5a72;
  --r:13px;
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-bot: env(safe-area-inset-bottom, 0px);
}
*{box-sizing:border-box;margin:0;padding:0;
  -webkit-tap-highlight-color:transparent;
  touch-action:manipulation;
  -webkit-user-select:none;user-select:none}
html{height:100%;height:100dvh;overflow:hidden}
body{
  height:100%;height:100dvh;
  background:var(--bg);color:var(--text);
  font-family:'Segoe UI',system-ui,sans-serif;
  overflow:hidden;
  padding-top:var(--safe-top);
  padding-bottom:var(--safe-bot);
  display:flex;flex-direction:column;
}

/* ─── HEADER ─────────────────────────────────────────────────── */
header{
  display:flex;align-items:center;gap:10px;
  padding:8px 14px;
  background:var(--surface);
  border-bottom:1px solid var(--border);
  flex-shrink:0;
}
.dot{width:9px;height:9px;border-radius:50%;background:var(--red);flex-shrink:0;transition:all .3s}
.dot.on{background:var(--green);box-shadow:0 0 8px var(--green)}
#st{font-size:11px;color:var(--muted)}
.brand{
  margin-left:auto;font-weight:800;font-size:13px;
  color:transparent;
  background:linear-gradient(135deg,var(--accent),var(--purple));
  -webkit-background-clip:text;background-clip:text;
  letter-spacing:1px;
}
.install-hint{
  display:none;
  font-size:9px;color:var(--purple);
  background:var(--ag);border:1px solid var(--accent);
  border-radius:6px;padding:2px 7px;cursor:pointer;
  white-space:nowrap;
}
.install-hint.show{display:block}

/* ─── TABS ───────────────────────────────────────────────────── */
nav{
  display:flex;background:var(--surface);
  border-bottom:1px solid var(--border);flex-shrink:0;
}
.tab{
  flex:1;padding:10px 2px;background:none;border:none;
  color:var(--muted);font-size:10px;font-weight:800;
  letter-spacing:.7px;text-transform:uppercase;cursor:pointer;
  border-bottom:2.5px solid transparent;transition:color .15s,border-color .15s;
}
.tab.on{color:var(--purple);border-color:var(--purple)}

/* ─── PANELS ─────────────────────────────────────────────────── */
main{flex:1;position:relative;overflow:hidden}
.panel{position:absolute;inset:0;display:none;flex-direction:column;overflow:hidden}
.panel.on{display:flex}

/* ─────────────────────────────────────────────────────────────── */
/*  MOUSE PANEL                                                    */
/* ─────────────────────────────────────────────────────────────── */
#pMouse{gap:0}

.sens-row{
  display:flex;align-items:center;gap:10px;
  padding:8px 14px;background:var(--surface);
  border-bottom:1px solid var(--border);flex-shrink:0;
}
.sens-row label{font-size:10px;color:var(--muted);white-space:nowrap;font-weight:700}
.sens-row input[type=range]{flex:1;height:4px;accent-color:var(--accent)}
#sv{font-size:11px;color:var(--purple);font-weight:800;min-width:22px;text-align:right}

.touchpad{
  flex:1;margin:10px;
  background:var(--card);
  border:1.5px solid var(--border);
  border-radius:18px;
  position:relative;overflow:hidden;
  touch-action:none;
  display:flex;align-items:center;justify-content:center;
}
.touchpad::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at 50% 50%,rgba(99,102,241,.04),transparent 70%);
  pointer-events:none;
}
.tp-hint{color:var(--muted);font-size:11px;text-align:center;line-height:2.2;pointer-events:none}
.tp-cursor{
  position:absolute;width:24px;height:24px;border-radius:50%;
  background:var(--purple);opacity:0;
  transform:translate(-50%,-50%);
  pointer-events:none;
  box-shadow:0 0 14px var(--purple);
  transition:opacity .15s;
}
.tp-cursor.show{opacity:.85}
.tp-ring{
  position:absolute;width:48px;height:48px;border-radius:50%;
  border:1.5px solid var(--purple);opacity:0;
  transform:translate(-50%,-50%) scale(.5);
  pointer-events:none;
  transition:opacity .2s,transform .2s;
}
.tp-ring.show{opacity:.3;transform:translate(-50%,-50%) scale(1)}

.mouse-row{
  display:grid;grid-template-columns:1fr 1fr;
  gap:8px;padding:0 10px 8px;flex-shrink:0;
}
.mbtn{
  padding:15px;text-align:center;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);font-size:13px;font-weight:700;
  cursor:pointer;transition:background .1s,transform .08s;
}
.mbtn:active{background:var(--accent);transform:scale(.94)}

.scroll-row{
  display:flex;gap:8px;padding:0 10px 10px;flex-shrink:0;
}
.sbtn{
  flex:1;padding:12px;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);text-align:center;
  font-size:18px;cursor:pointer;
  transition:background .1s;
}
.sbtn:active{background:var(--accent)}

/* ─────────────────────────────────────────────────────────────── */
/*  GAMEPAD PANEL                                                  */
/* ─────────────────────────────────────────────────────────────── */
#pGamepad{padding:8px;gap:7px;justify-content:space-between}

.gp-row{display:flex;gap:8px}
.bump,.trig{
  flex:1;padding:11px 6px;text-align:center;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);font-size:11px;font-weight:800;color:var(--text);
  cursor:pointer;transition:background .08s,transform .08s;
}
.bump:active,.bump.pr,.trig:active,.trig.pr{background:var(--accent);transform:scale(.94)}

.mid{display:flex;justify-content:space-between;align-items:center;gap:6px;flex:1}

/* D-PAD */
.dpad{position:relative;width:114px;height:114px;flex-shrink:0}
.dp{
  position:absolute;width:36px;height:36px;
  background:var(--card);border:1px solid var(--border);
  border-radius:7px;color:var(--text);font-size:16px;
  display:flex;align-items:center;justify-content:center;cursor:pointer;
  transition:background .07s,transform .07s;
}
.dp:active,.dp.pr{background:var(--accent);transform:scale(.9)}
.dp-u{top:0;left:39px}.dp-d{bottom:0;left:39px}
.dp-l{top:39px;left:0}.dp-r{top:39px;right:0}
.dp-c{top:39px;left:39px;background:var(--border);border-radius:50%;pointer-events:none}

/* CENTER */
.gp-center{display:flex;flex-direction:column;align-items:center;gap:8px}
.sys-row{display:flex;gap:6px}
.sys{
  background:var(--card);border:1px solid var(--border);
  border-radius:20px;color:var(--muted);
  font-size:9px;font-weight:800;padding:5px 10px;cursor:pointer;
  letter-spacing:.4px;transition:all .1s;
}
.sys:active{border-color:var(--accent);color:var(--purple)}

/* ABXY */
.abxy{position:relative;width:114px;height:114px;flex-shrink:0}
.face{
  position:absolute;width:38px;height:38px;border-radius:50%;border:none;
  font-size:13px;font-weight:800;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  transition:transform .07s,filter .07s;box-shadow:0 3px 10px rgba(0,0,0,.4);
}
.face:active,.face.pr{transform:scale(.84);filter:brightness(.6)}
.f-y{top:0;left:38px;background:#f59e0b;color:#000}
.f-b{top:38px;right:0;background:var(--red);color:#fff}
.f-a{bottom:0;left:38px;background:var(--green);color:#000}
.f-x{top:38px;left:0;background:var(--blue);color:#fff}

/* STICKS */
.sticks{display:flex;gap:12px;justify-content:space-around;flex-shrink:0}
.stk-wrap{display:flex;flex-direction:column;align-items:center;gap:4px}
.stk-lbl{font-size:8px;font-weight:800;color:var(--muted);letter-spacing:.8px;text-transform:uppercase}
.stk-pad{
  width:98px;height:98px;
  background:var(--card);border:2px solid var(--border);
  border-radius:50%;position:relative;touch-action:none;
}
.stk-thumb{
  position:absolute;width:38px;height:38px;border-radius:50%;
  background:radial-gradient(circle at 33% 33%,#6366f1,#312e81);
  box-shadow:0 3px 12px rgba(0,0,0,.7);
  top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;
}

/* ─────────────────────────────────────────────────────────────── */
/*  KEYBOARD PANEL                                                 */
/* ─────────────────────────────────────────────────────────────── */
#pKeyboard{overflow-y:auto;padding:7px;gap:5px}

.kb-lbl{font-size:8px;font-weight:800;color:var(--muted);
  text-transform:uppercase;letter-spacing:1px;padding:2px 1px}
.kr{display:flex;gap:4px;justify-content:center}
.k{
  flex:1;min-width:22px;max-width:46px;height:40px;
  background:var(--card);border:1px solid var(--border);
  border-radius:8px;color:var(--text);
  font-size:11px;font-weight:700;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;transition:background .07s,transform .07s;
}
.k:active{background:var(--accent);transform:scale(.9)}
.w2{flex:2;max-width:78px}.w3{flex:3;max-width:106px}
.sp{flex:5;max-width:190px;background:#141b2a}
.hi{background:var(--purple)!important;color:#000!important}

.shorts{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:2px}
.sk{
  padding:10px 4px;text-align:center;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);color:var(--text);
  font-size:9px;font-weight:700;cursor:pointer;line-height:1.5;
  transition:background .08s;
}
.sk:active{background:var(--accent)}

/* ─────────────────────────────────────────────────────────────── */
/*  INSTALL BANNER                                                 */
/* ─────────────────────────────────────────────────────────────── */
.install-banner{
  display:none;
  background:linear-gradient(135deg,#1c2535,#1a1040);
  border-top:1px solid var(--accent);
  padding:10px 14px;flex-shrink:0;
  align-items:center;gap:10px;
  font-size:11px;
}
.install-banner.show{display:flex}
.install-banner strong{color:var(--purple)}
.install-banner .ibtn{
  margin-left:auto;
  background:var(--accent);color:#fff;
  border:none;border-radius:8px;padding:6px 14px;
  font-size:11px;font-weight:700;cursor:pointer;
  flex-shrink:0;
}
.close-banner{
  background:none;border:none;color:var(--muted);
  font-size:16px;cursor:pointer;padding:0 4px;flex-shrink:0;
}

/* ─────────────────────────────────────────────────────────────── */
/*  RIPPLE                                                         */
/* ─────────────────────────────────────────────────────────────── */
@keyframes rip{from{transform:translate(-50%,-50%) scale(0);opacity:.5}to{transform:translate(-50%,-50%) scale(4);opacity:0}}
.rip{position:fixed;width:26px;height:26px;border-radius:50%;
  background:rgba(99,102,241,.35);animation:rip .4s ease-out forwards;
  pointer-events:none;z-index:9999}
</style>
</head>
<body>

<!-- HEADER -->
<header>
  <div class="dot" id="dot"></div>
  <span id="st">Bağlanıyor...</span>
  <button class="install-hint" id="install-hint" onclick="showInstallGuide()">📲 Uygulamayı Kur</button>
  <span class="brand">⬡ IRLE</span>
</header>

<!-- TABS -->
<nav>
  <button class="tab on"  id="t-Mouse"    onclick="go('Mouse')">🖱️ MOUSE</button>
  <button class="tab"     id="t-Gamepad"  onclick="go('Gamepad')">🎮 GAMEPAD</button>
  <button class="tab"     id="t-Keyboard" onclick="go('Keyboard')">⌨️ KLAVYE</button>
</nav>

<!-- INSTALL BANNER -->
<div class="install-banner" id="install-banner">
  <span id="install-text">📲 <strong>Uygulamayı</strong> ana ekrana ekle!</span>
  <button class="ibtn" id="install-btn">Yükle</button>
  <button class="close-banner" onclick="closeBanner()">✕</button>
</div>

<!-- MAIN -->
<main>

<!-- ══════════ MOUSE ══════════ -->
<div class="panel on" id="pMouse">
  <div class="sens-row">
    <label>⚡ Hız</label>
    <input type="range" id="sens" min="1" max="10" value="4" oninput="sv.textContent=this.value;sens_val=+this.value">
    <span id="sv">4</span>
  </div>
  <div class="touchpad" id="tp">
    <div class="tp-cursor" id="tpc"></div>
    <div class="tp-ring"   id="tpr"></div>
    <span class="tp-hint">
      ☝️ Kaydır → fare hareketi<br>
      ✌️ 2 parmak → scroll<br>
      👆👆 Çift dok → çift tık
    </span>
  </div>
  <div class="mouse-row">
    <div class="mbtn" ontouchstart="mc('left')"  onclick="mc('left')">🖱 Sol Tık</div>
    <div class="mbtn" ontouchstart="mc('right')" onclick="mc('right')">🖱 Sağ Tık</div>
  </div>
  <div class="scroll-row">
    <div class="sbtn" ontouchstart="sc('up')">▲</div>
    <div class="sbtn" ontouchstart="mc('middle')">⬤ Orta</div>
    <div class="sbtn" ontouchstart="sc('down')">▼</div>
  </div>
</div>

<!-- ══════════ GAMEPAD ══════════ -->
<div class="panel" id="pGamepad">
  <div class="gp-row">
    <div class="bump" id="b-lb" ontouchstart="btn('lb','d')" ontouchend="btn('lb','u')">LB</div>
    <div class="bump" id="b-rb" ontouchstart="btn('rb','d')" ontouchend="btn('rb','u')">RB</div>
  </div>
  <div class="gp-row">
    <div class="trig" id="b-lt" ontouchstart="btn('lt','d')" ontouchend="btn('lt','u')" style="background:#141e38">◀ LT</div>
    <div class="trig" id="b-rt" ontouchstart="btn('rt','d')" ontouchend="btn('rt','u')" style="background:#141e38">RT ▶</div>
  </div>

  <div class="mid">
    <div class="dpad">
      <div class="dp dp-u" id="dp-up"    ontouchstart="dp('up','d')"    ontouchend="dp('up','u')">▲</div>
      <div class="dp dp-d" id="dp-down"  ontouchstart="dp('down','d')"  ontouchend="dp('down','u')">▼</div>
      <div class="dp dp-l" id="dp-left"  ontouchstart="dp('left','d')"  ontouchend="dp('left','u')">◀</div>
      <div class="dp dp-r" id="dp-right" ontouchstart="dp('right','d')" ontouchend="dp('right','u')">▶</div>
      <div class="dp dp-c"></div>
    </div>
    <div class="gp-center">
      <div class="sys-row">
        <div class="sys" onclick="btn('back','c')">← BACK</div>
        <div class="sys" onclick="btn('home','c')" style="font-size:15px">⬡</div>
        <div class="sys" onclick="btn('start','c')">START ▶</div>
      </div>
    </div>
    <div class="abxy">
      <div class="face f-y" id="b-y" ontouchstart="btn('y','d')" ontouchend="btn('y','u')">Y</div>
      <div class="face f-b" id="b-b" ontouchstart="btn('b','d')" ontouchend="btn('b','u')">B</div>
      <div class="face f-a" id="b-a" ontouchstart="btn('a','d')" ontouchend="btn('a','u')">A</div>
      <div class="face f-x" id="b-x" ontouchstart="btn('x','d')" ontouchend="btn('x','u')">X</div>
    </div>
  </div>

  <div class="sticks">
    <div class="stk-wrap">
      <span class="stk-lbl">Sol Stick</span>
      <div class="stk-pad" id="sl"><div class="stk-thumb" id="tl"></div></div>
    </div>
    <div class="stk-wrap">
      <span class="stk-lbl">Sağ Stick</span>
      <div class="stk-pad" id="sr"><div class="stk-thumb" id="tr"></div></div>
    </div>
  </div>
</div>

<!-- ══════════ KEYBOARD ══════════ -->
<div class="panel" id="pKeyboard">
  <div class="kb-lbl">Fonksiyon</div>
  <div class="kr">
    <div class="k" onclick="sk('escape')">Esc</div>
    <div class="k" onclick="sk('f1')">F1</div><div class="k" onclick="sk('f2')">F2</div>
    <div class="k" onclick="sk('f3')">F3</div><div class="k" onclick="sk('f4')">F4</div>
    <div class="k" onclick="sk('f5')">F5</div><div class="k" onclick="sk('f11')">F11</div>
    <div class="k" onclick="sk('f12')">F12</div>
    <div class="k" onclick="sk('delete')">Del</div>
  </div>
  <div class="kb-lbl">Sayılar</div>
  <div class="kr">
    <div class="k" onclick="sk('1')">1</div><div class="k" onclick="sk('2')">2</div>
    <div class="k" onclick="sk('3')">3</div><div class="k" onclick="sk('4')">4</div>
    <div class="k" onclick="sk('5')">5</div><div class="k" onclick="sk('6')">6</div>
    <div class="k" onclick="sk('7')">7</div><div class="k" onclick="sk('8')">8</div>
    <div class="k" onclick="sk('9')">9</div><div class="k" onclick="sk('0')">0</div>
    <div class="k w2" onclick="sk('backspace')">⌫ Sil</div>
  </div>
  <div class="kb-lbl">Harfler</div>
  <div class="kr">
    <div class="k w2" onclick="sk('tab')">⇥ Tab</div>
    <div class="k" onclick="sk('q')">Q</div><div class="k" onclick="sk('w')">W</div>
    <div class="k" onclick="sk('e')">E</div><div class="k" onclick="sk('r')">R</div>
    <div class="k" onclick="sk('t')">T</div><div class="k" onclick="sk('y')">Y</div>
    <div class="k" onclick="sk('u')">U</div><div class="k" onclick="sk('i')">I</div>
    <div class="k" onclick="sk('o')">O</div><div class="k" onclick="sk('p')">P</div>
  </div>
  <div class="kr">
    <div class="k" onclick="sk('a')">A</div><div class="k" onclick="sk('s')">S</div>
    <div class="k" onclick="sk('d')">D</div><div class="k" onclick="sk('f')">F</div>
    <div class="k" onclick="sk('g')">G</div><div class="k" onclick="sk('h')">H</div>
    <div class="k" onclick="sk('j')">J</div><div class="k" onclick="sk('k')">K</div>
    <div class="k" onclick="sk('l')">L</div>
    <div class="k w3" onclick="sk('enter')">↵ Enter</div>
  </div>
  <div class="kr">
    <div class="k w2" id="k-sh" onclick="tsh()">⇧ Shift</div>
    <div class="k" onclick="sk('z')">Z</div><div class="k" onclick="sk('x')">X</div>
    <div class="k" onclick="sk('c')">C</div><div class="k" onclick="sk('v')">V</div>
    <div class="k" onclick="sk('b')">B</div><div class="k" onclick="sk('n')">N</div>
    <div class="k" onclick="sk('m')">M</div>
    <div class="k w2" id="k-ct" onclick="tct()">Ctrl</div>
  </div>
  <div class="kr">
    <div class="k" onclick="sk('win')">⊞</div>
    <div class="k" onclick="sk('alt')">Alt</div>
    <div class="k sp" onclick="sk('space')">BOŞLUK</div>
    <div class="k" onclick="sk('up')">↑</div><div class="k" onclick="sk('down')">↓</div>
    <div class="k" onclick="sk('left')">←</div><div class="k" onclick="sk('right')">→</div>
  </div>
  <div class="kb-lbl">Kısayollar</div>
  <div class="shorts">
    <div class="sk" onclick="hk(['ctrl','c'])">Ctrl+C<br>Kopyala</div>
    <div class="sk" onclick="hk(['ctrl','v'])">Ctrl+V<br>Yapıştır</div>
    <div class="sk" onclick="hk(['ctrl','z'])">Ctrl+Z<br>Geri Al</div>
    <div class="sk" onclick="hk(['ctrl','a'])">Ctrl+A<br>Hepsini Seç</div>
    <div class="sk" onclick="hk(['alt','tab'])">Alt+Tab<br>Pencere</div>
    <div class="sk" onclick="hk(['win','d'])">Win+D<br>Masaüstü</div>
    <div class="sk" onclick="hk(['ctrl','w'])">Ctrl+W<br>Kapat</div>
    <div class="sk" onclick="hk(['ctrl','shift','t'])">C+S+T<br>Geri Aç</div>
    <div class="sk" onclick="hk(['win','l'])">Win+L<br>Kilitle</div>
  </div>
</div>

</main>

<!-- Install Guide Modal -->
<div id="install-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;align-items:flex-end;justify-content:center;padding-bottom:var(--safe-bot)">
  <div style="background:var(--card);border-radius:20px 20px 0 0;padding:24px;width:100%;max-width:420px;border:1px solid var(--border)">
    <div id="modal-title" style="font-weight:800;font-size:16px;color:var(--purple);margin-bottom:12px">📲 Uygulamayı Kur</div>
    <div id="modal-content"></div>
    <button onclick="document.getElementById('install-modal').style.display='none'" 
      style="margin-top:16px;width:100%;padding:13px;background:var(--accent);border:none;border-radius:12px;color:#fff;font-weight:800;font-size:14px;cursor:pointer">
      Anladım!
    </button>
  </div>
</div>

<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
/* ── PWA SERVICE WORKER ──────────────────────────────────────── */
if('serviceWorker' in navigator){
  navigator.serviceWorker.register('/sw.js').catch(()=>{});
}

/* ── PWA INSTALL ─────────────────────────────────────────────── */
let deferredPrompt = null;
const isIOS = /iphone|ipad|ipod/.test(navigator.userAgent.toLowerCase());
const isStandalone = navigator.standalone === true || window.matchMedia('(display-mode:standalone)').matches;
const isDismissed = localStorage.getItem('irle-install-dismissed') === 'true';

// Listen for native install prompt (only fires on secure contexts like localhost/HTTPS)
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); deferredPrompt = e;
  if (!isStandalone && !isDismissed) {
    document.getElementById('install-text').innerHTML = "📲 <strong>Uygulamayı</strong> ana ekrana ekle!";
    document.getElementById('install-btn').textContent = "Yükle";
    document.getElementById('install-banner').classList.add('show');
  }
});

// Click event for the install/manual guide button in the banner
document.getElementById('install-btn').addEventListener('click', () => {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => { deferredPrompt = null; closeBanner(); });
  } else {
    showInstallGuide();
  }
});

window.addEventListener('appinstalled', () => closeBanner());

function closeBanner() {
  document.getElementById('install-banner').classList.remove('show');
  localStorage.setItem('irle-install-dismissed', 'true');
}

// Show manual installation options if it's NOT standalone and not dismissed
if (!isStandalone) {
  // Show the header hint button for both iOS and Android if not running standalone
  const hintBtn = document.getElementById('install-hint');
  if (hintBtn) hintBtn.classList.add('show');
  
  // Show manual banner if native prompt doesn't fire after 1.5 seconds and not dismissed
  setTimeout(() => {
    if (!deferredPrompt && !isDismissed) {
      const banner = document.getElementById('install-banner');
      const textEl = document.getElementById('install-text');
      const btnEl = document.getElementById('install-btn');
      
      if (isIOS) {
        textEl.innerHTML = "📲 <strong>IRLE'yi</strong> Safari üzerinden ana ekrana ekleyin!";
      } else {
        textEl.innerHTML = "📲 Tarayıcı menüsünden (⋮) <strong>'Ana Ekrana Ekle'</strong> seçin!";
      }
      btnEl.textContent = "Nasıl?";
      banner.classList.add('show');
    }
  }, 1500);
}

function showInstallGuide() {
  const modal = document.getElementById('install-modal');
  const title = document.getElementById('modal-title');
  const content = document.getElementById('modal-content');
  
  if (isIOS) {
    title.innerHTML = "📲 Ana Ekrana Ekle (iOS)";
    content.innerHTML = `
      <ol style="color:var(--text);font-size:13px;line-height:2.2;padding-left:20px">
        <li>Safari tarayıcısında en alttaki <strong style="color:var(--accent)">Paylaş</strong> simgesine ( ⎋ veya □↑ ) dokunun.</li>
        <li>Açılan menüyü aşağı kaydırıp <strong style="color:var(--accent)">Ana Ekrana Ekle</strong> seçeneğini bulun ve seçin.</li>
        <li>Gelen ekranda sağ üstteki <strong style="color:var(--green)">Ekle</strong> butonuna tıklayın.</li>
        <li>Artık uygulamayı ana ekranınızdaki simgeden tam ekran başlatabilirsiniz! ✓</li>
      </ol>
    `;
  } else {
    title.innerHTML = "📲 Ana Ekrana Ekle (Android / Chrome)";
    content.innerHTML = `
      <ol style="color:var(--text);font-size:13px;line-height:2.2;padding-left:20px">
        <li>Sağ üst köşedeki üç nokta <strong style="color:var(--accent)">⋮</strong> menü simgesine dokunun.</li>
        <li>Menüden <strong style="color:var(--accent)">Ana Ekrana Ekle</strong> veya <strong style="color:var(--accent)">Uygulamayı Yükle</strong> seçeneğine tıklayın.</li>
        <li>Açılan onay penceresinde <strong style="color:var(--green)">Ekle</strong> / <strong style="color:var(--green)">Yükle</strong> butonuna basıp onaylayın.</li>
        <li>Telefon ana ekranınızdaki <strong>IRLE</strong> simgesiyle uygulamayı tam ekran başlatın! ✓</li>
      </ol>
    `;
  }
  modal.style.display = 'flex';
}

/* ── SOCKET ──────────────────────────────────────────────────── */
const socket = io({reconnectionDelay:800,reconnectionAttempts:Infinity});
socket.on('connect',    ()=>{ dot('on');  st('Bağlandı ✓'); });
socket.on('disconnect', ()=>{ dot('off'); st('Yeniden bağlanıyor...'); });
function dot(s){ document.getElementById('dot').className='dot'+(s==='on'?' on':''); }
function st(t){  document.getElementById('st').textContent=t; }

/* ── TABS ────────────────────────────────────────────────────── */
let cur='Mouse';
function go(t){
  document.getElementById('p'+cur).classList.remove('on');
  document.getElementById('t-'+cur).classList.remove('on');
  cur=t;
  document.getElementById('p'+t).classList.add('on');
  document.getElementById('t-'+t).classList.add('on');
}

/* ── RIPPLE ──────────────────────────────────────────────────── */
document.addEventListener('touchstart',e=>{
  const d=document.createElement('div'); d.className='rip';
  const t=e.touches[0];
  d.style.left=t.clientX+'px'; d.style.top=t.clientY+'px';
  document.body.appendChild(d); setTimeout(()=>d.remove(),420);
},{passive:true});

/* ── MOUSE TOUCHPAD ──────────────────────────────────────────── */
const tp=document.getElementById('tp');
const tpc=document.getElementById('tpc');
const tpr=document.getElementById('tpr');
let lx=null,ly=null,lastTap=0,sens_val=4;
let twoFinger=false,frameReq=null,pdx=0,pdy=0;

function flushMove(){
  frameReq=null;
  if(pdx||pdy){ socket.emit('mm',{dx:pdx,dy:pdy}); pdx=0;pdy=0; }
}

tp.addEventListener('touchstart',e=>{
  e.preventDefault();
  twoFinger=e.touches.length>=2;
  if(twoFinger){ lx=e.touches[0].clientX; ly=e.touches[0].clientY; return; }
  const t=e.touches[0];
  lx=t.clientX; ly=t.clientY;
  const r=tp.getBoundingClientRect();
  const cx=t.clientX-r.left, cy=t.clientY-r.top;
  tpc.style.left=cx+'px'; tpc.style.top=cy+'px';
  tpr.style.left=cx+'px'; tpr.style.top=cy+'px';
  tpc.classList.add('show'); tpr.classList.add('show');
  const now=Date.now();
  if(now-lastTap<280){ socket.emit('mc',{b:'double'}); }
  lastTap=now;
  setTimeout(()=>tpr.classList.remove('show'),250);
},{passive:false});

tp.addEventListener('touchmove',e=>{
  e.preventDefault();
  twoFinger=e.touches.length>=2;
  if(twoFinger){
    const t=e.touches[0];
    if(lx!==null){ const dy=t.clientY-ly; if(Math.abs(dy)>1.5) socket.emit('scroll',{dir:dy<0?'up':'down',amt:Math.abs(dy)*.5}); }
    lx=e.touches[0].clientX; ly=e.touches[0].clientY; return;
  }
  const t=e.touches[0];
  const r=tp.getBoundingClientRect();
  tpc.style.left=(t.clientX-r.left)+'px'; tpc.style.top=(t.clientY-r.top)+'px';
  if(lx!==null){ pdx+=(t.clientX-lx)*sens_val*.7; pdy+=(t.clientY-ly)*sens_val*.7; if(!frameReq)frameReq=requestAnimationFrame(flushMove); }
  lx=t.clientX; ly=t.clientY;
},{passive:false});

function tpEnd(){
  lx=null;ly=null;twoFinger=false;
  tpc.classList.remove('show');
  if(frameReq){cancelAnimationFrame(frameReq);frameReq=null;pdx=0;pdy=0;}
}
tp.addEventListener('touchend',tpEnd,{passive:false});
tp.addEventListener('touchcancel',tpEnd,{passive:false});

function mc(b){ socket.emit('mc',{b}); }
function sc(d){ socket.emit('scroll',{dir:d,amt:120}); }

/* ── GAMEPAD ─────────────────────────────────────────────────── */
function btn(b,s){
  socket.emit('gp',{btn:b,state:s});
  const el=document.getElementById('b-'+b);
  if(el) el.classList.toggle('pr',s==='d');
}
function dp(dir,s){
  socket.emit('dp',{dir,state:s});
  const el=document.getElementById('dp-'+dir);
  if(el) el.classList.toggle('pr',s==='d');
}

function stick(padId,thumbId,side){
  const pad=document.getElementById(padId),th=document.getElementById(thumbId);
  let act=false,cx,cy; const R=28;
  pad.addEventListener('touchstart',e=>{e.preventDefault();act=true;const r=pad.getBoundingClientRect();cx=r.left+r.width/2;cy=r.top+r.height/2;},{passive:false});
  pad.addEventListener('touchmove',e=>{
    e.preventDefault();if(!act)return;
    const t=e.touches[0];let dx=t.clientX-cx,dy=t.clientY-cy;
    const d=Math.sqrt(dx*dx+dy*dy);if(d>R){dx=dx/d*R;dy=dy/d*R;}
    th.style.transform=`translate(calc(-50% + ${dx}px),calc(-50% + ${dy}px))`;
    socket.emit('stick',{side,x:dx/R,y:dy/R});
  },{passive:false});
  const rst=()=>{act=false;th.style.transform='translate(-50%,-50%)';socket.emit('stick',{side,x:0,y:0});};
  pad.addEventListener('touchend',rst);pad.addEventListener('touchcancel',rst);
}
stick('sl','tl','left'); stick('sr','tr','right');

/* ── KEYBOARD ────────────────────────────────────────────────── */
let sh=false,ct=false;
function tsh(){sh=!sh;document.getElementById('k-sh').classList.toggle('hi',sh);}
function tct(){ct=!ct;document.getElementById('k-ct').classList.toggle('hi',ct);}
function sk(key){
  const m=[];
  if(sh){m.push('shift');sh=false;document.getElementById('k-sh').classList.remove('hi');}
  if(ct){m.push('ctrl'); ct=false;document.getElementById('k-ct').classList.remove('hi');}
  socket.emit('kp',{key,mods:m});
}
function hk(keys){ socket.emit('hk',{keys}); }
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Flask App
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "irle-pwa-2025"
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
               logger=False, engineio_logger=False)

_stick_l = (0.0, 0.0)
_stick_r = (0.0, 0.0)
_running  = True

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/manifest.json")
def manifest():
    return Response(json.dumps(MANIFEST, ensure_ascii=False),
                    mimetype="application/manifest+json")

@app.route("/sw.js")
def sw():
    return Response(SERVICE_WORKER_JS, mimetype="application/javascript")

@app.route("/icon-192.png")
def icon192():
    return Response(ICON_192, mimetype="image/png")

@app.route("/icon-512.png")
def icon512():
    return Response(ICON_512, mimetype="image/png")

@app.route("/qr.png")
def qr_img():
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=7, border=3)
    qr.add_data(BASE_URL); qr.make(fit=True)
    img = qr.make_image(fill_color="#6366f1", back_color="#0f1117").get_image()
    buf = io.BytesIO(); img.save(buf,"PNG"); buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/info")
def info(): return jsonify({"url": BASE_URL, "port": PORT})

# ── SocketIO ─────────────────────────────────────────────────────────────────
@sio.on("connect")    
def on_connect(): logger.info("📱  Bağlandı")

@sio.on("disconnect") 
def on_disconnect(): logger.info("📱  Bağlantı kesildi")

@sio.on("mm")
def on_mm(data):
    try:
        dx,dy=float(data.get("dx",0)),float(data.get("dy",0))
        if not(dx or dy): return
        x,y=pyautogui.position(); sw,sh=pyautogui.size()
        pyautogui.moveTo(max(0,min(sw-1,int(x+dx))),max(0,min(sh-1,int(y+dy))),_pause=False)
    except: pass

@sio.on("mc")
def on_mc(data):
    try:
        b=data.get("b","left")
        if   b=="left":   pyautogui.click(button="left")
        elif b=="right":  pyautogui.click(button="right")
        elif b=="middle": pyautogui.click(button="middle")
        elif b=="double": pyautogui.doubleClick()
    except: pass

@sio.on("scroll")
def on_scroll(data):
    try:
        d=data.get("dir","down"); amt=float(data.get("amt",3))
        c=max(1,int(amt/30))
        pyautogui.scroll(c if d=="up" else -c)
    except: pass

GP_MAP={"a":"enter","b":"escape","x":"x","y":"y",
        "lb":["shift","tab"],"rb":"tab","lt":"left","rt":"right",
        "back":"backspace","start":"escape","home":"win"}

@sio.on("gp")
def on_gp(data):
    try:
        b=data.get("btn",""); s=data.get("state","c"); k=GP_MAP.get(b)
        if k is None: return
        if isinstance(k,list):
            if s in("d","c"): pyautogui.hotkey(*k)
        else:
            if s=="d": pyautogui.keyDown(k)
            elif s=="u": pyautogui.keyUp(k)
            elif s=="c": pyautogui.press(k)
    except: pass

@sio.on("dp")
def on_dp(data):
    try:
        d={"up":"up","down":"down","left":"left","right":"right"}.get(data.get("dir",""))
        s=data.get("state","d")
        if not d: return
        if s=="d": pyautogui.keyDown(d)
        elif s=="u": pyautogui.keyUp(d)
    except: pass

@sio.on("stick")
def on_stick(data):
    global _stick_l,_stick_r
    side=data.get("side","left")
    x,y=float(data.get("x",0)),float(data.get("y",0))
    if side=="left": _stick_l=(x,y)
    else:            _stick_r=(x,y)

@sio.on("kp")
def on_kp(data):
    try:
        k=data.get("key",""); m=data.get("mods",[])
        if m: pyautogui.hotkey(*m,k)
        else: pyautogui.press(k)
    except: pass

@sio.on("hk")
def on_hk(data):
    try:
        keys=data.get("keys",[])
        if keys: pyautogui.hotkey(*keys)
    except: pass

@sio.on("toggle_hand_mode")
def on_toggle_hand_mode(data):
    try:
        active = data.get("active", True)
        logger.info(f"📱  El Modu (Hand Mode): {active}")
    except: pass


# ── Stick loop ───────────────────────────────────────────────────────────────
def stick_loop():
    DEAD,SPEED=0.12,9
    while _running:
        lx,ly=_stick_l; rx,ry=_stick_r
        try:
            if abs(lx)>DEAD or abs(ly)>DEAD:
                x,y=pyautogui.position(); sw,sh=pyautogui.size()
                pyautogui.moveTo(max(0,min(sw-1,int(x+lx*SPEED))),
                                  max(0,min(sh-1,int(y+ly*SPEED))),_pause=False)
            if abs(ry)>DEAD: pyautogui.scroll(int(-ry*3))
        except: pass
        time.sleep(0.016)

# ─────────────────────────────────────────────────────────────────────────────
# QR Popup (tkinter)
# ─────────────────────────────────────────────────────────────────────────────
def show_qr_window():
    try:
        import tkinter as tk
        from PIL import Image as PILImg, ImageTk

        root=tk.Tk()
        root.title("IRLE Kontrolcü — Kur veya Tara")
        root.configure(bg="#0f1117")
        root.resizable(False,False)

        tk.Label(root,text="📱  IRLE Telefon Kontrolcü PWA",
                 bg="#0f1117",fg="#a78bfa",font=("Segoe UI",12,"bold")).pack(pady=(14,2))
        tk.Label(root,text=BASE_URL,bg="#0f1117",fg="#34d399",
                 font=("Consolas",11)).pack(pady=(0,10))

        # QR
        qr=qrcode.QRCode(version=1,error_correction=qrcode.constants.ERROR_CORRECT_M,
                          box_size=7,border=3)
        qr.add_data(BASE_URL); qr.make(fit=True)
        qr_img=qr.make_image(fill_color="#6366f1",back_color="#0f1117").get_image()
        photo=ImageTk.PhotoImage(qr_img.resize((240,240),PILImg.NEAREST))
        tk.Label(root,image=photo,bg="#0f1117").pack(padx=20)

        info_text=(
            "── Kurulum ──────────────────────────────\n"
            "Android Chrome  →  ⋮ → Uygulamayı Yükle\n"
            "iOS Safari      →  Paylaş □↑ → Ana Ekrana Ekle\n"
            "─────────────────────────────────────────\n"
            "Aynı WiFi ağında olduğundan emin ol!"
        )
        tk.Label(root,text=info_text,bg="#0f1117",fg="#4b5a72",
                 font=("Consolas",8),justify="left").pack(padx=20,pady=(8,4))

        tk.Button(root,text="Kapat  (sunucu arka planda çalışır)",
                  bg="#1c2535",fg="#a78bfa",borderwidth=0,
                  font=("Segoe UI",9),pady=7,
                  command=root.destroy,cursor="hand2").pack(fill="x",padx=16,pady=10)

        root.update_idletasks()
        sw=root.winfo_screenwidth(); sh=root.winfo_screenheight()
        w=root.winfo_width(); h=root.winfo_height()
        root.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")
        root.mainloop()
    except Exception as e:
        logger.warning(f"QR penceresi: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    print(f"""
╔══════════════════════════════════════════════════════╗
║   📱  IRLE Telefon Kontrolcü  —  PWA Edition v2.0   ║
╠══════════════════════════════════════════════════════╣
║   🌐  {BASE_URL:<48} ║
║   📲  Android: Chrome ⋮ → Uygulamayı Yükle          ║
║   📲  iOS: Paylaş → Ana Ekrana Ekle                  ║
║   ⌨️   Durdurmak: Ctrl+C                              ║
╚══════════════════════════════════════════════════════╝
""")
    threading.Thread(target=stick_loop,daemon=True,name="StickLoop").start()
    threading.Thread(
        target=lambda: sio.run(app,host="0.0.0.0",port=PORT,
                               allow_unsafe_werkzeug=True,use_reloader=False,log_output=False),
        daemon=True,name="FlaskServer"
    ).start()

    show_qr_window()   # tkinter — ana thread

    print(f"\n✓ Sunucu: {BASE_URL}\n  Durdurmak için Ctrl+C\n")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\nKapatılıyor..."); _running=False
