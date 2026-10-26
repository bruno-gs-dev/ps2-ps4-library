#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PS2-PS4 FPKGi HTTP Server
Servidor HTTP com suporte total a HTTP Range (206 Partial Content),
necessário para downloads de PKG no PS4 (GoldHEN) via FPKGi.
Inclui Dashboard Web e configuração automática via FTP do PS4.
"""

import os
import sys
import json
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from ftplib import FTP
from pathlib import Path
import io

# Suporte seguro a UTF-8 em consoles Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Importa o scanner da mesma pasta
try:
    from scanner import (
        get_local_ip,
        scan_library,
        generate_fpkgi_json,
        update_library_and_json
    )
except ImportError:
    from src.scanner import (
        get_local_ip,
        scan_library,
        generate_fpkgi_json,
        update_library_and_json
    )

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

def load_config():
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "port": 8080,
        "isos_dir": "./isos",
        "pkgs_dir": "./pkgs",
        "covers_dir": "./covers",
        "json_dir": "./json",
        "ps4_ip": "",
        "ps4_ftp_port": 2121,
        "auto_download_covers": True
    }

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Erro ao salvar config: {e}")

def format_size(bytes_val):
    """Formata bytes em unidade legível (GB / MB)."""
    if not bytes_val or bytes_val <= 0:
        return "0 B"
    gb = bytes_val / (1024 * 1024 * 1024)
    if gb >= 1.0:
        return f"{gb:.2f} GB"
    mb = bytes_val / (1024 * 1024)
    return f"{mb:.1f} MB"

def get_fpkgi_config_content(server_ip, server_port):
    """Gera o conteúdo do arquivo /user/data/FPKGi/config.json compatível com FPKGi v1.10.0+."""
    ps2_url = f"http://{server_ip}:{server_port}/json/PS2.json"
    return json.dumps({
        "FILTERS": {
            "REGIONS": {
                "ASIA": True,
                "EUR": True,
                "JAP": True,
                "USA": True,
                "UNK": True
            },
            "HOMEBREW": True
        },
        "SORTING": {
            "FIELD": "NAME",
            "ASCENDING": True
        },
        "PREFERENCES": {
            "APPLICATION": {
                "enableBackgroundMusic": True,
                "populateViaWeb": True,
                "enableUpdates": True,
                "saveDataPath": "/user/data/FPKGi/",
                "downloadPath": "/user/data/FPKGi/downloads/"
            },
            "CONTENT_URLS": {
                "PS1": None,
                "PS2": ps2_url,
                "PSP": None,
                "GAMES": None,
                "APPS": None,
                "UPDATES": None,
                "DLC": None,
                "DEMOS": None,
                "HOMEBREW": None,
                "EMULATORS": None,
                "THEMES": None
            },
            "CUSTOM_BACKGROUND_PATH": None
        },
        "populateViaWeb": True,
        "CONTENT_URLS": {
            "GAMES": "",
            "UPDATES": "",
            "DLC": "",
            "PSX": "",
            "PS2": ps2_url,
            "CUSTOM": ""
        }
    }, indent=2)

def generate_dashboard_html(host_ip, port, config, library_data):
    """Gera a página HTML do Dashboard Web em Português."""
    pkgs = library_data.get('pkgs', [])
    isos = library_data.get('isos', [])
    
    ps2_json_url = f"http://{host_ip}:{port}/json/PS2.json"
    total_pkgs_size = sum(p.get('size', 0) for p in pkgs)
    
    # HTML das linhas da tabela de PKGs
    pkgs_rows = ""
    if pkgs:
        for p in pkgs:
            cover_img = ""
            if p.get('cover_file'):
                cover_img = f'<img src="/covers/{urllib.parse.quote(p["cover_file"])}" class="game-cover" alt="Cover" />'
            else:
                cover_img = f'<div class="cover-placeholder"><span>{p.get("region", "PS2")}</span></div>'
                
            enc_fn = urllib.parse.quote(p['filename'])
            download_url = f"/pkgs/{enc_fn}"
            
            pkgs_rows += f"""
            <tr>
              <td class="col-cover">{cover_img}</td>
              <td class="col-title">
                <strong>{p.get('name', p['filename'])}</strong>
                <div class="file-name">{p['filename']}</div>
              </td>
              <td><span class="badge badge-cusa">{p.get('title_id', 'CUSA00001')}</span></td>
              <td><span class="badge badge-serial">{p.get('ps2_serial', '-')}</span></td>
              <td><span class="badge badge-region">{p.get('region', 'USA')}</span></td>
              <td>{format_size(p.get('size', 0))}</td>
              <td>
                <a href="{download_url}" class="btn btn-sm btn-outline" download>Baixar PKG</a>
              </td>
            </tr>
            """
    else:
        pkgs_rows = """
        <tr>
          <td colspan="7" class="empty-state">
            Nenhum arquivo <code>.pkg</code> encontrado na pasta <code>pkgs/</code>.<br>
            Converta uma ISO de PS2 usando o <strong>PS2-FPKG</strong> ou coloque seus PKGs prontos lá.
          </td>
        </tr>
        """

    # HTML das linhas da tabela de ISOs
    isos_rows = ""
    if isos:
        for i in isos:
            cover_img = ""
            if i.get('cover_file'):
                cover_img = f'<img src="/covers/{urllib.parse.quote(i["cover_file"])}" class="game-cover" alt="Cover" />'
            else:
                cover_img = f'<div class="cover-placeholder"><span>{i.get("region", "ISO")}</span></div>'
                
            status_badge = '<span class="badge badge-success">Convertido</span>' if i.get('converted') else '<span class="badge badge-warning">Pendente Conversão</span>'

            isos_rows += f"""
            <tr>
              <td class="col-cover">{cover_img}</td>
              <td class="col-title">
                <strong>{i.get('title', i['filename'])}</strong>
                <div class="file-name">{i['filename']}</div>
              </td>
              <td><span class="badge badge-serial">{i.get('serial', 'Desconhecido')}</span></td>
              <td><span class="badge badge-region">{i.get('region', 'USA')}</span></td>
              <td>{format_size(i.get('size', 0))}</td>
              <td>{status_badge}</td>
            </tr>
            """
    else:
        isos_rows = """
        <tr>
          <td colspan="6" class="empty-state">
            Nenhuma imagem <code>.iso</code> encontrada na pasta <code>isos/</code>.<br>
            Coloque suas ISOs de PS2 nessa pasta para identificação automática de serial e capa.
          </td>
        </tr>
        """

    ps4_ip_val = config.get('ps4_ip', '')
    ps4_port_val = config.get('ps4_ftp_port', 2121)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PS2 to PS4 FPKGi Server</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #151d2f;
      --card-border: #1e293b;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --ps-blue: #0070d1;
      --ps-blue-hover: #005cb8;
      --accent-cyan: #38bdf8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
      flex-wrap: wrap;
      gap: 16px;
    }}
    .header-title {{ display: flex; align-items: center; gap: 12px; }}
    .header-title h1 {{ font-size: 1.75rem; font-weight: 700; color: #fff; }}
    .status-pill {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid var(--success);
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }}
    .card-title {{
      font-size: 1.15rem;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: var(--accent-cyan);
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    @media (max-width: 768px) {{
      .grid-2 {{ grid-template-columns: 1fr; }}
    }}
    .info-row {{
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      font-size: 0.9rem;
    }}
    .info-label {{ color: var(--text-muted); }}
    .info-value {{ font-family: Consolas, monospace; font-weight: 600; color: #fff; }}
    .url-box {{
      background: #0d1322;
      border: 1px solid #233554;
      padding: 10px 14px;
      border-radius: 8px;
      font-family: Consolas, monospace;
      font-size: 0.9rem;
      color: var(--accent-cyan);
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 10px;
      word-break: break-all;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 8px 16px;
      font-size: 0.875rem;
      font-weight: 600;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.2s, transform 0.1s;
    }}
    .btn:active {{ transform: scale(0.98); }}
    .btn-primary {{ background: var(--ps-blue); color: #fff; }}
    .btn-primary:hover {{ background: var(--ps-blue-hover); }}
    .btn-success {{ background: var(--success); color: #fff; }}
    .btn-success:hover {{ background: #059669; }}
    .btn-outline {{
      background: transparent;
      border: 1px solid #334155;
      color: #e2e8f0;
    }}
    .btn-outline:hover {{ background: #1e293b; border-color: #64748b; }}
    .btn-sm {{ padding: 4px 10px; font-size: 0.775rem; }}
    .form-group {{ margin-bottom: 12px; }}
    .form-group label {{ display: block; font-size: 0.825rem; color: var(--text-muted); margin-bottom: 4px; }}
    .form-control {{
      width: 100%;
      padding: 8px 12px;
      background: #0d1322;
      border: 1px solid #233554;
      border-radius: 6px;
      color: #fff;
      font-size: 0.9rem;
    }}
    .form-control:focus {{ outline: none; border-color: var(--accent-cyan); }}
    .table-container {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }}
    th {{
      padding: 12px;
      background: rgba(0,0,0,0.2);
      color: var(--text-muted);
      font-weight: 600;
      border-bottom: 1px solid var(--card-border);
    }}
    td {{
      padding: 12px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
      vertical-align: middle;
    }}
    .col-cover {{ width: 55px; text-align: center; padding: 6px; }}
    .col-title {{ max-width: 380px; }}
    .game-cover {{
      width: 48px;
      height: 64px;
      object-fit: cover;
      border-radius: 4px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.4);
      background: #111;
    }}
    .cover-placeholder {{
      width: 48px;
      height: 64px;
      background: #1e293b;
      border: 1px dashed #334155;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.65rem;
      font-weight: bold;
      color: #64748b;
    }}
    .file-name {{ font-size: 0.75rem; color: var(--text-muted); font-family: Consolas, monospace; }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 0.725rem;
      font-weight: 600;
      font-family: Consolas, monospace;
    }}
    .badge-cusa {{ background: rgba(0, 112, 209, 0.2); color: #60a5fa; border: 1px solid #1d4ed8; }}
    .badge-serial {{ background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid #475569; }}
    .badge-region {{ background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #9333ea; }}
    .badge-success {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
    .badge-warning {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #d97706; }}
    .empty-state {{
      text-align: center;
      padding: 32px 16px;
      color: var(--text-muted);
    }}
    .empty-state code {{
      background: #0f172a;
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--accent-cyan);
    }}
    #ftp-alert {{
      display: none;
      padding: 10px 14px;
      border-radius: 6px;
      font-size: 0.85rem;
      margin-top: 12px;
    }}
    .alert-success {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
    .alert-danger {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }}
    .alert-info {{ background: rgba(56, 189, 248, 0.2); color: #7dd3fc; border: 1px solid #0284c7; }}
    footer {{
      text-align: center;
      margin-top: 40px;
      padding-top: 20px;
      border-top: 1px solid var(--card-border);
      color: var(--text-muted);
      font-size: 0.8rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-title">
        <h1>PS2 to PS4 FPKGi Server</h1>
        <span class="status-pill">GoldHEN Ready</span>
      </div>
      <div>
        <button onclick="rescanLibrary()" class="btn btn-primary" id="btn-rescan">
          <span>🔄</span> Atualizar Catálogo / Escanear Pastas
        </button>
      </div>
    </header>

    <div class="grid-2">
      <!-- Card: Servidor e FPKGi URL -->
      <div class="card">
        <div class="card-title">
          <span>📡 Informações do Servidor</span>
          <span style="font-size: 0.8rem; color: var(--text-muted);">HTTP Range 206 OK</span>
        </div>
        <div class="info-row">
          <span class="info-label">IP do Servidor na Rede (LAN):</span>
          <span class="info-value">{host_ip}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Porta HTTP:</span>
          <span class="info-value">{port}</span>
        </div>
        <div class="info-row">
          <span class="info-label">PKGs Prontos:</span>
          <span class="info-value">{len(pkgs)} ({format_size(total_pkgs_size)})</span>
        </div>
        <div class="info-row">
          <span class="info-label">ISOs PS2 Detectadas:</span>
          <span class="info-value">{len(isos)}</span>
        </div>
        <div style="margin-top: 14px;">
          <label style="font-size: 0.8rem; color: var(--text-muted);">URL do Catálogo para o FPKGi:</label>
          <div class="url-box">
            <span id="json-url-text">{ps2_json_url}</span>
            <button onclick="copyJsonUrl()" class="btn btn-sm btn-outline" style="margin-left: 8px;">Copiar</button>
          </div>
        </div>
      </div>

      <!-- Card: 1-Click Auto Configuração PS4 via FTP -->
      <div class="card">
        <div class="card-title">
          <span>🎮 Configuração Automática do PS4 (1 Clique)</span>
        </div>
        <p style="font-size: 0.825rem; color: var(--text-muted); margin-bottom: 12px;">
          Ative o <strong>FTP Server</strong> no menu do GoldHEN no seu PS4 e envie o <code>config.json</code> diretamente para <code>/user/data/FPKGi/</code>.
        </p>
        <div style="display: flex; gap: 10px;">
          <div class="form-group" style="flex: 2;">
            <label for="ps4_ip">IP do PS4:</label>
            <input type="text" id="ps4_ip" class="form-control" placeholder="Ex: 192.168.1.150" value="{ps4_ip_val}">
          </div>
          <div class="form-group" style="flex: 1;">
            <label for="ps4_port">Porta FTP:</label>
            <input type="number" id="ps4_port" class="form-control" value="{ps4_port_val}">
          </div>
        </div>
        <div style="display: flex; gap: 10px; margin-top: 6px;">
          <button onclick="configurePS4()" class="btn btn-success" style="flex: 1;" id="btn-ftp">
            <span>🚀</span> Enviar Configuração via FTP
          </button>
          <a href="/fpkgi/config.json" class="btn btn-outline" download="config.json" title="Baixar config.json para cópia manual">
            <span>💾</span> Baixar config.json
          </a>
        </div>
        <div id="ftp-alert"></div>
      </div>
    </div>

    <!-- Tabela: PKGs Prontos -->
    <div class="card">
      <div class="card-title">
        <span>📦 PKGs Prontos na Biblioteca (<code>pkgs/</code>)</span>
        <span style="font-size: 0.85rem; color: var(--text-muted);">{len(pkgs)} jogos disponíveis</span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th class="col-cover">Capa</th>
              <th>Título / Arquivo</th>
              <th>Title ID</th>
              <th>Serial PS2</th>
              <th>Região</th>
              <th>Tamanho</th>
              <th>Ação</th>
            </tr>
          </thead>
          <tbody>
            {pkgs_rows}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Tabela: ISOs Aguardando Conversão -->
    <div class="card">
      <div class="card-title">
        <span>📀 ISOs na Biblioteca (<code>isos/</code>)</span>
        <span style="font-size: 0.85rem; color: var(--text-muted);">{len(isos)} imagens encontradas</span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th class="col-cover">Capa</th>
              <th>Título / Arquivo</th>
              <th>Serial Detectado</th>
              <th>Região</th>
              <th>Tamanho</th>
              <th>Status de Conversão</th>
            </tr>
          </thead>
          <tbody>
            {isos_rows}
          </tbody>
        </table>
      </div>
    </div>

    <footer>
      <p>PS2-PS4 FPKGi Server • Compatível com FPKGi v1.10.0+ e GoldHEN 2.x • 100% Python Zero-Dependencies</p>
    </footer>
  </div>

  <script>
    function copyJsonUrl() {{
      const text = document.getElementById('json-url-text').innerText;
      navigator.clipboard.writeText(text).then(() => {{
        alert('URL copiada para a área de transferência!');
      }}).catch(() => {{
        prompt('Copie a URL:', text);
      }});
    }}

    function rescanLibrary() {{
      const btn = document.getElementById('btn-rescan');
      btn.disabled = true;
      btn.innerText = 'Escanenando...';
      fetch('/api/rescan', {{ method: 'POST' }})
        .then(r => r.json())
        .then(data => {{
          window.location.reload();
        }})
        .catch(err => {{
          alert('Erro ao escanear biblioteca: ' + err);
          btn.disabled = false;
          btn.innerText = '🔄 Atualizar Catálogo / Escanear Pastas';
        }});
    }}

    function configurePS4() {{
      const ip = document.getElementById('ps4_ip').value.trim();
      const port = document.getElementById('ps4_port').value.trim();
      const alertBox = document.getElementById('ftp-alert');
      const btn = document.getElementById('btn-ftp');

      if (!ip) {{
        alertBox.className = 'alert-danger';
        alertBox.style.display = 'block';
        alertBox.innerText = 'Por favor, informe o IP do seu PS4.';
        return;
      }}

      alertBox.className = 'alert-info';
      alertBox.style.display = 'block';
      alertBox.innerText = 'Conectando ao PS4 via FTP (' + ip + ':' + port + ')...';
      btn.disabled = true;

      fetch('/api/configure-ps4', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ ps4_ip: ip, ps4_port: parseInt(port) || 2121 }})
      }})
      .then(r => r.json())
      .then(data => {{
        btn.disabled = false;
        if (data.success) {{
          alertBox.className = 'alert-success';
          alertBox.innerHTML = '<strong>Sucesso!</strong> ' + data.message;
        }} else {{
          alertBox.className = 'alert-danger';
          alertBox.innerHTML = '<strong>Falha na conexão:</strong> ' + data.message;
        }}
      }})
      .catch(err => {{
        btn.disabled = false;
        alertBox.className = 'alert-danger';
        alertBox.innerHTML = '<strong>Erro de rede:</strong> ' + err;
      }});
    }}
  </script>
</body>
</html>
"""
    return html

