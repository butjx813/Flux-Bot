"""
ui.py — Interface web local (Flask) — Terminal de Trading
"""

from flask import Flask, render_template_string, jsonify, request
import json
import threading
import time
import os
import sys

# Adiciona diretório atual ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_capture import DataCapture
from market_analysis import MotorAnalise
from decision_engine import GeradorDecisao
from logger import registrar_decisao, obter_historico, calcular_taxa_acerto, calcular_ajuste_pesos

app = Flask(__name__)

# ─── Estado global ───
_capture = DataCapture(modo="simulacao")
_motores_analise: dict = {}
_gerador_decisao = GeradorDecisao()
_cache_resultados: dict = {}
_cache_lock = threading.Lock()
_ativos_ativos = set()

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FluxBot — Análise de Microestrutura B3</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Syne:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #080c10;
    --bg2: #0d1117;
    --bg3: #111820;
    --border: #1e2d3d;
    --accent: #00d4ff;
    --accent2: #ff6b35;
    --green: #00ff9d;
    --red: #ff3d5a;
    --yellow: #ffd60a;
    --text: #c8d8e8;
    --text2: #5a7a9a;
    --glow: 0 0 20px rgba(0,212,255,0.15);
    --glow-green: 0 0 20px rgba(0,255,157,0.2);
    --glow-red: 0 0 20px rgba(255,61,90,0.2);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Mono', monospace;
    font-size: 13px;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* Background grid */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  .app { position: relative; z-index: 1; display: flex; flex-direction: column; height: 100vh; }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 24px;
    background: linear-gradient(90deg, rgba(0,212,255,0.05), transparent);
    border-bottom: 1px solid var(--border);
  }
  .logo {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 20px;
    letter-spacing: 0.08em;
    color: var(--accent);
    text-shadow: 0 0 30px rgba(0,212,255,0.5);
  }
  .logo span { color: var(--text2); font-weight: 400; font-size: 12px; margin-left: 10px; }
  .status-bar { display: flex; gap: 20px; align-items: center; }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 10px var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .status-text { color: var(--text2); font-size: 11px; }
  .clock { color: var(--accent); font-size: 12px; font-weight: 700; letter-spacing: 2px; }
  .modo-badge {
    background: rgba(0,212,255,0.1);
    border: 1px solid rgba(0,212,255,0.3);
    color: var(--accent);
    padding: 3px 10px;
    border-radius: 3px;
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  /* ── Main layout ── */
  .main { display: flex; flex: 1; overflow: hidden; }

  /* ── Left panel ── */
  .left-panel {
    width: 300px;
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    flex-shrink: 0;
  }

  .search-area { padding: 16px; border-bottom: 1px solid var(--border); }
  .search-label { color: var(--text2); font-size: 10px; letter-spacing: 2px; margin-bottom: 8px; }
  .search-wrap { position: relative; }
  .search-input {
    width: 100%;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 14px;
    font-family: 'Space Mono', monospace;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .search-input:focus {
    border-color: var(--accent);
    box-shadow: var(--glow);
  }
  .search-input::placeholder { color: var(--text2); font-size: 11px; }
  .search-btn {
    width: 100%;
    margin-top: 8px;
    background: linear-gradient(90deg, rgba(0,212,255,0.15), rgba(0,212,255,0.05));
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 9px;
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    letter-spacing: 2px;
    cursor: pointer;
    transition: all 0.2s;
  }
  .search-btn:hover {
    background: rgba(0,212,255,0.25);
    box-shadow: var(--glow);
  }

  /* Ativo rápido */
  .quick-ativos { padding: 12px 16px; border-bottom: 1px solid var(--border); }
  .section-label { color: var(--text2); font-size: 10px; letter-spacing: 2px; margin-bottom: 8px; text-transform: uppercase; }
  .quick-grid { display: flex; flex-wrap: wrap; gap: 6px; }
  .quick-btn {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text2);
    padding: 5px 10px;
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.15s;
    letter-spacing: 1px;
  }
  .quick-btn:hover, .quick-btn.ativo {
    background: rgba(0,212,255,0.1);
    border-color: var(--accent);
    color: var(--accent);
  }

  /* Métricas rápidas */
  .metrics-panel { padding: 12px 16px; flex: 1; overflow-y: auto; }
  .metric-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(30,45,61,0.5); }
  .metric-label { color: var(--text2); font-size: 10px; letter-spacing: 1px; }
  .metric-val { font-size: 11px; font-weight: 700; }
  .metric-val.green { color: var(--green); }
  .metric-val.red { color: var(--red); }
  .metric-val.yellow { color: var(--yellow); }
  .metric-val.accent { color: var(--accent); }

  /* ── Center panel ── */
  .center-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  .chart-area {
    height: 200px;
    border-bottom: 1px solid var(--border);
    position: relative;
    padding: 8px;
  }
  .chart-area canvas { width: 100% !important; height: 100% !important; }

  .ticker-info {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(13,17,23,0.8);
  }
  .ticker-name {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 24px;
    color: var(--accent);
    letter-spacing: 2px;
  }
  .ticker-price { font-size: 20px; font-weight: 700; }
  .ticker-var { font-size: 13px; font-weight: 700; }
  .ticker-var.pos { color: var(--green); }
  .ticker-var.neg { color: var(--red); }

  /* Book / Tape tabs */
  .tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }
  .tab {
    padding: 8px 20px;
    font-size: 10px;
    letter-spacing: 2px;
    color: var(--text2);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    text-transform: uppercase;
  }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  .tab-content { flex: 1; overflow-y: auto; padding: 0; display: none; }
  .tab-content.active { display: block; }

  /* Book de ofertas */
  .book-table { width: 100%; border-collapse: collapse; }
  .book-table th {
    font-size: 9px;
    letter-spacing: 2px;
    color: var(--text2);
    padding: 6px 12px;
    text-align: right;
    border-bottom: 1px solid var(--border);
    position: sticky; top: 0;
    background: var(--bg2);
    text-transform: uppercase;
  }
  .book-table th:first-child { text-align: left; }
  .book-table td { padding: 4px 12px; text-align: right; font-size: 12px; }
  .book-table td:first-child { text-align: left; }
  .book-row-c { position: relative; }
  .book-row-c td:first-child { color: var(--green); }
  .book-row-v td:first-child { color: var(--red); }
  .book-bar {
    position: absolute; left: 0; top: 0; bottom: 0;
    opacity: 0.08;
  }
  .book-bar.c { background: var(--green); }
  .book-bar.v { background: var(--red); }

  /* Tape */
  .tape-row { display: flex; justify-content: space-between; padding: 4px 12px; font-size: 11px; border-bottom: 1px solid rgba(30,45,61,0.3); }
  .tape-row.c .tape-preco { color: var(--green); }
  .tape-row.v .tape-preco { color: var(--red); }
  .tape-qtd { color: var(--text2); }
  .tape-hora { color: var(--text2); font-size: 10px; }

  /* ── Right panel ── */
  .right-panel {
    width: 340px;
    border-left: 1px solid var(--border);
    background: var(--bg2);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    flex-shrink: 0;
  }

  .decision-header {
    padding: 14px 18px 10px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(135deg, rgba(0,212,255,0.05), transparent);
  }
  .decision-title {
    font-family: 'Syne', sans-serif;
    font-size: 11px;
    letter-spacing: 3px;
    color: var(--text2);
    text-transform: uppercase;
    margin-bottom: 4px;
  }

  /* Probabilidade bars */
  .prob-section { padding: 14px 18px; border-bottom: 1px solid var(--border); }
  .prob-row { margin-bottom: 12px; }
  .prob-header { display: flex; justify-content: space-between; margin-bottom: 5px; }
  .prob-label { font-size: 10px; letter-spacing: 2px; text-transform: uppercase; }
  .prob-pct { font-size: 16px; font-weight: 700; }
  .prob-bar-bg { height: 6px; background: var(--bg3); border-radius: 1px; overflow: hidden; }
  .prob-bar-fill { height: 100%; border-radius: 1px; transition: width 0.5s ease; }
  .prob-row.compra .prob-label { color: var(--green); }
  .prob-row.compra .prob-pct { color: var(--green); }
  .prob-row.compra .prob-bar-fill { background: var(--green); box-shadow: 0 0 8px rgba(0,255,157,0.4); }
  .prob-row.venda .prob-label { color: var(--red); }
  .prob-row.venda .prob-pct { color: var(--red); }
  .prob-row.venda .prob-bar-fill { background: var(--red); box-shadow: 0 0 8px rgba(255,61,90,0.4); }
  .prob-row.neutro .prob-label { color: var(--yellow); }
  .prob-row.neutro .prob-pct { color: var(--yellow); }
  .prob-row.neutro .prob-bar-fill { background: var(--yellow); }

  /* Recomendação */
  .rec-section {
    padding: 16px 18px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .rec-badge {
    padding: 10px 18px;
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 18px;
    letter-spacing: 3px;
    border: 2px solid;
    transition: all 0.3s;
  }
  .rec-badge.COMPRA { color: var(--green); border-color: var(--green); background: rgba(0,255,157,0.07); box-shadow: var(--glow-green); }
  .rec-badge.VENDA  { color: var(--red);   border-color: var(--red);   background: rgba(255,61,90,0.07);  box-shadow: var(--glow-red); }
  .rec-badge.NEUTRO { color: var(--yellow);border-color: var(--yellow);background: rgba(255,214,10,0.07); }
  .rec-info { flex: 1; }
  .rec-confianca { font-size: 10px; letter-spacing: 2px; color: var(--text2); margin-bottom: 3px; text-transform: uppercase; }
  .confianca-val { font-size: 14px; font-weight: 700; }
  .confianca-val.ALTA  { color: var(--green); }
  .confianca-val.MÉDIA { color: var(--yellow); }
  .confianca-val.BAIXA { color: var(--text2); }

  /* Tempo */
  .tempo-section { padding: 12px 18px; border-bottom: 1px solid var(--border); }
  .tempo-val {
    font-family: 'Syne', sans-serif;
    font-size: 22px;
    font-weight: 800;
    color: var(--accent);
    margin: 4px 0;
  }
  .tempo-tipo { font-size: 10px; letter-spacing: 2px; color: var(--text2); }

  /* Motivos */
  .motivos-section { padding: 12px 18px; border-bottom: 1px solid var(--border); }
  .motivo-item { display: flex; gap: 8px; margin-bottom: 6px; font-size: 11px; line-height: 1.4; }
  .motivo-item.fav { color: var(--text); }
  .motivo-item.contra { color: var(--text2); }

  /* Bloqueio */
  .bloqueio-banner {
    margin: 10px 18px;
    padding: 8px 12px;
    background: rgba(255,61,90,0.08);
    border: 1px solid rgba(255,61,90,0.3);
    color: var(--red);
    font-size: 10px;
    letter-spacing: 1px;
    display: none;
  }

  /* Alertas */
  .alertas-section { padding: 12px 18px; border-bottom: 1px solid var(--border); }
  .alerta-item { padding: 5px 0; font-size: 11px; color: var(--yellow); border-bottom: 1px solid rgba(30,45,61,0.5); }
  .alerta-item:last-child { border: none; }

  /* Histórico */
  .historico-section { padding: 12px 18px; }
  .hist-row {
    display: flex;
    justify-content: space-between;
    padding: 5px 0;
    border-bottom: 1px solid rgba(30,45,61,0.5);
    font-size: 10px;
  }
  .hist-ticker { color: var(--accent); font-weight: 700; }
  .hist-rec.COMPRA { color: var(--green); }
  .hist-rec.VENDA  { color: var(--red); }
  .hist-rec.NEUTRO { color: var(--yellow); }
  .hist-conf { color: var(--text2); }

  /* Loading */
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 12px;
    color: var(--text2);
  }
  .loading-spinner {
    width: 40px; height: 40px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* Stats bar inferior */
  .stats-bar {
    display: flex;
    gap: 24px;
    padding: 6px 24px;
    border-top: 1px solid var(--border);
    background: var(--bg2);
    font-size: 10px;
    color: var(--text2);
    letter-spacing: 1px;
    flex-shrink: 0;
  }
  .stat-item span { color: var(--text); margin-left: 6px; }

  /* Modo badge pulsando */
  .live-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    color: var(--green);
    letter-spacing: 1px;
  }

  /* Responsivo mínimo */
  @media (max-width: 1100px) {
    .right-panel { width: 280px; }
    .left-panel { width: 240px; }
  }
