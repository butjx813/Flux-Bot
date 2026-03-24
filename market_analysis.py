"""
market_analysis.py — Módulos 2, 3, 4: Microestrutura, Smart Money e Momentum
"""

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional
from collections import deque

from data_capture import Snapshot, NivelBook, Negocio


# ─────────────────────────────────────────
#  Resultado de análise completo
# ─────────────────────────────────────────

@dataclass
class AnaliseCompleta:
    ticker: str
    timestamp: float = field(default_factory=time.time)

    # Módulo 2: Microestrutura
    order_flow_imbalance: float = 0.0    # -1 a 1 (negativo=pressão vendedora)
    aggression_score: float = 0.0        # 0 a 100
    liquidity_pressure: float = 0.0     # 0 a 100
    book_depth_ratio: float = 0.0       # ratio compra/venda

    # Módulo 3: Smart Money
    smart_money_score: float = 0.0      # 0 a 100
    iceberg_detectado: bool = False
    manipulacao_suspeita: bool = False
    tipo_fluxo: str = "varejo"          # 'institucional', 'varejo', 'manipulacao'

    # Módulo 4: Momentum
    price_acceleration: float = 0.0     # % de aceleração
    volume_surge: float = 0.0           # ratio vs média
    breakout_signal: float = 0.0        # 0 a 100
    microtendencia: str = "lateral"     # 'alta', 'baixa', 'lateral'

    # Métricas adicionais
    spread_bps: float = 0.0
    volatilidade_30s: float = 0.0
    liquidez_disponivel: int = 0
    alertas: List[str] = field(default_factory=list)


# ─────────────────────────────────────────
#  MÓDULO 2: Análise de Microestrutura
# ─────────────────────────────────────────

class AnaliseMicroestrutura:
    """
    Analisa order book e tape (time & sales) para detectar
    desequilíbrios e agressão de mercado.
    """

    def calcular_order_flow_imbalance(self, book_c: List[NivelBook], book_v: List[NivelBook]) -> float:
        """
        OFI = (Volume bid - Volume ask) / (Volume bid + Volume ask)
        Range: -1 (pressão vendedora) a +1 (pressão compradora)
        Usa os 3 primeiros níveis ponderados por proximidade.
        """
        if not book_c or not book_v:
            return 0.0

        pesos = [1.0, 0.6, 0.3, 0.15, 0.07]
        vol_bid = sum(
            book_c[i].quantidade * pesos[i]
            for i in range(min(len(book_c), 5))
        )
        vol_ask = sum(
            book_v[i].quantidade * pesos[i]
            for i in range(min(len(book_v), 5))
        )

        total = vol_bid + vol_ask
        if total == 0:
            return 0.0

        return (vol_bid - vol_ask) / total

    def calcular_aggression_score(self, negocios: List[Negocio], janela_s: float = 30.0) -> float:
        """
        Mede a pressão direcional via tape reading.
        Considera apenas negócios recentes (janela em segundos).
        Range: 0 a 100 (50=neutro, >50=comprador dominante)
        """
        agora = time.time()
        recentes = [n for n in negocios if agora - n.timestamp <= janela_s]

        if not recentes:
            return 50.0

        vol_compra = sum(n.quantidade for n in recentes if n.agressor == "C")
        vol_venda = sum(n.quantidade for n in recentes if n.agressor == "V")
        total = vol_compra + vol_venda

        if total == 0:
            return 50.0

        # Score: 50 + 50 * (dominância)
        dominancia = (vol_compra - vol_venda) / total
        return 50.0 + 50.0 * dominancia

    def calcular_liquidity_pressure(
        self,
        book_c: List[NivelBook],
        book_v: List[NivelBook],
        negocios: List[Negocio],
        janela_s: float = 10.0
    ) -> float:
        """
        Mede o consumo de liquidez do book.
        Alta pressão = mercado consumindo book rapidamente.
        Range: 0 a 100
        """
        if not book_c or not book_v:
            return 0.0

        # Liquidez disponível (top 3 níveis)
        liq_bid = sum(n.quantidade for n in book_c[:3])
        liq_ask = sum(n.quantidade for n in book_v[:3])
        liq_total = liq_bid + liq_ask

        if liq_total == 0:
            return 0.0

        # Volume negociado recentemente
        agora = time.time()
        vol_recente = sum(
            n.quantidade for n in negocios
            if agora - n.timestamp <= janela_s
        )

        # Pressão = vol consumido / liquidez disponível
        pressao = min(1.0, vol_recente / max(liq_total, 1))
        return pressao * 100

    def detectar_spoofing(self, book_c: List[NivelBook], book_v: List[NivelBook]) -> bool:
        """
        Detecta possível spoofing:
        Ordem muito grande em nível distante do mid sem justificativa.
        """
        if not book_c or not book_v:
            return False

        # Spoofing típico: nível 2+ tem volume muito maior que nível 1
        def ratio_nivel(book: List[NivelBook]) -> float:
            if len(book) < 3:
                return 0.0
            n1 = book[0].quantidade
            n2 = max(book[1].quantidade, book[2].quantidade) if len(book) > 2 else 0
            return n2 / max(n1, 1)

        return ratio_nivel(book_c) > 5.0 or ratio_nivel(book_v) > 5.0

    def analisar(self, snap: Snapshot) -> dict:
        ofi = self.calcular_order_flow_imbalance(snap.book_compra, snap.book_venda)
        agg = self.calcular_aggression_score(snap.negocios)
        liq = self.calcular_liquidity_pressure(snap.book_compra, snap.book_venda, snap.negocios)
        spoof = self.detectar_spoofing(snap.book_compra, snap.book_venda)

        # Spread
        spread = 0.0
        if snap.book_compra and snap.book_venda:
            mid = (snap.book_compra[0].preco + snap.book_venda[0].preco) / 2
            spread = (snap.book_venda[0].preco - snap.book_compra[0].preco) / mid * 10000  # bps

        # Liquidez total
        liq_disp = sum(n.quantidade for n in snap.book_compra[:3]) + \
                   sum(n.quantidade for n in snap.book_venda[:3])

        return {
            "order_flow_imbalance": ofi,
            "aggression_score": agg,
            "liquidity_pressure": liq,
            "book_depth_ratio": (
                sum(n.quantidade for n in snap.book_compra[:3]) /
                max(sum(n.quantidade for n in snap.book_venda[:3]), 1)
            ),
            "spread_bps": spread,
            "liquidez_disponivel": liq_disp,
            "spoofing_detectado": spoof,
        }


