# Mapmaker do METAL MAX

Editor de mapa que usa as **peças do próprio jogo**: cada peça na tela é desenhada
pelo `desenhar` da entidade (`Espinhos`, `Mola`, `BlocoGrama`, `Plataforma`,
`CaixaSolida`, `Moeda`, `Pedra`, `Chave`, `Porta`). O que você monta aqui é o que
o jogo pinta.

## Rodar

```bash
cd ~/Desktop/mapmaker
~/Desktop/metalmax/venv/bin/python mapmaker.py
```

Precisa do pygame e do jogo: por padrão ele procura o jogo do lado do mapmaker
(`~/Desktop/metalmax`). Se estiver em outro lugar:

```bash
METALMAX=/caminho/do/jogo ~/Desktop/metalmax/venv/bin/python mapmaker.py
```

Ele abre o rascunho `mapmaker/mapa.json` se já existir; senão abre o mapa que o
jogo usa (`metalmax/assets/mapas/nivel1.json`).

### Windows

O python do venv fica em `Scripts` e o `set` precisa de `%USERPROFILE%`:

```bat
cd %USERPROFILE%\Desktop\mapmaker
%USERPROFILE%\Desktop\metalmax\venv\Scripts\python.exe mapmaker.py
```

Para apontar o jogo em outro lugar (PowerShell usa `$env:`):

```bat
set METALMAX=%USERPROFILE%\Desktop\metalmax
```

```powershell
$env:METALMAX = "$env:USERPROFILE\Desktop\metalmax"
```

O editor aceita o valor com ou sem aspas, então `set METALMAX="C:\jogo"` também
funciona. O mesmo vale para `METALMAX_MAPA` ao rodar o jogo.

O mapa exportado é JSON puro (tipo, retângulo e direção) — **não guarda caminho
nenhum**, então o mesmo arquivo serve no Linux e no Windows. Se um arquivo
estiver travado na hora de salvar ou exportar, o editor avisa no rodapé em vez de
fechar.

## A tela

- **barra de cima**: nome do mapa, contagem de peças e os botões *testar*,
  *salvar* e *exportar* (clicáveis, com a tecla ao lado).
- **coluna da esquerda**: a lista de peças — cada linha mostra a peça **desenhada
  pelo próprio jogo** (miniatura), o nome e a tecla. A peça escolhida fica
  acesa; as que giram mostram a direção atual. Embaixo, a lista fixa de teclas.
- **cenário**: o fundo é o cenário do jogo, com grade de 8 px (linha mais forte a
  cada 64), a linha amarela do chão e a marca de onde o pug nasce. A peça que vai
  nascer aparece apagada (fantasma) antes do clique.
- **rodapé**: grade, zoom, posição do cursor, o que está selecionado e uma dica do
  que fazer agora.
- **tira no pé do cenário**: o mapa inteiro em miniatura, com a área visível
  marcada — útil num mapa de 3830 px.

`H` abre o painel de ajuda com tudo em duas colunas.

## Teclas

| Ação | Como |
|---|---|
| escolher a peça | clique na lista da esquerda ou `1`..`0` |
| colocar | clique esquerdo no vazio (nasce centrada no cursor, encaixada na grade) |
| selecionar / mover | clique na peça e arraste |
| apagar | clique direito na peça, ou `Del` |
| girar | `R` (shift+`R` gira ao contrário) |
| **largura (X)** | `[` diminui, `]` aumenta (passo de 8 px) |
| **altura (Y)** | `-` diminui, `=` aumenta (passo de 8 px) |
| **X e Y na mão** | arraste uma das **alças** da peça selecionada: os cantos mudam os dois eixos, os meios mudam só um |
| empurrar | setas (`shift` = 8 px) |
| grade 8 px | `G` liga/desliga |
| nascimento do pug | `N` marca no cursor |
| desfazer | `Ctrl+Z` |
| salvar / abrir | `Ctrl+S` / `Ctrl+O` (`mapmaker/mapa.json`) |
| **exportar pro jogo** | `Ctrl+E` (grava em `metalmax/assets/mapas/`) |
| **testar** | `T` — abre o jogo de verdade com o mapa atual; feche a janela do jogo para voltar |
| zoom / arrastar a tela | roda do mouse / botão do meio |
| ajuda | `H` |

A linha amarela é o chão (`chao_y`): as alturas do mapa são contadas a partir dela.

## O que o giro faz em cada peça

- **espinhos**: `cima` → `direita` → `baixo` → `esquerda` (serra no chão, pendurada
  ou de parede).
- **mola**: `cima` (quem cai em cima sobe) ou `baixo` (quem bate de baixo é jogado
  para baixo).
- **bloco, caixa, plataforma, chão**: troca largura por altura (deitado ou em pé).
- **chave, moeda, pedra**: não giram e não redimensionam — o tamanho dessas vem
  da entidade no jogo, e o mapa só guarda a posição.

## Formato do mapa

JSON, o mesmo que `src/mundo/mapa.py` lê:

```json
{
  "versao": 1,
  "nome": "nivel1",
  "largura_mundo": 3830,
  "chao_y": 656,
  "nascer": {"x": 80, "y": 622},
  "objetos": [
    {"tipo": "chao", "x": 0, "y": 656, "w": 3830, "h": 90},
    {"tipo": "espinho", "x": 430, "y": 640, "w": 56, "h": 16, "direcao": "cima"},
    {"tipo": "mola", "x": 700, "y": 628, "w": 32, "h": 28, "direcao": "cima"}
  ]
}
```

Tipos: `chao`, `plataforma`, `bloco`, `caixa`, `espinho`, `mola`, `moeda`, `pedra`,
`chave`, `porta`. `direcao`: `cima`, `baixo`, `esquerda`, `direita`.

## Como o jogo acha o mapa

`src/mundo/mapa.py` procura nesta ordem: a variável `METALMAX_MAPA`, o arquivo
`assets/mapas/nivel1.json` do repo e, se nada abrir, um chão reto de emergência.
Exportar pelo editor já grava no lugar certo — é só rodar `python main.py`.

Para jogar um mapa específico sem mexer no repo:

```bash
cd ~/Desktop/metalmax
METALMAX_MAPA=~/Desktop/mapmaker/mapa.json ./venv/bin/python main.py
```
