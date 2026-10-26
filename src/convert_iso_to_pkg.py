#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PS2 ISO to PS4 fPKG Converter
Converte imagens ISO/BIN de PS2 em Fake PKGs (fPKG) para PS4 compatíveis com GoldHEN e FPKGi.
Utiliza a estrutura do Jak v2 emulator, gengp4_patch.exe e orbis-pub-cmd.
"""

import os
import sys
import re
import shutil
import struct
import subprocess
from pathlib import Path

# Suporte seguro a UTF-8 em consoles Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Adiciona diretório raiz e src ao sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SRC_DIR = os.path.join(BASE_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from scanner import (
    parse_iso,
    parse_pkg,
    normalize_serial,
    get_official_title,
    download_cover,
    update_library_and_json
)

BUILDER_DIR = os.path.join(BASE_DIR, 'tools', 'PS-Classics-fPKG-Builder', 'PS Classics fPKG Builder v1')
EMU_DIR = os.path.join(BUILDER_DIR, 'Tools', 'PS4', 'emus', 'Jak v2')
GENGP4_BIN = os.path.join(BUILDER_DIR, 'Tools', 'PS4', 'gengp4_patch.exe')
ORBIS_PUB_BIN = os.path.join(BUILDER_DIR, 'Tools', 'PS4', 'mod-pub', 'orbis-pub-cmd-3.38.exe')
CONFIGS_DIR = os.path.join(BUILDER_DIR, 'Tools', 'PS4', 'ps2-configs')
LUA_INC_DIR = os.path.join(BUILDER_DIR, 'Tools', 'PS4', 'lua_include')
LIBORBIS_DLL = os.path.join(BUILDER_DIR, 'LibOrbisPkg.dll')

ISOS_DIR = os.path.join(BASE_DIR, 'isos')
PKGS_DIR = os.path.join(BASE_DIR, 'pkgs')
COVERS_DIR = os.path.join(BASE_DIR, 'covers')
CACHE_DIR = os.path.join(BASE_DIR, 'tools', 'cache_converter')

def sanitize_filename(name):
    """Remove caracteres inválidos para nomes de arquivo no Windows."""
    name = name.replace(':', ' - ').replace('/', ' ').replace('\\', ' ')
    name = re.sub(r'[?*"<>|]', '', name)
    return re.sub(r'\s+', ' ', name).strip()

def is_raw_bin_sector(bin_path):
    """
    Verifica se o arquivo é um CD-ROM bruto com setores de 2352 bytes:
    Retorna (is_bin, header_offset)
    header_offset: 24 para Mode 2 Form 1, 16 para Mode 1.
    """
    size = os.path.getsize(bin_path)
    if size % 2352 != 0:
        return False, 0
    try:
        with open(bin_path, 'rb') as f:
            f.seek(16 * 2352)
            s16 = f.read(2352)
            if len(s16) == 2352:
                # Mode 2 Form 1 (CD001 no offset 24 + 1)
                if s16[24:30] == b'\x01CD001':
                    return True, 24
                # Mode 1 (CD001 no offset 16 + 1)
                if s16[16:22] == b'\x01CD001':
                    return True, 16
    except Exception:
        pass
    return False, 0

def convert_bin_to_iso(bin_path, out_iso_path, header_offset=24):
    """
    Converte uma imagem .bin de 2352 bytes/setor em .iso padrão de 2048 bytes/setor.
    """
    print(f"[*] Convertendo BIN (2352 B/setor) -> ISO (2048 B/setor): {os.path.basename(bin_path)}...")
    total_size = os.path.getsize(bin_path)
    total_sectors = total_size // 2352
    sectors_per_batch = 1024  # ~2.4 MB por lote

    bytes_read = 0
    with open(bin_path, 'rb') as fin, open(out_iso_path, 'wb') as fout:
        while True:
            chunk = fin.read(sectors_per_batch * 2352)
            if not chunk:
                break
            num_sectors = len(chunk) // 2352
            out_bytes = bytearray(num_sectors * 2048)
            for s in range(num_sectors):
                s_in = s * 2352 + header_offset
                s_out = s * 2048
                out_bytes[s_out:s_out + 2048] = chunk[s_in:s_in + 2048]
            fout.write(out_bytes)
            bytes_read += len(chunk)
            pct = (bytes_read / total_size) * 100
            print(f"\r  Progresso da conversão: {pct:.1f}% ({bytes_read // (1024*1024)} MB)", end='', flush=True)
    print(f"\n[✓] Conversão para ISO concluída: {os.path.getsize(out_iso_path) // (1024*1024)} MB")
    return True

def read_file_from_iso_dat(dat_path, serial_patterns):
    """
    Lê um arquivo de um arquivo .dat (imagem ISO9660 de configurações).
    serial_patterns: lista de substrings a procurar (ex: ['SLUS_201.74', 'SLUS-20174', '201.74']).
    """
    if not os.path.isfile(dat_path):
        return None
    try:
        with open(dat_path, 'rb') as f:
            f.seek(16 * 2048)
            pvd = f.read(2048)
            if len(pvd) < 2048 or pvd[0] != 1 or pvd[1:6] != b'CD001':
                return None
            root_rec = pvd[156:190]
            root_lba = struct.unpack('<I', root_rec[2:6])[0]
            root_size = struct.unpack('<I', root_rec[10:14])[0]
            f.seek(root_lba * 2048)
            dir_data = f.read(min(root_size, 2 * 1024 * 1024))
            curr = 0
            while curr < len(dir_data):
                rlen = dir_data[curr]
                if rlen == 0:
                    curr = ((curr // 2048) + 1) * 2048
                    continue
                if curr + rlen > len(dir_data):
                    break
                flba = struct.unpack('<I', dir_data[curr + 2:curr + 6])[0]
                fsize = struct.unpack('<I', dir_data[curr + 10:curr + 14])[0]
                nlen = dir_data[curr + 32]
                fname = dir_data[curr + 33:curr + 33 + nlen].decode('latin1', errors='ignore')
                for pat in serial_patterns:
                    if pat.upper() in fname.upper():
                        f.seek(flba * 2048)
                        return f.read(fsize)
                curr += rlen
    except Exception as e:
        print(f"[!] Erro ao ler {dat_path}: {e}")
    return None

def write_param_sfo(out_sfo_path, title, title_id, content_id):
    """
    Gera o param.sfo oficial usando LibOrbisPkg.dll.
    """
    safe_title = title.replace('"', '`"').replace('$', '`$')
    ps_script = f"""