</style>
</head>
<body>
<div class="app">

  <!-- ─── HEADER ─── -->
  <header class="header">
    <div style="display:flex;align-items:center;gap:16px">
      <div class="logo">FLUXBOT <span>// microestrutura B3</span></div>
      <div class="live-badge">
        <div class="status-dot"></div>
        LIVE
      </div>
    </div>
    <div class="status-bar">
      <div class="clock" id="clock">--:--:--</div>
      <div class="modo-badge" id="modo-badge">SIMULAÇÃO</div>
    </div>
  </header>

  <!-- ─── MAIN ─── -->
  <div class="main">

    <!-- ─── LEFT PANEL ─── -->
    <div class="left-panel">
      <div class="search-area">
        <div class="search-label">// ATIVO</div>
        <div class="search-wrap">
          <input class="search-input" id="search-input" type="text"
                 placeholder="Ex: PETR4" maxlength="10"
                 value="PETR4"
                 onkeydown="if(event.key==='Enter') buscarAtivo()">
        </div>
        <button class="search-btn" onclick="buscarAtivo()">▶ ANALISAR</button>
      </div>

      <div class="quick-ativos">
        <div class="section-label">// Acesso rápido</div>
        <div class="quick-grid">
          <button class="quick-btn ativo" onclick="selecionarAtivo('PETR4')">PETR4</button>
          <button class="quick-btn" onclick="selecionarAtivo('VALE3')">VALE3</button>
          <button class="quick-btn" onclick="selecionarAtivo('ITUB4')">ITUB4</button>
          <button class="quick-btn" onclick="selecionarAtivo('BBDC4')">BBDC4</button>
          <button class="quick-btn" onclick="selecionarAtivo('MGLU3')">MGLU3</button>
          <button class="quick-btn" onclick="selecionarAtivo('WEGE3')">WEGE3</button>
        </div>
      </div>

      <div class="metrics-panel">
        <div class="section-label">// Sinais internos</div>
        <div class="metric-row">
          <div class="metric-label">ORDER FLOW IMBALANCE</div>
          <div class="metric-val accent" id="m-ofi">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">AGGRESSION SCORE</div>
          <div class="metric-val" id="m-agg">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">LIQUIDITY PRESSURE</div>
          <div class="metric-val" id="m-liq">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">SMART MONEY SCORE</div>
          <div class="metric-val" id="m-sm">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">VOLUME SURGE</div>
          <div class="metric-val" id="m-vsurge">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">PRICE ACCELERATION</div>
          <div class="metric-val" id="m-pacc">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">BREAKOUT SIGNAL</div>
          <div class="metric-val" id="m-brk">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">VOLATILIDADE 30s</div>
          <div class="metric-val" id="m-vol">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">SPREAD</div>
          <div class="metric-val" id="m-spread">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">TIPO DE FLUXO</div>
          <div class="metric-val accent" id="m-tipo">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">TENDÊNCIA</div>
          <div class="metric-val" id="m-tend">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">ICEBERG</div>
          <div class="metric-val" id="m-ice">—</div>
        </div>
        <br>
        <div class="section-label">// Performance sistema</div>
        <div class="metric-row">
          <div class="metric-label">TAXA DE ACERTO</div>
          <div class="metric-val green" id="m-acerto">—</div>
        </div>
        <div class="metric-row">
          <div class="metric-label">DECISÕES AVALIADAS</div>
          <div class="metric-val accent" id="m-total">—</div>
        </div>
      </div>
    </div>

    <!-- ─── CENTER PANEL ─── -->
    <div class="center-panel">
      <div class="ticker-info">
        <div class="ticker-name" id="ticker-name">PETR4</div>
        <div class="ticker-price" id="ticker-price">—</div>
        <div class="ticker-var" id="ticker-var">—</div>
        <div style="flex:1"></div>
        <div style="font-size:10px;color:var(--text2)" id="vol-label">VOL: —</div>
      </div>

      <div class="chart-area">
        <canvas id="priceChart"></canvas>
      </div>

      <div class="tabs">
        <div class="tab active" onclick="mudarTab('book')">Book de Ofertas</div>
        <div class="tab" onclick="mudarTab('tape')">Time &amp; Sales</div>
      </div>

      <div id="tab-book" class="tab-content active">
        <table class="book-table">
          <thead>
            <tr>
              <th>Preço</th>
              <th>Quantidade</th>
              <th>Ordens</th>
              <th>Lado</th>
            </tr>
          </thead>
          <tbody id="book-body">
            <tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text2)">Aguardando dados...</td></tr>
          </tbody>
        </table>
      </div>

      <div id="tab-tape" class="tab-content">
        <div id="tape-body"></div>
      </div>
    </div>

    <!-- ─── RIGHT PANEL ─── -->
    <div class="right-panel">
      <div class="decision-header">
        <div class="decision-title">// Motor de Decisão</div>
        <div style="font-size:10px;color:var(--text2)" id="dec-ticker">—</div>
      </div>

      <div class="prob-section">
        <div class="prob-row compra">
          <div class="prob-header">
            <span class="prob-label">COMPRA</span>
            <span class="prob-pct" id="pct-compra">—%</span>
          </div>
          <div class="prob-bar-bg"><div class="prob-bar-fill" id="bar-compra" style="width:0%"></div></div>
        </div>
        <div class="prob-row venda">
          <div class="prob-header">
            <span class="prob-label">VENDA</span>
            <span class="prob-pct" id="pct-venda">—%</span>
          </div>
          <div class="prob-bar-bg"><div class="prob-bar-fill" id="bar-venda" style="width:0%"></div></div>
        </div>
        <div class="prob-row neutro">
          <div class="prob-header">
            <span class="prob-label">NEUTRO</span>
            <span class="prob-pct" id="pct-neutro">—%</span>
          </div>
          <div class="prob-bar-bg"><div class="prob-bar-fill" id="bar-neutro" style="width:0%"></div></div>
        </div>
      </div>

      <div class="rec-section">
        <div class="rec-badge NEUTRO" id="rec-badge">—</div>
        <div class="rec-info">
          <div class="rec-confianca">Confiança</div>
          <div class="confianca-val BAIXA" id="confianca-val">—</div>
          <div style="margin-top:4px;font-size:10px;color:var(--text2)" id="confianca-pct">—</div>
        </div>
      </div>

      <div class="tempo-section">
        <div class="section-label">// Tempo de posição</div>
        <div class="tempo-val" id="tempo-val">—</div>
        <div class="tempo-tipo" id="tempo-tipo">—</div>
      </div>

      <div id="bloqueio-banner" class="bloqueio-banner">
        🚫 <span id="bloqueio-msg"></span>
      </div>

      <div class="motivos-section">
        <div class="section-label">// Motivos</div>
        <div id="motivos-body"></div>
      </div>

      <div class="alertas-section" id="alertas-section" style="display:none">
        <div class="section-label">// Alertas</div>
        <div id="alertas-body"></div>
      </div>

      <div class="historico-section">
        <div class="section-label">// Histórico de decisões</div>
        <div id="historico-body">
          <div style="color:var(--text2);font-size:11px;padding:8px 0">Sem histórico ainda</div>
        </div>
      </div>
    </div>

  </div>

  <!-- ─── STATS BAR ─── -->
  <div class="stats-bar">
    <div class="stat-item">MODO: <span id="modo-label">SIMULAÇÃO</span></div>
    <div class="stat-item">FONTE: <span id="fonte-label">simulacao</span></div>
    <div class="stat-item">ATUALIZAÇÃO: <span id="upd-label">—</span></div>
    <div class="stat-item">LATÊNCIA: <span id="lat-label">—ms</span></div>
  </div>