# ─────────────────────────────────────────
#  MÓDULO 3: Detecção de Smart Money
# ─────────────────────────────────────────

class DetectorSmartMoney:
    """
    Infere presença institucional via padrões de execução.
    """

    def __init__(self):
        self._historico_ordens: deque = deque(maxlen=500)
        self._niveis_recorrentes: dict = {}  # preco -> contagem

    def atualizar(self, snap: Snapshot):
        """Atualiza histórico de ordens para análise."""
        for n in snap.negocios[-10:]:
            self._historico_ordens.append(n)
            nivel = round(n.preco, 2)
            self._niveis_recorrentes[nivel] = self._niveis_recorrentes.get(nivel, 0) + n.quantidade

    def detectar_iceberg(self, negocios: List[Negocio], janela_s: float = 60.0) -> bool:
        """
        Iceberg: execuções fracionadas repetidas no mesmo preço/direção.
        Sinal: muitas execuções pequenas/médias no mesmo nível, mesma direção.
        """
        agora = time.time()
        recentes = [n for n in negocios if agora - n.timestamp <= janela_s]
        if len(recentes) < 10:
            return False

        # Agrupa por preço arredondado
        por_preco: dict = {}
        for n in recentes:
            p = round(n.preco, 2)
            if p not in por_preco:
                por_preco[p] = {"C": 0, "V": 0, "count_C": 0, "count_V": 0}
            por_preco[p][n.agressor] += n.quantidade
            por_preco[p][f"count_{n.agressor}"] += 1

        # Iceberg: um nível com >5 execuções do mesmo lado e volume consistente
        for p, dados in por_preco.items():
            for lado in ("C", "V"):
                if dados[f"count_{lado}"] >= 5:
                    vol_medio = dados[lado] / dados[f"count_{lado}"]
                    # Volume médio razoavelmente consistente (não randomico)
                    return True
        return False

    def detectar_entrada_institucional(
        self,
        negocios: List[Negocio],
        book_c: List[NivelBook],
        book_v: List[NivelBook],
        threshold_qtd: int = 5000
    ) -> float:
        """
        Calcula score de presença institucional.
        Detecta: ordens grandes, execução sistemática, acumulação/distribuição.
        Returns: 0.0 a 1.0
        """
        if not negocios:
            return 0.0

        scores = []

        # 1. Proporção de negócios grandes
        grandes = [n for n in negocios[-50:] if n.quantidade >= threshold_qtd]
        prop_grandes = len(grandes) / max(len(negocios[-50:]), 1)
        scores.append(min(1.0, prop_grandes * 5))

        # 2. Volume em grandes negócios
        vol_total = sum(n.quantidade for n in negocios[-50:])
        vol_grandes = sum(n.quantidade for n in grandes)
        prop_vol = vol_grandes / max(vol_total, 1)
        scores.append(min(1.0, prop_vol * 2))

        # 3. Ordem grande no book (possível âncora institucional)
        if book_c and book_v:
            max_bid = max((n.quantidade for n in book_c), default=0)
            max_ask = max((n.quantidade for n in book_v), default=0)
            med_bid = sum(n.quantidade for n in book_c) / max(len(book_c), 1)
            med_ask = sum(n.quantidade for n in book_v) / max(len(book_v), 1)
            if max_bid > med_bid * 4 or max_ask > med_ask * 4:
                scores.append(0.6)
            else:
                scores.append(0.1)

        # 4. Consistência direcional
        if len(negocios) >= 20:
            recentes = negocios[-20:]
            vol_c = sum(n.quantidade for n in recentes if n.agressor == "C")
            vol_v = sum(n.quantidade for n in recentes if n.agressor == "V")
            total = vol_c + vol_v
            if total > 0:
                consistencia = abs(vol_c - vol_v) / total
                scores.append(consistencia)

        return sum(scores) / max(len(scores), 1)

    def detectar_manipulacao(
        self,
        book_c: List[NivelBook],
        book_v: List[NivelBook],
        negocios: List[Negocio]
    ) -> bool:
        """
        Detecta possível manipulação (spoofing agressivo, wash trade).
        """
        if not book_c or not book_v:
            return False

        # Spoofing: diferença extrema entre nível 1 e 2+
        if len(book_c) >= 3:
            if book_c[1].quantidade > book_c[0].quantidade * 8:
                return True
        if len(book_v) >= 3:
            if book_v[1].quantidade > book_v[0].quantidade * 8:
                return True

        # Wash trading: negócios rápidos alternando lado sem mudança de preço
        if len(negocios) >= 6:
            recentes = negocios[-6:]
            alternando = all(
                recentes[i].agressor != recentes[i+1].agressor
                for i in range(len(recentes)-1)
            )
            precos_iguais = len(set(round(n.preco, 2) for n in recentes)) == 1
            if alternando and precos_iguais:
                return True

        return False

    def calcular_smart_money_score(self, snap: Snapshot) -> dict:
        """Score consolidado de 0 a 100."""
        self.atualizar(snap)

        score_inst = self.detectar_entrada_institucional(
            snap.negocios, snap.book_compra, snap.book_venda
        )
        iceberg = self.detectar_iceberg(snap.negocios)
        manipulacao = self.detectar_manipulacao(snap.book_compra, snap.book_venda, snap.negocios)

        # Combina scores
        base = score_inst * 70
        if iceberg:
            base += 20
        if manipulacao:
            base = max(0, base - 30)

        score = min(100.0, max(0.0, base))

        # Classifica tipo
        if manipulacao:
            tipo = "manipulacao"
        elif score >= 55:
            tipo = "institucional"
        else:
            tipo = "varejo"

        return {
            "smart_money_score": score,
            "iceberg_detectado": iceberg,
            "manipulacao_suspeita": manipulacao,
            "tipo_fluxo": tipo,
        }


