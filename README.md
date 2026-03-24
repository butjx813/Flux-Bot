# FluxBot — Motor de Análise de Microestrutura B3

Sistema Python local para análise de fluxo de ordens e geração de decisões
probabilísticas de compra/venda/manutenção em ativos da bolsa brasileira (B3).

**Sem APIs externas. 100% local.**

---

## 🚀 Instalação rápida

```bash
# 1. Instale dependências mínimas
pip install flask

# 2. Execute
python main.py

# 3. Abra no navegador
# http://127.0.0.1:5000
```

---

## 📁 Estrutura do projeto

```
trading_bot/
├── main.py              # Ponto de entrada, CLI
├── data_capture.py      # Módulo 1: Captura de dados (OCR / CSV / Simulação)
├── ocr_engine.py        # Motor OCR com Tesseract
├── market_analysis.py   # Módulos 2-4: Microestrutura, Smart Money, Momentum
├── decision_engine.py   # Módulos 5-6: Decisão probabilística + Tempo de posição
├── ui.py                # Módulo 7: Interface web Flask
├── logger.py            # Módulo 8: Log + Aprendizado contínuo
├── requirements.txt     # Dependências Python
└── decisions_log.json   # Histórico de decisões (gerado automaticamente)
```

---

## 🎯 Modos de uso

### 1. Interface Web (recomendado)
```bash
python main.py
# Abre em http://127.0.0.1:5000
```

### 2. Modo Terminal (sem UI)
```bash
python main.py --ticker PETR4 --iteracoes 20
```

Saída:
```
[ATIVO: PETR4]
Compra: 72%
Venda: 18%
Neutro: 10%

Recomendação: COMPRA
Confiança: ALTA
Tempo estimado: 5–10 minutos
Tipo de operação: Day Trade

Motivo:
  ✅ Forte agressão compradora
  ✅ Presença institucional detectada (score: 68)
  ✅ Surge de volume (3.2x média)
  ⚠️ Spread de 12.3 bps
```

### 3. Modo OCR (captura de tela da corretora)
```bash
# Instalar dependências OCR primeiro:
pip install pytesseract pillow pyautogui
# Instalar Tesseract no sistema operacional:
# Windows: https://github.com/UB-Mannheim/tesseract/wiki
# Linux:   sudo apt install tesseract-ocr tesseract-ocr-por
# macOS:   brew install tesseract tesseract-lang

python main.py --modo ocr
```

### 4. Modo CSV (importação manual)
```bash
python main.py --modo csv
```

Enviar CSV via API:
```bash
curl -X POST http://127.0.0.1:5000/api/csv \
  -F "file=@negócios_PETR4.csv" \
  -F "ticker=PETR4"
```

Formato CSV esperado (Time & Sales):
```csv
hora,preco,quantidade,agressor
09:30:00,28.45,200,C
09:30:01,28.46,500,C
09:30:02,28.44,150,V
```

Formato CSV (Order Book):
```csv
tipo,preco,quantidade
C,28.45,1000
C,28.44,800
V,28.47,500
V,28.48,700
```

---

## 📊 Módulos

### Módulo 1 — Captura de Dados
- **OCR**: Captura a tela da corretora via Tesseract
- **CSV**: Lê arquivos exportados manualmente
- **Simulação**: Motor de simulação realista para desenvolvimento/teste

### Módulo 2 — Microestrutura
| Métrica | Descrição |
|---------|-----------|
| `ORDER_FLOW_IMBALANCE` | Desequilíbrio bid/ask ponderado (-1 a +1) |
| `AGGRESSION_SCORE` | Dominância compradora/vendedora no tape (0-100) |
| `LIQUIDITY_PRESSURE` | Taxa de consumo do book (0-100) |
| `SPREAD_BPS` | Spread em basis points |

### Módulo 3 — Smart Money
| Métrica | Descrição |
|---------|-----------|
| `SMART_MONEY_SCORE` | Score de presença institucional (0-100) |
| `ICEBERG_DETECTADO` | Ordens fracionadas repetidas no mesmo nível |
| `MANIPULACAO_SUSPEITA` | Spoofing / wash trading detectado |
| `TIPO_FLUXO` | `institucional` / `varejo` / `manipulacao` |

### Módulo 4 — Momentum
| Métrica | Descrição |
|---------|-----------|
| `PRICE_ACCELERATION` | 2ª derivada do preço (bps) |
| `VOLUME_SURGE` | Ratio volume recente / média histórica |
| `BREAKOUT_SIGNAL` | Sinal de rompimento de nível (0-100) |
| `MICROTENDENCIA` | `alta` / `baixa` / `lateral` |

### Módulo 5 — Motor de Decisão
Combina os sinais com pesos configuráveis:
- Order Flow: 30%
- Smart Money: 25%
- Momentum: 25%
- Liquidez: 20%

Regras de bloqueio:
- Probabilidade < 65% → não operar
- Liquidez insuficiente → bloquear
- Manipulação detectada → bloquear
- Sinal NEUTRO → bloquear

### Módulo 6 — Tempo de Posição
| Condição | Tipo | Tempo |
|----------|------|-------|
| Sinal fraco | Scalp | 2–5 min |
| Sinal moderado | Scalp | 5–15 min |
| Sinal forte | Day Trade | 10–30 min |
| Institucional | Swing Curto | 30–60+ min |

### Módulo 7 — Interface Web
Terminal de trading com:
- Campo de busca de ativos
- Gráfico de preço em tempo real
- Book de ofertas com barras visuais
- Time & Sales (tape)
- Painel de decisão com probabilidades
- Histórico de decisões
- Todos os 11 indicadores internos

### Módulo 8 — Aprendizado Contínuo
- Registra toda decisão em `decisions_log.json`
- Calcula taxa de acerto por ticker
- Ajusta pesos automaticamente via reinforcement simples
- Penaliza momentum em tickers com baixo acerto histórico

---

## ⚙️ Configuração avançada

### Ajustar regiões OCR (para sua corretora)
```python
from ocr_engine import OCREngine
ocr = OCREngine()
ocr.configurar_regiao("preco",   x=100, y=150, w=200, h=40)
ocr.configurar_regiao("volume",  x=100, y=200, w=200, h=40)
ocr.configurar_regiao("book_compra", x=50, y=300, w=250, h=400)
```

### Ajustar pesos do motor de decisão
```python
from decision_engine import GeradorDecisao
g = GeradorDecisao()
g.motor.atualizar_pesos({
    "order_flow": 0.40,
    "smart_money": 0.30,
    "momentum": 0.20,
    "liquidity": 0.10,
})
```

### Threshold de operação
Em `decision_engine.py`:
```python
THRESHOLD_OPERACAO = 0.65  # Mínimo 65% de probabilidade
LIQUIDEZ_MINIMA = 5000     # Lotes mínimos no top-3 book
```

---

## ⚠️ Aviso Legal

Este sistema é **exclusivamente educacional**. Não constitui recomendação
de investimento. Toda operação envolve risco de perda. Teste extensivamente
em simulação antes de qualquer uso com capital real.

O sistema opera em probabilidades — **nunca há certeza absoluta**.
