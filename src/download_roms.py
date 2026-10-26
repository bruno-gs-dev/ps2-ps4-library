#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
PS2-PS4 ROM Downloader: Baixa jogos de PS2 do romsgames.net para E:\PS2-PS4\isos\
Descompacta os arquivos .7z automaticamente, limpa temporários e aciona o scanner.py
para detecção de serial e download de capas.
"""

import os
import sys
import re
import json
import time
import shutil
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# Suporte seguro a UTF-8 em consoles Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ISOS_DIR = os.path.join(BASE_DIR, 'isos')
TEMP_DIR = os.path.join(ISOS_DIR, '_temp_downloads')

# Importa o scanner e conversor
try:
    from scanner import update_library_and_json, parse_iso
    from convert_iso_to_pkg import convert_single_game
except ImportError:
    from src.scanner import update_library_and_json, parse_iso
    from src.convert_iso_to_pkg import convert_single_game

# Lista padrão ordenada do menor para o maior
DEFAULT_GAMES = [
    {
        "name": "Rumble Racing",
        "url": "https://www.romsgames.net/playstation-2-rom-rumble-racing/",
        "media_id": "8336"
    },
    {
        "name": "Black",
        "url": "https://www.romsgames.net/playstation-2-rom-black/",
        "media_id": "7217"
    },
    {
        "name": "Guitar Hero III: Legends of Rock",
        "url": "https://www.romsgames.net/playstation-2-rom-guitar-hero-3-legends-of-rock/",
        "media_id": "9318"
    },
    {
        "name": "Midnight Club 3: DUB Edition Remix",
        "url": "https://www.romsgames.net/playstation-2-rom-midnight-club-3-dub-edition/",
        "media_id": "7949"
    }
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'X-Requested-With': 'XMLHttpRequest'
}

def resolve_media_id_from_url(page_url):
    """Obtém o data-media-id do HTML da página do jogo."""
    req = urllib.request.Request(page_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            m = re.search(r'data-media-id=["\'](\d+)["\']', html)
            if m:
                return m.group(1)
            m2 = re.search(r'mediaId["\']?\s*[:=]\s*["\']?(\d+)', html)
            if m2:
                return m2.group(1)
    except Exception as e:
        print(f"[!] Erro ao obter mediaId de {page_url}: {e}")
    return None

def get_download_info(page_url, media_id):
    """
    Chama a API de download do romsgames.net:
    POST <page_url>?download
    Body: mediaId=<id>&g-recaptcha-response=
    """
    endpoint = f"{page_url.rstrip('/')}/?download"
    data = f"mediaId={media_id}&g-recaptcha-response=".encode('utf-8')
    post_headers = dict(HEADERS)
    post_headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
    post_headers['Referer'] = page_url

    req = urllib.request.Request(endpoint, data=data, headers=post_headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            download_url = res_json.get('downloadUrl')
            download_name = res_json.get('downloadName')
            media_size = res_json.get('media', {}).get('size', 0)

            if not download_url or not download_name:
                print(f"[!] Resposta da API incompleta: {res_json}")
                return None

            final_url = f"{download_url}?mediaId={media_id}&attach={download_name}"
            clean_name = urllib.parse.unquote(download_name)
            return {
                "final_url": final_url,
                "filename": clean_name,
                "size": media_size
            }
    except Exception as e:
        print(f"[!] Falha na requisição da API de download ({page_url}): {e}")
        return None

def download_file(url, dest_path, referer, expected_size=0):
    """
    Baixa arquivo com suporte a resumo (resume) usando curl.exe
    ou fallback streaming em Python.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    # 1. Tentar curl.exe nativo
    curl_bin = shutil.which("curl.exe") or "curl.exe"
    try:
        cmd = [
            curl_bin,
            "-L",
            "--retry", "5",
            "--retry-delay", "3",
            "-C", "-",
            "-A", HEADERS['User-Agent'],
            "-e", referer,
            "-o", dest_path,
            url
        ]
        print(f"[*] Executando curl: {dest_path}")
        ret = subprocess.run(cmd)
        if ret.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024 * 1024:
            return True
        print(f"[!] curl retornou código {ret.returncode}. Tentando fallback Python...")
    except Exception as e:
        print(f"[!] Falha ao executar curl: {e}. Usando Python...")

    # 2. Fallback em Python com suporte a resume (Range: bytes=...)
    existing_bytes = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
    if expected_size and existing_bytes >= expected_size:
        print("[✓] Arquivo já completamente baixado.")
        return True

    py_headers = dict(HEADERS)
    py_headers['Referer'] = referer
    if existing_bytes > 0:
        py_headers['Range'] = f"bytes={existing_bytes}-"
        print(f"[*] Resumindo download a partir de {existing_bytes / (1024*1024):.2f} MB...")

    req = urllib.request.Request(url, headers=py_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            mode = 'ab' if existing_bytes > 0 and resp.status == 206 else 'wb'
            if mode == 'wb':
                existing_bytes = 0
            
            total = int(resp.headers.get('Content-Length', 0)) + existing_bytes
            downloaded = existing_bytes
            chunk_size = 1024 * 1024
            last_print = time.time()

            with open(dest_path, mode) as out_f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    if time.time() - last_print > 1.0:
                        pct = (downloaded / total * 100) if total else 0
                        print(f"\r  [{downloaded / (1024*1024):.1f} MB / {total / (1024*1024):.1f} MB] ({pct:.1f}%)", end="", flush=True)
                        last_print = time.time()
            print(f"\r  [✓] Download concluído: {downloaded / (1024*1024):.1f} MB")
            return True
    except Exception as e:
        print(f"\n[!] Falha no streaming Python: {e}")
        return False

def extract_archive(archive_path, extract_dir):
    """
    Descompacta arquivos .7z para extract_dir usando:
    1. 7z.exe (em tools/PS-Classics-fPKG-Builder/PS Classics fPKG Builder v1/Tools/7z.exe)
    2. C:\\Windows\\system32\\tar.exe
    3. Fallback para WinRAR se disponível
    """
    os.makedirs(extract_dir, exist_ok=True)
    print(f"[*] Descompactando: {os.path.basename(archive_path)}...")

    # 1. Tentar 7z.exe interno do projeto
    seven_zip = os.path.join(BASE_DIR, 'tools', 'PS-Classics-fPKG-Builder', 'PS Classics fPKG Builder v1', 'Tools', '7z.exe')
    if os.path.isfile(seven_zip):
        try:
            cmd = [seven_zip, "x", "-y", f"-o{extract_dir}", archive_path]
            ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if ret.returncode == 0:
                print("[✓] Descompactado com sucesso via 7z.exe!")
                return True
            else:
                print(f"[!] 7z.exe retornou código {ret.returncode}: {ret.stderr.decode('latin1', errors='ignore')}")
        except Exception as e:
            print(f"[!] Erro ao invocar 7z.exe: {e}")

    # 2. Tentar tar.exe
    tar_bin = shutil.which("tar.exe") or "tar.exe"
    try:
        cmd = [tar_bin, "-xf", archive_path, "-C", extract_dir]
        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ret.returncode == 0:
            print("[✓] Descompactado com sucesso via tar.exe!")
            return True
        else:
            print(f"[!] tar.exe retornou código {ret.returncode}: {ret.stderr.decode('latin1', errors='ignore')}")
    except Exception as e:
        print(f"[!] Erro ao invocar tar.exe: {e}")

    # 2. Fallback para WinRAR
    winrar_candidates = [
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe"
    ]
    for winrar in winrar_candidates:
        if os.path.isfile(winrar):
            try:
                cmd = [winrar, "x", "-ibck", "-y", archive_path, extract_dir + "\\"]
                print(f"[*] Tentando WinRAR: {winrar}")
                ret = subprocess.run(cmd)
                if ret.returncode == 0:
                    print("[✓] Descompactado com sucesso via WinRAR!")
                    return True
            except Exception as e:
                print(f"[!] Erro ao invocar WinRAR: {e}")

    return False

def find_extracted_iso(name_pattern=None):
    """Verifica se existem imagens .iso ou .bin em isos/."""
    isos = []
    for f in os.listdir(ISOS_DIR):
        if f.lower().endswith(('.iso', '.bin')):
            full_p = os.path.join(ISOS_DIR, f)
            if os.path.isfile(full_p) and os.path.getsize(full_p) > 10 * 1024 * 1024:
                isos.append(full_p)
    return isos

def is_game_already_present(game_name):
    """Verifica se o jogo já está extraído na pasta isos/."""
    clean_search = re.sub(r'[^a-zA-Z0-9]', '', game_name).lower()
    for f in os.listdir(ISOS_DIR):
        if f.lower().endswith(('.iso', '.bin')):
            clean_f = re.sub(r'[^a-zA-Z0-9]', '', f).lower()
            if clean_search in clean_f or clean_f in clean_search:
                full_p = os.path.join(ISOS_DIR, f)
                if os.path.getsize(full_p) > 50 * 1024 * 1024:
                    return full_p
    return None

def process_game(game):
    name = game['name']
    url = game['url']
    media_id = game.get('media_id')

    print("\n" + "=" * 65)
    print(f"🎮 Processando: {name}")
    print("=" * 65)

    # 1. Verifica se já existe ISO extraída
    existing = is_game_already_present(name)
    if existing:
        print(f"[✓] Jogo já presente em: {existing} ({os.path.getsize(existing) / (1024*1024*1024):.2f} GB)")
        iso_meta = parse_iso(existing)
        print(f"    Serial: {iso_meta.get('serial')} | Região: {iso_meta.get('region')} | Título: {iso_meta.get('title')}")
        convert_single_game(existing)
        return True

    # 2. Obtém mediaId se não especificado
    if not media_id:
        print(f"[*] Buscando mediaId para {url}...")
        media_id = resolve_media_id_from_url(url)
        if not media_id:
            print(f"[!] Não foi possível identificar o mediaId para {name}. Pulando.")
            return False

    # 3. Consulta API do romsgames.net
    print(f"[*] Consultando API de download (mediaId: {media_id})...")
    info = get_download_info(url, media_id)
    if not info:
        print(f"[!] Falha ao obter dados de download para {name}.")
        return False

    final_url = info['final_url']
    archive_name = info['filename']
    expected_size = info['size']
    archive_path = os.path.join(TEMP_DIR, archive_name)

    print(f"[*] Arquivo: {archive_name}")
    print(f"[*] Tamanho aproximado: {expected_size / (1024*1024):.2f} MB")

    # 4. Download do .7z
    os.makedirs(TEMP_DIR, exist_ok=True)
    success = download_file(final_url, archive_path, url, expected_size)
    if not success:
        print(f"[!] Erro no download de {archive_name}.")
        return False

    # 5. Descompactação do .7z para isos/
    extracted = extract_archive(archive_path, ISOS_DIR)
    if not extracted:
        print(f"[!] Falha ao descompactar {archive_path}.")
        return False

    # 6. Verifica se o .iso foi extraído
    iso_found = is_game_already_present(name)
    if not iso_found:
        # Se a busca por nome específico não bateu, busca qualquer iso recente
        isos = find_extracted_iso()
        if isos:
            iso_found = max(isos, key=os.path.getmtime)

    if iso_found:
        size_gb = os.path.getsize(iso_found) / (1024 * 1024 * 1024)
        print(f"[✓] ISO extraída com sucesso: {os.path.basename(iso_found)} ({size_gb:.2f} GB)")
        
        # Remove arquivo .7z para poupar espaço em disco
        try:
            if os.path.exists(archive_path):
                os.remove(archive_path)
                print(f"[*] Arquivo temporário {archive_name} removido.")
        except Exception as e:
            print(f"[!] Não foi possível remover {archive_path}: {e}")

        # 7. Atualiza o catálogo e baixa a capa automaticamente
        print("[*] Atualizando catálogo e baixando capa oficial...")
        update_library_and_json(BASE_DIR)
        
        iso_meta = parse_iso(iso_found)
        print(f"[✓] Serial: {iso_meta.get('serial', 'N/D')} | Região: {iso_meta.get('region')} | Título: {iso_meta.get('title')}")

        # 8. Converte a ISO em fPKG para PS4
        print("[*] Convertendo ISO em PKG de PS4 (fPKG)...")
        convert_single_game(iso_found)
        return True
    else:
        print(f"[!] Arquivo ISO não encontrado após descompactação!")
        return False

def main():
    print("=" * 65)
    print("🚀  PS2-PS4 ROM Downloader (romsgames.net)")
    print(f"📂  Pasta de Destino: {ISOS_DIR}")
    print("=" * 65)

    games_to_download = []

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith('http'):
                games_to_download.append({
                    "name": Path(urllib.parse.urlparse(arg).path.strip('/')).name,
                    "url": arg,
                    "media_id": None
                })
            else:
                games_to_download.append({
                    "name": arg,
                    "url": f"https://www.romsgames.net/playstation-2-rom-{arg.lower().replace(' ', '-')}/",
                    "media_id": None
                })
    else:
        games_to_download = DEFAULT_GAMES

    total = len(games_to_download)
    completed = 0

    for i, g in enumerate(games_to_download, 1):
        print(f"\n[{i}/{total}] Iniciando {g['name']}...")
        if process_game(g):
            completed += 1

    # Limpeza final de pasta temp
    if os.path.exists(TEMP_DIR):
        try:
            if not os.listdir(TEMP_DIR):
                os.rmdir(TEMP_DIR)
        except Exception:
            pass

    print("\n" + "=" * 65)
    print(f"🏁 Finalizado: {completed}/{total} jogos prontos em {ISOS_DIR}!")
    print("=" * 65)

if __name__ == '__main__':
    main()
