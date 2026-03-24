"""
main.py — Ponto de entrada principal do FluxBot
Sistema de Análise de Microestrutura B3

Uso:
  python main.py                     # Interface web (padrão)
  python main.py --modo ocr          # Modo OCR (captura de tela)
  python main.py --modo csv          # Modo CSV (importação manual)
  python main.py --ticker PETR4      # Análise terminal (sem UI)
  python main.py --port 8080         # Porta customizada
"""

import sys
import os
import argparse
import time
import threading

# Garante que o diretório local está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def verificar_dependencias():
    """Verifica e reporta dependências disponíveis."""
    deps = {}
    
    try:
        import flask
        deps["flask"] = flask.__version__
    except ImportError:
        deps["flask"] = None

    try:
        import PIL
        deps["pillow"] = PIL.__version__
    except ImportError:
        deps["pillow"] = None

    try:
        import pytesseract
        deps["pytesseract"] = "ok"
    except ImportError:
        deps["pytesseract"] = None

    try:
        import pyautogui
        deps["pyautogui"] = "ok"
    except ImportError:
        deps["pyautogui"] = None

    return deps


def instalar_dependencias_minimas():
    """Instala Flask se necessário."""
    try:
        import flask
    except ImportError:
        print("  Instalando Flask...")
        os.system(f"{sys.executable} -m pip install flask --quiet")


def modo_terminal(ticker: str, n_iteracoes: int = 10, intervalo: float = 2.0):
    """
    Modo terminal sem UI — imprime análise no console.
    Útil para testes e integração com outros sistemas.
    """
    from data_capture import DataCapture
    from market_analysis import MotorAnalise
    from decision_engine import GeradorDecisao
    from logger import calcular_ajuste_pesos, registrar_decisao

    print(f"\n{'='*55}")
    print(f"  FluxBot — Modo Terminal")
    print(f"  Ativo: {ticker.upper()}")
    print(f"  Iterações: {n_iteracoes} | Intervalo: {intervalo}s")
    print(f"{'='*55}\n")

    capture = DataCapture(modo="simulacao")
    motor = MotorAnalise(ticker)
    gerador = GeradorDecisao()

    for i in range(n_iteracoes):
        snap = capture.captura_unica(ticker)
        analise = motor.analisar(snap)
        pesos = calcular_ajuste_pesos(ticker)
        decisao = gerador.gerar(analise, pesos)

        print(f"[{time.strftime('%H:%M:%S')}] Iteração {i+1}/{n_iteracoes}")
        print(gerador.formatar_saida(decisao, analise))
        print()

        if i < n_iteracoes - 1:
            time.sleep(intervalo)

    print("Análise concluída.")


def main():
    parser = argparse.ArgumentParser(
        description="FluxBot — Análise de Microestrutura B3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--modo", choices=["simulacao", "ocr", "csv"], default="simulacao",
                        help="Modo de captura de dados (padrão: simulacao)")
    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor web")
    parser.add_argument("--port", type=int, default=5000, help="Porta do servidor (padrão: 5000)")
    parser.add_argument("--ticker", help="Ticker para análise em modo terminal (sem UI)")
    parser.add_argument("--iteracoes", type=int, default=10, help="Número de iterações no modo terminal")
    parser.add_argument("--debug", action="store_true", help="Modo debug do Flask")
    args = parser.parse_args()

    print("\n" + "="*55)
    print("  ███████╗██╗     ██╗   ██╗██╗  ██╗")
    print("  ██╔════╝██║     ██║   ██║╚██╗██╔╝")
    print("  █████╗  ██║     ██║   ██║ ╚███╔╝ ")
    print("  ██╔══╝  ██║     ██║   ██║ ██╔██╗ ")
    print("  ██║     ███████╗╚██████╔╝██╔╝ ██╗")
    print("  ╚═╝     ╚══════╝ ╚═════╝ ╚═╝  ╚═╝")
    print("  FluxBot — Microestrutura B3 v1.0")
    print("="*55)

    # Verifica deps
    deps = verificar_dependencias()
    print("\n  Dependências:")
    for k, v in deps.items():
        status = f"✓ {v}" if v else "✗ não instalado"
        print(f"    {k:15s} {status}")

    if not deps.get("flask"):
        print("\n  ⚠ Flask não encontrado. Instalando...")
        instalar_dependencias_minimas()

    if args.ticker:
        # Modo terminal
        modo_terminal(args.ticker.upper(), args.iteracoes)
    else:
        # Modo UI Web
        print(f"\n  Modo de captura: {args.modo.upper()}")
        if args.modo == "ocr" and not deps.get("pytesseract"):
            print("  ⚠ Pytesseract não disponível — usando simulação como fallback")
            print("  → pip install pytesseract pillow pyautogui")

        # Seta modo no módulo ui
        import ui
        ui._capture.modo = args.modo
        ui.iniciar_servidor(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