</div>

<script>
// ───────────── Estado global ─────────────
let tickerAtual = 'PETR4';
let intervaloUpdate = null;
let dadosPreco = [];
let chartCanvas, chartCtx;
let ultimaAtualiz = null;
let tabAtiva = 'book';

// ───────────── Inicialização ─────────────
document.addEventListener('DOMContentLoaded', () => {
  chartCanvas = document.getElementById('priceChart');
  chartCtx = chartCanvas.getContext('2d');
  atualizarRelogio();
  setInterval(atualizarRelogio, 1000);
  buscarAtivo();
  carregarHistorico();
  carregarStats();
  setInterval(carregarStats, 30000);
});

function atualizarRelogio() {
  const agora = new Date();
  document.getElementById('clock').textContent =
    agora.toLocaleTimeString('pt-BR', {hour12: false});
}

// ───────────── Busca de ativo ─────────────
function selecionarAtivo(ticker) {
  document.getElementById('search-input').value = ticker;
  document.querySelectorAll('.quick-btn').forEach(b => b.classList.remove('ativo'));
  event.target.classList.add('ativo');
  buscarAtivo();
}

function buscarAtivo() {
  const input = document.getElementById('search-input').value.trim().toUpperCase();
  if (!input) return;

  tickerAtual = input;
  dadosPreco = [];
  document.getElementById('ticker-name').textContent = input;
  document.getElementById('dec-ticker').textContent = `Analisando ${input}...`;

  // Limpa quick btns
  document.querySelectorAll('.quick-btn').forEach(b => {
    b.classList.toggle('ativo', b.textContent === input);
  });

  if (intervaloUpdate) clearInterval(intervaloUpdate);
  atualizarDados();
  intervaloUpdate = setInterval(atualizarDados, 1500);
}

