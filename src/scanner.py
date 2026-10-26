#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PS2-PS4 Scanner: Inspeção de ISOs de PS2 e PKGs de PS4 (Zero dependências externas)
Gera o catálogo FPKGi compatível para jailbreak PS4 (GoldHEN).
"""

import os
import sys
import json
import re
import struct
import socket
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# Suporte seguro a UTF-8 em consoles Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Prefixo de seriais PS2 e mapeamento de região
PS2_SERIAL_PREFIXES = ('SLUS', 'SCUS', 'SLES', 'SCES', 'SLPS', 'SLPM', 'SCPS', 'SLAJ', 'SCKA')

REGION_MAP = {
    'SLUS': 'USA',
    'SCUS': 'USA',
    'SLES': 'EUR',
    'SCES': 'EUR',
    'SLPS': 'JAP',
    'SLPM': 'JAP',
    'SCPS': 'JAP',
    'SLAJ': 'ASIA',
    'SCKA': 'KOR',
}

def get_local_ip():
    """Detecta o IP local na rede LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def normalize_serial(raw_str):
    """
    Normaliza um serial PS2 para o formato padrão XXXX-YYYYY.
    Exemplos:
      SLUS_200.62 -> SLUS-20062
      SLUS20062 -> SLUS-20062
      SLES-50123 -> SLES-50123
    """
    if not raw_str:
        return None
    raw_str = raw_str.upper()
    
    # Formato SLUS_200.62 ou SLUS-200.62
    m1 = re.search(r'([A-Z]{4})[_-](\d{3})\.?(\d{2})', raw_str)
    if m1 and m1.group(1) in PS2_SERIAL_PREFIXES:
        return f"{m1.group(1)}-{m1.group(2)}{m1.group(3)}"
        
    # Formato SLUS-20062 ou SLUS_20062
    m2 = re.search(r'([A-Z]{4})[_-](\d{5})', raw_str)
    if m2 and m2.group(1) in PS2_SERIAL_PREFIXES:
        return f"{m2.group(1)}-{m2.group(2)}"
        
    # Formato SLUS20062
    m3 = re.search(r'([A-Z]{4})(\d{5})', raw_str)
    if m3 and m3.group(1) in PS2_SERIAL_PREFIXES:
        return f"{m3.group(1)}-{m3.group(2)}"
        
    return None

def region_from_serial(serial):
    """Retorna a região com base no serial PS2."""
    if serial:
        prefix = serial.split('-')[0].upper()
        return REGION_MAP.get(prefix, 'USA')
    return 'USA'

_PS2_TITLES_DB = None