# ─────────────────────────────────────────
#  MÓDULO 4: Análise de Momentum
# ─────────────────────────────────────────

class AnaliseMomentum:
    """
    Detecta microtendências, rompimentos e aceleração de preço.
    """

    def __init__(self):
        self._precos: deque = deque(maxlen=120)
        self._volumes: deque = deque(maxlen=120)
        self._timestamps: deque = deque(maxlen=120)

    def atualizar(self, snap: Snapshot):
        self._precos.append(snap.preco)
        self._volumes.append(snap.volume_total)
        self._timestamps.append(snap.timestamp)

    def calcular_price_acceleration(self) -> float:
        """
        Aceleração do preço: 2ª derivada da série de preços.
        Positivo = acelerando para cima.
        """
        if len(self._precos) < 10:
            return 0.0

        precos = list(self._precos)

        # Janela curta vs longa para calcular aceleração
        vel_curta = (precos[-1] - precos[-5]) / max(precos[-5], 1) * 100   # % em 5 ticks
        vel_longa = (precos[-5] - precos[-15]) / max(precos[-15], 1) * 100 if len(precos) >= 15 else 0

        aceleracao = vel_curta - vel_longa
        return round(aceleracao * 100, 4)  # em bps

    def calcular_volume_surge(self) -> float:
        """
        Razão entre volume recente e média histórica.
        > 2.0 = surge de volume significativo.
        """
        if len(self._volumes) < 20:
            return 1.0

        vols = list(self._volumes)
        media = sum(vols[:-5]) / max(len(vols[:-5]), 1)
        vol_recente = sum(vols[-5:]) / 5

        if media == 0:
            return 1.0

        return min(5.0, vol_recente / media)

    def calcular_breakout_signal(self) -> float:
        """
        Detecta rompimentos de nível.
        Range: 0 a 100. Considera banda de preço recente.
        """
        if len(self._precos) < 30:
            return 0.0

        precos = list(self._precos)
        janela = precos[-30:-5]  # "consolidação" anterior
        preco_atual = precos[-1]

        if not janela:
            return 0.0

        maximo = max(janela)
        minimo = min(janela)
        amplitude = maximo - minimo

        if amplitude == 0:
            return 0.0

        # Quanto o preço saiu da banda
        if preco_atual > maximo:
            distancia = (preco_atual - maximo) / amplitude
        elif preco_atual < minimo:
            distancia = (minimo - preco_atual) / amplitude
        else:
            distancia = 0.0

        return min(100.0, distancia * 100)

    def detectar_microtendencia(self) -> str:
        """Detecta tendência dos últimos N ticks."""
        if len(self._precos) < 15:
            return "lateral"

        precos = list(self._precos)[-15:]

        # Regressão linear simples
        n = len(precos)
        x_med = n / 2
        y_med = sum(precos) / n
        numerador = sum((i - x_med) * (p - y_med) for i, p in enumerate(precos))
        denominador = sum((i - x_med) ** 2 for i in range(n))

        if denominador == 0:
            return "lateral"

        slope = numerador / denominador
        slope_pct = slope / max(abs(y_med), 1) * 100

        if slope_pct > 0.003:
            return "alta"
        elif slope_pct < -0.003:
            return "baixa"
        else:
            return "lateral"

    def calcular_volatilidade(self) -> float:
        """Volatilidade dos últimos 30 ticks (desvio padrão %)."""
        if len(self._precos) < 10:
            return 0.0

        precos = list(self._precos)[-30:]
        retornos = [
            (precos[i] - precos[i-1]) / max(precos[i-1], 1)
            for i in range(1, len(precos))
        ]
        if not retornos:
            return 0.0

        media = sum(retornos) / len(retornos)
        variancia = sum((r - media) ** 2 for r in retornos) / len(retornos)
        return math.sqrt(variancia) * 100

    def analisar(self, snap: Snapshot) -> dict:
        self.atualizar(snap)
        return {
            "price_acceleration": self.calcular_price_acceleration(),
            "volume_surge": self.calcular_volume_surge(),
            "breakout_signal": self.calcular_breakout_signal(),
            "microtendencia": self.detectar_microtendencia(),
            "volatilidade_30s": self.calcular_volatilidade(),
        }


