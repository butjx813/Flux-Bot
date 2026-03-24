"""
logger.py — Sistema de log com histórico de decisões e aprendizado contínuo
"""

import json
import os
import time
from datetime import datetime
from collections import deque
from threading import Lock

LOG_FILE = "decisions_log.json"
MAX_HISTORY = 500

_lock = Lock()


def _load_log() -> list:
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_log(data: list):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)


def registrar_decisao(ticker: str, decisao: dict, preco_entrada: float):
    """Registra uma decisão do sistema."""
    with _lock:
        log = _load_log()
        entry = {
            "id": int(time.time() * 1000),
            "timestamp": datetime.now().isoformat(),
            "ticker": ticker,
            "decisao": decisao,
            "preco_entrada": preco_entrada,
            "preco_saida": None,
            "resultado": None,
            "acerto": None,
        }
        log.append(entry)
        _save_log(log)
        return entry["id"]


def registrar_resultado(decision_id: int, preco_saida: float):
    """Registra o resultado real de uma decisão anterior."""
    with _lock:
        log = _load_log()
        for entry in log:
            if entry["id"] == decision_id:
                entry["preco_saida"] = preco_saida
                rec = entry["decisao"].get("recomendacao", "NEUTRO")
                entrada = entry["preco_entrada"] or 0
                delta = preco_saida - entrada if entrada else 0
                if rec == "COMPRA":
                    entry["acerto"] = delta > 0
                    entry["resultado"] = delta
                elif rec == "VENDA":
                    entry["acerto"] = delta < 0
                    entry["resultado"] = -delta
                else:
                    entry["acerto"] = abs(delta) < entrada * 0.005
                    entry["resultado"] = 0
                break
        _save_log(log)


def obter_historico(ticker: str = None, limit: int = 20) -> list:
    """Retorna histórico de decisões, opcionalmente filtrado por ticker."""
    log = _load_log()
    if ticker:
        log = [e for e in log if e.get("ticker") == ticker]
    return list(reversed(log[-limit:]))


def calcular_taxa_acerto() -> dict:
    """Calcula taxa de acerto global e por ticker."""
    log = _load_log()
    avaliados = [e for e in log if e.get("acerto") is not None]
    if not avaliados:
        return {"global": 0.5, "por_ticker": {}, "total": 0}
    
    acertos = sum(1 for e in avaliados if e["acerto"])
    taxa = acertos / len(avaliados)
    
    por_ticker = {}
    tickers = set(e["ticker"] for e in avaliados)
    for t in tickers:
        sub = [e for e in avaliados if e["ticker"] == t]
        a = sum(1 for e in sub if e["acerto"])
        por_ticker[t] = {"taxa": a / len(sub), "total": len(sub)}
    
    return {"global": taxa, "por_ticker": por_ticker, "total": len(avaliados)}


def calcular_ajuste_pesos(ticker: str) -> dict:
    """
    Aprendizado por reforço simples:
    Ajusta pesos baseado no histórico de acertos do ticker.
    """
    log = _load_log()
    recentes = [e for e in log if e.get("ticker") == ticker and e.get("acerto") is not None][-30:]
    
    if len(recentes) < 5:
        return {"order_flow": 1.0, "smart_money": 1.0, "momentum": 1.0, "liquidity": 1.0}
    
    acertos = [e for e in recentes if e["acerto"]]
    erros = [e for e in recentes if not e["acerto"]]
    
    taxa = len(acertos) / len(recentes)
    
    # Ajuste simples: se taxa < 50%, reduz momentum (mais volátil)
    momentum_adj = 1.0 + (taxa - 0.5) * 0.4
    smart_adj = 1.0 + (taxa - 0.5) * 0.2
    
    return {
        "order_flow": 1.0,
        "smart_money": max(0.5, min(1.5, smart_adj)),
        "momentum": max(0.5, min(1.5, momentum_adj)),
        "liquidity": 1.0,
    }