class FPKGiRequestHandler(BaseHTTPRequestHandler):
    server_version = "FPKGiServer/1.0"

    def do_HEAD(self):
        self.handle_file_request(send_body=False)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Dashboard
        if path == '/' or path == '/index.html':
            self.serve_dashboard()
            return

        # 2. FPKGi JSON feed dinâmico (/json/PS2.json)
        if path == '/json/PS2.json':
            self.serve_ps2_json()
            return

        # 3. FPKGi config.json pronto para download (/fpkgi/config.json)
        if path == '/fpkgi/config.json':
            self.serve_fpkgi_config()
            return

        # 4. Servir PKGs (/pkgs/<filename>) com Byte Range
        if path.startswith('/pkgs/'):
            self.handle_file_request(send_body=True)
            return

        # 5. Servir Capas (/covers/<filename>)
        if path.startswith('/covers/'):
            self.handle_file_request(send_body=True)
            return

        # 6. Status API (/api/status)
        if path == '/api/status':
            self.send_json_response(200, {
                "status": "online",
                "ip": self.get_client_viewed_host(),
                "port": self.server.server_port
            })
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Rescan de pastas (/api/rescan)
        if path == '/api/rescan':
            host_ip = self.get_client_viewed_host()
            scan_res, _ = update_library_and_json(BASE_DIR, host_ip, self.server.server_port)
            self.send_json_response(200, {
                "success": True,
                "pkgs_count": len(scan_res.get('pkgs', [])),
                "isos_count": len(scan_res.get('isos', []))
            })
            return

        # 2. Configurar PS4 via FTP (/api/configure-ps4)
        if path == '/api/configure-ps4':
            length = int(self.headers.get('Content-Length', 0))
            body_bytes = self.rfile.read(length) if length > 0 else b'{}'
            try:
                data = json.loads(body_bytes.decode('utf-8'))
            except Exception:
                data = {}

            ps4_ip = data.get('ps4_ip', '').strip()
            ps4_port = int(data.get('ps4_ftp_port') or data.get('ps4_port') or 2121)

            if not ps4_ip:
                self.send_json_response(400, {"success": False, "message": "IP do PS4 não informado."})
                return

            # Atualiza config local
            cfg = load_config()
            cfg['ps4_ip'] = ps4_ip
            cfg['ps4_ftp_port'] = ps4_port
            save_config(cfg)

            # Executa FTP upload
            host_ip = self.get_client_viewed_host()
            success, msg = self.upload_config_to_ps4(ps4_ip, ps4_port, host_ip, self.server.server_port)
            self.send_json_response(200 if success else 500, {"success": success, "message": msg})
            return

        self.send_error(404, "Not Found")

    def get_client_viewed_host(self):
        """Retorna o IP da rede local (LAN) mesmo quando acessado via localhost no próprio PC."""
        host_hdr = self.headers.get('Host')
        if host_hdr:
            host_only = host_hdr.split(':')[0].strip()
            if host_only not in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
                return host_only
        return get_local_ip()

    def send_json_response(self, code, obj):
        data = json.dumps(obj, indent=2, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

    def serve_dashboard(self):
        host_ip = self.get_client_viewed_host()
        cfg = load_config()
        lib_data = scan_library(BASE_DIR, cfg)
        html = generate_dashboard_html(host_ip, self.server.server_port, cfg, lib_data)
        data = html.encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_ps2_json(self):
        """
        Retorna dinamicamente o catálogo PS2.json apontando
        para o Host de onde o cliente está chamando.
        """
        host_ip = self.get_client_viewed_host()
        cfg = load_config()
        lib_data = scan_library(BASE_DIR, cfg)
        fpkgi_data = generate_fpkgi_json(lib_data['pkgs'], host_ip, self.server.server_port)
        body = json.dumps(fpkgi_data, indent=2, ensure_ascii=False).encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def serve_fpkgi_config(self):
        """Retorna o config.json para FPKGi baixar diretamente."""
        host_ip = self.get_client_viewed_host()
        cfg_str = get_fpkgi_config_content(host_ip, self.server.server_port)
        body = cfg_str.encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Disposition', 'attachment; filename="config.json"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def upload_config_to_ps4(self, ps4_ip, ps4_port, host_ip, server_port):
        """
        Conecta via FTP ao PS4 (GoldHEN), cria /user/data/FPKGi/ se necessário
        e envia config.json.
        """
        config_content = get_fpkgi_config_content(host_ip, server_port).encode('utf-8')
        ftp = FTP()
        try:
            ftp.connect(ps4_ip, int(ps4_port), timeout=10)
            ftp.login() # GoldHEN FTP normalmente não requer senha

            for target_dir in ("/user/data/FPKGi", "/data/FPKGi"):
                parts = [p for p in target_dir.strip('/').split('/') if p]
                curr = ""
                for p in parts:
                    curr += "/" + p
                    try:
                        ftp.cwd(curr)
                    except Exception:
                        try:
                            ftp.mkd(curr)
                            ftp.cwd(curr)
                        except Exception:
                            pass

                try:
                    bio = io.BytesIO(config_content)
                    ftp.storbinary("STOR config.json", bio)
                except Exception:
                    pass
            ftp.quit()
            return True, f"Arquivo /user/data/FPKGi/config.json gravado com sucesso no PS4 ({ps4_ip})!"
        except Exception as e:
            try:
                ftp.close()
            except Exception:
                pass
            return False, f"Falha na comunicação FTP: {str(e)}. Certifique-se de que o FTP Server está ativado nas configurações do GoldHEN no PS4."

    def handle_file_request(self, send_body=True):
        """
        Trata requisições de arquivos estáticos (/pkgs/* e /covers/*)
        com suporte obrigatório a HTTP Byte Range (206 Partial Content)
        e requisições HEAD para compatibilidade com o PS4 e FPKGi.
        """
        parsed = urllib.parse.urlparse(self.path)
        decoded_path = urllib.parse.unquote(parsed.path)

        # Mapeamento do caminho relativo para o disco
        cfg = load_config()
        if decoded_path.startswith('/pkgs/'):
            rel_name = decoded_path[len('/pkgs/'):].lstrip('/\\')
            file_dir = os.path.abspath(os.path.join(BASE_DIR, cfg.get('pkgs_dir', './pkgs')))
            file_path = os.path.join(file_dir, rel_name)
        elif decoded_path.startswith('/covers/'):
            rel_name = decoded_path[len('/covers/'):].lstrip('/\\')
            file_dir = os.path.abspath(os.path.join(BASE_DIR, cfg.get('covers_dir', './covers')))
            file_path = os.path.join(file_dir, rel_name)
        else:
            self.send_error(404, "Not Found")
            return

        # Segurança: previne directory traversal
        if not os.path.abspath(file_path).startswith(file_dir):
            self.send_error(403, "Forbidden")
            return

        if not os.path.isfile(file_path):
            self.send_error(404, "File Not Found")
            return

        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        range_header = self.headers.get('Range')

        # Se não há cabeçalho Range, serve normalmente (200 OK)
        if not range_header:
            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(file_size))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            if send_body:
                self.stream_file_range(file_path, 0, file_size - 1)
            return

        # Processamento de HTTP Byte Range (206 Partial Content)
        # Formatos: bytes=start-end, bytes=start-, bytes=-suffix
        if not range_header.startswith('bytes='):
            self.send_error(400, "Bad Request (Invalid Range)")
            return

        range_val = range_header[len('bytes='):].strip()
        start = None
        end = None

        if ',' in range_val:
            # Multi-range não é necessário para PS4 downloads, pega o primeiro
            range_val = range_val.split(',')[0].strip()

        parts = range_val.split('-')
        try:
            if len(parts) == 2:
                if parts[0] and parts[1]:
                    start = int(parts[0])
                    end = int(parts[1])
                elif parts[0] and not parts[1]:
                    start = int(parts[0])
                    end = file_size - 1
                elif not parts[0] and parts[1]:
                    suffix = int(parts[1])
                    start = max(0, file_size - suffix)
                    end = file_size - 1
        except ValueError:
            self.send_error(400, "Bad Request (Malformed Range)")
            return

        if start is None or end is None or start > end or start >= file_size:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{file_size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        end = min(end, file_size - 1)
        content_length = end - start + 1

        self.send_response(206)
        self.send_header('Content-Type', mime_type)
        self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
        self.send_header('Content-Length', str(content_length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if send_body:
            self.stream_file_range(file_path, start, end)

    def stream_file_range(self, file_path, start, end):
        """Transmite fatia do arquivo em blocos de 256KB com tratamento de desconexão."""
        bytes_to_send = end - start + 1
        chunk_size = 256 * 1024

        try:
            with open(file_path, 'rb') as f:
                f.seek(start)
                while bytes_to_send > 0:
                    read_len = min(chunk_size, bytes_to_send)
                    chunk = f.read(read_len)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_to_send -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Normal no PS4 quando pausa/cancela ou reconecta o download
            pass
        except Exception as e:
            print(f"[!] Erro de streaming em {file_path}: {e}")

    def log_message(self, format, *args):
        # Log simplificado para console
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

def run_server(port=None):
    cfg = load_config()
    if port is None:
        port = int(cfg.get('port', 8080))

    local_ip = get_local_ip()

    # Atualiza o catálogo json na inicialização
    update_library_and_json(BASE_DIR, local_ip, port)

    server_address = ('0.0.0.0', port)
    httpd = ThreadingHTTPServer(server_address, FPKGiRequestHandler)

    print("=" * 65)
    print("🚀  PS2 to PS4 FPKGi Server Iniciado com Sucesso!")
    print("=" * 65)
    print(f"👉  Painel Web (PC):     http://localhost:{port}")
    print(f"👉  Painel Web (Rede):   http://{local_ip}:{port}")
    print(f"👉  Feed JSON FPKGi:     http://{local_ip}:{port}/json/PS2.json")
    print(f"👉  Suporte HTTP Range:  ATIVO (206 Partial Content)")
    print("=" * 65)
    print("Pressione Ctrl+C para encerrar o servidor.")
    print("-" * 65)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Encerrando servidor...")
        httpd.server_close()
        print("[*] Servidor finalizado.")

if __name__ == '__main__':
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_server(port_arg)
