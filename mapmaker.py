"""Mapmaker do METAL MAX: monta o mapa, testa e exporta.

Roda com o python do venv do jogo (precisa do pygame e do proprio jogo no
caminho). O editor desenha cada peca chamando o `desenhar` da entidade do jogo,
entao o que aparece na tela e exatamente o que o jogo vai pintar — inclusive as
miniaturas da paleta.

    cd ~/Desktop/mapmaker
    ~/Desktop/metalmax/venv/bin/python mapmaker.py

A tecla H abre a lista completa de teclas. O mapa sai no mesmo JSON que o jogo
le: `src/mundo/mapa.py` documenta o formato.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _jogo_do_ambiente() -> Path:
    """Onde esta o jogo: `METALMAX` se estiver setado, senao do lado do mapmaker.

    As aspas sao removidas porque no Windows o jeito comum de setar e
    `set METALMAX="C:\\metalmax"`, que deixa as aspas no valor.
    """
    valor = os.environ.get("METALMAX", "").strip().strip('"').strip("'")
    return Path(valor).expanduser() if valor else RAIZ.parent / "metalmax"


JOGO = _jogo_do_ambiente()
if str(JOGO) not in sys.path:
    sys.path.insert(0, str(JOGO))

import pygame  # noqa: E402

from src.mundo import mapa as mapa_mod  # noqa: E402
from src.mundo.camera import Camera  # noqa: E402
from src.mundo.cenario import Cenario  # noqa: E402
from src.ui import estilo  # noqa: E402
from src.ui.config import ALTURA, LARGURA  # noqa: E402
from src.ui.cores import CORES  # noqa: E402

# ---------------------------------------------------------------- geometria
LARGURA_TELA, ALTURA_TELA = 1280, 760
TOPO = 56                       # barra de titulo e botoes
PAINEL = 236                    # paleta a esquerda
RODAPE = 30                     # barra de status
FAIXA = 16                      # tira do mapa inteiro, no pe do canvas
CANVAS = (LARGURA_TELA - PAINEL, ALTURA_TELA - TOPO - RODAPE)
GRADE = 8
PASSO_ZOOM = 1.15
ZOOM_MIN, ZOOM_MAX = 0.12, 3.0
LIMITE_DESFAZER = 60
ARQUIVO = RAIZ / "mapa.json"
DESTINO_EXPORTACAO = JOGO / "assets" / "mapas"

PALETA = [
    ("1", "chao", "chão"),
    ("2", "plataforma", "plataforma"),
    ("3", "bloco", "bloco"),
    ("4", "caixa", "caixa"),
    ("5", "espinho", "espinhos"),
    ("6", "mola", "mola"),
    ("7", "moeda", "moeda"),
    ("8", "pedra", "pedra"),
    ("9", "chave", "chave"),
    ("0", "porta", "porta"),
]
GIRA = {                        # ordem do giro, por tipo
    "espinho": ("cima", "direita", "baixo", "esquerda"),
    "mola": ("cima", "baixo"),
}
AMOSTRA = {                     # retangulo usado na miniatura da paleta
    "chao": (140, 26),
    "plataforma": (110, 14),
    "bloco": (40, 56),
    "caixa": (26, 26),
    "espinho": (70, 16),
    "mola": (30, 28),
    "moeda": (26, 26),
    "pedra": (26, 26),
    "chave": (22, 26),
    "porta": (44, 62),
}
TAMANHO_FIXO = ("chave", "moeda", "pedra")   # tamanho vem da entidade, nao do mapa
BOTOES = [("testar", "T  testar"), ("salvar", "Ctrl+S  salvar"), ("exportar", "Ctrl+E  exportar")]

# teclas mostradas sempre, na coluna da esquerda: (tecla, o que ela faz)
TECLAS = [
    ("R", "girar a peça"),
    ("[  ]", "largura (X)"),
    ("-  =", "altura (Y)"),
    ("Del", "apagar a peça"),
    ("Ctrl+Z", "desfazer"),
    ("N", "marcar o nascimento"),
    ("G", "ligar/desligar a grade"),
    ("T", "testar no jogo"),
    ("H", "ajuda completa"),
    ("Esc", "sair do mapmaker"),
]

TEXTO = CORES["texto"]                      # branco quente, o mesmo do HUD
FUNDO = CORES["painel"]                     # roxo do menu do jogo, nao cinza
FUNDO_ESCURO = CORES["painel_borda"]
FUNDO_CAMPO = (46, 34, 62)                  # um tom entre os dois, para campos
LINHA = (96, 78, 118)
LINHA_FORTE = (132, 108, 158)
DESTAQUE = CORES["plataforma"]              # amarelo do jogo
APAGADO = (176, 164, 198)


class Editor:
    """Estado do editor: mapa, camera, selecao, paleta e desfazer."""

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("METAL MAX - mapmaker")
        self.tela = pygame.display.set_mode((LARGURA_TELA, ALTURA_TELA))
        self.f18 = estilo.fonte(18)
        self.f22 = estilo.fonte(22)
        self.f28 = estilo.fonte(28)
        self.f14 = estilo.fonte(14)
        self.canvas = pygame.Surface(CANVAS)
        self.camera = Camera(CANVAS[0], CANVAS[1], 4000, ALTURA)
        self.cenario = Cenario(*CANVAS)
        self.zoom = 0.7
        self.camera.offset.update(0, 0)
        self.tipo = "bloco"
        self.rotacao = 0
        self.selecionado: int | None = None
        self.arrastando = False
        self.arrastando_tamanho = None      # (sentido em x, sentido em y) ou None
        self.base_tamanho = None            # (x, y, w, h) quando o arrasto comecou
        self.panando = False
        self.deslocamento = (0, 0)
        self.mouse = (PAINEL + 20, TOPO + 20)
        self.cursor_mundo = (0, 0)
        self.grade = True
        self.ajuda = False
        self.recado = "1..0 escolhe a peca, clique no cenario para por"
        self.recado_em = pygame.time.get_ticks()
        self.teste: subprocess.Popen | None = None
        self.teste_salvo = RAIZ / "_teste.json"
        self.mapa = self._abrir(ARQUIVO) or self._do_jogo()
        self.entidades: list[tuple[dict, object]] = []
        self.sujo = True
        self.desfazer: list[list[dict]] = []
        self.miniaturas = self._miniaturas()
        self.hover = None

    # ------------------------------------------------------------- arquivos
    def _do_jogo(self) -> dict:
        """Comeca com o mapa do jogo, para nao abrir numa tela vazia."""
        try:
            return mapa_mod.carregar()
        except Exception:
            return mapa_mod.padrao()

    def _abrir(self, caminho: Path) -> dict | None:
        if not caminho.exists():
            return None
        try:
            return mapa_mod.normalizar(json.loads(caminho.read_text(encoding="utf-8")))
        except ValueError:
            self._diz(f"{caminho.name} nao e um mapa valido")
            return None

    def _salvar(self, caminho: Path) -> bool:
        """Grava o mapa; arquivo travado ou pasta sem permissao vira aviso, nao erro."""
        self.mapa["largura_mundo"] = max(self.mapa["largura_mundo"], self._limite_direito() + 200)
        try:
            mapa_mod.salvar(self.mapa, caminho)
        except OSError as erro:
            self._diz(f"nao consegui salvar em {caminho}: {erro}")
            return False
        self._diz(f"salvo em {caminho}")
        return True

    def _limite_direito(self) -> int:
        return max((o["x"] + o["w"] for o in self.mapa["objetos"]), default=0)

    def _exportar(self) -> None:
        """Grava o mapa na pasta do jogo, guardando um .bak do que estava la.

        Exportar por cima do mapa do jogo e o uso normal — mas sem backup um
        Ctrl+E distraido apaga a versao anterior sem aviso.
        """
        nome = f"{self.mapa.get('nome', 'mapa')}.json"
        destino = DESTINO_EXPORTACAO / nome
        aviso = ""
        try:
            if destino.exists():
                copia = destino.with_suffix(destino.suffix + ".bak")
                copia.write_bytes(destino.read_bytes())
                aviso = f" (o anterior virou {copia.name})"
        except OSError as erro:
            self._diz(f"nao consegui copiar o mapa antigo: {erro}")
            return
        if self._salvar(destino):
            self._diz(f"exportado: {destino}{aviso}")

    def _diz(self, texto: str) -> None:
        self.recado = texto
        self.recado_em = pygame.time.get_ticks()

    # -------------------------------------------------------------- edicao
    def _lembrar(self) -> None:
        self.desfazer.append(copy.deepcopy(self.mapa["objetos"]))
        del self.desfazer[:-LIMITE_DESFAZER]

    def _desfazer(self) -> None:
        if self.desfazer:
            self.mapa["objetos"] = self.desfazer.pop()
            self.selecionado = None
            self.sujo = True
            self._diz("desfeito")

    def _encaixar(self, valor: float) -> int:
        return int(round(valor / GRADE) * GRADE) if self.grade else int(valor)

    def _mundo(self, tela_pos: tuple[int, int]) -> tuple[int, int]:
        """Ponto da tela -> coordenadas do mundo."""
        return (int((tela_pos[0] - PAINEL) / self.zoom + self.camera.offset.x),
                int((tela_pos[1] - TOPO) / self.zoom + self.camera.offset.y))

    def _tela(self, mundo: tuple[float, float]) -> tuple[int, int]:
        return (round((mundo[0] - self.camera.offset.x) * self.zoom) + PAINEL,
                round((mundo[1] - self.camera.offset.y) * self.zoom) + TOPO)

    def _retangulo(self, o: dict) -> pygame.Rect:
        return pygame.Rect(o["x"], o["y"], o["w"], o["h"])

    def _sob_o_cursor(self, mundo: tuple[int, int]) -> int | None:
        for i in range(len(self.mapa["objetos"]) - 1, -1, -1):
            if self._retangulo(self.mapa["objetos"][i]).collidepoint(mundo):
                return i
        return None

    def _no_canvas(self, pos: tuple[int, int]) -> bool:
        return PAINEL <= pos[0] < LARGURA_TELA and TOPO <= pos[1] < TOPO + CANVAS[1]

    def _direcao(self) -> str | None:
        if self.tipo not in GIRA:
            return None
        return GIRA[self.tipo][self.rotacao % len(GIRA[self.tipo])]

    def colocar(self, mundo: tuple[int, int]) -> None:
        largura, altura = mapa_mod.PADROES[self.tipo]
        if self.tipo in GIRA and len(GIRA[self.tipo]) == 4 and self.rotacao % 2:
            largura, altura = altura, largura
        x = self._encaixar(mundo[0] - largura / 2)
        y = self._encaixar(mundo[1] - altura / 2)
        self._lembrar()
        self.mapa["objetos"].append(mapa_mod.objeto(self.tipo, x, y, largura, altura, self._direcao()))
        self.selecionado = len(self.mapa["objetos"]) - 1
        self.sujo = True
        self._diz(f"{self.tipo} em ({x}, {y})")

    def girar(self, passo: int = 1) -> None:
        """Gira a selecao (ou o padrao da paleta): direcao ou troca de lado."""
        if self.selecionado is None:
            self.rotacao = (self.rotacao + passo) % 4
            self._diz(f"padrao da paleta: {self._direcao() or 'sem giro'}")
            return
        self._lembrar()
        o = self.mapa["objetos"][self.selecionado]
        if o["tipo"] in GIRA:
            opcoes = GIRA[o["tipo"]]
            atual = opcoes.index(o["direcao"]) if o.get("direcao") in opcoes else 0
            o["direcao"] = opcoes[(atual + passo) % len(opcoes)]
        elif o["tipo"] not in ("chave", "moeda", "pedra"):
            o["w"], o["h"] = o["h"], o["w"]
        self.sujo = True
        self._diz(f"{o['tipo']} girado")

    def redimensionar(self, passo: int, eixo: str) -> None:
        """Cresce/encolhe a selecao: `eixo` e "x" (largura) ou "y" (altura)."""
        if self.selecionado is None:
            return
        o = self.mapa["objetos"][self.selecionado]
        if o["tipo"] in TAMANHO_FIXO:
            self._diz(f"{o['tipo']} tem tamanho proprio, nao muda")
            return
        self._lembrar()
        campo = "w" if eixo == "x" else "h"
        o[campo] = max(GRADE, o[campo] + passo * GRADE)
        self.sujo = True

    def _arrastar_tamanho(self, mundo: tuple[int, int]) -> None:
        """Redimensiona pela alca que esta sendo puxada, eixo a eixo."""
        if self.arrastando_tamanho is None or self.selecionado is None:
            return
        o = self.mapa["objetos"][self.selecionado]
        sentido_x, sentido_y = self.arrastando_tamanho
        x0, y0, w0, h0 = self.base_tamanho
        if sentido_x:
            alvo = self._encaixar(mundo[0])
            if sentido_x > 0:                       # alca da direita: mexe na largura
                o["w"] = max(GRADE, alvo - x0)
            else:                                   # alca da esquerda: mexe na largura e no x
                novo_x = min(alvo, x0 + w0 - GRADE)
                o["x"] = novo_x
                o["w"] = x0 + w0 - novo_x
        if sentido_y:
            alvo = self._encaixar(mundo[1])
            if sentido_y > 0:
                o["h"] = max(GRADE, alvo - y0)
            else:
                novo_y = min(alvo, y0 + h0 - GRADE)
                o["y"] = novo_y
                o["h"] = y0 + h0 - novo_y
        self.sujo = True

    def apagar(self) -> None:
        if self.selecionado is None:
            return
        self._lembrar()
        o = self.mapa["objetos"].pop(self.selecionado)
        self.selecionado = None
        self.sujo = True
        self._diz(f"{o['tipo']} apagado")

    def mover_selecionado(self, dx: int, dy: int) -> None:
        if self.selecionado is None:
            return
        o = self.mapa["objetos"][self.selecionado]
        o["x"] += dx
        o["y"] += dy
        self.sujo = True

    def marcar_nascimento(self, mundo: tuple[int, int]) -> None:
        self.mapa["nascer"] = {"x": self._encaixar(mundo[0]), "y": self._encaixar(mundo[1])}
        self._diz(f"o pug nasce em ({self.mapa['nascer']['x']}, {self.mapa['nascer']['y']})")

    def testar(self) -> None:
        """Abre o jogo de verdade com o mapa atual, num processo separado."""
        mapa_mod.salvar(self.mapa, self.teste_salvo)
        ambiente = dict(os.environ, METALMAX_MAPA=str(self.teste_salvo))
        try:
            self.teste = subprocess.Popen([sys.executable, str(JOGO / "main.py")], cwd=str(JOGO), env=ambiente)
            self._diz("testando no jogo: feche a janela do jogo para voltar")
        except OSError as erro:
            self.teste = None
            self._diz(f"nao consegui abrir o jogo: {erro}")

    def _texto(self, conteudo: str, cor, pos=None, *, fonte=None, centro=None) -> pygame.Rect:
        """Texto de painel: sem contorno.

        O contorno do `estilo.texto` existe para letra em cima do cenario; em
        painel escuro ele engrossa o glifo e a letra vira um borrao.
        """
        fonte = fonte or self.f18
        imagem = fonte.render(conteudo, True, cor)
        destino = imagem.get_rect()
        if centro is not None:
            destino.center = centro
        else:
            destino.topleft = pos
        self.tela.blit(imagem, destino)
        return destino

    # ---------------------------------------------------------- miniaturas
    def _miniaturas(self) -> dict[str, pygame.Surface]:
        """Desenha cada peca num quadradinho, usando o desenho do jogo."""
        mini = {}
        for _, tipo, _ in PALETA:
            largura, altura = AMOSTRA[tipo]
            alvo = pygame.Surface((44, 40))
            alvo.fill(FUNDO_ESCURO)
            _, entidade = mapa_mod.construir(mapa_mod.objeto(tipo, 0, 0, largura, altura))
            if entidade is None:
                mini[tipo] = alvo
                continue
            camera = Camera(44, 40, largura, altura)
            camera.escala = min((44 - 6) / largura, (40 - 6) / altura)
            camera.offset.update(-3 / camera.escala, -3 / camera.escala)
            entidade.desenhar(alvo, camera)
            mini[tipo] = alvo
        return mini

    # -------------------------------------------------------------- desenho
    def _atualizar_entidades(self) -> None:
        if not self.sujo:
            return
        self.entidades = []
        for o in self.mapa["objetos"]:
            _, entidade = mapa_mod.construir(o)
            if entidade is not None:
                self.entidades.append((o, entidade))
        self.sujo = False

    def _desenhar_canvas(self) -> None:
        """Cenario do jogo, grade, pecas e sobreposicoes, na ordem certa."""
        self.canvas.blit(self._fundo(), (0, 0))
        self.camera.escala = self.zoom
        for _, entidade in self.entidades:
            entidade.desenhar(self.canvas, self.camera)
        self.camera.escala = 1.0
        self._desenhar_grade()
        self._desenhar_marcas()
        self.tela.blit(self.canvas, (PAINEL, TOPO))

    def _fundo(self) -> pygame.Surface:
        """O mesmo cenario do jogo, escurecido para as pecas aparecerem."""
        self.camera.escala = self.zoom
        self.cenario.desenhar(self.canvas, self.camera)
        self.camera.escala = 1.0
        veu = pygame.Surface(CANVAS)
        veu.fill((16, 20, 34))
        veu.set_alpha(92)
        self.canvas.blit(veu, (0, 0))
        return self.canvas

    def _desenhar_grade(self) -> None:
        if not self.grade:
            return
        passo = GRADE * 8
        x0, y0 = self.camera.offset
        x1, y1 = x0 + CANVAS[0] / self.zoom, y0 + CANVAS[1] / self.zoom
        for x in range(int(x0 // passo) * passo, int(x1) + passo, passo):
            px = round((x - x0) * self.zoom)
            pygame.draw.line(self.canvas, LINHA_FORTE if x % (passo * 4) == 0 else LINHA, (px, 0), (px, CANVAS[1]))
        for y in range(int(y0 // passo) * passo, int(y1) + passo, passo):
            py = round((y - y0) * self.zoom)
            pygame.draw.line(self.canvas, LINHA_FORTE if y % (passo * 4) == 0 else LINHA, (0, py), (CANVAS[0], py))

    def _desenhar_marcas(self) -> None:
        """Chao, limites do mundo, nascimento, selecao e a peca fantasma."""
        x0, y0 = self.camera.offset
        chao = round((self.mapa["chao_y"] - y0) * self.zoom)
        if 0 <= chao < CANVAS[1]:
            pygame.draw.line(self.canvas, CORES["plataforma"], (0, chao), (CANVAS[0], chao))
            estilo.texto(self.canvas, self.f18, "chão", CORES["plataforma"], pos=(6, chao + 3))
        limite = round((self.mapa["largura_mundo"] - x0) * self.zoom)
        if 0 <= limite < CANVAS[0]:
            pygame.draw.line(self.canvas, CORES["sombra"], (limite, 0), (limite, CANVAS[1]), 3)
        nascimento = self.mapa.get("nascer")
        if nascimento:
            px, py = round((nascimento["x"] - x0) * self.zoom), round((nascimento["y"] - y0) * self.zoom)
            if -20 <= px <= CANVAS[0] + 20:
                estilo.bola(self.canvas, (px, py), 7, CORES["coracao"])
                estilo.texto(self.canvas, self.f18, "nasce", CORES["coracao"], pos=(px + 12, py - 8))
        for i, o in enumerate(self.mapa["objetos"]):
            alvo = self._retangulo(o)
            px, py = round((alvo.x - x0) * self.zoom), round((alvo.y - y0) * self.zoom)
            caixa = pygame.Rect(px, py, max(2, round(alvo.w * self.zoom)), max(2, round(alvo.h * self.zoom)))
            if i == self.selecionado:
                pygame.draw.rect(self.canvas, TEXTO, caixa, 2)
                for _, alca, _, _ in self._alcas():
                    pygame.draw.rect(self.canvas, TEXTO, alca)
                    pygame.draw.rect(self.canvas, FUNDO, alca, 1)
            elif i == self.hover:
                pygame.draw.rect(self.canvas, DESTAQUE, caixa, 1)
        if self._no_canvas(self.mouse) and self._sob_o_cursor(self.cursor_mundo) is None:
            self._desenhar_fantasma()
        px, py = round((self.cursor_mundo[0] - x0) * self.zoom), round((self.cursor_mundo[1] - y0) * self.zoom)
        if 0 <= px < CANVAS[0] and 0 <= py < CANVAS[1]:
            pygame.draw.line(self.canvas, DESTAQUE, (px - 7, py), (px + 7, py), 1)
            pygame.draw.line(self.canvas, DESTAQUE, (px, py - 7), (px, py + 7), 1)

    def _alcas(self) -> list[tuple[str, pygame.Rect, int, int]]:
        """Alcas da peca selecionada: (nome, retangulo, sentido em x, sentido em y).

        Cantos mudam largura e altura; os meios mudam so um eixo.
        """
        if self.selecionado is None:
            return []
        o = self.mapa["objetos"][self.selecionado]
        if o["tipo"] in TAMANHO_FIXO:
            return []
        alvo = self._retangulo(o)
        x0, y0 = self.camera.offset
        esquerda = round((alvo.x - x0) * self.zoom)
        topo = round((alvo.y - y0) * self.zoom)
        caixa = pygame.Rect(esquerda, topo, max(2, round(alvo.w * self.zoom)), max(2, round(alvo.h * self.zoom)))
        meio = 4
        pontos = {
            "nw": (caixa.left, caixa.top, -1, -1), "n": (caixa.centerx, caixa.top, 0, -1),
            "ne": (caixa.right, caixa.top, 1, -1), "e": (caixa.right, caixa.centery, 1, 0),
            "se": (caixa.right, caixa.bottom, 1, 1), "s": (caixa.centerx, caixa.bottom, 0, 1),
            "sw": (caixa.left, caixa.bottom, -1, 1), "w": (caixa.left, caixa.centery, -1, 0),
        }
        return [(nome, pygame.Rect(x - meio, y - meio, meio * 2, meio * 2), sx, sy)
                for nome, (x, y, sx, sy) in pontos.items()]

    def _alca_sob_o_mouse(self) -> tuple[int, int] | None:
        """Alca sob o cursor, em coordenadas do canvas (o mouse vem da tela)."""
        local = (self.mouse[0] - PAINEL, self.mouse[1] - TOPO)
        for _, alca, sx, sy in self._alcas():
            if alca.collidepoint(local):
                return sx, sy
        return None

    def _desenhar_fantasma(self) -> None:
        """Mostra, apagada, a peca que vai nascer no clique."""
        largura, altura = mapa_mod.PADROES[self.tipo]
        if self.tipo in GIRA and len(GIRA[self.tipo]) == 4 and self.rotacao % 2:
            largura, altura = altura, largura
        x = self._encaixar(self.cursor_mundo[0] - largura / 2)
        y = self._encaixar(self.cursor_mundo[1] - altura / 2)
        _, entidade = mapa_mod.construir(mapa_mod.objeto(self.tipo, x, y, largura, altura, self._direcao()))
        if entidade is None:
            return
        fantasma = pygame.Surface(CANVAS, pygame.SRCALPHA)
        camera = Camera(CANVAS[0], CANVAS[1], 4000, ALTURA)
        camera.escala = self.zoom
        camera.offset.update(self.camera.offset)
        entidade.desenhar(fantasma, camera)
        fantasma.set_alpha(130)
        self.canvas.blit(fantasma, (0, 0))

    def _desenhar_faixa(self) -> None:
        """Tira com o mapa inteiro: onde a camera esta e onde estao as pecas."""
        caixa = pygame.Rect(PAINEL + 8, TOPO + CANVAS[1] - FAIXA - 6, CANVAS[0] - 16, FAIXA)
        estilo.painel(self.tela, caixa, FUNDO_CAMPO, raio=3)
        total = max(1, self.mapa["largura_mundo"])
        for o in self.mapa["objetos"]:
            x = caixa.x + 4 + round((o["x"] / total) * (caixa.w - 8))
            pygame.draw.line(self.tela, CORES["plataforma"] if o["tipo"] == "chao" else DESTAQUE,
                             (x, caixa.y + 3), (x, caixa.bottom - 3), 1)
        inicio = caixa.x + 4 + round((self.camera.offset.x / total) * (caixa.w - 8))
        largura = round((CANVAS[0] / self.zoom / total) * (caixa.w - 8))
        pygame.draw.rect(self.tela, TEXTO, pygame.Rect(inicio, caixa.y + 2, max(6, largura), caixa.h - 4), 1)

    def _desenhar_paleta(self) -> None:
        estilo.painel(self.tela, pygame.Rect(6, TOPO + 6, PAINEL - 12, ALTURA_TELA - TOPO - 12), FUNDO)
        self._texto("PEÇAS", DESTAQUE, (18, TOPO + 12), fonte=self.f22)
        for i, (tecla, tipo, rotulo) in enumerate(PALETA):
            caixa = self._caixa_paleta(i)
            if tipo == self.tipo:
                estilo.painel(self.tela, caixa, CORES["botao"], raio=4)
            else:
                cor_linha = CORES["botao_hover"] if i == self.hover_paleta else FUNDO_CAMPO
                estilo.painel(self.tela, caixa, cor_linha, raio=4)
            self.tela.blit(self.miniaturas[tipo], (caixa.x + 6, caixa.y + 2))
            cor = CORES["botao_texto"] if tipo == self.tipo else TEXTO
            self._texto(rotulo, cor, (caixa.x + 58, caixa.y + 5))
            self._tecla_desenho(tecla, pygame.Rect(caixa.right - 26, caixa.y + 9, 20, 20), cor)
            if tipo in GIRA:
                giro = self._direcao() if tipo == self.tipo and self.selecionado is None else None
                self._texto(giro or "gira com R", APAGADO if not giro else cor, (caixa.x + 58, caixa.y + 22), fonte=self.f14)
        self._desenhar_teclas()

    def _desenhar_teclas(self) -> None:
        """Lista curta de teclas, sempre visivel embaixo da paleta."""
        topo = TOPO + 42 + len(PALETA) * 42 + 8
        caixa = pygame.Rect(12, topo, PAINEL - 24, ALTURA_TELA - topo - 18)
        estilo.painel(self.tela, caixa, FUNDO_CAMPO, raio=4)
        self._texto("TECLAS", DESTAQUE, (caixa.x + 8, caixa.y + 5), fonte=self.f22)
        for i, (tecla, acao) in enumerate(TECLAS):
            y = caixa.y + 30 + i * 18
            self._tecla_desenho(tecla, pygame.Rect(caixa.x + 8, y, 54, 17), TEXTO)
            self._texto(acao, TEXTO, (caixa.x + 68, y))

    def _tecla_desenho(self, tecla: str, caixa: pygame.Rect, cor) -> None:
        """Desenha a tecla como uma tecla mesmo: caixinha com contorno."""
        pygame.draw.rect(self.tela, FUNDO_ESCURO, caixa, border_radius=3)
        pygame.draw.rect(self.tela, cor, caixa, width=1, border_radius=3)
        self._texto(tecla, cor, centro=(caixa.centerx, caixa.centery), fonte=self.f14)

    def _caixa_paleta(self, indice: int) -> pygame.Rect:
        return pygame.Rect(12, TOPO + 42 + indice * 42, PAINEL - 24, 38)

    @property
    def hover_paleta(self) -> int:
        for i in range(len(PALETA)):
            if self._caixa_paleta(i).collidepoint(self.mouse):
                return i
        return -1

    def _desenhar_topo(self) -> None:
        estilo.painel(self.tela, pygame.Rect(0, 0, LARGURA_TELA, TOPO), FUNDO, raio=0)
        self._texto("MAPMAKER", DESTAQUE, (16, 12), fonte=self.f28)
        self._texto(f"METAL MAX   mapa: {self.mapa.get('nome', '?')}   "
                    f"{len(self.mapa['objetos'])} peças", TEXTO, (170, 20))
        for i, (acao, rotulo) in enumerate(BOTOES):
            caixa = self._caixa_botao(i)
            cor = CORES["botao_hover"] if caixa.collidepoint(self.mouse) else CORES["botao"]
            estilo.painel(self.tela, caixa, cor, raio=4)
            self._texto(rotulo, CORES["botao_texto"], centro=(caixa.centerx, caixa.centery))

    def _caixa_botao(self, indice: int) -> pygame.Rect:
        largura = 150
        x = LARGURA_TELA - (len(BOTOES) - indice) * (largura + 8) - 8
        return pygame.Rect(x, 12, largura, 32)

    def _desenhar_rodape(self) -> None:
        estilo.painel(self.tela, pygame.Rect(0, ALTURA_TELA - RODAPE, LARGURA_TELA, RODAPE), FUNDO, raio=0)
        selecao = self._rotulo_selecao()
        estado = f"grade {'ligada' if self.grade else 'desligada'}   zoom {self.zoom:.2f}   " \
                 f"cursor ({self.cursor_mundo[0]}, {self.cursor_mundo[1]})"
        self._texto(estado, TEXTO, (12, ALTURA_TELA - RODAPE + 5))
        self._texto(selecao, DESTAQUE, (430, ALTURA_TELA - RODAPE + 5))
        recente = pygame.time.get_ticks() - self.recado_em < 6000
        recado = self.recado if recente else self._dica()
        self._texto(recado, (168, 230, 168), (780, ALTURA_TELA - RODAPE + 5))

    def _dica(self) -> str:
        """O que fazer agora, conforme o que esta debaixo do cursor."""
        if self.arrastando:
            return "arrastando a peça: solte para largar   (as alças mudam X e Y)"
        if self.selecionado is not None:
            return "R gira   [ ] largura (X)   - = altura (Y)   setas empurram   Del apaga"
        if self._no_canvas(self.mouse) and self._sob_o_cursor(self.cursor_mundo) is not None:
            return "clique para pegar a peça   direito apaga"
        return f"clique no cenário para pôr {self.tipo}   R gira antes de pôr"

    def _rotulo_selecao(self) -> str:
        if self.selecionado is None:
            return "nada selecionado"
        o = self.mapa["objetos"][self.selecionado]
        direcao = f" {o['direcao']}" if o.get("direcao") else ""
        return f"{o['tipo']}{direcao}  ({o['x']}, {o['y']})  largura {o['w']}  altura {o['h']}"

    def _desenhar_ajuda(self) -> None:
        if not self.ajuda:
            return
        caixa = pygame.Rect(PAINEL + 40, TOPO + 40, 700, 400)
        estilo.painel(self.tela, caixa, FUNDO)
        self._texto("COMO MEXER", DESTAQUE, (caixa.x + 20, caixa.y + 14), fonte=self.f28)
        esquerda, direita = caixa.x + 20, caixa.x + 360
        self._texto("MOUSE", DESTAQUE, (esquerda, caixa.y + 58), fonte=self.f22)
        for i, linha in enumerate([
            "esquerdo: pega ou põe a peça",
            "arrastar: move a peça",
            "alças: mudam X e Y na mão",
            "direito: apaga a peça",
            "roda: zoom",
            "botão do meio: arrasta a tela",
        ]):
            self._texto(linha, TEXTO, (esquerda, caixa.y + 86 + i * 24))
        self._texto("MAPA", DESTAQUE, (esquerda, caixa.y + 214), fonte=self.f22)
        for i, linha in enumerate([
            "a linha amarela é o chão",
            "a tira no pé mostra o mapa inteiro",
            "T testa o mapa no jogo de verdade",
            "Ctrl+E grava em metalmax/assets/mapas",
        ]):
            self._texto(linha, TEXTO, (esquerda, caixa.y + 242 + i * 24))
        self._texto("TECLADO", DESTAQUE, (direita, caixa.y + 58), fonte=self.f22)
        for i, (tecla, acao) in enumerate([
            ("1..0", "escolhe a peça"),
            ("R", "gira a peça"),
            ("[  ]", "largura (X)"),
            ("-  =", "altura (Y)"),
            ("setas", "empurra (shift: 8 px)"),
            ("Del", "apaga"),
            ("Ctrl+Z", "desfaz"),
            ("N", "marca o nascimento"),
            ("G", "liga/desliga a grade"),
            ("Ctrl+S", "salva"),
            ("Ctrl+O", "abre"),
        ]):
            y = caixa.y + 86 + i * 23
            self._tecla_desenho(tecla, pygame.Rect(direita, y, 58, 18), TEXTO)
            self._texto(acao, TEXTO, (direita + 74, y))
        self._texto("cada peça aqui é desenhada pelo próprio jogo", DESTAQUE,
                    (caixa.x + 20, caixa.bottom - 32))

    def desenhar(self) -> None:
        self._atualizar_entidades()
        self.tela.fill(FUNDO)
        self._desenhar_canvas()
        self._desenhar_paleta()
        self._desenhar_topo()
        self._desenhar_faixa()
        self._desenhar_rodape()
        self._desenhar_ajuda()

    # -------------------------------------------------------------- eventos
    def tratar(self, evento: pygame.event.Event) -> bool:
        """Trata um evento; devolve False quando e para fechar o editor."""
        if evento.type == pygame.QUIT:
            return False
        if evento.type == pygame.MOUSEMOTION:
            self.mouse = evento.pos
            if self.panando:
                self.camera.offset.x -= evento.rel[0] / self.zoom
                self.camera.offset.y -= evento.rel[1] / self.zoom
            if self.arrastando_tamanho is not None:
                self._arrastar_tamanho(self._mundo(evento.pos))
            if self.arrastando and self.selecionado is not None:
                mundo = self._mundo(evento.pos)
                o = self.mapa["objetos"][self.selecionado]
                self.mover_selecionado(self._encaixar(mundo[0] - self.deslocamento[0]) - o["x"],
                                       self._encaixar(mundo[1] - self.deslocamento[1]) - o["y"])
            self.hover = self._sob_o_cursor(self._mundo(evento.pos)) if self._no_canvas(evento.pos) else None
            return True
        if evento.type == pygame.MOUSEWHEEL:
            self._zoom(evento.y)
            return True
        if evento.type == pygame.MOUSEBUTTONDOWN:
            self._clique(evento)
            return True
        if evento.type == pygame.MOUSEBUTTONUP:
            if self.arrastando_tamanho is not None:
                o = self.mapa["objetos"][self.selecionado]
                self._diz(f"{o['tipo']} agora tem {o['w']} x {o['h']}")
            self.arrastando = False
            self.arrastando_tamanho = None
            self.base_tamanho = None
            self.panando = False
            return True
        if evento.type == pygame.KEYDOWN:
            return self._tecla(evento)
        return True

    def _zoom(self, passos: int) -> None:
        antes = self._mundo(self.mouse)
        self.zoom = min(ZOOM_MAX, max(ZOOM_MIN, self.zoom * (PASSO_ZOOM ** passos)))
        depois = self._mundo(self.mouse)
        self.camera.offset.x += antes[0] - depois[0]
        self.camera.offset.y += antes[1] - depois[1]

    def _clique(self, evento: pygame.event.Event) -> None:
        if self.mouse[1] < TOPO:
            for i, (acao, _) in enumerate(BOTOES):
                if self._caixa_botao(i).collidepoint(self.mouse):
                    {"testar": self.testar, "salvar": lambda: self._salvar(ARQUIVO),
                     "exportar": self._exportar}[acao]()
                    return
            return
        if self.mouse[0] < PAINEL:
            indice = self.hover_paleta
            if indice >= 0:
                self.tipo = PALETA[indice][1]
                self.selecionado = None
                self._diz(f"peça: {self.tipo}")
            return
        if not self._no_canvas(self.mouse):
            return
        mundo = self._mundo(self.mouse)
        if evento.button == 3:
            achado = self._sob_o_cursor(mundo)
            if achado is not None:
                self.selecionado = achado
                self.apagar()
            return
        if evento.button == 2:
            self.panando = True
            return
        if evento.button == 1:
            alca = self._alca_sob_o_mouse()
            if alca is not None:
                o = self.mapa["objetos"][self.selecionado]
                self._lembrar()
                self.arrastando_tamanho = alca
                self.base_tamanho = (o["x"], o["y"], o["w"], o["h"])
                self._diz("arrastando a alça: largura e altura saem da grade de 8")
                return
            achado = self._sob_o_cursor(mundo)
            if achado is None:
                self.colocar(mundo)
            else:
                self.selecionado = achado
                o = self.mapa["objetos"][achado]
                self.deslocamento = (mundo[0] - o["x"], mundo[1] - o["y"])
                self.arrastando = True
                self._lembrar()

    def _tecla(self, evento: pygame.event.Event) -> bool:
        tecla = evento.key
        # o mod vem do proprio evento: e o que vale quando o comando e simulado
        mods = getattr(evento, "mod", 0) or pygame.key.get_mods()
        ctrl = mods & pygame.KMOD_CTRL
        if tecla == pygame.K_ESCAPE:
            if self.ajuda:
                self.ajuda = False
                return True
            return False
        if ctrl and tecla == pygame.K_s:
            self._salvar(ARQUIVO)
        elif ctrl and tecla == pygame.K_o:
            novo = self._abrir(ARQUIVO)
            if novo:
                self.mapa = novo
                self.selecionado = None
                self.sujo = True
                self._diz(f"aberto {ARQUIVO}")
        elif ctrl and tecla == pygame.K_e:
            self._exportar()
        elif ctrl and tecla == pygame.K_z:
            self._desfazer()
        elif tecla == pygame.K_t:
            self.testar()
        elif tecla == pygame.K_r:
            self.girar(-1 if mods & pygame.KMOD_SHIFT else 1)
        elif tecla in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            self.redimensionar(1 if tecla == pygame.K_RIGHTBRACKET else -1, "x")
        elif tecla in (pygame.K_MINUS, pygame.K_EQUALS):
            self.redimensionar(1 if tecla == pygame.K_EQUALS else -1, "y")
        elif tecla == pygame.K_DELETE:
            self.apagar()
        elif tecla == pygame.K_n:
            self.marcar_nascimento(self._mundo(self.mouse))
        elif tecla == pygame.K_g:
            self.grade = not self.grade
            self._diz(f"grade {'ligada' if self.grade else 'desligada'}")
        elif tecla == pygame.K_h:
            self.ajuda = not self.ajuda
        elif tecla in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            passo = GRADE if mods & pygame.KMOD_SHIFT else 1
            dx = (tecla == pygame.K_RIGHT) - (tecla == pygame.K_LEFT)
            dy = (tecla == pygame.K_DOWN) - (tecla == pygame.K_UP)
            self.mover_selecionado(dx * passo, dy * passo)
        else:
            for tecla_txt, tipo, _ in PALETA:
                if tecla == getattr(pygame, f"K_{tecla_txt}", None):
                    self.tipo = tipo
                    self._diz(f"peça: {tipo}")
        return True

    # ---------------------------------------------------------------- loop
    def rodar(self) -> None:
        rodando = True
        relogio = pygame.time.Clock()
        while rodando:
            if self.teste is not None:
                pygame.event.pump()           # nao deixa a janela do editor "travar"
                if self.teste.poll() is None:
                    pygame.time.wait(50)      # o jogo esta na frente; espera fechar
                    continue
                self.teste = None
                self.teste_salvo.unlink(missing_ok=True)
                self._diz("teste encerrado")
            for evento in pygame.event.get():
                rodando = self.tratar(evento)
                if not rodando:
                    break
            self.cursor_mundo = self._mundo(self.mouse)
            self.desenhar()
            pygame.display.flip()
            relogio.tick(60)
        pygame.quit()


def main() -> int:
    if not (JOGO / "main.py").exists():
        print(f"nao achei o jogo em {JOGO}. Ajuste com a variavel METALMAX.")
        return 1
    Editor().rodar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