// ───────────── Atualização de dados ─────────────
async function atualizarDados() {
  const t0 = performance.now();
  try {
    const resp = await fetch(`/api/analisar/${tickerAtual}`);
    const data = await resp.json();
    const lat = Math.round(performance.now() - t0);
    document.getElementById('lat-label').textContent = lat + 'ms';

    if (data.erro) return;

    renderizarSnapshot(data.snapshot);
    renderizarAnalise(data.analise);
    renderizarDecisao(data.decisao);
    renderizarBook(data.snapshot);
    renderizarTape(data.snapshot);
    atualizarGrafico(data.snapshot.preco);

    ultimaAtualiz = new Date();
    document.getElementById('upd-label').textContent = ultimaAtualiz.toLocaleTimeString('pt-BR');
    document.getElementById('fonte-label').textContent = data.snapshot.fonte || '—';

  } catch(e) {
    console.error(e);
  }
}

// ───────────── Render snapshot ─────────────
function renderizarSnapshot(s) {
  document.getElementById('ticker-price').textContent = `R$ ${s.preco.toFixed(2)}`;
  const varEl = document.getElementById('ticker-var');
  const v = s.variacao_pct;
  varEl.textContent = (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
  varEl.className = 'ticker-var ' + (v >= 0 ? 'pos' : 'neg');
  document.getElementById('vol-label').textContent = 'VOL: ' + formatNum(s.volume_total);
}

// ───────────── Render análise ─────────────
function renderizarAnalise(a) {
  const ofi = a.order_flow_imbalance;
  setMetric('m-ofi', (ofi * 100).toFixed(1), ofi > 0.2 ? 'green' : ofi < -0.2 ? 'red' : 'accent');
  setMetric('m-agg', a.aggression_score.toFixed(1), a.aggression_score > 60 ? 'green' : a.aggression_score < 40 ? 'red' : 'accent');
  setMetric('m-liq', a.liquidity_pressure.toFixed(1), a.liquidity_pressure > 70 ? 'yellow' : 'accent');
  setMetric('m-sm', a.smart_money_score.toFixed(1), a.smart_money_score > 55 ? 'green' : 'accent');
  setMetric('m-vsurge', a.volume_surge.toFixed(2) + 'x', a.volume_surge > 2.5 ? 'yellow' : 'accent');
  setMetric('m-pacc', a.price_acceleration.toFixed(3), a.price_acceleration > 0 ? 'green' : 'red');
  setMetric('m-brk', a.breakout_signal.toFixed(1), a.breakout_signal > 60 ? 'yellow' : 'accent');
  setMetric('m-vol', a.volatilidade_30s.toFixed(3) + '%', a.volatilidade_30s > 0.5 ? 'yellow' : 'accent');
  setMetric('m-spread', a.spread_bps.toFixed(1) + ' bps', a.spread_bps > 20 ? 'red' : 'green');
  setMetric('m-tipo', a.tipo_fluxo.toUpperCase(), a.tipo_fluxo === 'institucional' ? 'green' : a.tipo_fluxo === 'manipulacao' ? 'red' : 'accent');
  setMetric('m-tend', a.microtendencia.toUpperCase(), a.microtendencia === 'alta' ? 'green' : a.microtendencia === 'baixa' ? 'red' : 'yellow');
  setMetric('m-ice', a.iceberg_detectado ? 'SIM ✓' : 'NÃO', a.iceberg_detectado ? 'yellow' : 'accent');
}

function setMetric(id, val, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = val;
  el.className = 'metric-val ' + (cls || 'accent');
}

// ───────────── Render decisão ─────────────
function renderizarDecisao(d) {
  // Probabilidades
  setPct('pct-compra', 'bar-compra', d.prob_compra);
  setPct('pct-venda',  'bar-venda',  d.prob_venda);
  setPct('pct-neutro', 'bar-neutro', d.prob_neutro);

  // Badge
  const badge = document.getElementById('rec-badge');
  badge.textContent = d.recomendacao;
  badge.className = 'rec-badge ' + d.recomendacao;

  // Confiança
  const confEl = document.getElementById('confianca-val');
  confEl.textContent = d.confianca;
  confEl.className = 'confianca-val ' + d.confianca.toUpperCase().replace('É','E');
  document.getElementById('confianca-pct').textContent = d.confianca_pct.toFixed(1) + '%';

  // Tempo
  document.getElementById('tempo-val').textContent = d.tempo_min + '–' + d.tempo_max + ' min';
  document.getElementById('tempo-tipo').textContent = d.tipo_operacao;

  // Dec ticker
  document.getElementById('dec-ticker').textContent = tickerAtual + ' // ' + new Date().toLocaleTimeString('pt-BR');

  // Bloqueio
  const bl = document.getElementById('bloqueio-banner');
  if (!d.operar && d.motivo_bloqueio) {
    bl.style.display = 'block';
    document.getElementById('bloqueio-msg').textContent = d.motivo_bloqueio;
  } else {
    bl.style.display = 'none';
  }

  // Motivos
  const motBody = document.getElementById('motivos-body');
  motBody.innerHTML = '';
  (d.motivos_favoraveis || []).forEach(m => {
    motBody.innerHTML += `<div class="motivo-item fav"><span>✅</span><span>${m}</span></div>`;
  });
  (d.motivos_contrarios || []).forEach(m => {
    motBody.innerHTML += `<div class="motivo-item contra"><span>⚠️</span><span>${m}</span></div>`;
  });
  if (!motBody.innerHTML) {
    motBody.innerHTML = '<div style="color:var(--text2);font-size:11px">Aguardando sinais...</div>';
  }
}

function setPct(pctId, barId, val) {
  document.getElementById(pctId).textContent = val.toFixed(1) + '%';
  document.getElementById(barId).style.width = Math.min(100, val) + '%';
}

// ───────────── Book de ofertas ─────────────
function renderizarBook(s) {
  if (tabAtiva !== 'book') return;
  const tbody = document.getElementById('book-body');
  let html = '';

  const maxQtd = Math.max(
    ...s.book_compra.map(n => n.quantidade),
    ...s.book_venda.map(n => n.quantidade),
    1
  );

  // Venda (decrescente)
  const vendas = [...s.book_venda].reverse();
  vendas.forEach(n => {
    const w = (n.quantidade / maxQtd * 100).toFixed(1);
    html += `<tr class="book-row-v" style="position:relative">
      <td style="position:relative"><div class="book-bar v" style="width:${w}%"></div>R$ ${n.preco.toFixed(2)}</td>
      <td>${formatNum(n.quantidade)}</td>
      <td>${n.ordens}</td>
      <td style="color:var(--red)">V</td>
    </tr>`;
  });

  // Spread visual
  if (s.book_compra.length && s.book_venda.length) {
    const spread = (s.book_venda[0].preco - s.book_compra[0].preco).toFixed(2);
    html += `<tr><td colspan="4" style="text-align:center;padding:4px;font-size:10px;color:var(--text2);background:rgba(0,212,255,0.03)">━ spread: R$ ${spread} ━</td></tr>`;
  }

  // Compra
  s.book_compra.forEach(n => {
    const w = (n.quantidade / maxQtd * 100).toFixed(1);
    html += `<tr class="book-row-c" style="position:relative">
      <td style="position:relative"><div class="book-bar c" style="width:${w}%"></div>R$ ${n.preco.toFixed(2)}</td>
      <td>${formatNum(n.quantidade)}</td>
      <td>${n.ordens}</td>
      <td style="color:var(--green)">C</td>
    </tr>`;
  });

  tbody.innerHTML = html || '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text2)">Sem dados</td></tr>';
}

// ───────────── Tape ─────────────
function renderizarTape(s) {
  if (tabAtiva !== 'tape') return;
  const body = document.getElementById('tape-body');
  let html = '';
  const negs = [...s.negocios].reverse().slice(0, 30);
  negs.forEach(n => {
    const hora = new Date(n.timestamp * 1000).toLocaleTimeString('pt-BR');
    html += `<div class="tape-row ${n.agressor.toLowerCase()}">
      <span class="tape-hora">${hora}</span>
      <span class="tape-preco">R$ ${n.preco.toFixed(2)}</span>
      <span class="tape-qtd">${formatNum(n.quantidade)}</span>
      <span style="color:${n.agressor==='C'?'var(--green)':'var(--red)'}">${n.agressor}</span>
    </div>`;
  });
  body.innerHTML = html || '<div style="padding:20px;color:var(--text2);text-align:center">Sem negócios</div>';
}

// ───────────── Gráfico de preços ─────────────
function atualizarGrafico(preco) {
  dadosPreco.push(preco);
  if (dadosPreco.length > 200) dadosPreco.shift();
  desenharGrafico();
}

function desenharGrafico() {
  const c = chartCanvas;
  const ctx = chartCtx;
  const W = c.parentElement.clientWidth;
  const H = c.parentElement.clientHeight - 16;
  c.width = W;
  c.height = H;

  if (dadosPreco.length < 2) return;

  const min = Math.min(...dadosPreco) * 0.9995;
  const max = Math.max(...dadosPreco) * 1.0005;
  const range = max - min || 0.01;

  const pad = {l: 60, r: 10, t: 10, b: 20};
  const w = W - pad.l - pad.r;
  const h = H - pad.t - pad.b;

  ctx.clearRect(0, 0, W, H);

  // Grade
  ctx.strokeStyle = 'rgba(30,45,61,0.6)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (h / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + w, y); ctx.stroke();
    const val = max - (range / 4) * i;
    ctx.fillStyle = '#5a7a9a';
    ctx.font = '10px Space Mono, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(val.toFixed(2), pad.l - 4, y + 4);
  }

  // Linha de preço
  const pts = dadosPreco.map((p, i) => ({
    x: pad.l + (i / (dadosPreco.length - 1)) * w,
    y: pad.t + h - ((p - min) / range) * h
  }));

  // Área preenchida
  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + h);
  const up = dadosPreco[dadosPreco.length-1] >= dadosPreco[0];
  grad.addColorStop(0, up ? 'rgba(0,255,157,0.15)' : 'rgba(255,61,90,0.15)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');

  ctx.beginPath();
  ctx.moveTo(pts[0].x, pad.t + h);
  pts.forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length-1].x, pad.t + h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Linha
  ctx.beginPath();
  pts.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = up ? '#00ff9d' : '#ff3d5a';
  ctx.lineWidth = 1.5;
  ctx.shadowColor = up ? 'rgba(0,255,157,0.4)' : 'rgba(255,61,90,0.4)';
  ctx.shadowBlur = 6;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Preço atual
  const last = pts[pts.length-1];
  ctx.fillStyle = up ? '#00ff9d' : '#ff3d5a';
  ctx.beginPath();
  ctx.arc(last.x, last.y, 3, 0, Math.PI*2);
  ctx.fill();
}

