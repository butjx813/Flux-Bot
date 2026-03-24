"""
ocr_engine.py — Extração de dados via OCR (Tesseract) e screen scraping
"""

import re
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List

# Importações opcionais — sistema funciona sem elas (modo simulação)
try:
    import pytesseract
    from PIL import Image, ImageGrab, ImageFilter, ImageEnhance
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


@dataclass
class RegiaoCaptua:
    """Define uma região da tela para captura."""
    nome: str
    x: int
    y: int
    largura: int
    altura: int


@dataclass
class DadosMercadoBrutos:
    """Dados brutos capturados da tela."""
    ticker: str = ""
    preco_texto: str = ""
    volume_texto: str = ""
    book_compra_texto: List[str] = field(default_factory=list)
    book_venda_texto: List[str] = field(default_factory=list)
    negocios_texto: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    fonte: str = "ocr"  # 'ocr', 'csv', 'simulacao'


class OCREngine:
    """
    Motor de OCR para captura de dados de corretoras.
    
    Suporta:
    - Captura de tela com Tesseract
    - Importação de CSV
    - Modo simulação (sem dependências externas)
    """

    # Configuração padrão para Tesseract em português
    TESSERACT_CONFIG = "--psm 6 -c tessedit_char_whitelist=0123456789.,- "

    def __init__(self):
        self.regioes: dict = {}
        self.ultimo_capture: Optional[DadosMercadoBrutos] = None
        self._lock = threading.Lock()
        self._configurar_regioes_padrao()

    def _configurar_regioes_padrao(self):
        """Regiões padrão do home broker (ajustar por corretora)."""
        self.regioes = {
            "preco": RegiaoCaptua("preco", 100, 150, 200, 40),
            "volume": RegiaoCaptua("volume", 100, 200, 200, 40),
            "book_compra": RegiaoCaptua("book_compra", 50, 300, 250, 400),
            "book_venda": RegiaoCaptua("book_venda", 350, 300, 250, 400),
            "negocios": RegiaoCaptua("negocios", 650, 150, 400, 600),
        }

    def configurar_regiao(self, nome: str, x: int, y: int, w: int, h: int):
        """Permite ao usuário ajustar regiões de captura."""
        self.regioes[nome] = RegiaoCaptua(nome, x, y, w, h)

    def capturar_tela(self, regiao: RegiaoCaptua) -> Optional[object]:
        """Captura uma região da tela."""
        if not OCR_AVAILABLE or not PYAUTOGUI_AVAILABLE:
            return None
        try:
            screenshot = ImageGrab.grab(bbox=(
                regiao.x, regiao.y,
                regiao.x + regiao.largura,
                regiao.y + regiao.altura
            ))
            return screenshot
        except Exception as e:
            return None

    def _preprocessar_imagem(self, img) -> object:
        """Pré-processa imagem para melhorar OCR."""
        if img is None:
            return None
        try:
            # Converte para escala de cinza
            img = img.convert("L")
            # Aumenta contraste
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            # Aumenta tamanho para melhor OCR
            w, h = img.size
            img = img.resize((w * 2, h * 2), Image.LANCZOS)
            # Filtro de nitidez
            img = img.filter(ImageFilter.SHARPEN)
            return img
        except Exception:
            return img

    def extrair_texto(self, img) -> str:
        """Extrai texto de uma imagem via Tesseract."""
        if not OCR_AVAILABLE or img is None:
            return ""
        try:
            img_proc = self._preprocessar_imagem(img)
            texto = pytesseract.image_to_string(img_proc, config=self.TESSERACT_CONFIG, lang="por")
            return texto.strip()
        except Exception:
            return ""

    def capturar_dados_tela(self, ticker: str) -> DadosMercadoBrutos:
        """Captura dados completos da tela da corretora."""
        dados = DadosMercadoBrutos(ticker=ticker, fonte="ocr")

        if not OCR_AVAILABLE:
            return dados  # Retorna vazio — fallback para simulação

        for nome, regiao in self.regioes.items():
            img = self.capturar_tela(regiao)
            texto = self.extrair_texto(img)

            if nome == "preco":
                dados.preco_texto = texto
            elif nome == "volume":
                dados.volume_texto = texto
            elif nome == "book_compra":
                dados.book_compra_texto = self._parse_linhas(texto)
            elif nome == "book_venda":
                dados.book_venda_texto = self._parse_linhas(texto)
            elif nome == "negocios":
                dados.negocios_texto = self._parse_linhas(texto)

        dados.timestamp = time.time()
        return dados

    def _parse_linhas(self, texto: str) -> List[str]:
        """Divide texto em linhas não-vazias."""
        return [l.strip() for l in texto.splitlines() if l.strip()]

    def importar_csv(self, caminho: str, ticker: str) -> DadosMercadoBrutos:
        """
        Importa dados de CSV exportado da corretora.
        
        Formato esperado (book):
        tipo,preco,quantidade
        C,28.45,1000
        V,28.47,500
        
        Formato time & sales:
        hora,preco,quantidade,agressor
        09:30:00,28.45,200,C
        """
        dados = DadosMercadoBrutos(ticker=ticker, fonte="csv")
        
        try:
            import csv
            with open(caminho, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                linhas = list(reader)

            if not linhas:
                return dados

            campos = set(linhas[0].keys()) if linhas else set()

            # Detecta tipo de CSV
            if "agressor" in campos or "tipo_negocio" in campos:
                # Time & Sales
                for l in linhas[-50:]:
                    preco = l.get("preco", l.get("price", ""))
                    qtd = l.get("quantidade", l.get("qty", ""))
                    agr = l.get("agressor", l.get("tipo_negocio", ""))
                    dados.negocios_texto.append(f"{preco},{qtd},{agr}")

                if linhas:
                    ultimo = linhas[-1]
                    dados.preco_texto = ultimo.get("preco", ultimo.get("price", ""))

            elif "tipo" in campos:
                # Order Book
                for l in linhas:
                    tipo = l.get("tipo", "").upper()
                    preco = l.get("preco", l.get("price", ""))
                    qtd = l.get("quantidade", l.get("qty", ""))
                    linha_fmt = f"{preco},{qtd}"
                    if tipo in ("C", "COMPRA", "BUY", "B"):
                        dados.book_compra_texto.append(linha_fmt)
                    elif tipo in ("V", "VENDA", "SELL", "S"):
                        dados.book_venda_texto.append(linha_fmt)

        except Exception as e:
            pass

        dados.timestamp = time.time()
        return dados

    @staticmethod
    def parse_preco(texto: str) -> float:
        """Converte texto de preço para float (formato brasileiro)."""
        if not texto:
            return 0.0
        # Remove caracteres não-numéricos exceto , e .
        limpo = re.sub(r"[^\d,.]", "", texto.strip())
        # Normaliza separadores BR
        if "," in limpo and "." in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        try:
            return float(limpo)
        except ValueError:
            return 0.0

    @staticmethod
    def parse_volume(texto: str) -> int:
        """Converte texto de volume para inteiro."""
        limpo = re.sub(r"[^\d]", "", texto.strip())
        try:
            return int(limpo)
        except ValueError:
            return 0
