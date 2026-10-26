#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Download de Ferramentas e Instruções de Conversão PS2-FPKG.
Baixa o PKG do FPKGi oficial e gera o guia de conversão.
"""

import os
import sys
import time
import urllib.request
import urllib.error

# Suporte seguro a UTF-8 em consoles Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TOOLS_DIR = os.path.join(BASE_DIR, 'tools')

FPKGI_URL = "https://github.com/ItsJokerZz/FPKGi/releases/download/v1.10.0/FPKGi_v1.10.0-release.pkg"
FPKGI_FILENAME = "FPKGi_v1.10.0-release.pkg"

BUILDER_URL = "https://github.com/SvenGDK/PS-Classics-fPKG-Builder/releases/download/v1/PS.Classics.fPKG.Builder.v1.Windows.7z"
BUILDER_FILENAME = "PS.Classics.fPKG.Builder.v1.Windows.7z"
BUILDER_DIR_NAME = "PS-Classics-fPKG-Builder"

CONVERSION_GUIDE = """================================================================================
GUIA PRÁTICO: COMO CONVERTER ISOS DE PS2 EM PKGS DE PS4 (PS2-FPKG)
================================================================================

Para jogar seus jogos de PS2 no PS4 com jailbreak (GoldHEN), você precisa
empacotar a ISO do PS2 em um instalador .pkg usando a ferramenta PS2-FPKG.

--------------------------------------------------------------------------------
1. BAIXAR O PS2-FPKG NO SEU COMPUTADOR
--------------------------------------------------------------------------------
O PS2-FPKG é o programa oficial da comunidade para Windows:
- Repositório / Releases: https://github.com/GDX-Tools/PS2-FPKG/releases
- Baixe a versão mais recente (ex: PS2-FPKG v0.7 ou superior) e extraia na pasta
  deste projeto em: `E:\\PS2-PS4\\tools\\PS2-FPKG\\` ou onde preferir.

--------------------------------------------------------------------------------
2. PASSO A PASSO DA CONVERSÃO
--------------------------------------------------------------------------------
1. Abra o executável `PS2-FPKG.exe`.
2. No campo "Disc 1", clique em "Browse" e selecione a sua ISO de PS2
   (que pode estar na pasta `E:\\PS2-PS4\\isos\\`).
3. O PS2-FPKG detectará automaticamente:
   - O Title ID / Serial do PS2 (ex: SLUS-20062).
   - O Game Title (Nome do Jogo).
4. No campo "Emulation settings / Template":
   - Escolha o template de compatibilidade recomendado ou mantenha o padrão
     (ex: Jak v2, Okami, Star Wars Racer Revenge, etc.).
   - O programa já inclui correções de widescreen, 60 FPS e LUA configs testadas.
5. Personalização de Capa e Ícone:
   - Se desejar, adicione o `icon0.png` (512x512) e `pic1.png` (1920x1080)
     ou use as capas automáticas baixadas em `E:\\PS2-PS4\\covers\\`.
6. Clique no botão "Create fPKG".
7. Escolha onde salvar o arquivo final `.pkg`:
   👉 Salve diretamente na pasta:
      `E:\\PS2-PS4\\pkgs\\`

--------------------------------------------------------------------------------
3. DISPONIBILIZAR NO PS4 VIA FPKGi
--------------------------------------------------------------------------------
Assim que o `.pkg` for gerado na pasta `pkgs/`:
1. Abra o painel do servidor no PC ou clique no botão:
   "Atualizar Catálogo / Escanear Pastas".