// ───────────── Tabs ─────────────
function mudarTab(tab) {
  tabAtiva = tab;
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', (i===0&&tab==='book')||(i===1&&tab==='tape')));
  document.getElementById('tab-book').classList.toggle('active', tab === 'book');
  document.getElementById('tab-tape').classList.toggle('active', tab === 'tape');
}

// ───────────── Histórico ─────────────
async function carregarHistorico() {
  try {
    const resp = await fetch(`/api/historico?limit=8`);
    const data = await resp.json();
    const body = document.getElementById('historico-body');
    if (!data.length) return;
    body.innerHTML = data.map(e => `
      <div class="hist-row">
        <span class="hist-ticker">${e.ticker}</span>
        <span class="hist-rec ${e.decisao.recomendacao}">${e.decisao.recomendacao}</span>
        <span class="hist-conf">${e.decisao.confianca}</span>
        <span style="color:var(--text2)">${new Date(e.timestamp).toLocaleTimeString('pt-BR')}</span>
      </div>
    `).join('');
  } catch(e) {}
  setTimeout(carregarHistorico, 10000);
}

// ───────────── Stats ─────────────
async function carregarStats() {
  try {
    const resp = await fetch('/api/stats');
    const d = await resp.json();
    if (d.global !== undefined) {
      document.getElementById('m-acerto').textContent = (d.global * 100).toFixed(1) + '%';
      document.getElementById('m-total').textContent = d.total;
    }
  } catch(e) {}
}

