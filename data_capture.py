"""
data_capture.py — Captura e normalização de dados de mercado
Suporta: OCR, CSV, Simulação realista (modo demo)
"""

import time
import random
import math
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Deque
from collections import deque

from ocr_engine import OCREngine, DadosMercadoBrutos


# ─────────────────────────────────────────
#  Estruturas de dados normalizadas
# ─────────────────────────────────────────

@dataclass
class NivelBook:
    preco: float
    quantidade: int
    ordens: int = 1


@dataclass
class Negocio:
    preco: float
    quantidade: int
    agressor: str  # 'C' comprador, 'V' vendedor
    timestamp: float = field(default_factory=time.time)


@dataclass
class Snapshot:
    """Snapshot completo do mercado em um instante."""
    ticker: str
    preco: float
    variacao_pct: float
    volume_total: int
    book_compra: List[NivelBook]   # melhor bid primeiro
    book_venda: List[NivelBook]    # melhor ask primeiro
    negocios: List[Negocio]        # últimos negócios
    timestamp: float = field(default_factory=time.time)
    fonte: str = "simulacao"


# ─────────────────────────────────────────
#  Motor de simulação realista
# ─────────────────────────────────────────

class SimulacaoMercado:
    """
    Simula microestrutura realista de mercado brasileiro.
    Útil para desenvolvimento/teste sem corretora.
    """

    ATIVOS_BASE = {
        "PETR4": {"preco": 38.50, "vol_medio": 45_000_000, "spread": 0.01, "volatilidade": 0.0012},
        "VALE3": {"preco": 68.20, "vol_medio": 30_000_000, "spread": 0.01, "volatilidade": 0.0010},
        "ITUB4": {"preco": 35.10, "vol_medio": 25_000_000, "spread": 0.01, "volatilidade": 0.0008},
        "BBDC4": {"preco": 15.80, "vol_medio": 20_000_000, "spread": 0.01, "volatilidade": 0.0009},
        "ABEV3": {"preco": 12.40, "vol_medio": 15_000_000, "spread": 0.02, "volatilidade": 0.0007},
        "MGLU3": {"preco": 9.85,  "vol_medio": 35_000_000, "spread": 0.01, "volatilidade": 0.0020},
        "WEGE3": {"preco": 52.30, "vol_medio": 8_000_000,  "spread": 0.02, "volatilidade": 0.0008},
        "BBAS3": {"preco": 28.90, "vol_medio": 18_000_000, "spread": 0.01, "volatilidade": 0.0009},
    }

    def __init__(self, ticker: str):
        cfg = self.ATIVOS_BASE.get(ticker, {
            "preco": 20.0, "vol_medio": 10_000_000, "spread": 0.02, "volatilidade": 0.0010
        })
        self.ticker = ticker
        self.preco_ref = cfg["preco"]
        self.preco_atual = cfg["preco"]
        self.spread = cfg["spread"]
        self.volatilidade = cfg["volatilidade"]
        self.vol_medio = cfg["vol_medio"]
        self.preco_abertura = cfg["preco"]

        # Estado interno
        self._volume_acumulado = 0
        self._negocios_buffer: Deque[Negocio] = deque(maxlen=200)
        self._tendencia = 0.0       # -1 a 1
        self._pressao_inst = 0.0    # pressão institucional simulada
        self._ciclo = 0

        # Regime de mercado (muda aleatoriamente)
        self._regime = "neutro"     # neutro, comprador, vendedor, volatil
        self._regime_timer = 0
        self._iniciar_regime()

    def _iniciar_regime(self):
        """Escolhe próximo regime de mercado."""
        regimes = ["neutro", "neutro", "neutro", "comprador", "vendedor", "volatil"]
        self._regime = random.choice(regimes)
        self._regime_timer = random.randint(20, 80)

    def tick(self) -> "Snapshot":
        """Avança o mercado um tick e retorna snapshot."""
        self._ciclo += 1
        self._regime_timer -= 1
        if self._regime_timer <= 0:
            self._iniciar_regime()

        # Atualiza tendência baseada no regime
        if self._regime == "comprador":
            self._tendencia = min(1.0, self._tendencia + random.uniform(0.02, 0.08))
            self._pressao_inst = min(1.0, self._pressao_inst + random.uniform(0, 0.05))
        elif self._regime == "vendedor":
            self._tendencia = max(-1.0, self._tendencia - random.uniform(0.02, 0.08))
            self._pressao_inst = max(0.0, self._pressao_inst - random.uniform(0, 0.03))
        elif self._regime == "volatil":
            self._tendencia += random.uniform(-0.15, 0.15)
            self._tendencia = max(-1.0, min(1.0, self._tendencia))
        else:
            self._tendencia *= 0.92  # mean reversion

        # Atualiza preço
        drift = self._tendencia * self.volatilidade * 0.5
        ruido = random.gauss(0, self.volatilidade)
        variacao = drift + ruido
        self.preco_atual *= (1 + variacao)
        self.preco_atual = max(self.preco_ref * 0.85, min(self.preco_ref * 1.15, self.preco_atual))

        # Gera negócios
        n_negocios = random.randint(1, 8) if self._regime != "volatil" else random.randint(5, 20)
        novos_negocios = []
        for _ in range(n_negocios):
            neg = self._gerar_negocio()
            self._negocios_buffer.append(neg)
            novos_negocios.append(neg)
            self._volume_acumulado += neg.quantidade

        # Constrói book
        book_c, book_v = self._gerar_book()

        var_pct = (self.preco_atual - self.preco_abertura) / self.preco_abertura * 100

        return Snapshot(
            ticker=self.ticker,
            preco=round(self.preco_atual, 2),
            variacao_pct=round(var_pct, 2),
            volume_total=self._volume_acumulado,
            book_compra=book_c,
            book_venda=book_v,
            negocios=list(self._negocios_buffer)[-50:],
            timestamp=time.time(),
            fonte="simulacao",
        )

    def _gerar_negocio(self) -> Negocio:
        """Gera um negócio realista."""
        # Agressor predominante conforme tendência
        prob_compra = 0.5 + self._tendencia * 0.3
        agressor = "C" if random.random() < prob_compra else "V"

        # Tamanho: maioria pequeno, alguns grandes (institucional)
        if random.random() < 0.05 and self._pressao_inst > 0.3:
            # Ordem grande (institucional)
            qtd = random.randint(5000, 50000)
        elif random.random() < 0.15:
            qtd = random.randint(500, 2000)
        else:
            qtd = random.randint(100, 500)

        # Preço com spread
        preco = self.preco_atual
        if agressor == "C":
            preco += random.uniform(0, self.spread)
        else:
            preco -= random.uniform(0, self.spread)

        return Negocio(
            preco=round(preco, 2),
            quantidade=qtd,
            agressor=agressor,
            timestamp=time.time() - random.uniform(0, 0.5),
        )

    def _gerar_book(self) -> tuple:
        """Gera livro de ofertas realista."""
        mid = self.preco_atual
        spread = self.spread

        # Desequilíbrio de book baseado em tendência
        fator_compra = 1 + self._tendencia * 0.4
        fator_venda = 1 - self._tendencia * 0.4

        book_c = []
        for i in range(5):
            preco = round(mid - spread / 2 - i * spread, 2)
            qtd = int(random.randint(500, 3000) * fator_compra)
            # Às vezes coloca ordem grande (institucional ou spoof)
            if i == 1 and self._pressao_inst > 0.5:
                qtd *= random.randint(3, 8)
            book_c.append(NivelBook(preco=preco, quantidade=qtd, ordens=random.randint(1, 10)))

        book_v = []
        for i in range(5):
            preco = round(mid + spread / 2 + i * spread, 2)
            qtd = int(random.randint(500, 3000) * fator_venda)
            if i == 1 and self._tendencia < -0.5:
                qtd *= random.randint(3, 8)
            book_v.append(NivelBook(preco=preco, quantidade=qtd, ordens=random.randint(1, 10)))

        return book_c, book_v