def load_ps2ids(base_dir=None):
    """Carrega a base oficial de títulos de PS2 (ps2ids.txt)."""
    global _PS2_TITLES_DB
    if _PS2_TITLES_DB is not None:
        return _PS2_TITLES_DB
        
    _PS2_TITLES_DB = {}
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
    candidates = [
        os.path.join(base_dir, 'tools', 'PS-Classics-fPKG-Builder', 'PS Classics fPKG Builder v1', 'Tools', 'ps2ids.txt'),
        os.path.join(base_dir, 'tools', 'ps2ids.txt'),
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or ';' not in line:
                            continue
                        parts = line.split(';', 1)
                        clean_ser = re.sub(r'[^A-Za-z0-9]', '', parts[0]).upper()
                        _PS2_TITLES_DB[clean_ser] = parts[1].strip()
                break
            except Exception:
                pass
    return _PS2_TITLES_DB

def get_official_title(serial, base_dir=None):
    """Busca o nome limpo e oficial do jogo pelo serial."""
    if not serial:
        return None
    db = load_ps2ids(base_dir)
    clean_ser = re.sub(r'[^A-Za-z0-9]', '', serial).upper()
    return db.get(clean_ser)

def clean_title_from_filename(filename):
    """Gera um nome legível a partir do nome de arquivo."""
    name = Path(filename).stem
    # Remove tags comuns como [SLUS-20062], (USA), [CUSA00001], etc.
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    # Remove seriais remanescentes
    name = re.sub(r'[A-Z]{4}[_-]?\d{3}\.?\d{2}', '', name, flags=re.IGNORECASE)
    name = re.sub(r'CUSA\d{5}', '', name, flags=re.IGNORECASE)
    # Substitui underscores e hífens múltiplos
    name = name.replace('_', ' ').replace('-', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name if name else Path(filename).stem

def parse_iso(iso_path):
    """
    Inspeciona arquivo .iso do PS2:
    1. Tenta ler o PVD do ISO9660 (Setor 16) e localizar o SYSTEM.CNF na raiz.
    2. Realiza busca por regex de BOOT2 no arquivo como fallback.
    Retorna dict com serial, title, region, size.
    """
    size = os.path.getsize(iso_path)
    serial = None
    volume_label = None
    
    try:
        with open(iso_path, 'rb') as f:
            # 1. Tentativa via ISO9660 PVD
            # Setor 16 (0x8000 = 32768)
            f.seek(16 * 2048)
            pvd = f.read(2048)
            if len(pvd) == 2048 and pvd[0] == 1 and pvd[1:6] == b'CD001':
                raw_vol = pvd[40:72].decode('latin1', errors='ignore').strip()
                if raw_vol and not raw_vol.upper().startswith(('CDROM', 'DVD_ROM', 'PLAYSTATION')):
                    volume_label = raw_vol.replace('_', ' ').strip()
                
                # Leitura do root directory record no PVD (offset 156, tamanho 34)
                root_rec = pvd[156:190]
                if len(root_rec) >= 34:
                    root_lba = struct.unpack('<I', root_rec[2:6])[0]
                    root_size = struct.unpack('<I', root_rec[10:14])[0]
                    
                    if 0 < root_size < 10 * 1024 * 1024:
                        f.seek(root_lba * 2048)
                        dir_data = f.read(min(root_size, 131072))
                        
                        curr = 0
                        while curr < len(dir_data):
                            rlen = dir_data[curr]
                            if rlen == 0:
                                curr = ((curr // 2048) + 1) * 2048
                                continue
                            if curr + rlen > len(dir_data):
                                break
                            flba = struct.unpack('<I', dir_data[curr+2:curr+6])[0]
                            fsize = struct.unpack('<I', dir_data[curr+10:curr+14])[0]
                            nlen = dir_data[curr+32]
                            fname = dir_data[curr+33:curr+33+nlen].decode('latin1', errors='ignore')
                            
                            if fname.upper().startswith('SYSTEM.CNF'):
                                f.seek(flba * 2048)
                                cnf = f.read(min(fsize, 4096)).decode('latin1', errors='ignore')
                                m = re.search(r'BOOT2\s*=\s*cdrom0:[\\/]?([A-Za-z]{4}[_-]\d{3}\.?\d{2})', cnf, re.IGNORECASE)
                                if m:
                                    serial = normalize_serial(m.group(1))
                                break
                            curr += rlen
                            
            # 2. Fallback: Escanear primeiros 16MB por SYSTEM.CNF / BOOT2
            if not serial:
                f.seek(0)
                chunk_size = 2 * 1024 * 1024
                bytes_scanned = 0
                max_scan = min(size, 16 * 1024 * 1024)
                
                while bytes_scanned < max_scan:
                    f.seek(bytes_scanned)
                    buf = f.read(chunk_size)
                    if not buf:
                        break
                    m = re.search(rb'BOOT2\s*=\s*cdrom0:[\\/]?([A-Za-z]{4}[_-]\d{3}\.?\d{2})', buf, re.IGNORECASE)
                    if m:
                        serial = normalize_serial(m.group(1).decode('latin1', errors='ignore'))
                        break
                    # Alternativa: procurar diretamente por executáveis de boot de PS2
                    m2 = re.search(rb'([A-Za-z]{4}[_-]\d{3}\.\d{2});1', buf, re.IGNORECASE)
                    if m2:
                        pot = normalize_serial(m2.group(1).decode('latin1', errors='ignore'))
                        if pot:
                            serial = pot
                            break
                    bytes_scanned += chunk_size - 1024 # overlap para não cortar borda
    except Exception as e:
        print(f"[!] Erro ao inspecionar ISO {iso_path}: {e}")

    # Fallback no nome do arquivo para serial
    if not serial:
        serial = normalize_serial(os.path.basename(iso_path))
        
    official = get_official_title(serial)
    if official:
        title = official
    elif volume_label:
        title = volume_label
    else:
        title = clean_title_from_filename(os.path.basename(iso_path))
    region = region_from_serial(serial)
    
    return {
        "filename": os.path.basename(iso_path),
        "path": os.path.abspath(iso_path),
        "size": size,
        "serial": serial,
        "title": title,
        "region": region
    }

def parse_sfo(data):
    """Decodifica um buffer param.sfo em dicionário Python."""
    if len(data) < 20 or data[:4] != b'\x00PSF':
        return {}
    try:
        key_offset, data_offset, count = struct.unpack('<III', data[8:20])
        entries = {}
        for i in range(count):
            entry_start = 20 + i * 16
            if entry_start + 16 > len(data):
                break
            k_off, fmt, d_len, d_max, d_off = struct.unpack('<HHIII', data[entry_start:entry_start+16])
            k_start = key_offset + k_off
            k_end = data.find(b'\x00', k_start)
            if k_end == -1:
                continue
            key = data[k_start:k_end].decode('utf-8', errors='ignore')
            val_start = data_offset + d_off
            val_bytes = data[val_start:val_start + d_len]
            if fmt in (0x0204, 0x0004):
                val = val_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
            elif fmt == 0x0404 and d_len == 4:
                val = struct.unpack('<I', val_bytes)[0]
            else:
                val = val_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore')
            entries[key] = val
        return entries
    except Exception:
        return {}

def parse_pkg(pkg_path):
    """
    Inspeciona arquivo .pkg do PS4:
    - Extrai CONTENT_ID do cabeçalho (offset 0x40)
    - Extrai TITLE_ID
    - Localiza param.sfo embutido nos primeiros 2MB
    - Extrai TITLE, APP_VER, e Serial PS2 se presente
    """
    size = os.path.getsize(pkg_path)
    filename = os.path.basename(pkg_path)
    
    content_id = ""
    title_id = ""
    title = ""
    app_ver = "1.00"
    ps2_serial = None
    
    try:
        with open(pkg_path, 'rb') as f:
            header = f.read(512)
            if len(header) >= 0x80 and header[:4] == b'\x7fCNT':
                raw_cid = header[0x40:0x64].decode('latin1', errors='ignore').strip('\x00').strip()
                if raw_cid:
                    content_id = raw_cid
                    # TITLE_ID costuma estar no formato UPxxxx-CUSAxxxxx_00...
                    m = re.search(r'CUSA\d{5}', content_id)
                    if m:
                        title_id = m.group(0)
                    # Verifica se o CONTENT_ID contém serial PS2 embutido (ex: SLUS20062)
                    ps2_m = re.search(r'(SLUS|SLES|SCUS|SCES|SLPS|SLPM|SCPS)\d{5}', content_id, re.IGNORECASE)
                    if ps2_m:
                        ps2_serial = normalize_serial(ps2_m.group(0))

            # Busca por param.sfo nos primeiros 2MB
            f.seek(0)
            search_buf = f.read(2 * 1024 * 1024)
            sfo_idx = search_buf.find(b'\x00PSF\x01\x01\x00\x00')
            if sfo_idx != -1:
                sfo_data = search_buf[sfo_idx:sfo_idx + 65536]
                sfo = parse_sfo(sfo_data)
                if 'TITLE' in sfo and sfo['TITLE']:
                    title = str(sfo['TITLE']).strip()
                if 'TITLE_ID' in sfo and sfo['TITLE_ID']:
                    title_id = str(sfo['TITLE_ID']).strip()
                if 'APP_VER' in sfo and sfo['APP_VER']:
                    app_ver = str(sfo['APP_VER']).strip()
                    
            # Se ainda não temos serial PS2, procura nos dados do cabeçalho/sfo
            if not ps2_serial:
                for prefix in PS2_SERIAL_PREFIXES:
                    m = re.search(prefix.encode('ascii') + rb'[-_]?\d{5}', search_buf, re.IGNORECASE)
                    if m:
                        cand = normalize_serial(m.group(0).decode('latin1', errors='ignore'))
                        if cand:
                            ps2_serial = cand
                            break
    except Exception as e:
        print(f"[!] Erro ao inspecionar PKG {pkg_path}: {e}")

    # Fallbacks a partir do nome do arquivo
    if not title_id:
        m = re.search(r'CUSA\d{5}', filename, re.IGNORECASE)
        title_id = m.group(0).upper() if m else "CUSA00001"
        
    if not ps2_serial:
        ps2_serial = normalize_serial(filename)

    official = get_official_title(ps2_serial) if ps2_serial else None
    if not title:
        title = official if official else clean_title_from_filename(filename)
    elif official and (title.upper().startswith(('SLUS', 'SLES', 'SCUS', 'SCES', 'CUSA')) or 'SOMETHING WENT FRONG' in title.upper()):
        title = official
        
    region = region_from_serial(ps2_serial) if ps2_serial else "USA"
    
    return {
        "filename": filename,
        "path": os.path.abspath(pkg_path),
        "size": size,
        "title_id": title_id,
        "name": title,
        "version": app_ver,
        "ps2_serial": ps2_serial,
        "region": region
    }

def download_cover(serial, covers_dir, auto_download=True):
    """
    Baixa a capa do jogo pelo serial PS2 no repositório xlenore/ps2-covers se não existir localmente.
    Retorna o nome do arquivo da capa existente ou baixada, ou None.
    """
    if not serial:
        return None
        
    clean_ser = serial.upper()
    dest_path = os.path.join(covers_dir, f"{clean_ser}.jpg")
    
    # Já existe?
    if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
        return f"{clean_ser}.jpg"
        
    # Capa em PNG já existente?
    png_path = os.path.join(covers_dir, f"{clean_ser}.png")
    if os.path.isfile(png_path) and os.path.getsize(png_path) > 0:
        return f"{clean_ser}.png"

    if not auto_download:
        return None

    # Tenta download
    url = f"https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/default/{clean_ser}.jpg"
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = resp.read()
                if len(data) > 1024:
                    with open(dest_path, 'wb') as out_f:
                        out_f.write(data)
                    print(f"[+] Capa baixada com sucesso: {clean_ser}.jpg")
                    return f"{clean_ser}.jpg"
    except Exception as e:
        # Silencioso se estiver offline ou capa não encontrada no repositório
        pass
        
    return None

def scan_library(base_dir=None, config=None):
    """
    Escaneia as pastas de ISOs e PKGs configuradas.
    Retorna dicionário com listas de 'pkgs' e 'isos'.
    """
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
    if config is None:
        config_path = os.path.join(base_dir, 'config.json')
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

    isos_dir = os.path.abspath(os.path.join(base_dir, config.get('isos_dir', './isos')))
    pkgs_dir = os.path.abspath(os.path.join(base_dir, config.get('pkgs_dir', './pkgs')))
    covers_dir = os.path.abspath(os.path.join(base_dir, config.get('covers_dir', './covers')))
    auto_download = config.get('auto_download_covers', True)

    os.makedirs(isos_dir, exist_ok=True)
    os.makedirs(pkgs_dir, exist_ok=True)
    os.makedirs(covers_dir, exist_ok=True)

    # 1. Escanear PKGs
    pkgs_found = []
    if os.path.isdir(pkgs_dir):
        for root, _, files in os.walk(pkgs_dir):
            for file in sorted(files):
                if file.lower().endswith('.pkg'):
                    full_p = os.path.join(root, file)
                    pkg_meta = parse_pkg(full_p)
                    # Verifica/baixa capa
                    cover = None
                    if pkg_meta.get('ps2_serial'):
                        cover = download_cover(pkg_meta['ps2_serial'], covers_dir, auto_download)
                    if not cover and pkg_meta.get('title_id'):
                        t_cov = f"{pkg_meta['title_id']}.jpg"
                        if os.path.isfile(os.path.join(covers_dir, t_cov)):
                            cover = t_cov
                    pkg_meta['cover_file'] = cover
                    pkgs_found.append(pkg_meta)

    # 2. Escanear ISOs
    isos_found = []
    if os.path.isdir(isos_dir):
        for root, _, files in os.walk(isos_dir):
            for file in sorted(files):
                if file.lower().endswith(('.iso', '.bin')):
                    full_p = os.path.join(root, file)
                    iso_meta = parse_iso(full_p)
                    cover = None
                    if iso_meta.get('serial'):
                        cover = download_cover(iso_meta['serial'], covers_dir, auto_download)
                    iso_meta['cover_file'] = cover
                    
                    # Checa se já foi convertido para PKG
                    converted = False
                    clean_iso_ser = re.sub(r'[^A-Za-z0-9]', '', iso_meta.get('serial') or '').upper()
                    for p in pkgs_found:
                        if iso_meta.get('serial') and p.get('ps2_serial') == iso_meta['serial']:
                            converted = True
                            break
                        clean_pkg_ser = re.sub(r'[^A-Za-z0-9]', '', p.get('ps2_serial') or '').upper()
                        clean_pkg_tid = re.sub(r'[^A-Za-z0-9]', '', p.get('title_id') or '').upper()
                        if clean_iso_ser and (clean_iso_ser == clean_pkg_ser or clean_iso_ser == clean_pkg_tid):
                            converted = True
                            break
                        if p.get('name') and iso_meta.get('title') and p['name'].strip().lower() == iso_meta['title'].strip().lower():
                            converted = True
                            break
                    iso_meta['converted'] = converted
                    isos_found.append(iso_meta)

    return {
        "pkgs": pkgs_found,
        "isos": isos_found,
        "timestamp": os.path.getmtime(pkgs_dir) if os.path.exists(pkgs_dir) else 0
    }

def generate_fpkgi_json(pkgs, host_ip, port):
    """
    Gera o schema JSON oficial esperado pelo homebrew FPKGi:
    {
      "DATA": {
        "http://<IP>:<PORT>/pkgs/<FILENAME>": {
          "title_id": "CUSA00001",
          "name": "Game Name",
          "region": "USA",
          "version": "1.00",
          "release": "01-01-2002",
          "size": 1234567890,
          "min_fw": "5.05",
          "cover_url": "http://<IP>:<PORT>/covers/SLUS-20062.jpg"
        }
      }
    }
    """
    data_dict = {}
    
    for item in pkgs:
        encoded_fn = urllib.parse.quote(item['filename'])
        pkg_url = f"http://{host_ip}:{port}/pkgs/{encoded_fn}"
        
        # URL da capa
        if item.get('cover_file'):
            cover_url = f"http://{host_ip}:{port}/covers/{urllib.parse.quote(item['cover_file'])}"
        elif item.get('ps2_serial'):
            cover_url = f"http://{host_ip}:{port}/covers/{item['ps2_serial']}.jpg"
        else:
            cover_url = f"http://{host_ip}:{port}/covers/{item['title_id']}.jpg"

        data_dict[pkg_url] = {
            "title_id": item.get('title_id') or "CUSA00001",
            "name": item.get('name') or item['filename'],
            "region": item.get('region') or "USA",
            "version": item.get('version') or "1.00",
            "release": "01-01-2002",
            "size": int(item.get('size', 1)),
            "min_fw": "5.05",
            "cover_url": cover_url
        }

    return {"DATA": data_dict}

def update_library_and_json(base_dir=None, host_ip=None, port=None):
    """Escaneia a biblioteca e salva json/PS2.json."""
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
    config_path = os.path.join(base_dir, 'config.json')
    config = {}
    if os.path.isfile(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

    if host_ip is None:
        host_ip = get_local_ip()
    if port is None:
        port = config.get('port', 8080)

    json_dir = os.path.abspath(os.path.join(base_dir, config.get('json_dir', './json')))
    os.makedirs(json_dir, exist_ok=True)
    
    scan_result = scan_library(base_dir, config)
    fpkgi_data = generate_fpkgi_json(scan_result['pkgs'], host_ip, port)
    
    target_json_path = os.path.join(json_dir, 'PS2.json')
    with open(target_json_path, 'w', encoding='utf-8') as f:
        json.dump(fpkgi_data, f, indent=2, ensure_ascii=False)
        
    print(f"[*] Catálogo atualizado em {target_json_path} ({len(scan_result['pkgs'])} PKGs, {len(scan_result['isos'])} ISOs)")
    return scan_result, fpkgi_data

if __name__ == '__main__':
    update_library_and_json()
