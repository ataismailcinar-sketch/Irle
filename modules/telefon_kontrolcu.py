"""
=============================================================================
TELEFON KONTROLCÜ MODÜLÜ — Mobil Gamepad Sunucusu
=============================================================================
Bu modülün sorumlulukları:
    1. Yerel ağda Flask+SocketIO sunucusu başlatmak.
    2. Telefon tarayıcısında Xbox/gamepad + klavye/mouse arayüzü sunmak.
    3. Buton basışlarını pyautogui ile bilgisayara uygulamak.
    4. QR kod ile kolay bağlantı sağlamak.

Kullanım:
    - Irle GUI'sinde "Telefon Kontrolcü" butonuna tıkla
    - QR kodu telefonunla tara
    - Aynı WiFi ağında olduğundan emin ol
=============================================================================
"""

import threading
import logging
import socket
import os
import io
import pyautogui
import qrcode
from PIL import Image
from flask import Flask, render_template_string, send_file
from flask_socketio import SocketIO, emit

import config

logger = logging.getLogger("TelefonKontrolcu")

pyautogui.FAILSAFE = False

# --- Port ayarı ---
KONTROLCU_PORT = getattr(config, "KONTROLCU_PORT", 5555)

# -----------------------------------------------------------------------
# HTML Arayüzü (tek dosya, inline template)
# -----------------------------------------------------------------------
KONTROLCU_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Irle Kontrolcü</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; touch-action: manipulation; }

  :root {
    --bg: #0f1117;
    --panel: #1a1d27;
    --border: #2a2d3e;
    --accent: #6366f1;
    --accent2: #a78bfa;
    --green: #34d399;
    --red: #f87171;
    --yellow: #fbbf24;
    --blue: #60a5fa;
    --text: #e2e8f0;
    --dim: #64748b;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ---- TAB BAR ---- */
  .tabs {
    display: flex;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    padding: 0 8px;
  }
  .tab-btn {
    flex: 1;
    padding: 10px 4px;
    background: none;
    border: none;
    color: var(--dim);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    cursor: pointer;
    transition: color 0.2s;
    text-transform: uppercase;
  }
  .tab-btn.active {
    color: var(--accent2);
    border-bottom: 2px solid var(--accent2);
  }

  /* ---- STATUS BAR ---- */
  .status-bar {
    background: var(--panel);
    padding: 6px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--dim);
    border-bottom: 1px solid var(--border);
  }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); transition: background 0.3s; }
  .status-dot.connected { background: var(--green); box-shadow: 0 0 6px var(--green); }

  /* ---- PANELS ---- */
  .panel { display: none; flex: 1; overflow: hidden; }
  .panel.active { display: flex; flex-direction: column; }

  /* ============================================================
     GAMEPAD PANEL
  ============================================================ */
  #gamepad-panel {
    flex: 1;
    display: none;
    flex-direction: column;
    justify-content: space-between;
    padding: 8px;
    gap: 8px;
  }
  #gamepad-panel.active { display: flex; }

  .gamepad-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  /* DPAD */
  .dpad {
    position: relative;
    width: 120px;
    height: 120px;
    flex-shrink: 0;
  }
  .dpad-btn {
    position: absolute;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    user-select: none;
    transition: background 0.1s, transform 0.1s;
    -webkit-user-select: none;
  }
  .dpad-btn:active, .dpad-btn.pressed { background: var(--accent); transform: scale(0.92); }
  .dpad-up    { top: 0;     left: 40px; width: 40px; height: 40px; }
  .dpad-down  { bottom: 0;  left: 40px; width: 40px; height: 40px; }
  .dpad-left  { top: 40px;  left: 0;   width: 40px; height: 40px; }
  .dpad-right { top: 40px;  right: 0;  width: 40px; height: 40px; }
  .dpad-center { top: 40px; left: 40px; width: 40px; height: 40px; background: var(--border); border-radius: 50%; }

  /* ABXY BUTTONS */
  .abxy {
    position: relative;
    width: 120px;
    height: 120px;
    flex-shrink: 0;
  }
  .abxy-btn {
    position: absolute;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    user-select: none;
    transition: transform 0.1s, filter 0.1s;
    -webkit-user-select: none;
  }
  .abxy-btn:active, .abxy-btn.pressed { transform: scale(0.88); filter: brightness(0.7); }
  .btn-y { top: 0;    left: 40px; background: #f59e0b; color: #000; }
  .btn-b { top: 40px; right: 0;   background: var(--red); color: #fff; }
  .btn-a { bottom: 0; left: 40px; background: var(--green); color: #000; }
  .btn-x { top: 40px; left: 0;    background: var(--blue); color: #fff; }

  /* CENTER BUTTONS */
  .center-btns {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }
  .center-row {
    display: flex;
    gap: 8px;
  }
  .sys-btn {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 20px;
    color: var(--dim);
    font-size: 10px;
    font-weight: 700;
    padding: 5px 12px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: color 0.2s, border-color 0.2s;
  }
  .sys-btn:active { border-color: var(--accent); color: var(--accent2); }

  /* BUMPERS & TRIGGERS */
  .bumper-row {
    display: flex;
    gap: 8px;
  }
  .bumper-btn {
    flex: 1;
    padding: 10px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text);
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    text-align: center;
    transition: background 0.1s;
  }
  .bumper-btn:active, .bumper-btn.pressed { background: var(--accent); }

  /* ANALOG STICK (Touchpad) */
  .sticks-row {
    display: flex;
    gap: 12px;
    justify-content: space-around;
    flex: 1;
    align-items: center;
  }
  .stick-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .stick-label { font-size: 10px; color: var(--dim); }
  .stick-pad {
    width: 110px;
    height: 110px;
    background: var(--panel);
    border: 2px solid var(--border);
    border-radius: 50%;
    position: relative;
    touch-action: none;
  }
  .stick-thumb {
    position: absolute;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #4f46e5, #312e81);
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    transition: none;
    pointer-events: none;
  }

  /* ============================================================
     KEYBOARD PANEL
  ============================================================ */
  #keyboard-panel {
    display: none;
    flex-direction: column;
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    gap: 6px;
  }
  #keyboard-panel.active { display: flex; }

  .kb-row {
    display: flex;
    gap: 5px;
    justify-content: center;
  }
  .key {
    flex: 1;
    min-width: 28px;
    max-width: 50px;
    height: 42px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.1s, transform 0.1s;
    user-select: none;
  }
  .key:active { background: var(--accent); transform: scale(0.92); }
  .key.wide { flex: 2; max-width: 80px; }
  .key.xwide { flex: 3; max-width: 120px; }
  .key.space { flex: 5; max-width: 200px; background: #1e2133; }
  .key.active-key { background: var(--accent2); color: #000; }

  .kb-section-title {
    font-size: 10px;
    font-weight: 700;
    color: var(--dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 4px 2px 0;
  }

  /* ============================================================
     MOUSE PANEL
  ============================================================ */
  #mouse-panel {
    display: none;
    flex-direction: column;
    flex: 1;
    padding: 10px;
    gap: 10px;
  }
  #mouse-panel.active { display: flex; }

  .mouse-touchpad {
    flex: 1;
    background: var(--panel);
    border: 2px solid var(--border);
    border-radius: 16px;
    position: relative;
    min-height: 200px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .mouse-touchpad-hint {
    color: var(--dim);
    font-size: 12px;
    text-align: center;
    line-height: 1.8;
    pointer-events: none;
  }
  .touch-cursor {
    position: absolute;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--accent2);
    opacity: 0;
    transform: translate(-50%, -50%);
    pointer-events: none;
    transition: opacity 0.2s;
  }
  .touch-cursor.visible { opacity: 0.8; }

  .mouse-btns {
    display: flex;
    gap: 10px;
  }
  .mouse-btn {
    flex: 1;
    padding: 16px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
    transition: background 0.15s;
  }
  .mouse-btn:active { background: var(--accent); }

  .scroll-section {
    display: flex;
    gap: 8px;
    justify-content: center;
  }
  .scroll-btn {
    width: 60px;
    height: 50px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text);
    font-size: 22px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.1s;
  }
  .scroll-btn:active { background: var(--accent); }

  /* ============================================================
     TOUCH RIPPLE EFFECT
  ============================================================ */
  @keyframes ripple {
    from { transform: translate(-50%, -50%) scale(0); opacity: 0.6; }
    to   { transform: translate(-50%, -50%) scale(3); opacity: 0; }
  }
  .ripple {
    position: fixed;
    border-radius: 50%;
    width: 30px;
    height: 30px;
    background: rgba(99, 102, 241, 0.4);
    animation: ripple 0.4s ease-out forwards;
    pointer-events: none;
    z-index: 9999;
  }
</style>
</head>
<body>

<!-- STATUS BAR -->
<div class="status-bar">
  <div class="status-dot" id="status-dot"></div>
  <span id="status-text">Bağlanıyor...</span>
  <span style="margin-left:auto;color:var(--accent2);font-weight:700;">⬡ IRLE</span>
</div>

<!-- TABS -->
<div class="tabs">
  <button class="tab-btn active" id="tab-gamepad"  onclick="switchTab('gamepad')">🎮 Gamepad</button>
  <button class="tab-btn"        id="tab-keyboard" onclick="switchTab('keyboard')">⌨️ Klavye</button>
  <button class="tab-btn"        id="tab-mouse"    onclick="switchTab('mouse')">🖱️ Mouse</button>
</div>

<!-- ==================== GAMEPAD PANEL ==================== -->
<div id="gamepad-panel" class="active">

  <!-- BUMPERS -->
  <div class="bumper-row">
    <button class="bumper-btn" id="btn-lb" ontouchstart="gpBtn('lb','down')" ontouchend="gpBtn('lb','up')">LB</button>
    <button class="bumper-btn" id="btn-rb" ontouchstart="gpBtn('rb','down')" ontouchend="gpBtn('rb','up')">RB</button>
  </div>
  <div class="bumper-row">
    <button class="bumper-btn" id="btn-lt" ontouchstart="gpBtn('lt','down')" ontouchend="gpBtn('lt','up')" style="background:#1a2240">LT ◀</button>
    <button class="bumper-btn" id="btn-rt" ontouchstart="gpBtn('rt','down')" ontouchend="gpBtn('rt','up')" style="background:#1a2240">RT ▶</button>
  </div>

  <!-- MAIN ROW: DPAD + CENTER + ABXY -->
  <div class="gamepad-row">
    <!-- D-PAD -->
    <div class="dpad">
      <div class="dpad-btn dpad-up"    id="dp-up"    ontouchstart="dpBtn('up','down')"    ontouchend="dpBtn('up','up')">▲</div>
      <div class="dpad-btn dpad-down"  id="dp-down"  ontouchstart="dpBtn('down','down')"  ontouchend="dpBtn('down','up')">▼</div>
      <div class="dpad-btn dpad-left"  id="dp-left"  ontouchstart="dpBtn('left','down')"  ontouchend="dpBtn('left','up')">◀</div>
      <div class="dpad-btn dpad-right" id="dp-right" ontouchstart="dpBtn('right','down')" ontouchend="dpBtn('right','up')">▶</div>
      <div class="dpad-center"></div>
    </div>

    <!-- CENTER BUTTONS -->
    <div class="center-btns">
      <div class="center-row">
        <button class="sys-btn" onclick="gpClick('back')">⬅ BACK</button>
        <button class="sys-btn" onclick="gpClick('home')">⬡</button>
        <button class="sys-btn" onclick="gpClick('start')">START ▶</button>
      </div>
    </div>

    <!-- ABXY -->
    <div class="abxy">
      <button class="abxy-btn btn-y" id="btn-y" ontouchstart="gpBtn('y','down')" ontouchend="gpBtn('y','up')">Y</button>
      <button class="abxy-btn btn-b" id="btn-b" ontouchstart="gpBtn('b','down')" ontouchend="gpBtn('b','up')">B</button>
      <button class="abxy-btn btn-a" id="btn-a" ontouchstart="gpBtn('a','down')" ontouchend="gpBtn('a','up')">A</button>
      <button class="abxy-btn btn-x" id="btn-x" ontouchstart="gpBtn('x','down')" ontouchend="gpBtn('x','up')">X</button>
    </div>
  </div>

  <!-- ANALOG STICKS -->
  <div class="sticks-row">
    <div class="stick-container">
      <span class="stick-label">SOL</span>
      <div class="stick-pad" id="stick-left" data-side="left">
        <div class="stick-thumb" id="thumb-left"></div>
      </div>
    </div>
    <div class="stick-container">
      <span class="stick-label">SAĞ</span>
      <div class="stick-pad" id="stick-right" data-side="right">
        <div class="stick-thumb" id="thumb-right"></div>
      </div>
    </div>
  </div>
</div>

<!-- ==================== KEYBOARD PANEL ==================== -->
<div id="keyboard-panel">
  <div class="kb-section-title">Fonksiyon Tuşları</div>
  <div class="kb-row">
    <div class="key" onclick="sendKey('escape')">Esc</div>
    <div class="key" onclick="sendKey('f1')">F1</div>
    <div class="key" onclick="sendKey('f2')">F2</div>
    <div class="key" onclick="sendKey('f3')">F3</div>
    <div class="key" onclick="sendKey('f4')">F4</div>
    <div class="key" onclick="sendKey('f5')">F5</div>
    <div class="key" onclick="sendKey('f6')">F6</div>
    <div class="key" onclick="sendKey('f11')">F11</div>
    <div class="key" onclick="sendKey('f12')">F12</div>
  </div>

  <div class="kb-section-title">Sayı Satırı</div>
  <div class="kb-row">
    <div class="key" onclick="sendKey('`')">`</div>
    <div class="key" onclick="sendKey('1')">1</div>
    <div class="key" onclick="sendKey('2')">2</div>
    <div class="key" onclick="sendKey('3')">3</div>
    <div class="key" onclick="sendKey('4')">4</div>
    <div class="key" onclick="sendKey('5')">5</div>
    <div class="key" onclick="sendKey('6')">6</div>
    <div class="key" onclick="sendKey('7')">7</div>
    <div class="key" onclick="sendKey('8')">8</div>
    <div class="key" onclick="sendKey('9')">9</div>
    <div class="key" onclick="sendKey('0')">0</div>
    <div class="key wide" onclick="sendKey('backspace')">⌫</div>
  </div>

  <div class="kb-section-title">Ana Satırlar</div>
  <div class="kb-row">
    <div class="key wide" onclick="sendKey('tab')">Tab</div>
    <div class="key" onclick="sendKey('q')">Q</div>
    <div class="key" onclick="sendKey('w')">W</div>
    <div class="key" onclick="sendKey('e')">E</div>
    <div class="key" onclick="sendKey('r')">R</div>
    <div class="key" onclick="sendKey('t')">T</div>
    <div class="key" onclick="sendKey('y')">Y</div>
    <div class="key" onclick="sendKey('u')">U</div>
    <div class="key" onclick="sendKey('i')">I</div>
    <div class="key" onclick="sendKey('o')">O</div>
    <div class="key" onclick="sendKey('p')">P</div>
  </div>
  <div class="kb-row">
    <div class="key" onclick="sendKey('a')">A</div>
    <div class="key" onclick="sendKey('s')">S</div>
    <div class="key" onclick="sendKey('d')">D</div>
    <div class="key" onclick="sendKey('f')">F</div>
    <div class="key" onclick="sendKey('g')">G</div>
    <div class="key" onclick="sendKey('h')">H</div>
    <div class="key" onclick="sendKey('j')">J</div>
    <div class="key" onclick="sendKey('k')">K</div>
    <div class="key" onclick="sendKey('l')">L</div>
    <div class="key xwide" onclick="sendKey('enter')">Enter ↵</div>
  </div>
  <div class="kb-row">
    <div class="key wide" id="key-shift" onclick="toggleShift()">⇧ Shift</div>
    <div class="key" onclick="sendKey('z')">Z</div>
    <div class="key" onclick="sendKey('x')">X</div>
    <div class="key" onclick="sendKey('c')">C</div>
    <div class="key" onclick="sendKey('v')">V</div>
    <div class="key" onclick="sendKey('b')">B</div>
    <div class="key" onclick="sendKey('n')">N</div>
    <div class="key" onclick="sendKey('m')">M</div>
    <div class="key wide" id="key-ctrl" onclick="toggleCtrl()">Ctrl</div>
  </div>
  <div class="kb-row">
    <div class="key" onclick="sendKey('win')">⊞</div>
    <div class="key" onclick="sendKey('alt')">Alt</div>
    <div class="key space" onclick="sendKey('space')">BOŞLUK</div>
    <div class="key" onclick="sendKey('up')">↑</div>
    <div class="key" onclick="sendKey('down')">↓</div>
    <div class="key" onclick="sendKey('left')">←</div>
    <div class="key" onclick="sendKey('right')">→</div>
  </div>

  <div class="kb-section-title">Kısayollar</div>
  <div class="kb-row">
    <div class="key xwide" onclick="sendCombo(['ctrl','c'])">Ctrl+C Kopyala</div>
    <div class="key xwide" onclick="sendCombo(['ctrl','v'])">Ctrl+V Yapıştır</div>
    <div class="key xwide" onclick="sendCombo(['ctrl','z'])">Ctrl+Z Geri Al</div>
  </div>
  <div class="kb-row">
    <div class="key xwide" onclick="sendCombo(['alt','tab'])">Alt+Tab</div>
    <div class="key xwide" onclick="sendCombo(['ctrl','w'])">Ctrl+W Kapat</div>
    <div class="key xwide" onclick="sendCombo(['win','d'])">Win+D Masaüstü</div>
  </div>
</div>

<!-- ==================== MOUSE PANEL ==================== -->
<div id="mouse-panel">
  <div class="mouse-touchpad" id="mouse-touchpad">
    <div class="touch-cursor" id="touch-cursor"></div>
    <span class="mouse-touchpad-hint">Parmağını kaydır → Fare hareketi<br>Çift dok → Çift tıklama</span>
  </div>
  <div class="mouse-btns">
    <button class="mouse-btn" id="mouse-left-btn" ontouchstart="mouseClick('left')">🖱️ Sol Tık</button>
    <button class="mouse-btn" id="mouse-right-btn" ontouchstart="mouseClick('right')">🖱️ Sağ Tık</button>
  </div>
  <div class="scroll-section">
    <div class="scroll-btn" ontouchstart="scroll('up')">▲</div>
    <div class="scroll-btn" ontouchstart="scroll('down')">▼</div>
    <div class="scroll-btn" ontouchstart="mouseClick('middle')">⬤</div>
  </div>
</div>

<!-- Socket.IO -->
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
const socket = io();
let shiftActive = false;
let ctrlActive = false;
let mouseLastX = null, mouseLastY = null;
let mouseLastTap = 0;
let mouseMoveThrottle = null;

// ---- Connection ----
socket.on('connect', () => {
  document.getElementById('status-dot').classList.add('connected');
  document.getElementById('status-text').textContent = 'Bağlandı ✓';
});
socket.on('disconnect', () => {
  document.getElementById('status-dot').classList.remove('connected');
  document.getElementById('status-text').textContent = 'Bağlantı kesildi...';
});

// ---- TABS ----
function switchTab(tab) {
  ['gamepad', 'keyboard', 'mouse'].forEach(t => {
    document.getElementById(t + '-panel').classList.remove('active');
    document.getElementById('tab-' + t).classList.remove('active');
  });
  document.getElementById(tab + '-panel').classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
}

// ---- RIPPLE EFFECT ----
function ripple(e) {
  const el = document.createElement('div');
  el.className = 'ripple';
  const touch = e.touches ? e.touches[0] : e;
  el.style.left = touch.clientX + 'px';
  el.style.top = touch.clientY + 'px';
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 400);
}
document.addEventListener('touchstart', ripple, {passive: true});

// ---- GAMEPAD ----
function gpBtn(btn, state) {
  socket.emit('gamepad', { btn: btn, state: state });
  if (state === 'down') {
    const el = document.getElementById('btn-' + btn);
    if (el) { el.classList.add('pressed'); }
  } else {
    const el = document.getElementById('btn-' + btn);
    if (el) { el.classList.remove('pressed'); }
  }
}

function gpClick(btn) {
  socket.emit('gamepad', { btn: btn, state: 'click' });
}

function dpBtn(dir, state) {
  socket.emit('dpad', { dir: dir, state: state });
  const el = document.getElementById('dp-' + dir);
  if (el) {
    if (state === 'down') el.classList.add('pressed');
    else el.classList.remove('pressed');
  }
}

// ---- ANALOG STICKS ----
function initStick(padId, thumbId, side) {
  const pad = document.getElementById(padId);
  const thumb = document.getElementById(thumbId);
  let active = false;
  let startX, startY;
  const radius = 33;

  pad.addEventListener('touchstart', e => {
    e.preventDefault();
    active = true;
    const r = pad.getBoundingClientRect();
    startX = r.left + r.width / 2;
    startY = r.top + r.height / 2;
  }, { passive: false });

  pad.addEventListener('touchmove', e => {
    e.preventDefault();
    if (!active) return;
    const t = e.touches[0];
    let dx = t.clientX - startX;
    let dy = t.clientY - startY;
    const dist = Math.sqrt(dx*dx + dy*dy);
    if (dist > radius) { dx = dx/dist*radius; dy = dy/dist*radius; }
    thumb.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
    socket.emit('stick', { side: side, x: dx/radius, y: dy/radius });
  }, { passive: false });

  const reset = () => {
    active = false;
    thumb.style.transform = 'translate(-50%, -50%)';
    socket.emit('stick', { side: side, x: 0, y: 0 });
  };
  pad.addEventListener('touchend', reset);
  pad.addEventListener('touchcancel', reset);
}

initStick('stick-left', 'thumb-left', 'left');
initStick('stick-right', 'thumb-right', 'right');

// ---- KEYBOARD ----
function toggleShift() {
  shiftActive = !shiftActive;
  const el = document.getElementById('key-shift');
  el.classList.toggle('active-key', shiftActive);
  socket.emit('modifier', { key: 'shift', active: shiftActive });
}

function toggleCtrl() {
  ctrlActive = !ctrlActive;
  const el = document.getElementById('key-ctrl');
  el.classList.toggle('active-key', ctrlActive);
  socket.emit('modifier', { key: 'ctrl', active: ctrlActive });
}

function sendKey(key) {
  const modifiers = [];
  if (shiftActive) { modifiers.push('shift'); shiftActive = false; document.getElementById('key-shift').classList.remove('active-key'); }
  if (ctrlActive)  { modifiers.push('ctrl');  ctrlActive = false;  document.getElementById('key-ctrl').classList.remove('active-key'); }
  socket.emit('keypress', { key: key, modifiers: modifiers });
}

function sendCombo(keys) {
  socket.emit('hotkey', { keys: keys });
}

// ---- MOUSE TOUCHPAD ----
const touchpad = document.getElementById('mouse-touchpad');
const touchCursor = document.getElementById('touch-cursor');

touchpad.addEventListener('touchstart', e => {
  e.preventDefault();
  const t = e.touches[0];
  mouseLastX = t.clientX;
  mouseLastY = t.clientY;
  touchCursor.style.left = t.clientX - touchpad.getBoundingClientRect().left + 'px';
  touchCursor.style.top  = t.clientY - touchpad.getBoundingClientRect().top  + 'px';
  touchCursor.classList.add('visible');

  // Double tap detection
  const now = Date.now();
  if (now - mouseLastTap < 300) { socket.emit('mouse_click', { button: 'double' }); }
  mouseLastTap = now;
}, { passive: false });

touchpad.addEventListener('touchmove', e => {
  e.preventDefault();
  const t = e.touches[0];
  const rect = touchpad.getBoundingClientRect();
  touchCursor.style.left = (t.clientX - rect.left) + 'px';
  touchCursor.style.top  = (t.clientY - rect.top) + 'px';

  if (mouseLastX !== null) {
    const dx = t.clientX - mouseLastX;
    const dy = t.clientY - mouseLastY;
    if (!mouseMoveThrottle) {
      mouseMoveThrottle = setTimeout(() => { mouseMoveThrottle = null; }, 16);
      socket.emit('mouse_move', { dx: dx * 2.5, dy: dy * 2.5 });
    }
  }
  mouseLastX = t.clientX;
  mouseLastY = t.clientY;
}, { passive: false });

touchpad.addEventListener('touchend', () => {
  mouseLastX = null; mouseLastY = null;
  touchCursor.classList.remove('visible');
}, { passive: false });

function mouseClick(btn) {
  socket.emit('mouse_click', { button: btn });
}

function scroll(dir) {
  socket.emit('scroll', { direction: dir });
}
</script>
</body>
</html>
"""


def _get_local_ip() -> str:
    """Yerel ağ IP adresini bulur."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class TelefonKontrolcuModulu:
    """
    Telefon gamepad/klavye/mouse kontrolcüsü modülü.
    Flask-SocketIO sunucusu çalıştırır, telefondan komutları alır
    ve pyautogui ile PC'de uygular.
    """

    def __init__(self, event_bus):
        self.bus = event_bus
        self._calisiyor = False
        self._thread = None
        self._ip = _get_local_ip()
        self._port = KONTROLCU_PORT
        self._url = f"http://{self._ip}:{self._port}"
        self._qr_image = None

        # Modifier key durumları
        self._shift = False
        self._ctrl  = False

        # Analog stick hareketi için
        self._stick_l = (0.0, 0.0)
        self._stick_r = (0.0, 0.0)
        self._stick_thread = None

        # Flask uygulaması
        self._app = Flask(__name__)
        self._app.config["SECRET_KEY"] = "irle-kontrolcu-secret"
        self._sio = SocketIO(
            self._app,
            cors_allowed_origins="*",
            async_mode="threading",
            logger=False,
            engineio_logger=False,
        )
        self._register_routes()
        self._register_events()

        # EventBus abonelikleri
        self.bus.subscribe("vision_el_modu_toggle", self._on_vision_el_modu_toggle)

        # QR kodu önceden oluştur
        self._qr_image = self._generate_qr()

    # -----------------------------------------------------------------------
    # Flask rotaları
    # -----------------------------------------------------------------------

    def _register_routes(self):
        app = self._app

        @app.route("/")
        def index():
            return render_template_string(KONTROLCU_HTML)

        @app.route("/qr.png")
        def qr_image():
            img_io = io.BytesIO()
            self._qr_image.save(img_io, "PNG")
            img_io.seek(0)
            return send_file(img_io, mimetype="image/png")

    # -----------------------------------------------------------------------
    # SocketIO event handler'ları
    # -----------------------------------------------------------------------

    def _register_events(self):
        sio = self._sio

        @sio.on("connect")
        def on_connect():
            logger.info(f"Telefon bağlandı: {self._ip}")
            self.bus.publish("bildirim", {"mesaj": "Telefon kontrolcü bağlandı!", "tip": "info"})

        @sio.on("disconnect")
        def on_disconnect():
            logger.info("Telefon bağlantısı kesildi.")

        # Supports both long ('gamepad') and short ('gp') events
        @sio.on("gamepad")
        @sio.on("gp")
        def on_gamepad(data):
            self._handle_gamepad(data)

        # Supports both long ('dpad') and short ('dp') events
        @sio.on("dpad")
        @sio.on("dp")
        def on_dpad(data):
            self._handle_dpad(data)

        @sio.on("stick")
        def on_stick(data):
            self._handle_stick(data)

        # Supports both long ('keypress') and short ('kp') events
        @sio.on("keypress")
        @sio.on("kp")
        def on_keypress(data):
            self._handle_keypress(data)

        # Supports both long ('hotkey') and short ('hk') events
        @sio.on("hotkey")
        @sio.on("hk")
        def on_hotkey(data):
            self._handle_hotkey(data)

        @sio.on("toggle_hand_mode")
        def on_toggle_hand_mode(data):
            try:
                active = data.get("active", True)
                logger.info(f"Telefondan gelen komutla El Modu: {active}")
                self.bus.publish("vision_el_modu_toggle", {"aktif": active})
            except Exception as e:
                logger.error(f"El modu degistirme hatasi: {e}")

        @sio.on("modifier")
        def on_modifier(data):
            key = data.get("key")
            active = data.get("active", False)
            if key == "shift": self._shift = active
            if key == "ctrl":  self._ctrl  = active

        # Supports both long ('mouse_move') and short ('mm') events
        @sio.on("mouse_move")
        @sio.on("mm")
        def on_mouse_move(data):
            try:
                dx = float(data.get("dx", 0))
                dy = float(data.get("dy", 0))
                if not (dx or dy):
                    return
                x, y = pyautogui.position()
                sw, sh = pyautogui.size()
                pyautogui.moveTo(
                    max(0, min(sw - 1, int(x + dx))),
                    max(0, min(sh - 1, int(y + dy))),
                    _pause=False,
                )
            except Exception as e:
                logger.warning(f"Mouse move hatası: {e}")

        # Supports both long ('mouse_click') and short ('mc') events
        @sio.on("mouse_click")
        @sio.on("mc")
        def on_mouse_click(data):
            btn = data.get("button", data.get("b", "left"))
            if btn == "left":
                pyautogui.click(button="left")
            elif btn == "right":
                pyautogui.click(button="right")
            elif btn == "middle":
                pyautogui.click(button="middle")
            elif btn == "double":
                pyautogui.doubleClick()

        @sio.on("scroll")
        def on_scroll(data):
            direction = data.get("direction", data.get("dir", "down"))
            amount = data.get("amount", data.get("amt", 3))
            try:
                amt = float(amount)
                if amt >= 10:
                    c = max(1, int(amt / 30))
                else:
                    c = max(1, int(amt))
            except Exception:
                c = 3
            if direction == "up":
                pyautogui.scroll(c)
            else:
                pyautogui.scroll(-c)

    # -----------------------------------------------------------------------
    # Gamepad handler'ları
    # -----------------------------------------------------------------------

    # Xbox → Klavye eşleşmesi
    GAMEPAD_MAP = {
        "a":     "enter",
        "b":     "escape",
        "x":     "x",
        "y":     "y",
        "lb":    ["shift", "tab"],   # LB → Shift+Tab (önceki element)
        "rb":    "tab",              # RB → Tab (sonraki element)
        "lt":    "left",             # Sol ok
        "rt":    "right",            # Sağ ok
        "back":  "backspace",
        "start": "escape",
        "home":  "win",
    }

    def _handle_gamepad(self, data):
        btn   = data.get("btn", "")
        state = data.get("state", "click")
        mapping = self.GAMEPAD_MAP.get(btn)
        if mapping is None:
            return

        try:
            if isinstance(mapping, list):
                if state in ("down", "click"):
                    pyautogui.hotkey(*mapping)
            else:
                if state == "down":
                    pyautogui.keyDown(mapping)
                elif state == "up":
                    pyautogui.keyUp(mapping)
                elif state == "click":
                    pyautogui.press(mapping)
        except Exception as e:
            logger.warning(f"Gamepad tuş hatası: {e}")

    DPAD_MAP = {
        "up":    "up",
        "down":  "down",
        "left":  "left",
        "right": "right",
    }

    def _handle_dpad(self, data):
        direction = data.get("dir", "")
        state     = data.get("state", "down")
        key = self.DPAD_MAP.get(direction)
        if not key:
            return
        try:
            if state == "down":
                pyautogui.keyDown(key)
            else:
                pyautogui.keyUp(key)
        except Exception as e:
            logger.warning(f"DPad tuş hatası: {e}")

    def _handle_stick(self, data):
        side = data.get("side", "left")
        x = data.get("x", 0.0)
        y = data.get("y", 0.0)
        if side == "left":
            self._stick_l = (x, y)
        else:
            self._stick_r = (x, y)

    # -----------------------------------------------------------------------
    # Klavye handler'ları
    # -----------------------------------------------------------------------

    def _handle_keypress(self, data):
        key       = data.get("key", "")
        modifiers = data.get("modifiers", data.get("mods", []))
        try:
            if modifiers:
                pyautogui.hotkey(*modifiers, key)
            else:
                pyautogui.press(key)
        except Exception as e:
            logger.warning(f"Klavye tuş hatası ({key}): {e}")

    def _handle_hotkey(self, data):
        keys = data.get("keys", [])
        try:
            if keys:
                pyautogui.hotkey(*keys)
        except Exception as e:
            logger.warning(f"Hotkey hatası ({keys}): {e}")

    # -----------------------------------------------------------------------
    # Analog stick sürekli hareket döngüsü
    # -----------------------------------------------------------------------

    def _stick_loop(self):
        """Analog stick girişini fare hareketine çevirir."""
        import time
        DEAD_ZONE = 0.15
        SPEED = 8

        while self._calisiyor:
            lx, ly = self._stick_l
            rx, ry = self._stick_r

            # Sol stick → Fare hareketi
            if abs(lx) > DEAD_ZONE or abs(ly) > DEAD_ZONE:
                x, y = pyautogui.position()
                dx = lx * SPEED
                dy = ly * SPEED
                pyautogui.moveTo(max(0, x + dx), max(0, y + dy), _pause=False)

            # Sağ stick → Scroll
            if abs(ry) > DEAD_ZONE:
                scroll_val = int(-ry * 3)
                if scroll_val != 0:
                    pyautogui.scroll(scroll_val)

            time.sleep(0.016)  # ~60Hz

    # -----------------------------------------------------------------------
    # QR Kod
    # -----------------------------------------------------------------------

    def _generate_qr(self) -> Image.Image:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(self._url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#6366f1", back_color="#0f1117")
        return img.get_image()

    def get_qr_bytes(self) -> bytes:
        """GUI'de göstermek için QR kodu PNG bayt dizisi olarak döner."""
        buf = io.BytesIO()
        self._qr_image.save(buf, "PNG")
        return buf.getvalue()

    def get_url(self) -> str:
        return self._url

    # -----------------------------------------------------------------------
    # Modül yaşam döngüsü
    # -----------------------------------------------------------------------

    def baslat(self) -> None:
        self._calisiyor = True

        # Stick döngüsü
        self._stick_thread = threading.Thread(
            target=self._stick_loop,
            name="StickLoopThread",
            daemon=True,
        )
        self._stick_thread.start()

        # Flask sunucusu
        self._thread = threading.Thread(
            target=self._run_server,
            name="TelefonKontrolcuThread",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Telefon Kontrolcü başlatıldı → {self._url}")

    def _run_server(self):
        try:
            self._sio.run(
                self._app,
                host="0.0.0.0",
                port=self._port,
                allow_unsafe_werkzeug=True,
                use_reloader=False,
                log_output=False,
            )
        except Exception as e:
            logger.error(f"Flask sunucu hatası: {e}")

    def durdur(self) -> None:
        self._calisiyor = False
        logger.info("Telefon Kontrolcü durduruldu.")

    def _on_vision_el_modu_toggle(self, mesaj: dict):
        try:
            data = mesaj.get("data", {})
            aktif = data.get("aktif", True)
            self._sio.emit("hand_mode_changed", {"active": aktif})
            logger.info(f"El modu değişikliği soketle telefona bildirildi: {aktif}")
        except Exception as e:
            logger.error(f"El modu soket yayinlama hatasi: {e}")
