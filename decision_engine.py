"""
decision_engine.py — Módulos 5 e 6: Motor de Decisão e Estimativa de Tempo de Posição
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from market_analysis import AnaliseCompleta


# ─────────────────────────────────────────
#  Estrutura de decisão
# ─────────────────────────────────────────

@dataclass
class Decisao:
    ticker: str
    timestamp: float = field(default_factory=time.time)

    # Probabilidades
    prob_compra: float = 0.0
    prob_venda: float = 0.0
    prob_neutro: float = 0.0

    # Decisão final
    recomendacao: str = "NEUTRO"      # 'COMPRA', 'VENDA', 'NEUTRO'
    confianca: str = "BAIXA"          # 'ALTA', 'MEDIA', 'BAIXA'
    confianca_pct: float = 0.0

    # Tempo de posição
    tempo_min: int = 0
    tempo_max: int = 0
    tipo_operacao: str = "—"          # 'Scalp', 'Day Trade', 'Swing Curto'

    # Motivos
    motivos_favoraveis: list = field(default_factory=list)
    motivos_contrarios: list = field(default_factory=list)

    # Operar?
    operar: bool = False
    motivo_bloqueio: str = ""

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "timestamp": self.timestamp,
            "prob_compra": round(self.prob_compra, 1),
            "prob_venda": round(self.prob_venda, 1),
            "prob_neutro": round(self.prob_neutro, 1),
            "recomendacao": self.recomendacao,
            "confianca": self.confianca,
            "confianca_pct": round(self.confianca_pct, 1),
            "tempo_min": self.tempo_min,
            "tempo_max": self.tempo_max,
            "tipo_operacao": self.tipo_operacao,
            "motivos_favoraveis": self.motivos_favoraveis,
            "motivos_contrarios": self.motivos_contrarios,
            "operar": self.operar,
            "motivo_bloqueio": self.motivo_bloqueio,
        }


# ─────────────────────────────────────────
#  MÓDULO 5: Motor de Decisão
# ─────────────────────────────────────────

class MotorDecisao:
    """
    Combina todos os sinais de análise e gera probabilidades de compra/venda.
    
    Pesos padrão (ajustáveis pelo módulo de aprendizado):
    - order_flow:   30%
    - smart_money:  25%
    - momentum:     25%
    - liquidity:    20%
    """

    PESOS_PADRAO = {
        "order_flow": 0.30,
        "smart_money": 0.25,
        "momentum": 0.25,
        "liquidity": 0.20,
    }

    # Threshold mínimo para recomendar operação
    THRESHOLD_OPERACAO = 0.65

    # Threshold de liquidez mínima
    LIQUIDEZ_MINIMA = 5000

    def __init__(self, pesos: Optional[Dict] = None):
        self.pesos = pesos or self.PESOS_PADRAO.copy()

    def atualizar_pesos(self, novos_pesos: dict):
        """Permite ajuste externo dos pesos (aprendizado contínuo)."""
        for k, v in novos_pesos.items():
            if k in self.pesos:
                self.pesos[k] = max(0.1, min(0.5, v))
        # Normaliza
        total = sum(self.pesos.values())
        for k in self.pesos:
            self.pesos[k] /= total

    def _calcular_sinal_order_flow(self, analise: AnaliseCompleta) -> float:
        """
        Converte métricas de order flow em sinal direcional.
        Returns: -1.0 (venda forte) a +1.0 (compra forte)
        """
        ofi = analise.order_flow_imbalance          # -1 a 1
        agg = (analise.aggression_score - 50) / 50  # -1 a 1 (normalizado de 0-100)
        liq_p = analise.liquidity_pressure / 100    # 0 a 1

        # OFI tem maior peso, agression confirma
        sinal_base = ofi * 0.6 + agg * 0.4

        # Liquidez alta amplifica (mais confiança)
        multiplicador = 1.0 + liq_p * 0.3
        return max(-1.0, min(1.0, sinal_base * multiplicador))

    def _calcular_sinal_smart_money(self, analise: AnaliseCompleta) -> float:
        """
        Converte smart money score em sinal direcional.
        A direção é inferida do order flow (smart money confirma ou diverge).
        """
        if analise.manipulacao_suspeita:
            return 0.0  # Anula sinal em manipulação

        score = analise.smart_money_score / 100  # 0 a 1

        # Direção: alinhar com order flow (smart money confirma tendência)
        dir_ofi = 1.0 if analise.order_flow_imbalance > 0 else -1.0
        dir_agg = 1.0 if analise.aggression_score > 50 else -1.0

        direcao = dir_ofi if dir_ofi == dir_agg else dir_ofi * 0.5

        return score * direcao * 0.8  # Amortece — institutional pode estar distribuindo

    def _calcular_sinal_momentum(self, analise: AnaliseCompleta) -> float:
        """Converte momentum em sinal direcional."""
        tend_map = {"alta": 1.0, "baixa": -1.0, "lateral": 0.0}
        tend = tend_map.get(analise.microtendencia, 0.0)

        acel = max(-1.0, min(1.0, analise.price_acceleration / 10))  # normaliza
        brk = analise.breakout_signal / 100  # 0 a 1

        sinal = tend * 0.5 + acel * 0.3
        # Breakout amplifica se alinhado com tendência
        if brk > 0.5 and tend != 0:
            sinal += tend * brk * 0.2

        return max(-1.0, min(1.0, sinal))

    def _calcular_sinal_liquidez(self, analise: AnaliseCompleta) -> float:
        """
        Liquidez não tem direção, mas penaliza decisões em mercados illíquidos.
        Returns: multiplicador 0 a 1 (1 = alta liquidez, ok para operar)
        """
        if analise.liquidez_disponivel < self.LIQUIDEZ_MINIMA:
            return 0.2
        elif analise.spread_bps > 30:
            return 0.5
        elif analise.spread_bps > 15:
            return 0.8
        return 1.0

    def calcular_probabilidades(self, analise: AnaliseCompleta, pesos_externos: dict = None) -> dict:
        """
        Calcula probabilidades de compra/venda/neutro.
        """
        pesos = pesos_externos or self.pesos

        s_of = self._calcular_sinal_order_flow(analise)
        s_sm = self._calcular_sinal_smart_money(analise)
        s_mom = self._calcular_sinal_momentum(analise)
        fator_liq = self._calcular_sinal_liquidez(analise)

        # Sinal ponderado (-1 a 1)
        sinal = (
            s_of * pesos["order_flow"] +
            s_sm * pesos["smart_money"] +
            s_mom * pesos["momentum"]
        )

        # Penaliza por liquidez
        sinal *= fator_liq

        # Penaliza sinais conflitantes
        sinais_individuais = [s_of, s_sm, s_mom]
        positivos = sum(1 for s in sinais_individuais if s > 0.1)
        negativos = sum(1 for s in sinais_individuais if s < -0.1)
        conflito = positivos > 0 and negativos > 0
        if conflito:
            sinal *= 0.6

        # Converte sinal em probabilidades via sigmoid
        # sinal 1.0 -> compra muito alta, sinal -1.0 -> venda muito alta
        import math
        sinal_clamp = max(-1.0, min(1.0, sinal))

        # Probabilidade base de compra (sigmoid centrado)
        prob_compra_raw = 1 / (1 + math.exp(-sinal_clamp * 4))

        # Distribui as probabilidades
        prob_compra = prob_compra_raw
        prob_venda = 1 - prob_compra_raw
        prob_neutro = 0.0

        # Puxa para neutro em sinal fraco
        forca = abs(sinal_clamp)
        if forca < 0.3:
            neutro_adj = (0.3 - forca) / 0.3 * 0.35
            prob_compra -= neutro_adj / 2
            prob_venda -= neutro_adj / 2
            prob_neutro = neutro_adj

        # Normaliza para soma 100%
        total = prob_compra + prob_venda + prob_neutro
        prob_compra /= total
        prob_venda /= total
        prob_neutro /= total

        return {
            "prob_compra": prob_compra * 100,
            "prob_venda": prob_venda * 100,
            "prob_neutro": prob_neutro * 100,
            "sinal": sinal,
            "fator_liquidez": fator_liq,
            "conflito": conflito,
            "sinais": {"order_flow": s_of, "smart_money": s_sm, "momentum": s_mom},
        }

    def _determinar_motivos(self, analise: AnaliseCompleta, probs: dict) -> tuple:
        """Gera lista de motivos favoráveis e contrários."""
        favoraveis = []
        contrarios = []
        is_compra = probs["prob_compra"] > probs["prob_venda"]

        # Order flow
        ofi = analise.order_flow_imbalance
        if abs(ofi) > 0.3:
            msg = f"{'Forte' if abs(ofi) > 0.6 else 'Moderada'} agressão {'compradora' if ofi > 0 else 'vendedora'}"
            (favoraveis if (ofi > 0) == is_compra else contrarios).append(msg)

        # Smart money
        if analise.smart_money_score > 55:
            msg = f"Presença institucional detectada (score: {analise.smart_money_score:.0f})"
            favoraveis.append(msg)
        if analise.iceberg_detectado:
            favoraveis.append("Ordens iceberg identificadas")
        if analise.manipulacao_suspeita:
            contrarios.append("Possível manipulação/spoofing — cautela")

        # Momentum
        if analise.microtendencia != "lateral":
            msg = f"Microtendência de {'alta' if analise.microtendencia == 'alta' else 'baixa'}"
            (favoraveis if (analise.microtendencia == "alta") == is_compra else contrarios).append(msg)
        if analise.breakout_signal > 60:
            favoraveis.append(f"Rompimento com volume ({analise.breakout_signal:.0f}/100)")
        if analise.volume_surge > 2.5:
            msg = f"Surge de volume ({analise.volume_surge:.1f}x média)"
            favoraveis.append(msg)

        # Liquidez
        if analise.spread_bps > 20:
            contrarios.append(f"Spread elevado ({analise.spread_bps:.1f} bps)")
        if probs["conflito"]:
            contrarios.append("Sinais conflitantes entre indicadores")

        return favoraveis, contrarios


# ─────────────────────────────────────────
#  MÓDULO 6: Estimativa de Tempo de Posição
# ─────────────────────────────────────────

class EstimadorTempoPos:
    """
    Estima quanto tempo manter a posição baseado na força do movimento.
    """

    def estimar(self, analise: AnaliseCompleta, sinal: float) -> dict:
        """
        Returns: dict com tempo_min, tempo_max, tipo_operacao.
        """
        forca = abs(sinal)
        vol = analise.volatilidade_30s
        vol_surge = analise.volume_surge
        smart = analise.smart_money_score

        # Classificação base por força do sinal
        if forca < 0.3:
            base_min, base_max = 2, 5
            tipo = "Scalp"
        elif forca < 0.6:
            base_min, base_max = 5, 15
            tipo = "Scalp"
        else:
            base_min, base_max = 10, 30
            tipo = "Day Trade"

        # Ajuste por presença institucional (movimentos mais persistentes)
        if smart > 60:
            base_min = int(base_min * 1.5)
            base_max = int(base_max * 1.8)
            if base_max >= 60:
                tipo = "Swing Curto"

        # Ajuste por volatilidade
        if vol > 0.5:
            # Alta volatilidade → encurta posição
            base_max = max(base_min + 2, int(base_max * 0.7))
            tipo = "Scalp"
        elif vol < 0.1:
            # Baixa volatilidade → pode segurar mais
            base_max = int(base_max * 1.3)

        # Volume surge → movimento pode ser mais curto (exaustão)
        if vol_surge > 3.0:
            base_max = max(base_min + 1, int(base_max * 0.8))

        return {
            "tempo_min": base_min,
            "tempo_max": base_max,
            "tipo_operacao": tipo,
        }


# ─────────────────────────────────────────
#  Gerador de decisão unificado
# ─────────────────────────────────────────

class GeradorDecisao:
    """
    Combina Motor de Decisão + Estimador de Tempo.
    Interface principal para o sistema.
    """

    def __init__(self):
        self.motor = MotorDecisao()
        self.estimador = EstimadorTempoPos()

    def gerar(self, analise: AnaliseCompleta, pesos_aprendido: dict = None) -> Decisao:
        d = Decisao(ticker=analise.ticker)

        # Calcula probabilidades
        probs = self.motor.calcular_probabilidades(analise, pesos_aprendido)
        d.prob_compra = probs["prob_compra"]
        d.prob_venda = probs["prob_venda"]
        d.prob_neutro = probs["prob_neutro"]

        # Determina recomendação
        if d.prob_compra >= d.prob_venda and d.prob_compra >= d.prob_neutro:
            d.recomendacao = "COMPRA"
            prob_dominante = d.prob_compra
        elif d.prob_venda > d.prob_compra and d.prob_venda >= d.prob_neutro:
            d.recomendacao = "VENDA"
            prob_dominante = d.prob_venda
        else:
            d.recomendacao = "NEUTRO"
            prob_dominante = d.prob_neutro

        d.confianca_pct = prob_dominante

        # Nível de confiança
        if prob_dominante >= 75:
            d.confianca = "ALTA"
        elif prob_dominante >= 65:
            d.confianca = "MÉDIA"
        else:
            d.confianca = "BAIXA"

        # Verificações de bloqueio
        bloqueios = []
        if analise.liquidez_disponivel < MotorDecisao.LIQUIDEZ_MINIMA:
            bloqueios.append("Liquidez insuficiente")
        if analise.manipulacao_suspeita:
            bloqueios.append("Manipulação detectada")
        if prob_dominante < MotorDecisao.THRESHOLD_OPERACAO * 100:
            bloqueios.append(f"Probabilidade abaixo do mínimo ({MotorDecisao.THRESHOLD_OPERACAO*100:.0f}%)")
        if d.recomendacao == "NEUTRO":
            bloqueios.append("Sem direcionalidade clara")

        d.operar = len(bloqueios) == 0
        d.motivo_bloqueio = "; ".join(bloqueios)

        # Tempo de posição (só faz sentido se vai operar)
        tempo = self.estimador.estimar(analise, probs["sinal"])
        d.tempo_min = tempo["tempo_min"]
        d.tempo_max = tempo["tempo_max"]
        d.tipo_operacao = tempo["tipo_operacao"]

        # Motivos
        d.motivos_favoraveis, d.motivos_contrarios = self.motor._determinar_motivos(analise, probs)

        return d

    def formatar_saida(self, decisao: Decisao, analise: AnaliseCompleta) -> str:
        """Formata saída no padrão solicitado."""
        linhas = [
            f"[ATIVO: {decisao.ticker}]",
            f"Compra: {decisao.prob_compra:.0f}%",
            f"Venda: {decisao.prob_venda:.0f}%",
            f"Neutro: {decisao.prob_neutro:.0f}%",
            "",
            f"Recomendação: {decisao.recomendacao}",
            f"Confiança: {decisao.confianca}",
            f"Tempo estimado: {decisao.tempo_min}–{decisao.tempo_max} minutos",
            f"Tipo de operação: {decisao.tipo_operacao}",
            "",
            "Motivo:",
        ]

        for m in decisao.motivos_favoraveis:
            linhas.append(f"  ✅ {m}")
        for m in decisao.motivos_contrarios:
            linhas.append(f"  ⚠️ {m}")

        if not decisao.operar:
            linhas.append(f"\n🚫 OPERAÇÃO BLOQUEADA: {decisao.motivo_bloqueio}")

        if analise.alertas:
            linhas.append("\nAlertas:")
            for a in analise.alertas:
                linhas.append(f"  {a}")

        return "\n".join(linhas)