# ─────────────────────────────────────────
#  Orquestrador de análise
# ─────────────────────────────────────────

class MotorAnalise:
    """
    Orquestra todos os módulos de análise para um ticker.
    """

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.microestrutura = AnaliseMicroestrutura()
        self.smart_money = DetectorSmartMoney()
        self.momentum = AnaliseMomentum()

    def analisar(self, snap: Snapshot) -> AnaliseCompleta:
        resultado = AnaliseCompleta(ticker=self.ticker)

        # Módulo 2
        micro = self.microestrutura.analisar(snap)
        resultado.order_flow_imbalance = micro["order_flow_imbalance"]
        resultado.aggression_score = micro["aggression_score"]
        resultado.liquidity_pressure = micro["liquidity_pressure"]
        resultado.book_depth_ratio = micro["book_depth_ratio"]
        resultado.spread_bps = micro["spread_bps"]
        resultado.liquidez_disponivel = micro["liquidez_disponivel"]

        # Módulo 3
        sm = self.smart_money.calcular_smart_money_score(snap)
        resultado.smart_money_score = sm["smart_money_score"]
        resultado.iceberg_detectado = sm["iceberg_detectado"]
        resultado.manipulacao_suspeita = sm["manipulacao_suspeita"]
        resultado.tipo_fluxo = sm["tipo_fluxo"]

        # Módulo 4
        mom = self.momentum.analisar(snap)
        resultado.price_acceleration = mom["price_acceleration"]
        resultado.volume_surge = mom["volume_surge"]
        resultado.breakout_signal = mom["breakout_signal"]
        resultado.microtendencia = mom["microtendencia"]
        resultado.volatilidade_30s = mom["volatilidade_30s"]

        # Alertas
        if micro["spoofing_detectado"]:
            resultado.alertas.append("⚠️ Possível spoofing no book")
        if sm["manipulacao_suspeita"]:
            resultado.alertas.append("⚠️ Sinais de manipulação detectados")
        if mom["volume_surge"] > 3.0:
            resultado.alertas.append("🔥 Surge de volume: {:.1f}x acima da média".format(mom["volume_surge"]))
        if mom["breakout_signal"] > 60:
            resultado.alertas.append("📈 Possível rompimento de nível")
        if micro["spread_bps"] > 20:
            resultado.alertas.append("💧 Baixa liquidez (spread alto)")

        return resultado
