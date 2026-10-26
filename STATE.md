# STATE & HANDOFF — Projeto `PS2-PS4` (Servidor PC + Loja Nativa PS4 `.pkg`)

> **Instrução para a próxima sessão de IA (OpenCode / Claude Code):**
> Leia este arquivo (`E:\PS2-PS4\STATE.md`) antes de qualquer ação. Ele contém todo o estado atual do projeto, IPs da rede, estrutura de pastas, jogos já convertidos, problemas diagnosticados no FPKGi e a especificação completa para construir o **nosso próprio aplicativo nativo de PS4 (`.pkg`)** usando como base o projeto `xcloud-ps4`.

---

## 1. Visão Geral e Decisão Atual do Usuário (2026-10-26)

- **Objetivo:** Ter uma biblioteca de jogos de PS2 hospedada no PC (`E:\PS2-PS4\`) que converte ISOs de PS2 automaticamente em `.pkg` de PS4 (emulador oficial Sony `PS2-on-PS4` / `Jak v2`) e permite navegar pelas capas e instalar os jogos direto pelo sofá no PS4 destravado (FW 9.00 + GoldHEN).
- **Decisão do Usuário (Mudança para App Próprio):**
  - Testamos o `FPKGi v1.10.0` no PS4, mas **o usuário não gostou do layout do FPKGi** (e o FPKGi tem peculiaridades chatas de filtro de região e cache local em `/user/data/FPKGi/ContentJSONs/`).
  - **Próximo Passo Principal:** Construir o **nosso próprio aplicativo nativo de PS4 (`.pkg`)** — uma loja/biblioteca visual bonita, moderna e rápida (estilo Netflix / PS5 / Xbox Game Pass), feita sob medida para o nosso servidor `E:\PS2-PS4`, **usando como base e modelo técnico o projeto `xcloud-ps4`** que já funciona no PS4 do usuário!

---

## 2. Ambiente, Rede, Caminhos e Repositório

### Rede Local & PS4
- **IP do PC (Servidor LAN):** `192.168.0.13` (Porta HTTP: `8080` → `http://192.168.0.13:8080`)
- **IP do PS4 (FW 9.00 + GoldHEN):** `192.168.0.15`
  - **FTP do GoldHEN:** `192.168.0.15:2121` (sem senha, login anônimo)
  - **Remote Package Installer (RPI) no PS4:** `http://192.168.0.15:12800` (`POST /api/install` com `{"type":"direct","packages":["http://192.168.0.13:8080/pkgs/..."]}`)

### Caminhos no PC
1. **Projeto Principal (Servidor + Conversor + Catálogo PS2):**
   - Pasta: `E:\PS2-PS4\` (Unidade `E:\` tem ~560 GB livres; `C:\` e `D:\` têm pouco espaço, **nunca** salvar ISOs/PKGs em `C:\` ou `D:\`).
   - Repositório GitHub: `https://github.com/bruno-gs-dev/ps2-ps4-library` (branch `main`, conta `bruno-gs-dev`).
2. **Projeto Modelo para o App Nativo de PS4 (`xcloud-ps4`):**
   - Pasta: `C:\Users\Bruno\_LIMPEZA\4-PASTAS-GERADAS-POR-IA-revisar\projects\xcloud-ps4`
   - Toolchain instalado no **WSL2**: OpenOrbis PS4 Toolchain + PacBrew (`/opt/pacbrew/ps4/openorbis/ps4vars.sh`, `openorbis-cmake`, `SDL2`, `SDL2_image`, `libcurl`, `mbedtls`, `ScePigletv2VSH`, `SceNet`, `ScePad`, `SceBgft` / RPI).

---

## 3. O Que Já Está Pronto e Funcionando em `E:\PS2-PS4\`

### Pipeline no PC (`E:\PS2-PS4\`)
- `src/scanner.py`:
  - Lê `.iso` e `.bin` (suporta setores de 2048 bytes e 2352 bytes raw Mode 2 Form 1), extrai o serial do PS2 (`SLUS-20174`, `SLUS-21376`, etc.) do `SYSTEM.CNF` via ISO9660.
  - Lê `.pkg` de PS4 (`\x7fCNT`) e extrai `TITLE_ID`, `TITLE`, `VERSION` do `param.sfo` embutido (`\x00PSF`), além do serial PS2 no nome do arquivo.
  - Baixa capas automaticamente do repositório `xlenore/ps2-covers` para `E:\PS2-PS4\covers\<SERIAL>.jpg`.
  - Gera `E:\PS2-PS4\json\PS2.json`.
- `src/convert_iso_to_pkg.py`:
  - Converte automaticamente qualquer `.iso` ou `.bin` de PS2 em `.pkg` instalável de PS4 usando o emulador oficial `Jak v2` (`E:\PS2-PS4\tools\PS-Classics-fPKG-Builder\PS Classics fPKG Builder v1\`), aplicando configs de emulador (`ps2-configs`), Lua scripts, capa `icon0.png` (512x512) + `pic0.png` (1920x1080) e empacotando via `LibOrbisPkg.dll` (.NET) ou `orbis-pub-cmd.exe`.
- `src/download_roms.py`:
  - Faz scrape do `romsgames.net`, resolve a API `POST ?get-rom`, baixa o `.7z` da CDN (`cache.romsgames.net`), extrai com `7z.exe`, converte para `.pkg` e atualiza o catálogo.
- `src/server.py`:
  - Servidor HTTP multi-thread na porta `8080` com suporte completo a **HTTP Byte Range (`206 Partial Content`)** e `HEAD` (obrigatório para o PS4 baixar PKGs sem dar erro `Unable to load system file object`).
  - Dashboard Web em `http://localhost:8080` com botão de enviar `.pkg` direto para o PS4 via RPI (`192.168.0.15:12800`), conversão em 1 clique e download de jogos.

### Jogos Já Baixados e Convertidos em `E:\PS2-PS4\pkgs\`
1. **Rumble Racing** (`Rumble Racing [SLUS20174].pkg` — 421.9 MB) + capa `SLUS-20174.jpg`
2. **Black** (`Black [SLUS21376].pkg` — 1.29 GB) + capa `SLUS-21376.jpg`
3. **Guitar Hero III: Legends of Rock** (`Guitar Hero III - Legends of Rock [SLUS21672].pkg` — 3.03 GB) + capa `SLUS-21672.jpg`
4. **Midnight Club 3: DUB Edition Remix** (`isos/_temp_downloads/Midnight Club 3 - DUB Edition Remix (USA).7z` — em finalização de download/conversão)
5. **Naruto: Ultimate Ninja 3** (na fila do `download_roms.py`)

---

## 4. Arquitetura do Novo App Nativo de PS4 (`ps2-store-ps4`) — Baseado no `xcloud-ps4`

### Por que usar o `xcloud-ps4` como base?
O projeto `C:\Users\Bruno\_LIMPEZA\4-PASTAS-GERADAS-POR-IA-revisar\projects\xcloud-ps4` já resolveu **todos** os problemas difíceis do PS4 em FW 9.00 + GoldHEN:
1. **Build system pronto no WSL2 (`build.sh` + `CMakeLists.txt`):** Compila C++17 com `openorbis-cmake` e gera o `.pkg` instalável (`add_self` + `add_pkg`).
2. **Inicialização correta de rede no Orbis OS (`platform_net_init()` em `src/main.cpp`):**
   - Carrega `SCE_SYSMODULE_INTERNAL_NET`, `NETCTL`, `SSL`, `HTTP`.
   - Chama `sceNetInit()`, `sceNetPoolCreate("netPool", 4 * 1024, 0)` (evita travamento em DNS/socket), `sceNetCtlInit()`, `sceSslInit(0x40000)`.
   - Inicializa `libcurl` (`curl_global_init`).
3. **Renderização e Controle DualShock 4 (`src/ui/ui.cpp`):**
   - Usa `SDL2` (via `ScePigletv2VSH` OpenGL ES 2.0) + `SDL2_image` (carrega capas JPG/PNG direto da rede) + fonte bitmap/TTF customizada em 1920x1080 a 60 FPS.
   - Lê todos os botões do DualShock 4 (`SDL_GameController`).

### Como o nosso App Nativo (`PS2 Store PS4`) vai funcionar:
1. **Conexão Automática com o Servidor PC (`E:\PS2-PS4`):**
   - Ao abrir no PS4, o app lê `/data/ps2store/config.json` (ou descobre automaticamente o servidor na LAN / usa `http://192.168.0.13:8080` por padrão) e busca `GET /json/PS2.json`.
2. **Layout Moderno de Console (Melhor que o FPKGi):**
   - **Grade de Capas Grande (Poster Grid / Carrossel estilo PS5 / Game Pass)** com sombras, destaque animado no card selecionado, barra superior com status do servidor e espaço livre no HD do PS4.
   - **Painel de Detalhes (Hero / Sidebar ou Modal):** Ao selecionar um jogo, mostra a capa em alta resolução, Título, Serial (`SLUS-xxxxx`), Região, Tamanho em GB/MB, e status (Disponível para Download / Baixando / Instalado).
   - **Filtro e Busca Rápida:** Por região, ordem alfabética ou tamanho, acionados com `L1/R1` ou `Triângulo`.
3. **Download e Instalação Direta no PS4 (2 modos suportados):**
   - **Modo 1 — Nativo via `SceBgft` / `SceAppInstUtil` (igual ao FPKGi, em segundo plano nas Notificações do PS4):**
     - O app chama `sceAppInstUtilInitialize()` + `sceBgftServiceIntInitialize()` + `sceBgftServiceIntDownloadRegisterTaskByStorageEx()` passando a URL `http://192.168.0.13:8080/pkgs/<jogo>.pkg`, o nome do jogo e a URL da capa (`cover_url`) para aparecer direto nas **Notificações > Downloads** do PS4!
   - **Modo 2 — Fallback via Localhost RPI (`127.0.0.1:12800`) ou Download Direto para `/data/pkg/`:**
     - Caso `SceBgft` não esteja disponível ou o usuário prefira, pode acionar a API ou baixar com barra de progresso na própria tela.
4. **Funcionalidade Extra Exclusiva (Solicitar Jogo do `romsgames.net` pelo PS4!):**
   - Como o nosso `server.py` no PC já tem o endpoint `POST /api/download-game`, o app do PS4 pode ter uma aba **"Baixar Novo Jogo no PC"**: você digita o nome do jogo de PS2 no PS4 (ex.: `"God of War II"`), o PC baixa a ISO do `romsgames.net`, converte para `.pkg` sozinho e o jogo aparece pronto na tela da TV!

---

## 5. Como Retomar na Próxima Conversa

Quando você abrir uma nova conversa após o `/clear`, basta colar:

```text
Leia o arquivo E:\PS2-PS4\STATE.md e vamos criar o nosso app nativo de PS4 (.pkg) para a biblioteca de PS2 usando o xcloud-ps4 como base.
```

### Checklist Imediato para a Próxima Sessão:
1. Ler `E:\PS2-PS4\STATE.md` e `C:\Users\Bruno\_LIMPEZA\4-PASTAS-GERADAS-POR-IA-revisar\projects\xcloud-ps4\src\main.cpp` + `src\ui\ui.cpp`.
2. Verificar se `Midnight Club 3` e `Naruto Ultimate Ninja 3` terminaram de converter em `E:\PS2-PS4\pkgs\`.
3. Criar a pasta `E:\PS2-PS4\ps4-app\` (estruturada como o `xcloud-ps4` com `CMakeLists.txt`, `build.sh`, `data/sce_sys/`, `src/`).
4. Implementar a UI estilo PS5/Game Pass em `SDL2` + `SDL2_image`, listando os jogos de `http://192.168.0.13:8080/json/PS2.json` com capas e disparando o download/instalação no PS4.
5. Compilar via WSL2 (`openorbis-cmake`) gerando o `.pkg` do app e instalar no PS4 (`192.168.0.15:12800`).