[System.Reflection.Assembly]::LoadFrom('{LIBORBIS_DLL}') | Out-Null
$sfo = New-Object LibOrbisPkg.SFO.ParamSfo
$sfo.SetValue("APP_TYPE", [LibOrbisPkg.SFO.SfoEntryType]::Integer, "1", 4)
$sfo.SetValue("APP_VER", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "01.00", 8)
$sfo.SetValue("ATTRIBUTE", [LibOrbisPkg.SFO.SfoEntryType]::Integer, "0", 4)
$sfo.SetValue("CATEGORY", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "gd", 4)
$sfo.SetValue("CONTENT_ID", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "{content_id}", 48)
$sfo.SetValue("DOWNLOAD_DATA_SIZE", [LibOrbisPkg.SFO.SfoEntryType]::Integer, "0", 4)
$sfo.SetValue("FORMAT", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "obs", 4)
$sfo.SetValue("PARENTAL_LEVEL", [LibOrbisPkg.SFO.SfoEntryType]::Integer, "5", 4)
$sfo.SetValue("REMOTE_PLAY_KEY_ASSIGN", [LibOrbisPkg.SFO.SfoEntryType]::Integer, "0", 4)
$sfo.SetValue("SYSTEM_VER", [LibOrbisPkg.SFO.SfoEntryType]::Integer, "0", 4)
$sfo.SetValue("TITLE", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "{safe_title}", 128)
$sfo.SetValue("TITLE_ID", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "{title_id}", 12)
$sfo.SetValue("VERSION", [LibOrbisPkg.SFO.SfoEntryType]::Utf8, "01.00", 8)
[System.IO.File]::WriteAllBytes('{out_sfo_path}', $sfo.Serialize())
"""
    ret = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script], capture_output=True, text=True)
    if ret.returncode != 0 or not os.path.isfile(out_sfo_path):
        raise RuntimeError(f"Falha ao gerar param.sfo com LibOrbisPkg: {ret.stderr}")

def convert_cover_to_icon0(cover_path, out_icon_path):
    """
    Converte a imagem de capa em um PNG 512x512 24-bit RGB (icon0.png).
    Tenta PIL; fallback para .NET System.Drawing via PowerShell.
    """
    if not os.path.isfile(cover_path):
        return False
    try:
        from PIL import Image
        img = Image.open(cover_path).convert('RGB')
        img = img.resize((512, 512), Image.Resampling.LANCZOS)
        img.save(out_icon_path, 'PNG')
        return True
    except Exception:
        pass

    # Fallback: .NET System.Drawing via PowerShell
    try:
        ps_code = f"""
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile('{cover_path}')
$bmp = New-Object System.Drawing.Bitmap(512, 512, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($img, 0, 0, 512, 512)
$bmp.Save('{out_icon_path}', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
$img.Dispose()
"""
        ret = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_code], capture_output=True)
        if ret.returncode == 0 and os.path.isfile(out_icon_path) and os.path.getsize(out_icon_path) > 1024:
            return True
    except Exception as e:
        print(f"[!] Erro ao converter icon0.png via PowerShell: {e}")

    return False

def get_serial_variants(serial):
    """
    Gera variantes de formato de serial para busca:
    SLUS-20174 -> ['SLUS_201.74', 'SLUS-20174', 'SLUS20174', '201.74', '20174']
    """
    if not serial:
        return []
    clean = re.sub(r'[^A-Za-z0-9]', '', serial).upper()
    prefix = clean[:4]
    num = clean[4:]
    dot_fmt = f"{prefix}_{num[:3]}.{num[3:]}" if len(num) == 5 else clean
    dash_fmt = f"{prefix}-{num}"
    short_dot = f"{num[:3]}.{num[3:]}" if len(num) == 5 else num
    return [dot_fmt, dash_fmt, clean, short_dot, num]

def convert_single_game(game_file_path):
    r"""
    Converte um único arquivo .iso ou .bin em um .pkg em E:\PS2-PS4\pkgs\.
    """
    if not os.path.isfile(game_file_path):
        print(f"[!] Arquivo não encontrado: {game_file_path}")
        return None

    filename = os.path.basename(game_file_path)
    print("\n" + "=" * 65)
    print(f"🎮 Iniciando Conversão: {filename}")
    print("=" * 65)

    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(PKGS_DIR, exist_ok=True)
    os.makedirs(COVERS_DIR, exist_ok=True)

    # 1. Identifica se é BIN CD-ROM e se precisa de conversão prévia
    is_bin, h_off = is_raw_bin_sector(game_file_path)
    temp_iso_path = None
    iso_to_process = game_file_path

    if is_bin:
        temp_iso_path = os.path.join(CACHE_DIR, Path(filename).stem + "_converted.iso")
        convert_bin_to_iso(game_file_path, temp_iso_path, header_offset=h_off)
        iso_to_process = temp_iso_path

    # 2. Inspeciona a imagem ISO para extrair Serial e Título
    meta = parse_iso(iso_to_process)
    serial = meta.get('serial')
    if not serial:
        serial = normalize_serial(filename)
    if not serial:
        serial = "SLUS-20001"

    clean_serial = re.sub(r'[^A-Za-z0-9]', '', serial).upper()
    title_id = clean_serial  # ex: SLUS20174
    content_id = f"UP9000-{title_id}_00-{title_id}0000001"

    # Nome oficial do banco ps2ids.txt
    official_title = get_official_title(serial, BASE_DIR)
    game_title = official_title or meta.get('title') or Path(filename).stem
    safe_title = sanitize_filename(game_title)

    print(f"[*] Serial Detectado: {serial}")
    print(f"[*] Title ID PS4:    {title_id}")
    print(f"[*] Content ID:       {content_id}")
    print(f"[*] Título Oficial:   {game_title}")

    # Verifica se já existe PKG
    expected_pkg_name = f"{safe_title} [{title_id}].pkg"
    final_pkg_path = os.path.join(PKGS_DIR, expected_pkg_name)
    if os.path.isfile(final_pkg_path) and os.path.getsize(final_pkg_path) > 10 * 1024 * 1024:
        print(f"[✓] O arquivo PKG já existe em: {final_pkg_path}")
        if temp_iso_path and os.path.exists(temp_iso_path):
            os.remove(temp_iso_path)
        return final_pkg_path

    # 3. Cria pasta de Staging
    staging_dir = os.path.join(CACHE_DIR, f"stage_{title_id}")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)

    print(f"[*] Montando staging do emulador Jak v2...")
    shutil.copytree(EMU_DIR, staging_dir)
    os.makedirs(os.path.join(staging_dir, 'image'), exist_ok=True)
    os.makedirs(os.path.join(staging_dir, 'patches'), exist_ok=True)
    os.makedirs(os.path.join(staging_dir, 'sce_sys'), exist_ok=True)

    # 4. Cria sce_sys/param.sfo
    sfo_path = os.path.join(staging_dir, 'sce_sys', 'param.sfo')
    write_param_sfo(sfo_path, game_title, title_id, content_id)
    print(f"  [✓] param.sfo gerado com sucesso via LibOrbisPkg.")

    # 5. Capa / Ícone (icon0.png)
    cover_file = download_cover(serial, COVERS_DIR, auto_download=True)
    if cover_file:
        cover_path = os.path.join(COVERS_DIR, cover_file)
        icon0_dest = os.path.join(staging_dir, 'sce_sys', 'icon0.png')
        if convert_cover_to_icon0(cover_path, icon0_dest):
            print(f"  [✓] Capa convertida para sce_sys/icon0.png (512x512 24bpp).")
        else:
            print(f"  [!] Não foi possível redimensionar capa, usando ícone padrão.")
    else:
        print(f"  [*] Usando ícone padrão do emulador.")

    # 6. Busca de Patches LUA e TXT
    variants = get_serial_variants(serial)
    has_patches = False
    
    # LUA Config
    lua_dat = os.path.join(CONFIGS_DIR, 'configs_lua.dat')
    lua_bytes = read_file_from_iso_dat(lua_dat, variants)
    if lua_bytes:
        lua_out = os.path.join(staging_dir, 'patches', f"{serial}_config.lua")
        with open(lua_out, 'wb') as f:
            f.write(lua_bytes)
        has_patches = True
        print(f"  [✓] Patch LUA oficial encontrado e injetado: {os.path.basename(lua_out)} ({len(lua_bytes)} bytes)")
        # Copia lua_include
        if os.path.isdir(LUA_INC_DIR):
            shutil.copytree(LUA_INC_DIR, os.path.join(staging_dir, 'lua_include'), dirs_exist_ok=True)

    # TXT Config
    txt_dat = os.path.join(CONFIGS_DIR, 'configs_txt.dat')
    txt_bytes = read_file_from_iso_dat(txt_dat, variants)
    txt_patch_content = ""
    if txt_bytes:
        try:
            txt_patch_content = txt_bytes.decode('utf-8', errors='ignore').strip()
            print(f"  [✓] Configuração TXT oficial encontrada ({len(txt_patch_content)} caracteres).")
        except Exception:
            pass

    # 7. Configura config-emu-ps4.txt
    emu_cfg_path = os.path.join(staging_dir, 'config-emu-ps4.txt')
    emu_config_lines = [
        '--path-vmc="/tmp/vmc"',
        '--config-local-lua=""',
        f'--ps2-title-id={serial}',
        '--max-disc-num=1',
        '--gs-uprender=2x2',
        '--gs-upscale=edgesmooth',
        '--host-audio=1',
        '--rom="PS20220WD20050620.crack"',
        '--verbose-cdvd-reads=0',
        '--host-display-mode=full',
    ]
    if has_patches:
        emu_config_lines.append('--path-patches="/app0/patches"')
    if txt_patch_content:
        emu_config_lines.append('\n# Game Specific Config')
        emu_config_lines.append(txt_patch_content)

    with open(emu_cfg_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(emu_config_lines) + '\n')
    print(f"  [✓] config-emu-ps4.txt configurado.")

    # 8. Gera o projeto GP4 via gengp4_patch.exe
    print(f"[*] Gerando arquivo de projeto .gp4 com gengp4_patch.exe...")
    ret_gp4 = subprocess.run([GENGP4_BIN, staging_dir], capture_output=True, text=True)
    gp4_path = staging_dir + ".gp4"
    if ret_gp4.returncode != 0 or not os.path.isfile(gp4_path):
        print(f"[!] Falha ao gerar .gp4 via gengp4_patch.exe: {ret_gp4.stderr}")
        return None

    # 9. Ajusta o GP4 para versão 1.0 e insere disc01.iso
    with open(gp4_path, 'r', encoding='utf-8') as f:
        gp4_xml = f.read()

    gp4_xml = gp4_xml.replace('<?xml version="1.1"', '<?xml version="1.0"')
    gp4_xml = gp4_xml.replace('<scenarios default_id="1">', '<scenarios default_id="0">')
    disc_entry = f'    <file targ_path="image/disc01.iso" orig_path="{iso_to_process}" pfs_compression="enable"/>\n</files>'
    gp4_xml = gp4_xml.replace('</files>', disc_entry)

    with open(gp4_path, 'w', encoding='utf-8') as f:
        f.write(gp4_xml)
    print(f"  [✓] Projeto GP4 estruturado com disc01.iso.")

    # 10. Empacota com orbis-pub-cmd
    print(f"[*] Compilando PKG com orbis-pub-cmd (isso pode levar alguns minutos)...")
    cmd_pub = [
        ORBIS_PUB_BIN,
        "img_create",
        "--oformat", "pkg",
        "--skip_digest",
        "--no_progress_bar",
        gp4_path,
        PKGS_DIR
    ]
    ret_pub = subprocess.run(cmd_pub, capture_output=True, text=True)
    if ret_pub.returncode != 0:
        print(f"[!] Falha na criação do PKG: {ret_pub.stdout}\n{ret_pub.stderr}")
        return None

    # Localiza o PKG gerado (UP9000-...-A0100-V0100.pkg)
    created_pkg = None
    for f in os.listdir(PKGS_DIR):
        if f.startswith(content_id) and f.endswith('.pkg'):
            created_pkg = os.path.join(PKGS_DIR, f)
            break

    if not created_pkg or not os.path.isfile(created_pkg):
        # Fallback: procura o PKG mais recente na pasta
        all_pkgs = [os.path.join(PKGS_DIR, p) for p in os.listdir(PKGS_DIR) if p.endswith('.pkg')]
        if all_pkgs:
            created_pkg = max(all_pkgs, key=os.path.getmtime)

    if created_pkg and os.path.isfile(created_pkg):
        # Renomeia para nome amigável se desejado
        if created_pkg != final_pkg_path:
            if os.path.exists(final_pkg_path):
                os.remove(final_pkg_path)
            shutil.move(created_pkg, final_pkg_path)
            created_pkg = final_pkg_path

        size_mb = os.path.getsize(created_pkg) / (1024 * 1024)
        print(f"\n🎉 [SUCESSO] PKG Criado: {os.path.basename(created_pkg)} ({size_mb:.1f} MB)")
    else:
        print(f"[!] PKG não encontrado na pasta de destino após compilação.")
        return None

    # 11. Limpeza de temporários
    print(f"[*] Limpando arquivos temporários de staging...")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)
    if os.path.exists(gp4_path):
        os.remove(gp4_path)
    if temp_iso_path and os.path.exists(temp_iso_path):
        os.remove(temp_iso_path)

    # 12. Atualiza catálogo do FPKGi
    update_library_and_json(BASE_DIR)
    return created_pkg

def convert_all_pending_isos():
    """
    Busca todas as ISOs/BINs em isos/ que ainda não foram convertidas e as converte.
    """
    print("=" * 65)
    print("📀 Verificando ISOs pendentes de conversão em isos/...")
    print("=" * 65)

    converted_list = []
    
    # Coleta PKGs existentes
    existing_serials = set()
    existing_names = set()
    if os.path.isdir(PKGS_DIR):
        for f in os.listdir(PKGS_DIR):
            if f.lower().endswith('.pkg'):
                pkg_p = os.path.join(PKGS_DIR, f)
                meta = parse_pkg(pkg_p)
                if meta.get('title_id'):
                    existing_serials.add(meta['title_id'].upper())
                if meta.get('ps2_serial'):
                    clean_s = re.sub(r'[^A-Za-z0-9]', '', meta['ps2_serial']).upper()
                    existing_serials.add(clean_s)
                if meta.get('name'):
                    existing_names.add(meta['name'].strip().lower())

    # Lista ISOs
    iso_candidates = []
    if os.path.isdir(ISOS_DIR):
        for f in sorted(os.listdir(ISOS_DIR)):
            if f.lower().endswith(('.iso', '.bin')):
                full_p = os.path.join(ISOS_DIR, f)
                if os.path.isfile(full_p) and os.path.getsize(full_p) > 10 * 1024 * 1024:
                    iso_candidates.append(full_p)

    print(f"[*] Encontradas {len(iso_candidates)} imagens de PS2 em {ISOS_DIR}.")

    for iso_p in iso_candidates:
        fname = os.path.basename(iso_p)
        meta = parse_iso(iso_p)
        serial = meta.get('serial') or normalize_serial(fname)
        clean_ser = re.sub(r'[^A-Za-z0-9]', '', serial or '').upper()
        title = meta.get('title') or ''

        # Checa se já convertido
        if clean_ser in existing_serials or (title and title.strip().lower() in existing_names):
            print(f"[✓] {fname} ({title}) já possui PKG compilado. Pulando.")
            continue

        pkg = convert_single_game(iso_p)
        if pkg:
            converted_list.append(pkg)
            if clean_ser:
                existing_serials.add(clean_ser)

    print("\n" + "=" * 65)
    print(f"🏁 Processo finalizado: {len(converted_list)} novos PKGs gerados!")
    print("=" * 65)
    return converted_list

def main():
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if os.path.isfile(arg):
                convert_single_game(arg)
            else:
                print(f"[!] Arquivo inválido: {arg}")
    else:
        convert_all_pending_isos()

if __name__ == '__main__':
    main()