2. O servidor identificará o novo jogo e atualizará o arquivo `json/PS2.json`.
3. Abra o aplicativo **FPKGi** no seu PS4.
4. O novo jogo de PS2 aparecerá na lista pronto para download e instalação direta!
================================================================================
"""

def download_file_with_progress(url, dest_path):
    print(f"[*] Iniciando download: {url}")
    print(f"[*] Destino: {dest_path}")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get('content-length', 0))
            block_size = 64 * 1024
            downloaded = 0
            start_time = time.time()

            with open(dest_path, 'wb') as out_f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    out_f.write(buffer)
                    downloaded += len(buffer)
                    
                    if total_size > 0:
                        percent = downloaded * 100 / total_size
                        mb_down = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        elapsed = time.time() - start_time
                        speed = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        
                        bar_len = 30
                        filled = int(bar_len * downloaded // total_size)
                        bar = '=' * filled + '>' + ' ' * (bar_len - filled - 1) if filled < bar_len else '=' * bar_len
                        
                        sys.stdout.write(f"\r[{bar}] {percent:5.1f}% ({mb_down:6.2f} / {mb_total:6.2f} MB) @ {speed:5.1f} MB/s")
                        sys.stdout.flush()
                    else:
                        mb_down = downloaded / (1024 * 1024)
                        sys.stdout.write(f"\rBaixando... {mb_down:6.2f} MB")
                        sys.stdout.flush()

        print("\n[+] Download concluído com sucesso!")
        return True
    except Exception as e:
        print(f"\n[!] Falha ao baixar arquivo: {e}")
        if os.path.exists(dest_path) and os.path.getsize(dest_path) == 0:
            os.remove(dest_path)
        return False

def extract_archive(archive_path, extract_dir):
    import shutil
    import subprocess
    os.makedirs(extract_dir, exist_ok=True)
    print(f"[*] Descompactando {os.path.basename(archive_path)} para {extract_dir}...")
    
    tar_bin = shutil.which("tar.exe") or "tar.exe"
    try:
        cmd = [tar_bin, "-xf", archive_path, "-C", extract_dir]
        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ret.returncode == 0:
            print("[✓] Descompactado com sucesso via tar.exe!")
            return True
    except Exception as e:
        print(f"[!] tar.exe falhou: {e}")

    winrar = r"C:\Program Files\WinRAR\WinRAR.exe"
    if os.path.isfile(winrar):
        try:
            cmd = [winrar, "x", "-ibck", "-y", archive_path, extract_dir + "\\"]
            ret = subprocess.run(cmd)
            if ret.returncode == 0:
                print("[✓] Descompactado com sucesso via WinRAR!")
                return True
        except Exception as e:
            print(f"[!] WinRAR falhou: {e}")
            
    return False

def main():
    os.makedirs(TOOLS_DIR, exist_ok=True)
    
    # 1. Cria o guia de conversão
    guide_path = os.path.join(TOOLS_DIR, 'COMO_CONVERTER_ISO_EM_PKG.txt')
    with open(guide_path, 'w', encoding='utf-8') as f:
        f.write(CONVERSION_GUIDE)
    print(f"[+] Guia de conversão criado em: {guide_path}")

    # 2. Baixa o PKG do FPKGi se não existir
    target_pkg = os.path.join(TOOLS_DIR, FPKGI_FILENAME)
    if os.path.isfile(target_pkg) and os.path.getsize(target_pkg) > 1024 * 1024:
        print(f"[✓] Arquivo {FPKGI_FILENAME} já existe ({os.path.getsize(target_pkg) / (1024*1024):.2f} MB). Pulei o download.")
    else:
        success = download_file_with_progress(FPKGI_URL, target_pkg)
        if not success:
            print("[!] Não foi possível baixar automaticamente o PKG. Você pode baixá-lo manualmente em:")
            print(f"    {FPKGI_URL}")
            print(f"    e colocá-lo na pasta: {TOOLS_DIR}")

    # 3. Baixa e extrai PS-Classics-fPKG-Builder (emuladores e ferramentas orbis-pub-cmd, etc.)
    builder_dir = os.path.join(TOOLS_DIR, BUILDER_DIR_NAME)
    if os.path.isdir(builder_dir) and any(os.scandir(builder_dir)):
        print(f"[✓] Ferramenta {BUILDER_DIR_NAME} já existe em {builder_dir}.")
    else:
        builder_archive = os.path.join(TOOLS_DIR, BUILDER_FILENAME)
        if not (os.path.isfile(builder_archive) and os.path.getsize(builder_archive) > 10 * 1024 * 1024):
            print(f"[*] Baixando emulador base e ferramentas de empacotamento PS2-on-PS4...")
            download_file_with_progress(BUILDER_URL, builder_archive)

        if os.path.isfile(builder_archive) and os.path.getsize(builder_archive) > 10 * 1024 * 1024:
            extract_ok = extract_archive(builder_archive, builder_dir)
            if extract_ok:
                try:
                    os.remove(builder_archive)
                    print(f"[*] Arquivo temporário {BUILDER_FILENAME} removido após extração.")
                except Exception:
                    pass
            else:
                print(f"[!] Falha na extração de {builder_archive}.")

    print("\n" + "=" * 65)
    print("Ferramentas configuradas com sucesso!")
    print("=" * 65)

if __name__ == '__main__':
    main()
