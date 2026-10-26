# 🎮 PS2 to PS4 FPKGi Server

Servidor HTTP portátil e de **zero dependências externas** (apenas Python 3 padrão) desenvolvido para disponibilizar sua biblioteca de jogos de PlayStation 2 em um PlayStation 4 com desbloqueio (**GoldHEN**) através do homebrew **FPKGi** (`ItsJokerZz/FPKGi`).

---

## 📋 Sumário
1. [Como Funciona](#-como-funciona)
2. [Estrutura de Pastas](#-estrutura-de-pastas)
3. [Como Instalar o FPKGi no PS4](#-como-instalar-o-fpkgi-no-ps4)
4. [Como Converter ISOs de PS2 em PKG com o PS2-FPKG](#-como-converter-isos-de-ps2-em-pkg-com-o-ps2-fpkg)
5. [Como Configurar o FPKGi no PS4 (Automático via FTP em 1 Clique)](#-como-configurar-o-fpkgi-no-ps4-automático-via-ftp-em-1-clique)
6. [Como Usar no Dia a Dia](#-como-usar-no-dia-a-dia)
7. [Portabilidade: Como Mover para Outro PC ou Usar via GitHub](#-portabilidade-como-mover-para-outro-pc-ou-usar-via-github)

---

## ⚡ Como Funciona

```
                                                     [ Rede Local / Wi-Fi ]
  [ ISOs PS2 ]                                                 │
       │                                                       ▼
       ▼                                               ┌───────────────┐
[ PS2-FPKG ] ──► [ pkgs/meu_jogo.pkg ] ──► [ Servidor HTTP ]   │  PlayStation 4│
                                           │  Range 206 OK  │──►  (GoldHEN)   │
                                           │  Dashboard Web │   │    FPKGi      │
                                           └────────────────┘   └───────────────┘
```

1. **Inspeção Inteligente**: O scanner lê suas ISOs de PS2 (extraindo o Serial `SLUS-xxxxx` pelo descritor ISO9660 e `SYSTEM.CNF`) e os arquivos PKG já convertidos (extraindo Title ID `CUSAxxxxx` e dados do `param.sfo`).
2. **Capas Automáticas**: Quando um serial PS2 é identificado, a capa oficial em alta qualidade é baixada automaticamente do acervo da comunidade.
3. **Catálogo Dinâmico para FPKGi**: O servidor gera o endpoint `http://<IP>:8080/json/PS2.json` adaptando-se em tempo real ao IP da máquina, garantindo que o catálogo nunca quebre caso você mude de rede Wi-Fi ou roteador.
4. **Downloads Rápidos e Confiáveis**: O servidor possui implementação nativa completa de **HTTP Byte Range (`206 Partial Content`)** e respostas a requisições `HEAD`. Isso é estritamente obrigatório pelo gerenciador de downloads em segundo plano do PS4 (`SceBgft`), permitindo pausar e continuar downloads gigantescos de dezenas de gigabytes sem corromper.

---

## 📁 Estrutura de Pastas

```text
E:\PS2-PS4\
│
├── 1_baixar_ferramentas.bat     # Baixa o FPKGi.pkg oficial e cria instruções
├── 2_iniciar_servidor.bat       # Inicia o servidor e abre o Dashboard no navegador
├── config.json                  # Configurações do servidor e IP do PS4 (caminhos relativos)
├── README.md                    # Este guia completo em Português
├── .gitignore                   # Ignora ISOs/PKGs pesados mantendo a estrutura limpa
│
├── isos/                        # Coloque suas imagens .iso de PS2 aqui
├── pkgs/                        # Coloque os arquivos .pkg convertidos para PS4 aqui
├── covers/                      # Capas dos jogos (baixadas automaticamente pelo scanner)
├── json/                        # Contém o arquivo PS2.json gerado para o FPKGi
├── tools/                       # Instalador do FPKGi e guias de conversão
│
└── src/
    ├── scanner.py               # Analisador de ISO/PKG e gerador de JSON
    ├── server.py                # Servidor HTTP Threading com suporte a Range 206 e Dashboard
    └── setup_tools.py           # Script auxiliar de download de ferramentas
```

---

## 🚀 Como Instalar o FPKGi no PS4

O **FPKGi** é um aplicativo homebrew moderno para o PS4 que permite navegar por lojas e repositórios locais via HTTP e instalar jogos diretamente para o disco interno ou HD externo do console.

1. No seu PC, dê dois cliques em `1_baixar_ferramentas.bat`.
   - O script baixará automaticamente o arquivo `FPKGi_v1.10.0-release.pkg` para a pasta `tools/`.
2. Para instalar no PS4:
   - **Opção A (Pen Drive / HD Externo)**: Copie o arquivo `tools/FPKGi_v1.10.0-release.pkg` para a raiz de um pen drive formatado em exFAT ou FAT32. Conecte ao PS4 e instale em **Configurações > GoldHEN > Package Installer**.
   - **Opção B (Via Rede / DirectPackageInstaller)**: Se você já utiliza alguma ferramenta de envio de PKG por rede, envie o arquivo diretamente para o IP do seu PS4.
3. O ícone do **FPKGi** aparecerá no menu principal do PS4.

---

## 💿 Como Converter ISOs de PS2 em PKG com o PS2-FPKG

Para rodar no PS4, a ISO de PS2 precisa ser empacotada com o emulador oficial da Sony usando a ferramenta gratuita **PS2-FPKG**.

1. Baixe o **PS2-FPKG** no GitHub:
   - Link oficial: https://github.com/GDX-Tools/PS2-FPKG/releases
   - Extraia o programa no seu computador (por exemplo, dentro de `tools/PS2-FPKG/`).
2. Abra o `PS2-FPKG.exe`:
   - No campo **Disc 1**, clique em **Browse** e selecione a ISO desejada (ex: `E:\PS2-PS4\isos\God of War II.iso`).
   - O programa detectará automaticamente o serial do PS2 (ex: `SCUS-97481`).
   - No campo **Emulation settings / Template**, você pode escolher uma predefinição recomendada para o jogo ou manter o padrão (o PS2-FPKG já inclui correções de compatibilidade e widescreen LUA).
   - Opcional: personalize ícones e telas de boot se desejar.
3. Clique em **Create fPKG**.
4. Quando perguntado onde salvar o arquivo, selecione diretamente a pasta do projeto:
   - 👉 `E:\PS2-PS4\pkgs\`
5. Pronto! O arquivo `.pkg` agora faz parte do seu acervo.

---

## 🎯 Como Configurar o FPKGi no PS4 (Automático via FTP em 1 Clique)

O FPKGi no PS4 precisa saber onde encontrar o arquivo `PS2.json` na sua rede. O nosso painel web faz isso automaticamente via FTP em 1 clique!

### Configuração em 1 Clique (Recomendado):
1. No seu PS4, certifique-se de que o **GoldHEN** está ativo e com a opção de **FTP Server** ligada (porta padrão: `2121`).
2. No seu PC, inicie o servidor clicando duas vezes em `2_iniciar_servidor.bat`. O Dashboard abrirá no seu navegador em `http://localhost:8080`.
3. No painel, localize o quadro **"🎮 Configuração Automática do PS4 (1 Clique)"**:
   - Digite o **IP do seu PS4** (ex: `192.168.1.150`).
   - Mantenha a porta `2121`.
   - Clique em **"🚀 Enviar Configuração via FTP"**.
4. O servidor criará automaticamente a pasta `/user/data/FPKGi/` no PS4 e gravará o arquivo `config.json` pré-configurado!
5. Abra o **FPKGi** no seu PS4. Vá na categoria **PS2** e todos os seus jogos estarão listados com capas e tamanhos prontos para instalação!

### Configuração Manual (Alternativa):
Se preferir configurar manualmente:
1. No painel web do servidor, clique no botão **"💾 Baixar config.json"**.
2. Usando qualquer cliente FTP (FileZilla, etc.) conectado ao seu PS4, envie o arquivo `config.json` para a pasta:
   `/user/data/FPKGi/config.json`

---

## 🕹️ Como Usar no Dia a Dia

1. Coloque novas ISOs na pasta `isos/` ou novos `.pkg` prontos na pasta `pkgs/`.
2. Dê dois cliques em `2_iniciar_servidor.bat`.
3. No navegador, clique em **"🔄 Atualizar Catálogo / Escanear Pastas"**.
   - O scanner inspeciona os novos arquivos, extrai títulos/seriais e baixa as capas faltantes automaticamente.
4. No PS4, abra o **FPKGi**, pressione o botão de atualizar lista (ou reabra o aplicativo) e instale qualquer jogo diretamente com um clique no controle!

---

## 🌐 Portabilidade: Como Mover para Outro PC ou Usar via GitHub

Este projeto foi construído do zero com foco absoluto em portabilidade:
- **Zero Dependências Pip**: Não necessita `pip install` de nenhum pacote externo. Roda diretamente em qualquer instalação pura do **Python 3.8+**.
- **Caminhos Relativos**: Todos os caminhos de pastas em `config.json` usam `./isos`, `./pkgs`, `./covers`, `./json`, permitindo mover a pasta inteira para outro disco ou computador sem quebrar nada.
- **Detecção Dinâmica de IP**: Não importa se o PC mudou de endereço IP ou se você está em outra casa; ao ser consultado, o servidor gera os links para o IP local ativo no momento.

### Clonando ou Enviando para o GitHub:
O arquivo `.gitignore` já está pré-configurado para ignorar arquivos pesados (ISOs, PKGs e ferramentas binárias), mantendo intactas as pastas e arquivos de configuração.
Para subir em um repositório pessoal:
```bash
git init
git add .
git commit -m "Initial commit - PS2 to PS4 FPKGi Server"
```
Ao clonar em outro PC com Windows:
1. Tenha o **Python 3** instalado (marcando "Add python.exe to PATH").
2. Execute `1_baixar_ferramentas.bat` para baixar o instalador do FPKGi.
3. Coloque seus jogos e execute `2_iniciar_servidor.bat`!
