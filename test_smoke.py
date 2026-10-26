#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke / Unit Test para validação do PS2-PS4 FPKGi Server.
Testa:
1. Leitura de ISO9660 e extração de SYSTEM.CNF / Serial PS2
2. Leitura de PKG PS4 com CONTENT_ID e param.sfo
3. Schema do json/PS2.json gerado
4. Servidor HTTP: HEAD, GET /, GET /json/PS2.json, GET /fpkgi/config.json
5. HTTP Byte Range (206 Partial Content) para downloads no PS4
6. Endpoint POST /api/rescan
"""

import os
import sys
import time
import struct
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Força UTF-8 no stdout do Windows se necessário
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from scanner import parse_iso, parse_pkg, generate_fpkgi_json, normalize_serial, parse_sfo
from server import FPKGiRequestHandler, BASE_DIR

def build_dummy_sfo(title="Grand Theft Auto", title_id="CUSA00001", app_ver="1.00"):
    """Constrói um buffer binário sintético param.sfo válido."""
    magic = b'\x00PSF'
    version = b'\x01\x01\x00\x00'
    entries_dict = {
        'APP_VER': app_ver.encode('utf-8') + b'\x00',
        'TITLE': title.encode('utf-8') + b'\x00',
        'TITLE_ID': title_id.encode('utf-8') + b'\x00',
    }
    
    count = len(entries_dict)
    key_table = bytearray()
    data_table = bytearray()
    index_table = bytearray()
    
    for key, val_bytes in sorted(entries_dict.items()):
        k_off = len(key_table)
        key_table.extend(key.encode('utf-8') + b'\x00')
        d_off = len(data_table)
        data_table.extend(val_bytes)
        # 16 bytes per entry: key_off(2), fmt(2), len(4), max_len(4), data_off(4)
        index_table.extend(struct.pack('<HHIII', k_off, 0x0204, len(val_bytes), len(val_bytes), d_off))
        
    key_offset = 20 + count * 16
    data_offset = key_offset + len(key_table)
    
    header = struct.pack('<4s4sIII', magic, version, key_offset, data_offset, count)
    return header + bytes(index_table) + bytes(key_table) + bytes(data_table)

def create_synthetic_pkg(path):
    """Cria um arquivo .pkg sintético com cabeçalho PS4 e param.sfo."""
    with open(path, 'wb') as f:
        # Magic \x7fCNT
        f.write(b'\x7fCNT')
        f.write(b'\x00' * (0x40 - 4))
        # CONTENT_ID em 0x40 (36 bytes)
        content_id = b'UP9000-CUSA01234_00-SLUS200620000001'
        f.write(content_id.ljust(36, b'\x00'))
        f.write(b'\x00' * (512 - 0x40 - 36))
        # param.sfo nos primeiros 64KB
        f.seek(1024)
        sfo_bytes = build_dummy_sfo(title="Shadow of the Colossus", title_id="CUSA01234")
        f.write(sfo_bytes)
        # Preenche com dados até 1MB
        f.seek(1024 * 1024 - 1)
        f.write(b'\x00')

def create_synthetic_iso(path):
    """Cria uma imagem .iso sintética com PVD ISO9660 e SYSTEM.CNF."""
    with open(path, 'wb') as f:
        # Setores 0 a 15 zerados
        f.write(b'\x00' * (16 * 2048))
        
        # Setor 16: PVD
        pvd = bytearray(2048)
        pvd[0] = 1 # Type
        pvd[1:6] = b'CD001' # Identifier
        # Volume label no offset 40
        vol_label = b'SOTC_PS2_TEST'
        pvd[40:40+len(vol_label)] = vol_label
        
        # Root dir record no offset 156
        # LBA = 17, size = 2048
        root_rec = bytearray(34)
        root_rec[0] = 34
        root_rec[2:6] = struct.pack('<I', 17) # LBA LE
        root_rec[6:10] = struct.pack('>I', 17) # LBA BE
        root_rec[10:14] = struct.pack('<I', 2048) # Size LE
        root_rec[14:18] = struct.pack('>I', 2048) # Size BE
        pvd[156:190] = root_rec
        f.write(pvd)
        
        # Setor 17: Diretório Raiz contendo entrada SYSTEM.CNF
        root_dir = bytearray(2048)
        # Entrada 1: SYSTEM.CNF (LBA = 18, size = 64)
        name = b'SYSTEM.CNF;1'
        rec_len = 33 + len(name)
        if rec_len % 2 != 0:
            rec_len += 1
        entry = bytearray(rec_len)
        entry[0] = rec_len
        entry[2:6] = struct.pack('<I', 18) # LBA LE
        entry[6:10] = struct.pack('>I', 18) # LBA BE
        entry[10:14] = struct.pack('<I', 64) # Size LE
        entry[14:18] = struct.pack('>I', 64) # Size BE
        entry[32] = len(name)
        entry[33:33+len(name)] = name
        root_dir[0:rec_len] = entry
        f.write(root_dir)
        
        # Setor 18: Conteúdo de SYSTEM.CNF
        cnf_data = b"BOOT2 = cdrom0:\\SLUS_200.62;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
        f.write(cnf_data.ljust(2048, b'\x00'))

def run_tests():
    print("[*] Iniciando testes de validação...")
    
    # 1. Teste de normalização de seriais
    assert normalize_serial("SLUS_200.62") == "SLUS-20062", "Falha na normalização de SLUS_200.62"
    assert normalize_serial("SLUS20062") == "SLUS-20062", "Falha na normalização de SLUS20062"
    assert normalize_serial("sles_501.23") == "SLES-50123", "Falha na normalização de sles_501.23"
    print("  [✓] Teste de normalização de seriais passou.")

    # 2. Teste do parser SFO
    sfo_sample = build_dummy_sfo("Test Game", "CUSA00123")
    parsed_sfo = parse_sfo(sfo_sample)
    assert parsed_sfo.get('TITLE') == "Test Game", "Falha ao decodificar TITLE no SFO"
    assert parsed_sfo.get('TITLE_ID') == "CUSA00123", "Falha ao decodificar TITLE_ID no SFO"
    print("  [✓] Teste de decodificação param.sfo passou.")

    # Cria diretórios de teste em E:\PS2-PS4
    test_pkgs_dir = os.path.join(BASE_DIR, 'pkgs')
    test_isos_dir = os.path.join(BASE_DIR, 'isos')
    dummy_pkg_path = os.path.join(test_pkgs_dir, 'Test_Game.pkg')
    dummy_iso_path = os.path.join(test_isos_dir, 'Test_Game.iso')

    create_synthetic_pkg(dummy_pkg_path)
    create_synthetic_iso(dummy_iso_path)

    try:
        # 3. Teste de parse_pkg
        pkg_res = parse_pkg(dummy_pkg_path)
        assert pkg_res['title_id'] == 'CUSA01234', f"Esperado CUSA01234, obteve {pkg_res['title_id']}"
        assert pkg_res['name'] == 'Shadow of the Colossus', f"Nome incorreto: {pkg_res['name']}"
        assert pkg_res['ps2_serial'] == 'SLUS-20062', f"Serial incorreto: {pkg_res['ps2_serial']}"
        print(f"  [✓] Teste de parse_pkg passou ({pkg_res['title_id']} - {pkg_res['name']}).")

        # 4. Teste de parse_iso
        iso_res = parse_iso(dummy_iso_path)
        assert iso_res['serial'] == 'SLUS-20062', f"Serial ISO incorreto: {iso_res['serial']}"
        assert iso_res['region'] == 'USA', f"Região ISO incorreta: {iso_res['region']}"
        print(f"  [✓] Teste de parse_iso passou ({iso_res['serial']} - {iso_res['region']}).")

        # 5. Teste de schema do FPKGi JSON
        fpkgi_json = generate_fpkgi_json([pkg_res], "192.168.1.100", 8080)
        assert "DATA" in fpkgi_json, "Chave DATA ausente no JSON do FPKGi"
        first_key = list(fpkgi_json["DATA"].keys())[0]
        assert first_key == "http://192.168.1.100:8080/pkgs/Test_Game.pkg"
        item = fpkgi_json["DATA"][first_key]
        assert item["title_id"] == "CUSA01234"
        assert item["name"] == "Shadow of the Colossus"
        assert item["size"] > 0
        assert item["region"] == "USA"
        print("  [✓] Schema do FPKGi JSON válido.")

        # 6. Teste do Servidor HTTP com Threads e Range Requests
        test_port = 18099
        httpd = ThreadingHTTPServer(('127.0.0.1', test_port), FPKGiRequestHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)

        base_url = f"http://127.0.0.1:{test_port}"

        # GET / (Dashboard)
        with urllib.request.urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            html_text = resp.read().decode('utf-8')
            assert "PS2 to PS4 FPKGi Server" in html_text
            assert "Shadow of the Colossus" in html_text
        print("  [✓] Servidor HTTP: GET / (Dashboard) respondeu 200 OK.")

        # GET /json/PS2.json
        with urllib.request.urlopen(f"{base_url}/json/PS2.json") as resp:
            assert resp.status == 200
            json_body = json.loads(resp.read().decode('utf-8'))
            assert "DATA" in json_body
            assert len(json_body["DATA"]) >= 1
        print("  [✓] Servidor HTTP: GET /json/PS2.json respondeu 200 OK com catálogo dinâmico.")

        # GET /fpkgi/config.json
        with urllib.request.urlopen(f"{base_url}/fpkgi/config.json") as resp:
            assert resp.status == 200
            cfg_body = json.loads(resp.read().decode('utf-8'))
            assert cfg_body.get("populateViaWeb") is True
            assert cfg_body["PREFERENCES"]["APPLICATION"]["populateViaWeb"] is True
            assert "/json/PS2.json" in cfg_body["PREFERENCES"]["CONTENT_URLS"]["PS2"]
            assert "127.0.0.1" not in cfg_body["PREFERENCES"]["CONTENT_URLS"]["PS2"] or get_local_ip() == "127.0.0.1"
        print("  [✓] Servidor HTTP: GET /fpkgi/config.json respondeu 200 OK configurado com IP da LAN.")

        # HEAD /pkgs/Test_Game.pkg
        req_head = urllib.request.Request(f"{base_url}/pkgs/Test_Game.pkg", method='HEAD')
        with urllib.request.urlopen(req_head) as resp:
            assert resp.status == 200
            assert resp.headers.get('Accept-Ranges') == 'bytes'
            assert int(resp.headers.get('Content-Length')) == 1024 * 1024
        print("  [✓] Servidor HTTP: HEAD respondeu 200 OK com Accept-Ranges e Content-Length.")

        # GET /pkgs/Test_Game.pkg com Range: bytes=10-29 (20 bytes)
        req_range = urllib.request.Request(f"{base_url}/pkgs/Test_Game.pkg")
        req_range.add_header('Range', 'bytes=10-29')
        with urllib.request.urlopen(req_range) as resp:
            assert resp.status == 206, f"Esperado 206 Partial Content, obteve {resp.status}"
            assert resp.headers.get('Content-Range') == f"bytes 10-29/{1024*1024}"
            assert resp.headers.get('Content-Length') == '20'
            slice_data = resp.read()
            assert len(slice_data) == 20
        print("  [✓] Servidor HTTP: Range request (206 Partial Content) respondeu com fatia exata.")

        # POST /api/rescan
        req_rescan = urllib.request.Request(f"{base_url}/api/rescan", data=b'', method='POST')
        with urllib.request.urlopen(req_rescan) as resp:
            assert resp.status == 200
            rescan_data = json.loads(resp.read().decode('utf-8'))
            assert rescan_data.get('success') is True
            assert rescan_data.get('pkgs_count') >= 1
        print("  [✓] Servidor HTTP: POST /api/rescan respondeu 200 OK com contagem de jogos.")

        # Desliga servidor de teste
        httpd.shutdown()
        httpd.server_close()
        print("  [✓] Servidor de teste encerrado com sucesso.")

    finally:
        # Limpa arquivos de teste
        if os.path.exists(dummy_pkg_path):
            os.remove(dummy_pkg_path)
        if os.path.exists(dummy_iso_path):
            os.remove(dummy_iso_path)
        test_cover = os.path.join(BASE_DIR, 'covers', 'SLUS-20062.jpg')
        if os.path.exists(test_cover):
            os.remove(test_cover)
        print("[*] Arquivos sintéticos de teste removidos.")

    print("\n" + "=" * 65)
    print("🎉 TODOS OS TESTES PASSARAM COM SUCESSO! 100% OPERACIONAL.")
    print("=" * 65)

if __name__ == '__main__':
    run_tests()