// ───────────── Utils ─────────────
function formatNum(n) {
  if (n >= 1_000_000) return (n/1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n/1_000).toFixed(0) + 'K';
  return n;
}
</script>
</body>
</html>
"""


# ─────────────────────────────────────────
#  Cache de motores por ticker
# ─────────────────────────────────────────

def _obter_motor(ticker: str) -> MotorAnalise:
    if ticker not in _motores_analise:
        _motores_analise[ticker] = MotorAnalise(ticker)
    return _motores_analise[ticker]


# ─────────────────────────────────────────
#  Rotas da API
# ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/analisar/<ticker>")
def api_analisar(ticker: str):
    ticker = ticker.upper().strip()[:10]
    
    try:
        # Captura dados
        snap = _capture.captura_unica(ticker)
        
        # Análise
        motor = _obter_motor(ticker)
        analise = motor.analisar(snap)
        
        # Ajuste de pesos por aprendizado
        pesos_aj = calcular_ajuste_pesos(ticker)
        
        # Decisão
        decisao = _gerador_decisao.gerar(analise, pesos_aj)
        
        # Registra se for recomendação ativa
        if decisao.operar:
            registrar_decisao(ticker, decisao.to_dict(), snap.preco)
        
        # Serializa snapshot
        snap_dict = {
            "ticker": snap.ticker,
            "preco": snap.preco,
            "variacao_pct": snap.variacao_pct,
            "volume_total": snap.volume_total,
            "fonte": snap.fonte,
            "book_compra": [{"preco": n.preco, "quantidade": n.quantidade, "ordens": n.ordens} for n in snap.book_compra],
            "book_venda":  [{"preco": n.preco, "quantidade": n.quantidade, "ordens": n.ordens} for n in snap.book_venda],
            "negocios": [
                {"preco": n.preco, "quantidade": n.quantidade, "agressor": n.agressor, "timestamp": n.timestamp}
                for n in snap.negocios[-40:]
            ],
        }
        
        analise_dict = {
            "order_flow_imbalance": analise.order_flow_imbalance,
            "aggression_score": analise.aggression_score,
            "liquidity_pressure": analise.liquidity_pressure,
            "smart_money_score": analise.smart_money_score,
            "volume_surge": analise.volume_surge,
            "price_acceleration": analise.price_acceleration,
            "breakout_signal": analise.breakout_signal,
            "volatilidade_30s": analise.volatilidade_30s,
            "spread_bps": analise.spread_bps,
            "tipo_fluxo": analise.tipo_fluxo,
            "microtendencia": analise.microtendencia,
            "iceberg_detectado": analise.iceberg_detectado,
            "manipulacao_suspeita": analise.manipulacao_suspeita,
            "alertas": analise.alertas,
        }
        
        return jsonify({
            "snapshot": snap_dict,
            "analise": analise_dict,
            "decisao": decisao.to_dict(),
        })
    
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/historico")
def api_historico():
    ticker = request.args.get("ticker")
    limit = int(request.args.get("limit", 20))
    return jsonify(obter_historico(ticker, limit))


@app.route("/api/stats")
def api_stats():
    return jsonify(calcular_taxa_acerto())


@app.route("/api/modo/<modo>")
def api_modo(modo: str):
    if modo in ("simulacao", "ocr", "csv"):
        _capture.modo = modo
        return jsonify({"ok": True, "modo": modo})
    return jsonify({"erro": "Modo inválido"}), 400


def iniciar_servidor(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Inicia o servidor Flask."""
    print(f"\n{'='*50}")
    print(f"  FluxBot — Motor de Análise B3")
    print(f"  http://{host}:{port}")
    print(f"{'='*50}\n")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