# ─────────────────────────────────────────
#  Gerenciador central de dados
# ─────────────────────────────────────────

class DataCapture:
    """
    Gerencia captura de dados de múltiplos ativos.
    Suporta OCR, CSV e simulação.
    """

    def __init__(self, modo: str = "simulacao"):
        """
        modo: 'simulacao' | 'ocr' | 'csv'
        """
        self.modo = modo
        self.ocr = OCREngine()
        self._simulacoes: dict = {}
        self._snapshots: dict = {}
        self._historico: dict = {}   # ticker -> deque de snapshots
        self._lock = threading.Lock()
        self._ativos = set()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def adicionar_ativo(self, ticker: str):
        """Registra um ativo para monitoramento."""
        ticker = ticker.upper().strip()
        with self._lock:
            self._ativos.add(ticker)
            if ticker not in self._simulacoes:
                self._simulacoes[ticker] = SimulacaoMercado(ticker)
            if ticker not in self._historico:
                self._historico[ticker] = deque(maxlen=300)

    def remover_ativo(self, ticker: str):
        ticker = ticker.upper().strip()
        with self._lock:
            self._ativos.discard(ticker)

    def iniciar(self, intervalo: float = 1.0):
        """Inicia captura contínua em thread separada."""
        self._running = True
        self._intervalo = intervalo
        self._thread = threading.Thread(target=self._loop_captura, daemon=True)
        self._thread.start()

    def parar(self):
        self._running = False

    def _loop_captura(self):
        while self._running:
            inicio = time.time()
            for ticker in list(self._ativos):
                try:
                    snap = self._capturar(ticker)
                    with self._lock:
                        self._snapshots[ticker] = snap
                        self._historico[ticker].append(snap)
                except Exception:
                    pass
            elapsed = time.time() - inicio
            sleep_time = max(0, self._intervalo - elapsed)
            time.sleep(sleep_time)

    def _capturar(self, ticker: str) -> Snapshot:
        if self.modo == "ocr":
            brutos = self.ocr.capturar_dados_tela(ticker)
            return self._normalizar_ocr(brutos)
        elif self.modo == "csv":
            # CSV deve ser carregado externamente
            return self._simulacoes.get(ticker, SimulacaoMercado(ticker)).tick()
        else:
            # Simulação
            sim = self._simulacoes.get(ticker)
            if sim is None:
                sim = SimulacaoMercado(ticker)
                self._simulacoes[ticker] = sim
            return sim.tick()

    def _normalizar_ocr(self, brutos: DadosMercadoBrutos) -> Snapshot:
        """Converte dados brutos OCR em Snapshot normalizado."""
        preco = OCREngine.parse_preco(brutos.preco_texto)
        volume = OCREngine.parse_volume(brutos.volume_texto)

        book_c = self._parse_book_linhas(brutos.book_compra_texto)
        book_v = self._parse_book_linhas(brutos.book_venda_texto)
        negocios = self._parse_negocios_linhas(brutos.negocios_texto)

        return Snapshot(
            ticker=brutos.ticker,
            preco=preco,
            variacao_pct=0.0,
            volume_total=volume,
            book_compra=book_c,
            book_venda=book_v,
            negocios=negocios,
            timestamp=brutos.timestamp,
            fonte=brutos.fonte,
        )

    def _parse_book_linhas(self, linhas: List[str]) -> List[NivelBook]:
        niveis = []
        for l in linhas[:5]:
            partes = l.replace(";", ",").split(",")
            if len(partes) >= 2:
                preco = OCREngine.parse_preco(partes[0])
                qtd = OCREngine.parse_volume(partes[1])
                if preco > 0 and qtd > 0:
                    niveis.append(NivelBook(preco=preco, quantidade=qtd))
        return niveis

    def _parse_negocios_linhas(self, linhas: List[str]) -> List[Negocio]:
        negocios = []
        for l in linhas[-50:]:
            partes = l.replace(";", ",").split(",")
            if len(partes) >= 3:
                preco = OCREngine.parse_preco(partes[0])
                qtd = OCREngine.parse_volume(partes[1])
                agr = partes[2].strip().upper()[:1]
                if preco > 0 and qtd > 0 and agr in ("C", "V"):
                    negocios.append(Negocio(preco=preco, quantidade=qtd, agressor=agr))
        return negocios

    def carregar_csv(self, caminho: str, ticker: str):
        """Carrega dados de CSV e atualiza o snapshot."""
        ticker = ticker.upper()
        brutos = self.ocr.importar_csv(caminho, ticker)
        snap = self._normalizar_ocr(brutos)
        snap.fonte = "csv"
        with self._lock:
            self._snapshots[ticker] = snap
            self._historico.setdefault(ticker, deque(maxlen=300))
            self._historico[ticker].append(snap)

    def obter_snapshot(self, ticker: str) -> Optional[Snapshot]:
        ticker = ticker.upper()
        with self._lock:
            return self._snapshots.get(ticker)

    def obter_historico(self, ticker: str, n: int = 100) -> List[Snapshot]:
        ticker = ticker.upper()
        with self._lock:
            hist = self._historico.get(ticker, deque())
            return list(hist)[-n:]

    def captura_unica(self, ticker: str) -> Snapshot:
        """Captura single-shot sem thread (para uso síncrono)."""
        ticker = ticker.upper()
        self.adicionar_ativo(ticker)
        snap = self._capturar(ticker)
        with self._lock:
            self._snapshots[ticker] = snap
            self._historico.setdefault(ticker, deque(maxlen=300))
            self._historico[ticker].append(snap)
        return snap
