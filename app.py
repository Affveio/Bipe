import os
import sys

# Garante saída UTF-8 no Windows prevenindo erro: 'charmap' codec can't encode characters
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import json
import datetime
import time
import re
import urllib.request
import unicodedata
import sqlite3
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
try:
    from license_client import obter_hwid, checar_status_licenca as validar_licenca, ativar_licenca_terminal as salvar_licenca
except Exception:
    from licenca import obter_hwid, validar_licenca, salvar_licenca
try:
    import pix_service
except Exception as e_pix:
    print(f"[Aviso] Falha ao importar pix_service: {e_pix}")
    pix_service = None
import atualizador
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException

app = Flask(__name__)
CORS(app)  # Permite que o frontend converse com o script local

CONFIG_MOTORISTAS = 'config_motoristas.json'
CONFIG_PLATAFORMAS = 'config_plataformas.json'
CONFIG_LOCAL_CREDENTIALS = 'credenciais_locais.json'
CONFIG_CIDADES = 'config_cidades.json'
CONFIG_HISTORICO = 'historico_bips.json'
CONFIG_CEP_CACHE = 'cep_cache.json'
EXCEL_MOTORISTAS = 'Motoristas_Cidades.xlsx'
DB_CONFIG_FILE = 'db_config.json'
DATABASE_PATH = 'triagem.db'
if os.path.exists(DB_CONFIG_FILE):
    try:
        with open(DB_CONFIG_FILE, 'r', encoding='utf-8') as f:
            db_cfg = json.load(f)
            DATABASE_PATH = db_cfg.get("database_path", "triagem.db")
            print(f"[Banco] Caminho do banco configurado: {DATABASE_PATH}")
    except Exception as e_cfg:
        print(f"[Aviso] Erro ao ler {DB_CONFIG_FILE}: {str(e_cfg)}")
else:
    try:
        with open(DB_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"database_path": "triagem.db"}, f, indent=4)
            print("[Banco] db_config.json criado com sucesso!")
    except Exception as e_cfg:
        print(f"[Aviso] Erro ao criar {DB_CONFIG_FILE}: {str(e_cfg)}")

def normalizar_texto(texto):
    if not texto:
        return ""
    try:
        nfkd = unicodedata.normalize('NFKD', str(texto))
        return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip().lower()
    except Exception:
        return str(texto).strip().lower()

def conectar_banco():
    return sqlite3.connect(DATABASE_PATH, timeout=30.0)

# Estado Global do Selenium
driver = None
aba_recebimento = None
aba_descarregamento = None
aba_atribuicao = None
aba_atribuicao_anjun = None
plataforma_ativa = None

# Estado da Atribuição Sequencial
motorista_atribuicao_ativa = None
contagem_atribuicao_ativa = 0
contagem_motoristas = {}
alertas_gerencia = []
modo_consulta = False
ultimo_motorista_bipado = None
primeiro_bip_validado = False
total_bipes_processados = 0
switches_imile_ativados = False

import threading
driver_lock = threading.Lock()

def inicializar_db():
    realizar_backup_db()
    conn = conectar_banco()
    cursor = conn.cursor()
    
    # 1. Tabela Historico
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            codigo TEXT,
            plataforma TEXT,
            cidade TEXT,
            motorista TEXT,
            status TEXT,
            recebedor TEXT,
            telefone TEXT,
            email TEXT,
            tempo_criacao TEXT,
            status_pacote TEXT,
            valor_declarado TEXT,
            negocios TEXT,
            bairro TEXT
        )
    ''')
    
    # Executa de forma segura a adição de colunas caso elas não existam
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN valor_declarado TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN negocios TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN bairro TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN status_entrega TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN motorista_entrega TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE historico ADD COLUMN tempo_atraso REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_historico_dup ON historico (codigo, status, timestamp)")
    except Exception:
        pass
    
    # 2. Tabela CEP Cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cep_cache (
            cep TEXT PRIMARY KEY,
            cidade TEXT,
            timestamp TEXT
        )
    ''')
    
    # 3. Tabela Cidades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cidades (
            cidade TEXT PRIMARY KEY
        )
    ''')
    
    # 4. Tabela Motoristas (Legada - Compatibilidade)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS motoristas (
            cidade TEXT PRIMARY KEY,
            motorista TEXT
        )
    ''')
    
    # 4b. Tabela Motoristas por Plataforma (Nova - Multiplataforma e Múltiplos Motoristas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS motoristas_plataforma (
            cidade TEXT,
            plataforma TEXT,
            motorista TEXT,
            PRIMARY KEY (cidade, plataforma, motorista)
        )
    ''')
    
    # 5. Tabela Divergências Pendentes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS divergencias_pendentes (
            codigo TEXT PRIMARY KEY,
            motorista_lote TEXT,
            motorista_esperado TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pendente'
        )
    ''')
    
    # 6. Tabela Lotes Finalizados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lotes_finalizados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motorista TEXT,
            cidades TEXT,
            quantidade INTEGER,
            plataforma TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    
    # Migração para chave primária composta (cidade, plataforma, motorista)
    try:
        cursor.execute("PRAGMA table_info(motoristas_plataforma)")
        cols_info = cursor.fetchall()
        pk_cols = [col[1] for col in cols_info if col[5] > 0]
        if 'motorista' not in pk_cols:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS motoristas_plataforma_temp (
                    cidade TEXT,
                    plataforma TEXT,
                    motorista TEXT,
                    PRIMARY KEY (cidade, plataforma, motorista)
                )
            ''')
            cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma_temp SELECT cidade, plataforma, motorista FROM motoristas_plataforma")
            cursor.execute("DROP TABLE motoristas_plataforma")
            cursor.execute("ALTER TABLE motoristas_plataforma_temp RENAME TO motoristas_plataforma")
            conn.commit()
            print("[+] Migração: Tabela motoristas_plataforma atualizada para chave primária (cidade, plataforma, motorista)!")
    except Exception as e_pk:
        print(f"[Aviso] Migração de PK motoristas_plataforma: {str(e_pk)}")

    # Migração incremental para adicionar colunas faltantes se elas não existirem
    try:
        cursor.execute("PRAGMA table_info(lotes_finalizados)")
        colunas = [col[1] for col in cursor.fetchall()]
        if 'motorista' not in colunas:
            cursor.execute("ALTER TABLE lotes_finalizados ADD COLUMN motorista TEXT")
            conn.commit()
            print("[+] Migração: Coluna 'motorista' adicionada com sucesso à tabela lotes_finalizados!")
        if 'plataforma' not in colunas:
            cursor.execute("ALTER TABLE lotes_finalizados ADD COLUMN plataforma TEXT")
            conn.commit()
            print("[+] Migração: Coluna 'plataforma' adicionada com sucesso à tabela lotes_finalizados!")
    except Exception as e_mig:
        print(f"[Aviso] Falha ao rodar migração de lotes_finalizados: {str(e_mig)}")
    
    # --- MIGRAÇÃO DE JSON LEGADO PARA SQLITE ---
    
    # 1. Migração Incremental de Cidades
    if os.path.exists(CONFIG_CIDADES):
        try:
            with open(CONFIG_CIDADES, 'r', encoding='utf-8') as f:
                cidades_legacy = json.load(f)
            for c in cidades_legacy:
                cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (c,))
            conn.commit()
        except Exception as e_cid:
            print(f"[Erro] Falha ao importar cidades legadas: {str(e_cid)}")
            
    # 2. Migração Incremental de Motoristas (e suas cidades correspondentes)
    if os.path.exists(CONFIG_MOTORISTAS):
        try:
            with open(CONFIG_MOTORISTAS, 'r', encoding='utf-8') as f:
                motoristas_legacy = json.load(f)
            
            # Detecta formatos:
            # Novo: {"anjun": [{"cidade": "...", "motorista": "..."}, ...]}
            # Intermediário: {"anjun": {"Cidade": "Mot" ou ["Mot1", "Mot2"]}}
            # Legado: {"Cidade": "Mot"}
            if isinstance(motoristas_legacy, dict):
                for k, v in motoristas_legacy.items():
                    if isinstance(v, list):
                        # Formato novo de plataformas com lista de mapeamentos
                        plat = k
                        for item in v:
                            if isinstance(item, dict):
                                cid = (item.get("cidade") or "").strip()
                                mot = (item.get("motorista") or "").strip()
                                if cid and mot:
                                    cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid,))
                                    cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista) VALUES (?, ?, ?)", (cid, plat, mot))
                    elif isinstance(v, dict):
                        # Formato intermediário com dicionário por plataforma
                        plat = k
                        for cid, mot in v.items():
                            cid_clean = str(cid).strip()
                            cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid_clean,))
                            if isinstance(mot, list):
                                for m in mot:
                                    m_str = str(m).strip()
                                    if m_str:
                                        cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista) VALUES (?, ?, ?)", (cid_clean, plat, m_str))
                            else:
                                mot_str = str(mot).strip()
                                if mot_str:
                                    cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista) VALUES (?, ?, ?)", (cid_clean, plat, mot_str))
                                    if plat == 'anjun':
                                        cursor.execute("INSERT OR IGNORE INTO motoristas (cidade, motorista) VALUES (?, ?)", (cid_clean, mot_str))
                    elif isinstance(v, str):
                        # Formato antigo plano {"Cidade": "Motorista"}
                        cid = str(k).strip()
                        mot = str(v).strip()
                        cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid,))
                        cursor.execute("INSERT OR IGNORE INTO motoristas (cidade, motorista) VALUES (?, ?)", (cid, mot))
                        cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista) VALUES (?, 'anjun', ?)", (cid, mot))
            conn.commit()
            print("[Banco de Dados] Mapeamento de motoristas importado/sincronizado com sucesso!")
        except Exception as e_mot:
            print(f"[Erro] Falha ao importar motoristas legados/novos: {str(e_mot)}")
            
        # Garante que todos os registros existentes na tabela antiga sejam copiados para a nova tabela de multi-plataformas
        try:
            cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista) SELECT cidade, 'anjun', motorista FROM motoristas")
            conn.commit()
        except Exception as e_cop:
            print(f"[Aviso] Falha ao copiar motoristas legados para a nova tabela: {str(e_cop)}")
        
    # Migrar CEP Cache
    cursor.execute("SELECT COUNT(*) FROM cep_cache")
    if cursor.fetchone()[0] == 0:
        cache_legacy = {}
        if os.path.exists(CONFIG_CEP_CACHE):
            try:
                with open(CONFIG_CEP_CACHE, 'r', encoding='utf-8') as f:
                    cache_legacy = json.load(f)
            except Exception:
                pass
        import datetime
        agora = datetime.datetime.now().isoformat()
        for cep, cid in cache_legacy.items():
            cursor.execute("INSERT OR IGNORE INTO cep_cache (cep, cidade, timestamp) VALUES (?, ?, ?)", (cep, cid, agora))
        conn.commit()
        
    # Migrar Histórico
    cursor.execute("SELECT COUNT(*) FROM historico")
    if cursor.fetchone()[0] == 0:
        historico_legacy = []
        if os.path.exists(CONFIG_HISTORICO):
            try:
                with open(CONFIG_HISTORICO, 'r', encoding='utf-8') as f:
                    historico_legacy = json.load(f)
            except Exception:
                pass
        for item in historico_legacy:
            cursor.execute('''
                INSERT INTO historico (timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get("timestamp"),
                item.get("codigo"),
                item.get("plataforma"),
                item.get("cidade"),
                item.get("motorista"),
                item.get("status"),
                item.get("recebedor", "---"),
                item.get("telefone", "---"),
                item.get("email", "---"),
                item.get("tempo_criacao", "---"),
                item.get("status_pacote", "---")
            ))
        conn.commit()
        
    conn.close()

    # 3. Sincronização Automática com Motoristas_Cidades.xlsx na inicialização
    excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_MOTORISTAS)
    if os.path.exists(excel_path):
        try:
            mtime = os.path.getmtime(excel_path)
            meta_mtime_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.excel_sync_meta')
            deve_sincronizar = True
            if os.path.exists(meta_mtime_file):
                try:
                    with open(meta_mtime_file, 'r') as f_meta:
                        if float(f_meta.read().strip()) == mtime:
                            deve_sincronizar = False
                except Exception:
                    pass
            if deve_sincronizar:
                ok, c_qtd, m_qtd, msg = sincronizar_motoristas_excel(excel_path)
                if ok:
                    with open(meta_mtime_file, 'w') as f_meta:
                        f_meta.write(str(mtime))
                    print(f"[+] Inicialização: Motoristas_Cidades.xlsx sincronizado automaticamente ({c_qtd} cidades, {m_qtd} mapeamentos)!")
        except Exception as e_boot_excel:
            print(f"[Aviso] Sincronização automática do Excel no boot: {str(e_boot_excel)}")

def sincronizar_motoristas_excel(caminho_arquivo=None):
    """
    Importa cidades e motoristas a partir de uma planilha Excel (Motoristas_Cidades.xlsx).
    Se caminho_arquivo for None, busca pelo arquivo na pasta do sistema.
    Garante sincronização total entre o Excel, o banco SQLite e os arquivos JSON de compatibilidade.
    """
    if not caminho_arquivo:
        caminho_arquivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_MOTORISTAS)
        
    if not os.path.exists(caminho_arquivo):
        return False, 0, 0, f"Planilha '{EXCEL_MOTORISTAS}' não encontrada na pasta."
        
    import openpyxl
    try:
        wb = openpyxl.load_workbook(caminho_arquivo, data_only=True)
        ws = wb.active
        
        col_cidade = -1
        col_motorista = -1
        col_plat = -1
        
        primeira_linha = [str(cell.value or '').strip().upper() for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        
        for idx, val in enumerate(primeira_linha):
            if 'CIDADE' in val:
                col_cidade = idx
            elif 'MOTORISTA' in val:
                col_motorista = idx
            elif 'PLATAFORMA' in val or 'PLAT' in val:
                col_plat = idx
                
        if col_cidade == -1 or col_motorista == -1:
            return False, 0, 0, "A planilha deve conter as colunas 'CIDADE' e 'MOTORISTA' no cabeçalho."
            
        cidades_para_inserir = set()
        mapeamentos_para_inserir = []
        
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not any(row):
                continue
            cidade = str(row[col_cidade] or '').strip() if col_cidade < len(row) and row[col_cidade] is not None else ''
            motorista = str(row[col_motorista] or '').strip() if col_motorista < len(row) and row[col_motorista] is not None else ''
            plat_raw = str(row[col_plat] or '').strip().lower() if col_plat != -1 and col_plat < len(row) and row[col_plat] is not None else 'todas'
            
            if not cidade or not motorista:
                continue
                
            cidades_para_inserir.add(cidade)
            
            if plat_raw in ['todas', 'geral', 'ambas', '', 'todos']:
                platas = ['anjun', 'imile', 'loggi']
            else:
                platas = [plat_raw]
                
            for p in platas:
                mapeamentos_para_inserir.append((cidade, p, motorista))
                
        if not cidades_para_inserir or not mapeamentos_para_inserir:
            return False, 0, 0, "A planilha está vazia ou não contém registros válidos de Cidade e Motorista."
            
        conn = conectar_banco()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM cidades")
        cursor.execute("DELETE FROM motoristas_plataforma")
        cursor.execute("DELETE FROM motoristas")
        
        for cid in sorted(cidades_para_inserir):
            cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid,))
            
        for cid, plat, mot in mapeamentos_para_inserir:
            cursor.execute("""
                INSERT OR REPLACE INTO motoristas_plataforma (cidade, plataforma, motorista)
                VALUES (?, ?, ?)
            """, (cid, plat, mot))
            if plat == 'anjun':
                cursor.execute("INSERT OR REPLACE INTO motoristas (cidade, motorista) VALUES (?, ?)", (cid, mot))
                
        conn.commit()
        conn.close()
        
        try:
            with open(CONFIG_CIDADES, 'w', encoding='utf-8') as f_c:
                json.dump(sorted(list(cidades_para_inserir)), f_c, indent=4, ensure_ascii=False)
                
            mapeamento_completo = {}
            for cid, plat, mot in mapeamentos_para_inserir:
                if plat not in mapeamento_completo:
                    mapeamento_completo[plat] = []
                mapeamento_completo[plat].append({"cidade": cid, "motorista": mot})
                
            with open(CONFIG_MOTORISTAS, 'w', encoding='utf-8') as f_m:
                json.dump(mapeamento_completo, f_m, indent=4, ensure_ascii=False)
        except Exception as e_json_sync:
            print(f"[Aviso] Falha ao atualizar JSONs no sync do Excel: {str(e_json_sync)}")
            
        print(f"[+] Sincronização Excel: {len(cidades_para_inserir)} cidades e {len(mapeamentos_para_inserir)} mapeamentos sincronizados com sucesso!")
        return True, len(cidades_para_inserir), len(mapeamentos_para_inserir), f"{len(cidades_para_inserir)} cidades e {len(mapeamentos_para_inserir)} mapeamentos sincronizados com sucesso!"
    except Exception as e:
        print(f"[Erro] Falha ao sincronizar planilha Excel: {str(e)}")
        return False, 0, 0, f"Erro ao processar planilha: {str(e)}"

def gerar_planilha_motoristas_excel(caminho_destino=None):
    """
    Gera/atualiza o arquivo Motoristas_Cidades.xlsx com os dados atuais do banco SQLite.
    """
    if not caminho_destino:
        caminho_destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_MOTORISTAS)
        
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT cidade, motorista, plataforma FROM motoristas_plataforma ORDER BY cidade ASC, plataforma ASC")
    rows = cursor.fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Motoristas e Cidades"
    
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")
    
    headers = ["CIDADE", "MOTORISTA", "PLATAFORMA"]
    ws.append(headers)
    
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    for r in rows:
        ws.append([r[0], r[1], (r[2] or "TODAS").capitalize()])
        
    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 20
    
    wb.save(caminho_destino)
    return caminho_destino


def remover_acentos(txt):
    if not txt:
        return ""
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def encontrar_cidade_mapeada(cidade_resolvida, lista_cidades):
    if not cidade_resolvida or not lista_cidades:
        return None
        
    cidade_res_clean = remover_acentos(str(cidade_resolvida).strip().lower())
    
    # Ordena as cidades cadastradas pelo comprimento do nome de forma decrescente
    # Ex: "Bom Sucesso de Itarare" vem antes de "Itarare"
    cidades_ordenadas = sorted(lista_cidades, key=lambda c: len(c), reverse=True)
    
    # 1. Tenta correspondência exata primeiro (ignorando acentos e espaços extras)
    for cidade in cidades_ordenadas:
        cidade_clean = remover_acentos(cidade.strip().lower())
        if cidade_clean == cidade_res_clean:
            return cidade
            
    # 2. Tenta correspondência com limites de palavra (word boundaries)
    # A cidade cadastrada (cidade_clean) precisa aparecer inteira como palavra no texto/endereço resolvido
    # Ex: "Itarare" nunca baterá se o endereço for apenas "Bom Sucesso de Itarare"
    for cidade in cidades_ordenadas:
        cidade_clean = remover_acentos(cidade.strip().lower())
        padrao = r'(?:\b|^)' + re.escape(cidade_clean) + r'(?:\b|$)'
        if re.search(padrao, cidade_res_clean):
            return cidade
            
    return None

# --- HELPERS PARA CONSULTA DE CEP E VIA CEP (OTIMIZADO COM CACHE LOCAL) ---
def carregar_cep_cache():
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT cep, cidade FROM cep_cache")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}

def salvar_cep_cache(cache):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        import datetime
        agora = datetime.datetime.now().isoformat()
        for cep, cidade in cache.items():
            cursor.execute("INSERT OR REPLACE INTO cep_cache (cep, cidade, timestamp) VALUES (?, ?, ?)", (cep, cidade, agora))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Erro] Falha ao salvar CEP cache no SQLite: {str(e)}")

def obter_cidade_por_cep(cep):
    cep_limpo = "".join(filter(str.isdigit, str(cep)))
    if len(cep_limpo) != 8:
        return None
        
    # 1. Tenta obter do cache local (0ms de latência!)
    cache = carregar_cep_cache()
    if cep_limpo in cache:
        print(f"[Cache] CEP {cep_limpo} resolvido instantaneamente do cache local: {cache[cep_limpo]}")
        return cache[cep_limpo]
        
    # 2. Se não está no cache, consulta APIs brasileiras de alta velocidade (CDN Cloudflare)
    cidade = None
    
    # API 1: BrasilAPI (Super rápida)
    try:
        url = f"https://brasilapi.com.br/api/cep/v1/{cep_limpo}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=1.2) as response:
            dados = json.loads(response.read().decode('utf-8'))
            if "city" in dados:
                cidade = dados["city"]
                print(f"[API] CEP {cep_limpo} resolvido pela BrasilAPI: {cidade}")
    except Exception as e:
        print(f"[Aviso] Falha na BrasilAPI para o CEP {cep_limpo}: {str(e)}")

    # API 2: AwesomeAPI (Segunda opção rápida)
    if not cidade:
        try:
            url = f"https://cep.awesomeapi.com.br/json/{cep_limpo}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=1.2) as response:
                dados = json.loads(response.read().decode('utf-8'))
                if "city" in dados:
                    cidade = dados["city"]
                    print(f"[API] CEP {cep_limpo} resolvido pela AwesomeAPI: {cidade}")
        except Exception as e:
            print(f"[Aviso] Falha na AwesomeAPI para o CEP {cep_limpo}: {str(e)}")

    # API 3: ViaCEP (Último recurso, mais lenta)
    if not cidade:
        try:
            url = f"https://viacep.com.br/ws/{cep_limpo}/json/"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=2.0) as response:
                dados = json.loads(response.read().decode('utf-8'))
                if "localidade" in dados:
                    cidade = dados["localidade"]
                    print(f"[API] CEP {cep_limpo} resolvido pelo ViaCEP: {cidade}")
        except Exception as e:
            print(f"[Erro] Falha no ViaCEP para o CEP {cep_limpo}: {str(e)}")

    # Se encontrou a cidade em qualquer uma das APIs, salva no cache local
    if cidade:
        cache[cep_limpo] = cidade
        salvar_cep_cache(cache)
        return cidade
        
    return None

def normalizar_texto(texto):
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()

def extrair_cep_da_pagina(driver):
    candidatos_xpath = [
        "//*[contains(text(), 'CEP do destinatário')]/following-sibling::*[1]",
        "//*[contains(text(), 'CEP do Destinatário')]/following-sibling::*[1]",
        "//*[contains(text(), 'CEP do destinatario')]/following-sibling::*[1]",
        "//*[contains(text(), 'CEP')]/following-sibling::*[1]",
        "//td[contains(., 'CEP')]/following-sibling::td[1]",
        "//span[contains(., 'CEP')]/following-sibling::span[1]",
        "//div[contains(., 'CEP')]/following-sibling::div[1]"
    ]
    
    for xpath in candidatos_xpath:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            cep_limpo = "".join(filter(str.isdigit, texto))
            if len(cep_limpo) == 8:
                return cep_limpo
        except Exception:
            continue
            
    # Fallback: pesquisar no texto da página inteira usando regex
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        texto_pagina = body.text
        # Encontra "CEP" seguido de espaço/quebra e 8 dígitos (ou 5+3 dígitos com traço)
        match = re.search(r"CEP[^\d]*(\d{8}|\d{5}-\d{3})", texto_pagina, re.IGNORECASE)
        if match:
            cep_limpo = "".join(filter(str.isdigit, match.group(1)))
            return cep_limpo
    except Exception as e:
        print(f"[Aviso] Falha no fallback de busca de CEP por regex: {str(e)}")
        
    return None

def obter_input_recebimento(driver, xpath_config):
    try:
        fechar_possiveis_lembretes(driver)
    except Exception:
        pass
    if xpath_config and "el-id-" not in xpath_config:
        try:
            elemento = driver.find_element(By.XPATH, xpath_config)
            if elemento.is_displayed():
                return elemento
        except Exception:
            pass
            
    candidatos = [
        "//input[contains(@placeholder, 'digitalizar') or contains(@placeholder, 'digitar')]",
        "//label[contains(., 'pacote')]/following::input[1]",
        "//input[@name='scanNumber']",
        "//*[@id='scanNumber']//input",
        "//input[contains(@placeholder, 'insira') or contains(@placeholder, 'Insira')]",
        "//input[contains(@placeholder, 'pacote') or contains(@placeholder, 'Pacote')]",
        "//input[contains(@placeholder, 'Waybill') or contains(@placeholder, 'waybill')]",
        "//input[contains(@placeholder, 'código') or contains(@placeholder, 'Código')]",
        "//input[contains(@placeholder, 'scan') or contains(@placeholder, 'Scan')]",
        "//input[@type='text']"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            if elemento.is_displayed():
                return elemento
        except Exception:
            continue
            
    # Último recurso: usa o configurado
    return driver.find_element(By.XPATH, xpath_config)

def obter_input_descarregamento(driver, xpath_config=None):
    if xpath_config:
        try:
            elemento = driver.find_element(By.XPATH, xpath_config)
            if elemento.is_displayed():
                return elemento
        except Exception:
            pass
            
    candidatos = [
        "//*[@id='scanNumber']/div/div[2]/div/div[1]/div/input",
        "//input[@name='scanNumber']",
        "//*[@id='scanNumber']//input",
        "//input[contains(@placeholder, 'insira') or contains(@placeholder, 'Insira')]",
        "//input[contains(@placeholder, 'Palete') or contains(@placeholder, 'AWB')]",
        "//input[@type='text']"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            if elemento.is_displayed():
                return elemento
        except Exception:
            continue
    return None

def fechar_modais_imile(driver):
    try:
        # Confirma ou fecha avisos de forma segura via JavaScript sem cancelar reatribuições
        driver.execute_script("""
            try {
                var dialogs = document.querySelectorAll("div[role='dialog'], .MuiDialog-root, .MuiModal-root, .el-dialog__wrapper, .el-dialog, .ImileDialog-root, .ImileModal-root, .ant-modal");
                if (!dialogs || dialogs.length === 0) return;
                for (var d = 0; d < dialogs.length; d++) {
                    var dlg = dialogs[d];
                    if (dlg && (dlg.offsetParent !== null || dlg.offsetWidth > 0 || dlg.offsetHeight > 0)) {
                        // 1. Prioridade máxima: Confirmar / Sim / OK / Entendi
                        var btnConfirm = dlg.querySelector(".ImileDialogFooter-confirm, .el-button--primary, button.MuiButton-containedPrimary, button.MuiButton-contained, button.ImileButton-containedPrimary, button.ImileButton-contained");
                        if (btnConfirm) {
                            btnConfirm.click();
                            continue;
                        }
                        var allBtns = dlg.querySelectorAll("button, [role='button']");
                        var confirmou = false;
                        for (var i = 0; i < allBtns.length; i++) {
                            var b = allBtns[i];
                            var txt = (b.innerText || b.textContent || '').toLowerCase().trim();
                            if (txt === 'confirmar' || txt === 'confirm' || txt === 'sim' || txt === 'yes' || txt === 'ok' || txt === 'entendi' || txt === 'concluir' || txt === 'enviar') {
                                b.click();
                                confirmou = true;
                                break;
                            }
                        }
                        if (confirmou) continue;

                        // 2. Se for modal apenas informativo, fecha pelo X ou Fechar
                        var btnClose = dlg.querySelector(".close, .el-dialog__headerbtn, .el-message-box__headerbtn, .ant-modal-close");
                        if (btnClose) {
                            btnClose.click();
                            continue;
                        }
                        for (var i = 0; i < allBtns.length; i++) {
                            var b = allBtns[i];
                            var txt = (b.innerText || b.textContent || '').toLowerCase().trim();
                            if (txt === 'fechar' || txt === 'close' || txt === 'cancelar' || txt === 'cancel') {
                                b.click();
                                break;
                            }
                        }
                    }
                }
            } catch(e) {}
        """)
    except Exception:
        pass

def obter_input_imile_html(driver, timeout=2.0):
    """
    Localiza com precisão e tolerância a atrasos de renderização o campo de bipe de pacote da iMile:
    - Aba 1: ArrivalScan (Entrada)
    - Aba 2: dsOffloadingScan (Descarregamento)
    - Aba 4: assignDA (Atribuição)
    Clica em 'Começar Leitura' se necessário e evita estritamente inputs do dropdown de motorista (#daCode).
    """
    if not driver:
        return None
        
    inicio_busca = time.time()
    while time.time() - inicio_busca < max(0.5, timeout):
        try:
            # 1. Se houver botão 'Começar Leitura' / 'Start Scan' fechando a tela de scan na Aba 2, clica para abrir
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll("button, .ImileButton, .MuiButton-root, [role='button'], .ant-btn");
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].innerText || btns[i].textContent || '').trim().toLowerCase();
                        if (t === 'começar leitura' || t === 'comecar leitura' || t === 'start scan' || t === 'iniciar leitura' || t === 'começar') {
                            btns[i].click();
                            break;
                        }
                    }
                """)
            except Exception:
                pass

            # 2. Busca o input diretamente no DOM via JS com seletores robustos
            el_js = driver.execute_script("""
                // 1. Procura pelo container padrão #scanNumber
                var container = document.querySelector("#scanNumber");
                if (container) {
                    var inp = container.querySelector("input:not([type='hidden']):not([disabled])");
                    if (inp && (inp.offsetParent !== null || inp.offsetWidth > 0 || inp.offsetHeight > 0)) {
                        return inp;
                    }
                }

                // 2. Procura por input com name='scanNumber' ou id='scanNumber'
                var inpName = document.querySelector("input[name='scanNumber'], input#scanNumber");
                if (inpName && (inpName.offsetParent !== null || inpName.offsetWidth > 0 || inpName.offsetHeight > 0)) {
                    return inpName;
                }

                // 3. Procura por inputs com placeholders típicos de bipe da iMile (excluindo #daCode e menus)
                var allInputs = document.querySelectorAll("input[type='text']:not([readonly]):not([disabled]), input:not([type]):not([readonly]):not([disabled])");
                for (var i = 0; i < allInputs.length; i++) {
                    var el = allInputs[i];
                    if (el.closest && (el.closest("#daCode") || el.closest(".popover") || el.closest(".popper") || el.closest(".dropdown") || el.closest(".Language") || el.closest("header"))) {
                        continue;
                    }
                    var ph = (el.getAttribute("placeholder") || "").toLowerCase();
                    var name = (el.getAttribute("name") || "").toLowerCase();
                    var id = (el.getAttribute("id") || "").toLowerCase();

                    if (name.includes("scan") || id.includes("scan") || ph.includes("insira") || ph.includes("scan") || ph.includes("waybill") || ph.includes("awb") || ph.includes("pacote") || ph.includes("código") || ph.includes("codigo") || ph.includes("digitaliz") || ph.includes("digite")) {
                        if (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0) {
                            return el;
                        }
                    }
                }

                // 4. Fallback para classes ImileInput, ant-input ou MuiInputBase fora do #daCode
                var uiInputs = document.querySelectorAll("input.ImileInput-input:not([readonly]):not([disabled]), input.ant-input:not([readonly]):not([disabled]), input.MuiInputBase-input:not([readonly]):not([disabled])");
                for (var k = 0; k < uiInputs.length; k++) {
                    var elM = uiInputs[k];
                    if (elM.closest && (elM.closest("#daCode") || elM.closest(".popover") || elM.closest(".popper") || elM.closest(".dropdown") || elM.closest(".Language") || elM.closest("header"))) {
                        continue;
                    }
                    if (elM.offsetParent !== null || elM.offsetWidth > 0 || elM.offsetHeight > 0) {
                        return elM;
                    }
                }

                return null;
            """)
            if el_js:
                return el_js
        except Exception as e_find:
            pass

        # 3. Fallbacks clássicos por XPath dentro do loop de tolerância
        candidatos = [
            "//*[@id='scanNumber']//input",
            "//*[@id='scanNumber']/div/div[2]/div/div[1]/div/input",
            "//input[@name='scanNumber']",
            "//input[contains(@placeholder, 'insira') and not(ancestor::*[@id='daCode'])]",
            "//input[contains(@placeholder, 'Insira') and not(ancestor::*[@id='daCode'])]",
            "//input[contains(@placeholder, 'Waybill') or contains(@placeholder, 'waybill')]",
            "//input[contains(@placeholder, 'pacote') or contains(@placeholder, 'Pacote')]",
            "//input[contains(@placeholder, 'scan') or contains(@placeholder, 'Scan')]",
            "//input[contains(@placeholder, 'digitalizar') or contains(@placeholder, 'digitar')]"
        ]
        for xpath in candidatos:
            try:
                elementos = driver.find_elements(By.XPATH, xpath)
                for el in elementos:
                    if el.is_displayed():
                        return el
            except Exception:
                continue

        time.sleep(0.1)

    return None

def enviar_bipe_imile_html(driver, campo, codigo_qr):
    """
    Garante que o código seja efetivamente digitado/colado e submetido com Enter
    no campo de input da iMile em qualquer uma das abas (Aba 1, Aba 2, Aba 4).
    Combina digitação nativa estilo leitor de código de barras USB com
    fallback reativo via JavaScript (Native Property Setter + KeyboardEvents de Enter).
    """
    if not driver:
        return False
    if not campo:
        campo = obter_input_imile_html(driver, timeout=1.5)
    if not campo:
        print("[Aviso] Campo de bipe iMile não encontrado para envio.")
        return False

    codigo_qr = str(codigo_qr).strip()
    if not codigo_qr:
        return False

    try:
        # 1. Garante visibilidade, foco e clique no campo
        try:
            driver.execute_script("""
                var el = arguments[0];
                if (el) {
                    try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch(e) {}
                    try { el.focus(); } catch(e) {}
                    try { el.click(); } catch(e) {}
                }
            """, campo)
        except Exception:
            pass
        time.sleep(0.05)

        # 2. Digitação nativa estilo leitor de código de barras USB (Ctrl+A, Backspace, Código + Enter)
        digitado = False
        try:
            campo.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, codigo_qr + Keys.ENTER)
            digitado = True
        except Exception as e_send_keys:
            print(f"[*] Tentando clique direto no campo antes do send_keys: {str(e_send_keys)}")
            try:
                campo.click()
                campo.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, codigo_qr + Keys.ENTER)
                digitado = True
            except Exception:
                pass

        time.sleep(0.06)

        # 3. Fallback inteligente: se o send_keys falhou ou se o valor não foi processado pela página,
        # injeta o valor usando o prototype setter nativo (compatível com React, Ant Design e Vue)
        # e dispara a sequência completa de eventos de teclado Enter
        val_atual = ""
        try:
            val_atual = campo.get_attribute("value") or ""
        except Exception:
            pass

        # Se o campo não recebeu o valor ou não limpou (no iMile bem-sucedido o input pode limpar automaticamente após processar)
        if not digitado or (val_atual != "" and val_atual != codigo_qr):
            print(f"[*] Injetando código {codigo_qr} via Native Setter + Enter Event...")
            driver.execute_script("""
                var el = arguments[0];
                var val = arguments[1];
                if (el) {
                    try { el.focus(); } catch(e) {}
                    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
                    if (nativeSetter && nativeSetter.set) {
                        nativeSetter.set.call(el, val);
                    } else {
                        el.value = val;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                    ['keydown', 'keypress', 'keyup'].forEach(function(evName) {
                        el.dispatchEvent(new KeyboardEvent(evName, {
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, charCode: 13,
                            bubbles: true, cancelable: true, composed: true
                        }));
                    });
                    if (el.form) {
                        try { el.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); } catch(e) {}
                    }
                }
            """, campo, codigo_qr)
            try:
                campo.send_keys(Keys.ENTER)
            except Exception:
                pass

        # 4. Pequeno delay de segurança para a requisição de rede/bipagem ser disparada pela página antes da troca de aba
        time.sleep(0.15)
        return True
    except Exception as e_send:
        print(f"[Erro] Falha ao enviar bipe iMile: {str(e_send)}")
        return False

def obter_input_anjun_html(driver):
    """
    Localiza instantaneamente o campo de input de bipe da Anjun (Aba 1 e Aba 3)
    diretamente no DOM via JavaScript (~1ms), sem overhead de múltiplos XPaths.
    """
    if not driver:
        return None
    try:
        el_js = driver.execute_script("""
            var inp = document.querySelector("input[placeholder*='digitalizar'], input[placeholder*='digitar']");
            if (!inp) {
                var all = document.querySelectorAll("input.el-input__inner:not([readonly])");
                for (var i = 0; i < all.length; i++) {
                    if (all[i].offsetParent !== null && all[i].offsetWidth > 0 && all[i].offsetHeight > 0) {
                        inp = all[i];
                        break;
                    }
                }
            }
            return inp;
        """)
        if el_js:
            return el_js
    except Exception:
        pass

    # Fallback via seletores Selenium se necessário
    candidatos = [
        (By.XPATH, "//input[contains(@placeholder, 'digitalizar') or contains(@placeholder, 'digitar')]"),
        (By.XPATH, "//label[contains(., 'pacote') or contains(., 'Bipar')]/following::input[1]"),
        (By.CSS_SELECTOR, "input.el-input__inner:not([readonly])"),
        (By.XPATH, "//*[@id='app']//input[@type='text']")
    ]
    for by_type, selector in candidatos:
        try:
            elementos = driver.find_elements(by_type, selector)
            for el in elementos:
                if el.is_displayed():
                    return el
        except Exception:
            continue
    return None

def enviar_bipe_anjun_html(driver, campo, codigo_qr):
    """
    Digita e envia o bipe na Anjun (Aba 1 ou Aba 3) de forma ultra-rápida,
    focando e limpando via DOM em 1ms e disparando o código com Enter.
    """
    if not campo:
        campo = obter_input_anjun_html(driver)
    if not campo:
        print("[Aviso] Campo de bipe Anjun não encontrado para envio.")
        return False

    # 1. Garante foco atômico via JS
    try:
        driver.execute_script("var el = arguments[0]; if (el) { el.focus(); }", campo)
    except Exception:
        pass

    # 2. Digita o código e aperta Enter em chamada única de teclado nativo
    digitado_com_sucesso = False
    try:
        campo.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, codigo_qr + Keys.ENTER)
        digitado_com_sucesso = True
    except Exception:
        try:
            campo.click()
            campo.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, codigo_qr + Keys.ENTER)
            digitado_com_sucesso = True
        except Exception:
            pass

    # 3. Dispara eventos sintéticos do Element UI / Vue imediatamente para garantir 0ms de processamento
    try:
        driver.execute_script("""
            var el = arguments[0];
            var codigo = arguments[1];
            if (el) {
                if (!el.value || el.value !== codigo) {
                    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    if (nativeSetter) { nativeSetter.call(el, codigo); } else { el.value = codigo; }
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            }
        """, campo, codigo_qr)
    except Exception:
        pass

    return True

def obter_input_loggi_html(driver, modo='recebimento'):
    """
    Localiza instantaneamente o campo de input de bipe/pesquisa da Loggi (Arco Loggi)
    diretamente no DOM via JavaScript (~1ms), tolerante a IDs dinâmicos (ex: _r_5_, _r_6_).
    Modos: 'recebimento' (Aba 1), 'consulta' (Aba 2), 'atribuicao' (Aba 3 - Gaveta de Grupos), 'geral'.
    """
    if not driver:
        return None
    try:
        el_js = driver.execute_script("""
            var mode = arguments[0] || 'geral';
            
            function isVisible(el) {
                return !!(el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.offsetParent !== null));
            }
            
            // 1. Gaveta de Grupos / Atribuição (Aba 3)
            if (mode === 'atribuicao' || mode === 'gaveta') {
                var drawerInputs = document.querySelectorAll(
                    ".MuiDrawer-paper input, aside input, [role='dialog'] input, div[class*='Drawer'] input, div[class*='drawer'] input"
                );
                for (var i = 0; i < drawerInputs.length; i++) {
                    if (isVisible(drawerInputs[i]) && !drawerInputs[i].disabled && !drawerInputs[i].readOnly) {
                        return drawerInputs[i];
                    }
                }
            }
            
            // 2. Campo de Pesquisa (Aba 2 - Consulta)
            if (mode === 'consulta') {
                var searchInputs = document.querySelectorAll(
                    "input[type='search'], input[placeholder*='Buscar'], input[placeholder*='buscar'], input[placeholder*='pesquisar'], input[placeholder*='Pesquisar'], input[aria-label*='search'], input[placeholder*='código'], input[placeholder*='codigo']"
                );
                for (var s = 0; s < searchInputs.length; s++) {
                    if (isVisible(searchInputs[s]) && !searchInputs[s].disabled && !searchInputs[s].readOnly) {
                        return searchInputs[s];
                    }
                }
            }
            
            // 3. Campo de Recebimento na Base (Aba 1)
            if (mode === 'recebimento') {
                var recInputs = document.querySelectorAll(
                    "input[placeholder*='Bipe para receber'], input[placeholder*='receber pacotes'], input[placeholder*='pacotes e sacas'], input[placeholder*='receber'], input[placeholder*='Receber'], input[placeholder*='pacotes'], input[placeholder*='Bipe'], input[placeholder*='bipe'], input[placeholder*='saca']"
                );
                for (var r = 0; r < recInputs.length; r++) {
                    if (isVisible(recInputs[r]) && !recInputs[r].disabled && !recInputs[r].readOnly) {
                        return recInputs[r];
                    }
                }
            }
            
            // 4. Fallback Material UI (.MuiInputBase-input)
            var muiInputs = document.querySelectorAll("input.MuiInputBase-input:not([readonly]):not([disabled]), input.MuiOutlinedInput-input:not([readonly]):not([disabled])");
            for (var m = 0; m < muiInputs.length; m++) {
                if (isVisible(muiInputs[m])) {
                    return muiInputs[m];
                }
            }
            
            // 5. Fallback Geral de qualquer input visível
            var allInputs = document.querySelectorAll("main input[type='text'], main input[type='search'], form input[type='text'], input[type='text'], input:not([type])");
            for (var a = 0; a < allInputs.length; a++) {
                var inp = allInputs[a];
                if (isVisible(inp) && !inp.disabled && !inp.readOnly && inp.type !== 'hidden' && inp.type !== 'checkbox' && inp.type !== 'radio') {
                    return inp;
                }
            }
            
            return null;
        """, modo)
        if el_js:
            return el_js
    except Exception:
        pass

    # Fallbacks via Selenium se o JS falhar
    candidatos = [
        (By.XPATH, "//input[contains(@placeholder, 'Bipe para receber') or contains(@placeholder, 'receber pacotes') or contains(@placeholder, 'pacotes e sacas')]"),
        (By.XPATH, "//input[contains(@placeholder, 'receber') or contains(@placeholder, 'Receber') or contains(@placeholder, 'Bipe') or contains(@placeholder, 'bipe')]"),
        (By.XPATH, "//input[contains(@class, 'MuiInputBase-input') or contains(@class, 'MuiOutlinedInput-input')]"),
        (By.XPATH, "//main//input[@type='text'] | //form//input[@type='text']"),
        (By.CSS_SELECTOR, "input[type='text']:not([readonly])")
    ]
    for by_type, selector in candidatos:
        try:
            elementos = driver.find_elements(by_type, selector)
            for el in elementos:
                if el.is_displayed():
                    return el
        except Exception:
            continue
    return None

def enviar_bipe_loggi_html(driver, campo, codigo_qr, modo='recebimento'):
    """
    Digita e envia o bipe na Loggi (Arco Loggi) de forma atômica e 100% compatível com a reatividade do React 18 e Material UI.
    Elimina o erro 'Preencha este campo' garantindo sincronização com o _valueTracker e simulando digitação real.
    """
    if not campo:
        campo = obter_input_loggi_html(driver, modo=modo)
    if not campo:
        print(f"[Aviso] Campo de bipe Loggi ({modo}) não encontrado para envio.")
        return False

    codigo_limpo = str(codigo_qr or '').strip()

    # 1. Injeção direta ultra-robusta com suporte a React 18 _valueTracker e eventos completos
    try:
        sucesso_js = driver.execute_script("""
            var el = arguments[0];
            var codigo = (arguments[1] || '').trim();
            if (!el) return false;

            try {
                el.scrollIntoView({ block: 'center' });
                el.focus();
                el.click();
            } catch(e) {}

            // Reseta o _valueTracker do React 18 para garantir que a mudança seja detectada
            if (el._valueTracker) {
                el._valueTracker.setValue('');
            }

            // Atribui o valor pelo protótipo nativo do HTMLInputElement
            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
            if (nativeSetter && nativeSetter.set) {
                nativeSetter.set.call(el, codigo);
            } else {
                el.value = codigo;
            }

            // Dispara evento InputEvent para o React
            try {
                var evInput = new InputEvent('input', {
                    bubbles: true,
                    cancelable: true,
                    inputType: 'insertText',
                    data: codigo
                });
                el.dispatchEvent(evInput);
            } catch(e) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
            el.dispatchEvent(new Event('change', { bubbles: true }));

            // Dispara sequência completa de eventos de teclado Enter
            var keyOpts = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, charCode: 13, bubbles: true, cancelable: true };
            el.dispatchEvent(new KeyboardEvent('keydown', keyOpts));
            el.dispatchEvent(new KeyboardEvent('keypress', keyOpts));
            el.dispatchEvent(new KeyboardEvent('keyup', keyOpts));

            // Se estiver em formulário, submete de forma segura
            if (el.form) {
                try { el.form.requestSubmit(); } catch(e) {
                    try { el.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); } catch(e2) {}
                }
            }

            return (el.value === codigo);
        """, campo, codigo_limpo)
        print(f"[*] [Loggi] Preenchimento JS no campo ({modo}): valor={codigo_limpo}, conferido={sucesso_js}")
    except Exception as e_js:
        print(f"[Aviso] Falha no preenchimento JS Loggi: {str(e_js)}")

    # 2. Confirmação nativa via Selenium sem quebrar o valor digitado
    try:
        val_atual = campo.get_attribute('value')
        if not val_atual:
            print("[*] [Loggi] Valor não retido via JS. Digitando via Selenium nativo...")
            campo.click()
            campo.send_keys(codigo_limpo)
        
        # Envia Enter nativo do Selenium
        campo.send_keys(Keys.ENTER)
    except Exception:
        try:
            webdriver.ActionChains(driver).send_keys(Keys.ENTER).perform()
        except Exception:
            pass

    return True

def fechar_possiveis_lembretes(driver):
    """
    Fecha instantaneamente popups, avisos, notificações e modais na Anjun e outras plataformas.
    Utiliza injeção direta de JavaScript de altíssima velocidade (execução em ~1ms)
    capaz de fechar popups de notificações (ex: 'Tratamento de reclamações Alertas push'),
    botões de 'X' (div.popup-header__close, span.icon-guanbi, el-dialog__close, etc.)
    e botões de confirmação/fechamento (Fecha, Fechar, Entendi, OK, etc.).
    """
    if not driver:
        return False
    try:
        fechados = driver.execute_script("""
            return (function() {
                var fechados = 0;
                function triggerClick(el) {
                    if (!el) return false;
                    try {
                        el.click();
                        var evNames = ['mousedown', 'mouseup', 'click'];
                        for (var i = 0; i < evNames.length; i++) {
                            var ev = new MouseEvent(evNames[i], {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            });
                            el.dispatchEvent(ev);
                        }
                        return true;
                    } catch (err) {
                        try { el.click(); return true; } catch (e) { return false; }
                    }
                }
                
                // 1. Busca botões de fechar (X) específicos da Anjun (.popup-header__close, .icon-guanbi) e Element UI
                var seletoresFechar = [
                    '.popup-header__close',
                    '.popup-header__close span',
                    '.popup-header .icon-guanbi',
                    '.icon-guanbi',
                    '.popup-header [class*="close"]',
                    '.el-dialog__headerbtn',
                    '.el-message-box__headerbtn',
                    '.el-dialog__close',
                    '[class*="popup-header__close"]',
                    '[class*="popup__close"]',
                    '[class*="dialog-close"]'
                ];
                try {
                    var btnsFechar = document.querySelectorAll(seletoresFechar.join(', '));
                    for (var i = 0; i < btnsFechar.length; i++) {
                        var btnX = btnsFechar[i];
                        if (btnX && (btnX.offsetWidth > 0 || btnX.offsetHeight > 0 || btnX.offsetParent !== null || window.getComputedStyle(btnX).display !== 'none')) {
                            if (triggerClick(btnX)) fechados++;
                        }
                    }
                } catch (e) {}

                // 2. Busca botões de texto (Fecha, Fechar, Entendi, OK, Confirmar, etc.)
                var alvosTexto = ['fecha', 'fechar', 'fechar aviso', 'entendi', 'ok', 'confirmar', 'conhecer', 'compreendi', 'close'];
                try {
                    var botoes = document.querySelectorAll('button, .el-button, [role="button"], span.dialog-footer button, .el-dialog__footer button, .dialog-footer button');
                    for (var j = 0; j < botoes.length; j++) {
                        var b = botoes[j];
                        if (!b) continue;
                        var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                        if (alvosTexto.indexOf(txt) !== -1) {
                            if (triggerClick(b)) fechados++;
                        }
                    }
                } catch (e) {}

                // 3. Modais/Overlays com título ou conteúdo de Notificação / Alertas push / Reclamações
                try {
                    var overlays = document.querySelectorAll('.el-overlay, [role="dialog"], .el-dialog, .popup-box');
                    for (var k = 0; k < overlays.length; k++) {
                        var dlg = overlays[k];
                        if (!dlg) continue;
                        var dlgText = (dlg.innerText || dlg.textContent || '').toLowerCase();
                        if (dlgText.indexOf('notificação') !== -1 || dlgText.indexOf('notificacao') !== -1 || dlgText.indexOf('alertas push') !== -1 || dlgText.indexOf('reclamações') !== -1 || dlgText.indexOf('reclamacoes') !== -1) {
                            var fecharInterno = dlg.querySelector('.popup-header__close, .icon-guanbi, button, .el-button');
                            if (fecharInterno) {
                                triggerClick(fecharInterno);
                                fechados++;
                            }
                            if (dlg.classList.contains('el-overlay')) {
                                setTimeout(function(el) {
                                    try {
                                        if (el && el.parentNode) el.style.display = 'none';
                                    } catch(e) {}
                                }.bind(null, dlg), 100);
                            }
                        }
                    }
                } catch (e) {}

                return fechados;
            })();
        """)
        if fechados and fechados > 0:
            print(f"[+] {fechados} popup(s)/aviso(s) da Anjun fechado(s) com sucesso via JS.")
            return True
    except Exception:
        pass
    return False

def fechar_avisos_todas_abas_anjun(driver):
    """
    Percorre todas as abas abertas da Anjun (Recebimento, Consulta, Atribuição)
    e fecha qualquer modal de notificação/aviso pendente.
    Garante que o foco retorne à aba de recebimento.
    """
    global aba_recebimento, aba_atribuicao, aba_atribuicao_anjun
    if not driver:
        return
    try:
        handles = list(driver.window_handles)
        for h in handles:
            try:
                driver.switch_to.window(h)
                fechar_possiveis_lembretes(driver)
            except Exception:
                pass
        if aba_recebimento and aba_recebimento in handles:
            try:
                driver.switch_to.window(aba_recebimento)
            except Exception:
                pass
    except Exception as e:
        print(f"[Aviso] Falha ao verificar avisos em todas as abas Anjun: {e}")

def obter_input_pesquisa(driver):
    candidatos = [
        "//textarea[contains(@placeholder, 'pesquisas') or contains(@placeholder, 'linha') or contains(@placeholder, 'avanços')]",
        "//textarea[contains(@placeholder, 'waybill') or contains(@placeholder, 'Waybill') or contains(@placeholder, 'pacote')]",
        "//textarea",
        "//input[contains(@placeholder, 'Waybill') or contains(@placeholder, 'waybill')]",
        "//input[contains(@placeholder, 'código') or contains(@placeholder, 'Código')]",
        "//input[contains(@placeholder, 'insira') or contains(@placeholder, 'Insira')]",
        "//input[contains(@placeholder, 'pacote') or contains(@placeholder, 'Pacote')]",
        "//div[contains(@class, 'el-form-item')]//input",
        "//input"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            if elemento.is_displayed():
                return elemento
        except Exception:
            continue
    raise Exception("Não foi possível encontrar o campo de busca/pesquisa de pacotes.")

def extrair_endereco_da_pagina(driver):
    candidatos_xpath = [
        "//div[contains(@class, 'descriptionItme') and contains(., 'Endereço')]/following-sibling::div[contains(@class, 'descriptionItmeValue')][1]",
        "//*[contains(text(), 'Endereço')]/../following-sibling::div[1]",
        "//*[contains(text(), 'Endereço')]/following-sibling::*[1]"
    ]
    for xpath in candidatos_xpath:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if len(texto) > 10:
                return texto
        except Exception:
            continue
            
    # Fallback: pesquisar no texto do modal completo usando regex
    try:
        # Localiza o modal/janela de detalhes
        modal = driver.find_element(By.XPATH, "//*[contains(@class, 'modal') or contains(@class, 'dialog') or contains(., 'Detalhes do destinatário')]")
        texto_modal = modal.text
        match = re.search(r"Endereço\s*[\n\r]*\s*(.+)", texto_modal, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    except Exception as e:
        print(f"[Aviso] Falha no fallback de busca de endereço por regex: {str(e)}")
        
    return None

def revelar_dados_sensiveis(driver):
    candidatos_olho = [
        # 1. O próprio span de texto (o centro dele é exatamente o meio do texto azul)
        "//span[contains(text(), 'Visualizar Informações Sensíveis')]",
        # 2. O ícone do olho em si (icon-chakanyinsi)
        "//i[contains(@class, 'icon-chakanyinsi')]",
        # 3. O span azul pai que engloba o texto e o ícone do olho
        "//span[contains(text(), 'Visualizar Informações Sensíveis')]/parent::*"
    ]
    for xpath in candidatos_olho:
        try:
            el = driver.find_element(By.XPATH, xpath)
            if el.is_displayed():
                print(f"[*] Tentando revelar dados clicando no XPath: {xpath}")
                # Tenta clique físico nativo do Selenium
                try:
                    el.click()
                except Exception:
                    # Tenta simulação física via ActionChains
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(driver)
                        actions.move_to_element(el).click().perform()
                    except Exception:
                        # Fallback: clique via JavaScript
                        driver.execute_script("arguments[0].click();", el)
                
                # Aguarda 0.3s e testa se desmascarou (verifica se o telefone não tem mais asterisco)
                time.sleep(0.3)
                tel_teste = extrair_telefone_da_pagina(driver)
                if tel_teste and "*" not in tel_teste and tel_teste != "---":
                    print(f"[+] Sucesso! Dados revelados clicando no XPath: {xpath}")
                    return
        except Exception as e_click:
            print(f"[Aviso] Falha ao tentar clicar no XPath {xpath}: {str(e_click)}")
            continue
    print("[-] Não foi possível revelar os dados sensíveis após tentar todos os XPaths.")

def extrair_recebedor_da_pagina(driver):
    candidatos = [
        "//div[contains(@class, 'descriptionItme') and (contains(., 'Recebedor') or contains(., 'Destinatário') or contains(., 'destinatário'))]/following-sibling::div[contains(@class, 'descriptionItmeValue')][1]",
        "//*[contains(text(), 'Recebedor') or contains(text(), 'Destinatário') or contains(text(), 'destinatário')]/following-sibling::*[1]",
        "//*[contains(text(), 'Nome')]/following-sibling::*[1]"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if texto:
                return texto
        except Exception:
            continue
    return "---"

def extrair_telefone_da_pagina(driver):
    candidatos = [
        "//div[contains(@class, 'descriptionItme') and (contains(., 'celular') or contains(., 'Celular') or contains(., 'Telefone'))]/following-sibling::div[contains(@class, 'descriptionItmeValue')][1]",
        "//*[contains(text(), 'celular') or contains(text(), 'Celular') or contains(text(), 'Telefone')]/following-sibling::*[1]",
        "//*[contains(text(), 'Contato')]/following-sibling::*[1]"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if texto:
                return texto
        except Exception:
            continue
    return "---"

def extrair_email_da_pagina(driver):
    candidatos = [
        "//div[contains(@class, 'descriptionItme') and (contains(., 'E-mail') or contains(., 'e-mail') or contains(., 'Email') or contains(., 'email'))]/following-sibling::div[contains(@class, 'descriptionItmeValue')][1]",
        "//*[contains(text(), 'E-mail') or contains(text(), 'Email') or contains(text(), 'email')]/following-sibling::*[1]"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if texto:
                return texto
        except Exception:
            continue
    return "---"

def extrair_tempo_criacao(driver):
    candidatos = [
        "//div[contains(@class, 'descriptionItme') and (contains(., 'Criação') or contains(., 'criação'))]/following-sibling::div[contains(@class, 'descriptionItmeValue')][1]",
        "//*[contains(text(), 'Criação') or contains(text(), 'criação')]/following-sibling::*[1]",
        "//*[contains(text(), 'Tempo')]/following-sibling::*[1]"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if texto:
                return texto
        except Exception:
            continue
    return "---"

def extrair_status_pacote(driver):
    candidatos = [
        "//div[contains(@class, 'descriptionItme') and contains(., 'Status')]/following-sibling::div[contains(@class, 'descriptionItmeValue')][1]",
        "//*[contains(text(), 'Status do Pacote') or contains(text(), 'Status do pacote')]/following-sibling::*[1]",
        "//*[contains(text(), 'Status')]/following-sibling::*[1]"
    ]
    for xpath in candidatos:
        try:
            elemento = driver.find_element(By.XPATH, xpath)
            texto = elemento.text.strip()
            if texto:
                return texto
        except Exception:
            continue
    return "---"

# --- CARREGAMENTO DE ARQUIVOS DE CONFIGURAÇÃO ---
def carregar_historico():
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, status_entrega, motorista_entrega, tempo_atraso FROM historico")
        rows = cursor.fetchall()
        conn.close()
        
        historico = []
        for r in rows:
            historico.append({
                "timestamp": r[0],
                "codigo": r[1],
                "plataforma": r[2],
                "cidade": r[3],
                "motorista": r[4],
                "status": r[5],
                "recebedor": r[6],
                "telefone": r[7],
                "email": r[8],
                "tempo_criacao": r[9],
                "status_pacote": r[10],
                "valor_declarado": r[11] if len(r) > 11 else "---",
                "negocios": r[12] if len(r) > 12 else "---",
                "bairro": r[13] if len(r) > 13 else "---",
                "status_entrega": r[14] if len(r) > 14 and r[14] is not None else "",
                "motorista_entrega": r[15] if len(r) > 15 and r[15] is not None else "",
                "tempo_atraso": r[16] if len(r) > 16 and r[16] is not None else 0.0
            })
        return historico
    except Exception:
        return []

def salvar_historico(historico):
    if len(historico) == 0:
        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM historico")
            conn.commit()
            conn.close()
        except Exception:
            pass

def realizar_backup_db():
    try:
        import os
        import shutil
        import datetime
        
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            
        # Limpa backups antigos (mantém os últimos 7)
        arquivos = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith('.db')])
        while len(arquivos) >= 7:
            try:
                os.remove(arquivos.pop(0))
            except Exception:
                pass
                
        # Cria novo backup
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f'triagem_backup_{timestamp}.db')
        if os.path.exists(DATABASE_PATH):
            shutil.copy2(DATABASE_PATH, backup_path)
            print(f"[+] Backup automático do banco de dados realizado com sucesso: {backup_path}")
    except Exception as e:
        print(f"[Aviso] Falha ao realizar backup automático do banco de dados: {str(e)}")

def otimizar_memoria():
    global driver
    try:
        import gc
        gc.collect()
        print("[+] Otimização de memória Python executada com sucesso!")
        
        if driver:
            try:
                driver.execute_script("if (window.gc) window.gc();")
            except Exception:
                pass
    except Exception as e_otim:
        print(f"[Aviso] Falha ao otimizar memória: {str(e_otim)}")

def salvar_entrada_historico(codigo, plataforma, cidade, motorista, status, recebedor="---", telefone="---", email="---", tempo_criacao="---", status_pacote="---", valor_declarado="---", negocios="---", bairro="---"):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        import datetime
        agora = datetime.datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO historico (timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (agora, codigo, plataforma, cidade, motorista if motorista else "Sem Motorista", status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Erro] Falha ao salvar entrada de histórico no SQLite: {str(e)}")

def carregar_cidades():
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT cidade FROM cidades ORDER BY cidade COLLATE NOCASE ASC")
        rows = cursor.fetchall()
        conn.close()
        cidades_unicas = []
        for r in rows:
            if r[0] and r[0].strip() and r[0].strip() not in cidades_unicas:
                cidades_unicas.append(r[0].strip())
        return cidades_unicas
    except Exception:
        return []

def carregar_motoristas(plataforma=None):
    if not plataforma:
        plataforma = plataforma_ativa if plataforma_ativa else "anjun"
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cidade, motorista 
            FROM motoristas_plataforma 
            WHERE plataforma = ? 
            ORDER BY cidade COLLATE NOCASE ASC, motorista COLLATE NOCASE ASC
        """, (plataforma,))
        rows = cursor.fetchall()
        conn.close()
        return [{"cidade": r[0].strip(), "motorista": r[1].strip()} for r in rows if r[0] and r[1]]
    except Exception:
        # Fallback para a tabela antiga de compatibilidade
        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            cursor.execute("SELECT cidade, motorista FROM motoristas ORDER BY cidade COLLATE NOCASE ASC, motorista COLLATE NOCASE ASC")
            rows = cursor.fetchall()
            conn.close()
            return [{"cidade": r[0].strip(), "motorista": r[1].strip()} for r in rows if r[0] and r[1]]
        except Exception:
            return []

def carregar_motoristas_cidade(cidade, plataforma=None):
    if not cidade:
        return []
    if not plataforma:
        plataforma = plataforma_ativa if plataforma_ativa else "anjun"
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT motorista, cidade 
            FROM motoristas_plataforma 
            WHERE plataforma = ?
            ORDER BY motorista COLLATE NOCASE ASC
        """, (plataforma,))
        rows = cursor.fetchall()
        conn.close()
        
        cidade_clean = remover_acentos(cidade.strip().lower())
        motoristas = [r[0].strip() for r in rows if r[0] and r[0].strip() and remover_acentos(r[1].strip().lower()) == cidade_clean]
        
        if not motoristas and plataforma == 'anjun':
            try:
                conn2 = conectar_banco()
                cursor2 = conn2.cursor()
                cursor2.execute("SELECT motorista, cidade FROM motoristas")
                rows2 = cursor2.fetchall()
                conn2.close()
                motoristas = [r[0].strip() for r in rows2 if r[0] and r[0].strip() and remover_acentos(r[1].strip().lower()) == cidade_clean]
            except Exception:
                pass
        return motoristas
    except Exception:
        return []

_cache_plataformas = None

def carregar_plataformas():
    global _cache_plataformas
    if _cache_plataformas:
        return _cache_plataformas
    plataformas = {}
    if not os.path.exists(CONFIG_PLATAFORMAS):
        # Cria padrão caso não exista
        padrao = {
            "imile": {
                "id": "imile",
                "nome": "iMile",
                "recebimento_url": "https://ds.imile.com/#/DSOperation/OperationManagement/ArrivalScan",
                "recebimento_input_xpath": "//*[@id=\"scanNumber\"]/div/div[2]/div/div[1]/div/input",
                "recebimento_dados_xpath": "//*[@id=\"waterMark-wrap\"]/div[2]/div/div/div/div/div/div/div[2]/div/div[1]/form/div/div/div[2]/div",
                "descarregamento_url": "https://ds.imile.com/#/DSOperation/OperationManagement/dsOffloadingScan",
                "descarregamento_input_xpath": "//*[@id=\"scanNumber\"]/div/div[2]/div/div[1]/div/input",
                "atribuicao_url": "https://ds.imile.com/#/DSOperation/DSDelivery/assignDA",
                "atribuicao_motorista_xpath": "//*[@id=\"daCode\"]/div[2]/div/div[1]/div/div",
                "atribuicao_bip_xpath": "//*[@id=\"scanNumber\"]/div/div[2]/div/div[1]/div/input"
            }
        }
        with open(CONFIG_PLATAFORMAS, 'w', encoding='utf-8') as f:
            json.dump(padrao, f, indent=4, ensure_ascii=False)
        plataformas = padrao
    else:
        with open(CONFIG_PLATAFORMAS, 'r', encoding='utf-8') as f:
            plataformas = json.load(f)
            
    # Mescla as credenciais locais caso existam
    if os.path.exists(CONFIG_LOCAL_CREDENTIALS):
        try:
            with open(CONFIG_LOCAL_CREDENTIALS, 'r', encoding='utf-8') as f:
                cred_locais = json.load(f)
                for p_id, creds in cred_locais.items():
                    if p_id in plataformas:
                        plataformas[p_id]["login_usuario"] = creds.get("login_usuario", "")
                        plataformas[p_id]["login_senha"] = creds.get("login_senha", "")
        except Exception as e_cred:
            print(f"[Aviso] Falha ao carregar credenciais locais: {str(e_cred)}")
            
    _cache_plataformas = plataformas
    return plataformas

# --- CONTROLE SELENIUM ---
def is_driver_ativo(rapido=True):
    global driver
    if not driver:
        return False
    try:
        if rapido:
            # Em modo rápido (fluxo contínuo de bipes), validação em memória instantânea (~0ms)
            return bool(getattr(driver, 'session_id', None))
        # Acesso completo para testar se a sessão ainda responde
        _ = driver.window_handles
        return True
    except Exception:
        # Limpa referências se o browser foi fechado pelo operador
        fechar_selenium()
        return False

def fechar_selenium():
    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, motorista_atribuicao_ativa, contagem_atribuicao_ativa, switches_imile_ativados
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        time.sleep(1.0)  # Aguarda liberação de locks no Windows
        try:
            import subprocess
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    driver = None
    aba_recebimento = None
    aba_descarregamento = None
    aba_atribuicao = None
    aba_atribuicao_anjun = None
    plataforma_ativa = None
    motorista_atribuicao_ativa = None
    contagem_atribuicao_ativa = 0
    switches_imile_ativados = False

def forcar_idioma_portugues_imile(driver):
    try:
        # Busca o seletor de idioma no topo (geralmente tem texto 'English' ou ícone)
        print("[*] Verificando se o idioma da aba está em Inglês...")
        trigger = None
        candidatos_trigger = [
            "//div[contains(@class, 'Language') or contains(@class, 'lang') or contains(@class, 'header')]//*[contains(text(), 'English')]",
            "//*[contains(@class, 'locale-select') or contains(@class, 'language-select')]//*[contains(text(), 'English')]",
            "//header//*[contains(text(), 'English')]",
            "//*[contains(@class, 'Language-select') or contains(@class, 'locale')]//*[contains(text(), 'English')]"
        ]
        for xpath_t in candidatos_trigger:
            try:
                el = driver.find_element(By.XPATH, xpath_t)
                if el.is_displayed():
                    trigger = el
                    break
            except Exception:
                continue
                
        if trigger:
            print("[*] Alterando idioma desta aba para Português...")
            driver.execute_script("arguments[0].click();", trigger)
            time.sleep(0.4)
            
            # Seleciona 'Portuguese' ou 'Português' na lista suspensa
            opcoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Portuguese') or contains(text(), 'português') or contains(text(), 'Português')]")
            opt_pt = None
            for opt in opcoes:
                if opt.is_displayed():
                    opt_pt = opt
                    break
            if opt_pt:
                driver.execute_script("arguments[0].click();", opt_pt)
                print("[+] Idioma desta aba alterado com sucesso!")
                time.sleep(0.5)
    except Exception as e:
        print(f"[Aviso] Falha ao forçar idioma português nesta aba: {str(e)}")

def garantir_abas_loggi(driver):
    global aba_recebimento, aba_atribuicao, aba_atribuicao_anjun
    if not driver:
        return
    try:
        handles = driver.window_handles
        # 1. Verifica se aba_atribuicao_anjun realmente tem 'grupos' na URL
        aba_grupos_ok = False
        if aba_atribuicao_anjun and aba_atribuicao_anjun in handles:
            try:
                driver.switch_to.window(aba_atribuicao_anjun)
                if "grupos" in driver.current_url.lower():
                    aba_grupos_ok = True
            except Exception:
                pass
                
        # 2. Se não estiver OK, faz o escaneamento em todas as abas para achar 'grupos'
        if not aba_grupos_ok:
            aba_atribuicao_anjun = None
            for h in handles:
                try:
                    driver.switch_to.window(h)
                    u = driver.current_url.lower()
                    if "grupos" in u:
                        aba_atribuicao_anjun = h
                        print(f"[+] Aba 3 Loggi (Grupos) identificada dinamicamente: {h}")
                        aba_grupos_ok = True
                        break
                except Exception:
                    continue
                    
        # 3. Se mesmo assim não achou a aba de grupos, abre uma nova
        if not aba_grupos_ok:
            print("[*] Aba Grupos da Loggi ausente. Abrindo nova aba de grupos...")
            driver.execute_script("window.open('https://arco.loggi.com/AV3/na-base/grupos', '_blank');")
            time.sleep(1.0)
            for h in driver.window_handles:
                try:
                    driver.switch_to.window(h)
                    if "grupos" in driver.current_url.lower():
                        aba_atribuicao_anjun = h
                        break
                except Exception:
                    continue
                    
        # 4. Garante que aba_recebimento esteja na tela de coleções/recebimento
        aba_rec_ok = False
        if aba_recebimento and aba_recebimento in handles and aba_recebimento != aba_atribuicao_anjun:
            try:
                driver.switch_to.window(aba_recebimento)
                if "colecoes" in driver.current_url.lower():
                    aba_rec_ok = True
            except Exception:
                pass
                
        if not aba_rec_ok:
            for h in handles:
                if h == aba_atribuicao_anjun:
                    continue
                try:
                    driver.switch_to.window(h)
                    if "colecoes" in driver.current_url.lower():
                        aba_recebimento = h
                        print(f"[+] Aba 1 Loggi (Recebimento) identificada dinamicamente: {h}")
                        break
                except Exception:
                    continue
                    
        # 5. Garante que aba_atribuicao seja a Aba 2 ('hoje')
        aba_hoje_ok = False
        if aba_atribuicao and aba_atribuicao in handles and aba_atribuicao not in [aba_recebimento, aba_atribuicao_anjun]:
            try:
                driver.switch_to.window(aba_atribuicao)
                if "hoje" in driver.current_url.lower():
                    aba_hoje_ok = True
            except Exception:
                pass
                
        if not aba_hoje_ok:
            for h in handles:
                if h == aba_recebimento or h == aba_atribuicao_anjun:
                    continue
                try:
                    driver.switch_to.window(h)
                    if "hoje" in driver.current_url.lower():
                        aba_atribuicao = h
                        print(f"[+] Aba 2 Loggi (Hoje) identificada dinamicamente: {h}")
                        aba_hoje_ok = True
                        break
                except Exception:
                    continue
                    
        if not aba_hoje_ok:
            for h in handles:
                if h != aba_recebimento and h != aba_atribuicao_anjun:
                    aba_atribuicao = h
                    break
    except Exception as e:
        print(f"[Aviso] Falha ao mapear abas da Loggi: {str(e)}")

def garantir_abas_imile(driver):
    """
    Garante que os handles das abas da iMile estejam mapeados e válidos.
    Se alguma aba foi recarregada ou alternada, remapeia automaticamente pelas URLs.
    """
    global aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun
    if not driver:
        return
    try:
        handles = driver.window_handles
        if not handles:
            return

        # Verifica se alguma das referências cruciais está ausente ou inválida
        precisa_mapear = False
        for h in [aba_recebimento, aba_descarregamento, aba_atribuicao_anjun]:
            if not h or h not in handles:
                precisa_mapear = True
                break

        if precisa_mapear:
            print("[*] Mapeando abas da iMile dinamicamente...")
            for h in handles:
                try:
                    driver.switch_to.window(h)
                    u = (driver.current_url or '').lower()
                    if "arrivalscan" in u or "offloadingarrival" in u:
                        aba_recebimento = h
                        print(f"[+] Aba 1 iMile (ArrivalScan) identificada: {h}")
                    elif "dsoffloadingscan" in u or "offloadingscan" in u:
                        aba_descarregamento = h
                        print(f"[+] Aba 2 iMile (dsOffloadingScan) identificada: {h}")
                    elif "dstrackquery" in u:
                        aba_atribuicao = h
                        print(f"[+] Aba 3 iMile (dsTrackQuery) identificada: {h}")
                    elif "assignda" in u:
                        aba_atribuicao_anjun = h
                        print(f"[+] Aba 4 iMile (assignDA) identificada: {h}")
                except Exception:
                    continue
    except Exception as e:
        print(f"[Aviso] Falha ao garantir abas da iMile: {str(e)}")

def inicializar_selenium(plataforma_id):
    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, motorista_atribuicao_ativa, contagem_atribuicao_ativa
    
    # Se o driver estiver ativo e já estiver na plataforma correta, não faz nada
    if is_driver_ativo() and plataforma_ativa == plataforma_id:
        return
        
    # Se estiver em outra plataforma, reinicia
    fechar_selenium()
    
    plataformas = carregar_plataformas()
    config = plataformas.get(plataforma_id)
    if not config:
        raise Exception(f"Configurações para a plataforma '{plataforma_id}' não encontradas.")
        
    print(f"[*] Iniciando Chrome para a plataforma: {config['nome']}...")
    
    from selenium.webdriver.chrome.options import Options
    chrome_options = Options()
    
    # Aponta para um diretório de perfil exclusivo do robô dentro da pasta do projeto (específico por plataforma)
    diretorio_projeto = os.path.dirname(os.path.abspath(__file__))
    caminho_perfil = os.path.join(diretorio_projeto, f"perfil_robo_{plataforma_id}")
    chrome_options.add_argument(f"--user-data-dir={caminho_perfil}")
    chrome_options.add_argument("--disable-restore-session-state")
    chrome_options.add_argument("--lang=pt-BR")
    chrome_options.add_argument("--disable-print-preview")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--js-flags=--max-old-space-size=512")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("detach", True)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_experimental_option("prefs", {
        "credentials_enable_service": True,
        "profile.password_manager_enabled": True
    })
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # Oculta o navigator.webdriver para permitir login com o Google (OAuth)
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            print("[+] navigator.webdriver ocultado com sucesso via CDP.")
        except Exception as e_cdp:
            print(f"[Aviso] Falha ao ocultar navigator.webdriver via CDP: {str(e_cdp)}")
            
        driver.maximize_window()
        
        # Garante início com apenas uma aba aberta (evita abas acumuladas de sessões anteriores)
        print("[*] Limpando abas extras residuais...")
        while len(driver.window_handles) > 1:
            try:
                driver.switch_to.window(driver.window_handles[-1])
                driver.close()
            except Exception:
                break
        try:
            driver.switch_to.window(driver.window_handles[0])
        except Exception:
            pass
    except Exception as e:
        print("\n" + "=" * 60)
        print("[ERRO CRÍTICO] NÃO FOI POSSÍVEL INICIAR O CHROME!")
        print(f"Detalhes do Erro: {str(e)}")
        print("DICA: Certifique-se de que nenhuma outra execução do robô está ativa em segundo plano.")
        print("=" * 60 + "\n")
        raise e
    
    if plataforma_id == 'loggi':
        print("[*] Iniciando fluxo de login para a Loggi...")
        driver.get(config['recebimento_url'])
        time.sleep(1.5)
        
        print("[*] Aguardando o login ser concluído no navegador para Loggi...")
        login_concluido = False
        inicio_login = time.time()
        while time.time() - inicio_login < 180.0:
            try:
                if not driver or not driver.window_handles:
                    break
                current_url = driver.current_url.lower()
                if "login" not in current_url and "arco.loggi.com" in current_url:
                    print("[+] Login detectado com sucesso!")
                    login_concluido = True
                    break
            except Exception:
                pass
            time.sleep(1.0)
            
        if not login_concluido:
            raise Exception("Tempo limite esgotado para o login na Loggi.")
            
        # Cria a segunda aba (Hoje)
        driver.execute_script("window.open('https://arco.loggi.com/AV3/hoje', '_blank');")
        time.sleep(0.5)
        
        # Cria a terceira aba (Atribuição / Grupos)
        driver.execute_script("window.open('https://arco.loggi.com/AV3/na-base/grupos', '_blank');")
        time.sleep(1.0)
        
        garantir_abas_loggi(driver)
        plataforma_ativa = plataforma_id
        
        try:
            if aba_recebimento:
                driver.switch_to.window(aba_recebimento)
        except Exception:
            pass
            
    elif plataforma_id == 'imile':
        print("[*] Iniciando fluxo de login para a iMile...")
        # Abre primeiro a página de login
        driver.get("https://ds-login.imile.com/")
        time.sleep(1.0)
        
        # Tenta mudar o idioma para Português na tela de login
        try:
            print("[*] Verificando idioma da página iMile...")
            # Procure se o seletor atual diz "English"
            candidatos_trigger = [
                "//*[@id='waterMark-wrap']/div[2]/div/div[1]/div/div/div/div",
                "//div[contains(text(), 'English') or contains(@class, 'Dropdown') and contains(., 'English')]"
            ]
            trigger_lang = None
            for xpath_t in candidatos_trigger:
                try:
                    el = driver.find_element(By.XPATH, xpath_t)
                    if el.is_displayed():
                        # Se já estiver em português, não precisa clicar
                        if "Portuguese" in el.text or "Português" in el.text:
                            print("[*] Site da iMile já carregou em Português.")
                            break
                        trigger_lang = el
                        break
                except Exception:
                    continue
                    
            if trigger_lang:
                print("[*] Mudando idioma para Português...")
                driver.execute_script("arguments[0].click();", trigger_lang)
                time.sleep(0.4)
                
                # Procura a opção "Portuguese" na lista suspensa
                opcoes_pt = driver.find_elements(By.XPATH, "//*[contains(text(), 'Portuguese') or contains(text(), 'português') or contains(text(), 'Português')]")
                opt_pt = None
                for opt in opcoes_pt:
                    if opt.is_displayed():
                        opt_pt = opt
                        break
                        
                if opt_pt:
                    driver.execute_script("arguments[0].click();", opt_pt)
                    print("[+] Idioma alterado para Português com sucesso! Aguardando aplicação do idioma...")
                    # Aguarda até que o texto da página seja atualizado para Português
                    inicio_recarga = time.time()
                    while time.time() - inicio_recarga < 3.0:
                        try:
                            corpo_texto = driver.find_element(By.TAG_NAME, "body").text
                            if "Conecte-se" in corpo_texto or "Bem-vindo" in corpo_texto or "Lembrar" in corpo_texto:
                                print("[+] Tradução para Português confirmada na tela!")
                                break
                        except Exception:
                            pass
                        time.sleep(0.1)
                    time.sleep(0.5)
        except Exception as e_lang:
            print(f"[Aviso] Não foi possível alterar o idioma para Português: {str(e_lang)}")
            
        usuario = config.get("login_usuario", "").strip()
        senha = config.get("login_senha", "").strip()
        autofill_feito = False
        
        # Loop aguardando o login ser concluído
        print("[*] Aguardando o login ser concluído no navegador...")
        login_concluido = False
        inicio_login = time.time()
        while time.time() - inicio_login < 180.0:  # Limite de 3 minutos para logar
            try:
                if not driver or not driver.window_handles:
                    break
                current_url = driver.current_url
                
                # Se a URL redirecionou para o sistema interno (ds.imile.com) e não contém mais login
                if "ds.imile.com" in current_url and "login" not in current_url:
                    print("[+] Login detectado com sucesso!")
                    login_concluido = True
                    break
                    
                # Tentativa de auto-preencher e clicar se credenciais salvas no banco existirem
                if (usuario or senha) and not autofill_feito:
                    try:
                        user_input = None
                        for xpath_user in ["//*[@id=':r3:']", "//input[@name='userCode']", "//input[contains(@placeholder, 'usuário') or contains(@placeholder, 'username') or contains(@placeholder, 'User')]"]:
                            try:
                                el = driver.find_element(By.XPATH, xpath_user)
                                if el.is_displayed():
                                    user_input = el
                                    break
                            except Exception:
                                continue
                                
                        pass_input = None
                        for xpath_pass in ["//input[@name='password']", "//input[@type='password']", "//input[contains(@placeholder, 'senha') or contains(@placeholder, 'password')]"]:
                            try:
                                el = driver.find_element(By.XPATH, xpath_pass)
                                if el.is_displayed():
                                    pass_input = el
                                    break
                            except Exception:
                                continue
                                
                        btn_login = None
                        for xpath_btn in ["//button[contains(., 'Conecte-se') or contains(., 'Login') or contains(text(), 'Login') or contains(text(), 'Conecte-se')]", "//button[contains(@class, 'ImileButton')]"]:
                            try:
                                el = driver.find_element(By.XPATH, xpath_btn)
                                if el.is_displayed():
                                    btn_login = el
                                    break
                            except Exception:
                                continue
                                
                        if user_input and pass_input:
                            # Preenche o usuário
                            if usuario:
                                user_input.click()
                                user_input.send_keys(Keys.CONTROL + "a")
                                user_input.send_keys(Keys.BACKSPACE)
                                time.sleep(0.1)
                                user_input.send_keys(usuario)
                                print("[+] Usuário preenchido via credenciais configuradas!")
                                
                            # Preenche a senha
                            if senha:
                                pass_input.click()
                                pass_input.send_keys(Keys.CONTROL + "a")
                                pass_input.send_keys(Keys.BACKSPACE)
                                time.sleep(0.1)
                                pass_input.send_keys(senha)
                                print("[+] Senha preenchida via credenciais configuradas!")
                                
                            time.sleep(0.3)
                            
                            # Clica no botão de login
                            if btn_login and not btn_login.get_attribute("disabled") and "disabled" not in btn_login.get_attribute("class"):
                                driver.execute_script("arguments[0].click();", btn_login)
                                print("[+] Clicado no botão de Login automaticamente com credenciais configuradas!")
                                
                            autofill_feito = True
                    except Exception as e_auto:
                        print(f"[Aviso] Falha na tentativa de autofill automático: {str(e_auto)}")
                        
                # Fallback: Se o próprio navegador (autofill do Chrome) preencheu e não usamos o autofill do banco
                if not autofill_feito:
                    try:
                        user_input = None
                        for xpath_user in ["//*[@id=':r3:']", "//input[@name='userCode']"]:
                            try:
                                el = driver.find_element(By.XPATH, xpath_user)
                                if el.is_displayed():
                                    user_input = el
                                    break
                            except Exception:
                                continue
                                
                        pass_input = None
                        for xpath_pass in ["//input[@name='password']", "//input[@type='password']"]:
                            try:
                                el = driver.find_element(By.XPATH, xpath_pass)
                                if el.is_displayed():
                                    pass_input = el
                                    break
                            except Exception:
                                continue
                                
                        btn_login = None
                        for xpath_btn in ["//button[contains(., 'Conecte-se') or contains(., 'Login')]", "//button[contains(@class, 'ImileButton')]"]:
                            try:
                                el = driver.find_element(By.XPATH, xpath_btn)
                                if el.is_displayed():
                                    btn_login = el
                                    break
                            except Exception:
                                continue
                                
                        if user_input and pass_input and btn_login:
                            user_val = user_input.get_attribute("value")
                            pass_val = pass_input.get_attribute("value")
                            if user_val and pass_val and not btn_login.get_attribute("disabled") and "disabled" not in btn_login.get_attribute("class"):
                                time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", btn_login)
                                print("[+] Autofill detectado. Clicado no botão de Login automaticamente!")
                                autofill_feito = True
                    except Exception:
                        pass
                        
            except Exception as e_loop:
                print(f"[Aviso] Aguardando tela de login: {str(e_loop)}")
                
            time.sleep(1.0)
            
        if not login_concluido:
            raise Exception("Tempo limite esgotado para o login na iMile.")
            
        print("[*] Redirecionando para as abas operacionais da iMile...")
        driver.get(config.get('recebimento_url', 'https://ds.imile.com/#/DSOperation/OperationManagement/ArrivalScan'))
        time.sleep(0.5)
        
        # Abre Descarregamento (Aba 2)
        descarregamento_url = config.get('descarregamento_url', 'https://ds.imile.com/#/DSOperation/OperationManagement/dsOffloadingScan')
        driver.execute_script(f"window.open('{descarregamento_url}', '_blank');")
        
        # Abre Consulta (Aba 3)
        driver.execute_script("window.open('https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery', '_blank');")
        
        # Abre Atribuição (Aba 4)
        driver.execute_script(f"window.open('{config['atribuicao_url']}', '_blank');")  # assignDA
        
        # Aguarda carregamento inicial das URLs nas novas abas
        time.sleep(1.5)
        
        # Aguarda até que as 4 abas estejam abertas no navegador
        print("[*] Aguardando 4 abas serem abertas pelo Chrome...")
        inicio_abas = time.time()
        while len(driver.window_handles) < 4 and time.time() - inicio_abas < 5.0:
            time.sleep(0.1)
            
        # Mapeia as abas dinamicamente pelas URLs para evitar erros de ordem dos handles e força idioma em cada uma
        print("[*] Mapeando abas iMile pelas URLs...")
        for handle in driver.window_handles:
            try:
                driver.switch_to.window(handle)
                url_atual = driver.current_url.lower()
                if "arrivalscan" in url_atual or "offloadingarrival" in url_atual:
                    aba_recebimento = handle
                    print(f"[+] Aba Recebimento (ArrivalScan) iMile mapeada: {handle}")
                    forcar_idioma_portugues_imile(driver)
                elif "dsoffloadingscan" in url_atual or "offloadingscan" in url_atual:
                    aba_descarregamento = handle
                    print(f"[+] Aba Descarregamento (dsOffloadingScan) iMile mapeada: {handle}")
                    forcar_idioma_portugues_imile(driver)
                elif "dstrackquery" in url_atual:
                    aba_atribuicao = handle
                    print(f"[+] Aba Consulta iMile mapeada: {handle}")
                    forcar_idioma_portugues_imile(driver)
                elif "assignda" in url_atual:
                    aba_atribuicao_anjun = handle
                    print(f"[+] Aba Atribuição iMile mapeada: {handle}")
                    forcar_idioma_portugues_imile(driver)
            except Exception as e_map:
                print(f"[Aviso] Falha ao mapear aba iMile: {str(e_map)}")
                
        try:
            handles = driver.window_handles
            if not aba_recebimento and len(handles) > 0: aba_recebimento = handles[0]
            if not aba_descarregamento and len(handles) > 1: aba_descarregamento = handles[1]
            if not aba_atribuicao and len(handles) > 2: aba_atribuicao = handles[2]
            if not aba_atribuicao_anjun and len(handles) > 3: aba_atribuicao_anjun = handles[3]
        except Exception as e_h:
            print(f"[Erro] Falha ao ler window_handles: {str(e_h)}")
            raise Exception("O Chrome foi fechado ou travou durante o mapeamento das abas. Por favor, tente novamente.")
        
        plataforma_ativa = plataforma_id
        
        def inicializar_aba_atribuicao_imile_boot():
            inicio = time.time()
            lang_ok = False
            sw_ok = False
            
            while time.time() - inicio < 25.0:
                try:
                    if not driver:
                        break
                    if len(driver.window_handles) < 4:
                        time.sleep(0.5)
                        continue
                        
                    driver_lock.acquire()
                    try:
                        # 1. Primeiro tenta garantir o idioma em Português na Aba 3
                        if not lang_ok:
                            driver.switch_to.window(aba_atribuicao_anjun)
                            trigger = None
                            candidatos_trigger = [
                                "//div[contains(@class, 'Language') or contains(@class, 'lang') or contains(@class, 'header')]//*[contains(text(), 'English')]",
                                "//*[contains(@class, 'locale-select') or contains(@class, 'language-select')]//*[contains(text(), 'English')]",
                                "//header//*[contains(text(), 'English')]",
                                "//*[contains(@class, 'Language-select') or contains(@class, 'locale')]//*[contains(text(), 'English')]"
                            ]
                            for xpath_t in candidatos_trigger:
                                try:
                                    el = driver.find_element(By.XPATH, xpath_t)
                                    if el.is_displayed():
                                        trigger = el
                                        break
                                except Exception:
                                    continue
                                    
                            if trigger:
                                print("[*] Boot iMile: Alterando idioma para Português...")
                                driver.execute_script("arguments[0].click();", trigger)
                                time.sleep(0.5)
                                
                                opcoes = driver.find_elements(By.XPATH, "//*[contains(text(), 'Portuguese') or contains(text(), 'português') or contains(text(), 'Português')]")
                                opt_pt = None
                                for opt in opcoes:
                                    if opt.is_displayed():
                                        opt_pt = opt
                                        break
                                if opt_pt:
                                    driver.execute_script("arguments[0].click();", opt_pt)
                                    print("[+] Boot iMile: Idioma alterado para PT-BR!")
                                    lang_ok = True
                                    time.sleep(1.0) # Espera a página recarregar com o novo idioma
                            else:
                                # Se não achar o botão 'English', pode ser que já esteja em Português!
                                try:
                                    if driver.find_elements(By.XPATH, "//header//*[contains(text(), 'Português') or contains(text(), 'Portuguese') or contains(text(), 'PT')]"):
                                        lang_ok = True
                                except Exception:
                                    pass
                                    
                        # 2. Agora tenta ligar as chaves (suporta rótulos em PT e EN)
                        if not sw_ok:
                            driver.switch_to.window(aba_atribuicao_anjun)
                            sw_ativados = 0
                            
                            # Aguarda renderização de pelo menos 2 switches
                            try:
                                WebDriverWait(driver, 4).until(
                                    lambda d: len(d.find_elements(By.XPATH, "//input[@type='checkbox' and (contains(@class, 'MuiSwitch-input') or contains(@class, 'Switch-input'))]")) >= 2
                                )
                            except Exception:
                                pass
                                
                            checkboxes = driver.find_elements(By.XPATH, "//input[@type='checkbox' and (contains(@class, 'MuiSwitch-input') or contains(@class, 'Switch-input'))]")
                            
                            if len(checkboxes) >= 2:
                                for i, chk in enumerate(checkboxes[:2]):
                                    try:
                                        parent_span = chk.find_element(By.XPATH, "./parent::span")
                                        is_checked = "Mui-checked" in parent_span.get_attribute("class")
                                        
                                        label_nome = "Forçar" if i == 0 else "OFD"
                                        if not is_checked:
                                            try:
                                                parent_span.click()
                                                print(f"[+] Boot: Switch '{label_nome}' ativado com clique físico!")
                                            except Exception:
                                                driver.execute_script("arguments[0].click();", parent_span)
                                                print(f"[+] Boot: Switch '{label_nome}' ativado via JS!")
                                            time.sleep(0.25)
                                            sw_ativados += 1
                                        else:
                                            print(f"[*] Boot: Switch '{label_nome}' já está ativo.")
                                            sw_ativados += 1
                                    except Exception as e_chk_boot:
                                        print(f"[Aviso] Falha ao tentar ativar switch por índice no boot: {str(e_chk_boot)}")
                            
                            if sw_ativados >= 2:
                                print("[+] Boot: Ambos os switches iMile foram verificados/ativados com sucesso!")
                                sw_ok = True
                                
                        if lang_ok and sw_ok:
                            break
                    finally:
                        driver_lock.release()
                except Exception as e_sw_loop:
                    print(f"[Aviso] Tentando inicializar Aba 3 iMile no boot: {str(e_sw_loop)}")
                time.sleep(1.0)
                
            try:
                driver.switch_to.window(aba_recebimento)
            except Exception:
                pass
                
        import threading
        threading.Thread(target=inicializar_aba_atribuicao_imile_boot, daemon=True).start()

    else:
        # Configura aba de Recebimento
        driver.get(config['recebimento_url'])
        time.sleep(1.5)
        
        # Se for Anjun Express e cair na tela de login
        current_url = driver.current_url
        if plataforma_id == 'anjun' and ("login" in current_url.lower() or "newsupplier.anjunexpress.com/#/login" in current_url):
            print("[*] Tela de login da Anjun detectada. Aguardando login...")
            usuario = config.get("login_usuario", "").strip()
            senha = config.get("login_senha", "").strip()
            autofill_feito = False
            
            login_concluido = False
            inicio_login = time.time()
            while time.time() - inicio_login < 180.0:  # Limite de 3 minutos
                try:
                    if not driver or not driver.window_handles:
                        break
                    current_url = driver.current_url
                    if "login" not in current_url.lower() and "newsupplier" in current_url:
                        print("[+] Login detectado com sucesso na Anjun!")
                        login_concluido = True
                        break
                        
                    # Preenche os campos se tiver credenciais configuradas
                    if (usuario or senha) and not autofill_feito:
                        try:
                            user_input = None
                            for xpath in ["//input[@placeholder='Digite nome de usuário']", "//input[contains(@placeholder, 'usuário')]", "//input[@type='text']"]:
                                try:
                                    el = driver.find_element(By.XPATH, xpath)
                                    if el.is_displayed():
                                        user_input = el
                                        break
                                except Exception:
                                    continue
                                    
                            pass_input = None
                            for xpath in ["//input[@placeholder='Por favor digite a senha']", "//input[@type='password']"]:
                                try:
                                    el = driver.find_element(By.XPATH, xpath)
                                    if el.is_displayed():
                                        pass_input = el
                                        break
                                except Exception:
                                    continue
                                    
                            if user_input and pass_input:
                                if usuario:
                                    user_input.click()
                                    user_input.send_keys(Keys.CONTROL + "a")
                                    user_input.send_keys(Keys.BACKSPACE)
                                    time.sleep(0.1)
                                    user_input.send_keys(usuario)
                                if senha:
                                    pass_input.click()
                                    pass_input.send_keys(Keys.CONTROL + "a")
                                    pass_input.send_keys(Keys.BACKSPACE)
                                    time.sleep(0.1)
                                    pass_input.send_keys(senha)
                                print("[+] Credenciais da Anjun preenchidas no formulário!")
                                autofill_feito = True
                        except Exception as e_auto:
                            print(f"[Aviso] Falha no autofill Anjun: {str(e_auto)}")
                except Exception:
                    pass
                time.sleep(1.0)
                
            if not login_concluido:
                raise Exception("Tempo limite esgotado para o login na Anjun.")
                
            # Após o login, garante que está na URL de recebimento
            driver.get(config['recebimento_url'])
            time.sleep(1.0)
            
        # Cria e configura aba de Atribuição (Consulta de Pacotes)
        driver.execute_script(f"window.open('{config['atribuicao_url']}', '_blank');")
        
        # Se for Anjun Express, abre a terceira aba específica para Atribuição de Motoristas (TaskAssignment)
        if plataforma_id == 'anjun':
            print("[*] Abrindo aba 3 para Atribuição de Motoristas (TaskAssignment)...")
            driver.execute_script("window.open('https://newsupplier.anjunexpress.com/#/views/operatingCenter/TaskAssignment', '_blank');")
            
        # Aguarda as abas carregarem as URLs
        time.sleep(1.5)
        
        # Mapeia as abas dinamicamente pelas URLs para evitar erros de ordem dos handles
        print("[*] Mapeando abas Anjun pelas URLs...")
        for handle in driver.window_handles:
            try:
                driver.switch_to.window(handle)
                url_atual = driver.current_url.lower()
                if "netentryscanning" in url_atual or "recebimento" in url_atual:
                    aba_recebimento = handle
                    print(f"[+] Aba Recebimento Anjun mapeada: {handle}")
                elif "packagequery" in url_atual or "atribuicao" in url_atual:
                    aba_atribuicao = handle
                    print(f"[+] Aba Consulta Anjun mapeada: {handle}")
                elif "taskassignment" in url_atual or "atribuicao_motoristas" in url_atual:
                    aba_atribuicao_anjun = handle
                    print(f"[+] Aba Atribuição Anjun mapeada: {handle}")
            except Exception as e_map:
                print(f"[Aviso] Falha ao mapear aba Anjun: {str(e_map)}")
                
        # Fallbacks
        if not aba_recebimento: aba_recebimento = driver.window_handles[0]
        if not aba_atribuicao: aba_atribuicao = driver.window_handles[1]
        if plataforma_id == 'anjun' and not aba_atribuicao_anjun:
            aba_atribuicao_anjun = driver.window_handles[2]
            
        plataforma_ativa = plataforma_id
        
        if plataforma_id == 'anjun':
            fechar_avisos_todas_abas_anjun(driver)
        
        def monitorar_carregamento_anjun():
            inicio = time.time()
            aba1_pronta = False
            aba2_pronta = False
            aba3_pronta = False
            data_limpa = False
            
            print("[*] Aguardando elementos da Anjun carregarem nas abas (verificação dinâmica de HTML)...")
            
            # Limite máximo de segurança caso o operador ainda precise fazer login
            while time.time() - inicio < 25.0:
                try:
                    if not driver:
                        break
                    if len(driver.window_handles) < 2:
                        time.sleep(0.3)
                        continue
                        
                    driver_lock.acquire()
                    try:
                        # 1. Verifica Aba 1: Input de Entrada/Digitalizar (Imagem 1: 'Favor digitalizar ou digitar')
                        if not aba1_pronta and aba_recebimento and aba_recebimento in driver.window_handles:
                            driver.switch_to.window(aba_recebimento)
                            fechar_possiveis_lembretes(driver)
                            tem_input_rec = driver.execute_script("""
                                var inp = document.querySelector("input[placeholder*='digitalizar'], input[placeholder*='digitar']");
                                if (!inp) inp = document.querySelector("input.el-input__inner");
                                return !!(inp && (inp.offsetWidth > 0 || inp.offsetHeight > 0 || inp.offsetParent !== null));
                            """)
                            if tem_input_rec:
                                aba1_pronta = True
                                print("[+] Aba 1 da Anjun 100% pronta (campo 'Favor digitalizar ou digitar' detectado)!")

                        # 2. Verifica Aba 2: Textarea de Consulta (Imagem 2: 'Suporta pesquisas de vários avanços de linha')
                        if not aba2_pronta and aba_atribuicao and aba_atribuicao in driver.window_handles:
                            driver.switch_to.window(aba_atribuicao)
                            fechar_possiveis_lembretes(driver)
                            tem_txt_cons = driver.execute_script("""
                                var txt = document.querySelector("textarea[placeholder*='pesquisas'], textarea[placeholder*='linha'], textarea.el-textarea__inner");
                                return !!(txt && (txt.offsetWidth > 0 || txt.offsetHeight > 0 || txt.offsetParent !== null));
                            """)
                            if tem_txt_cons:
                                aba2_pronta = True
                                print("[+] Aba 2 da Anjun 100% pronta (campo de consulta detectado)!")
                                
                                # Limpa o filtro de data ativo se houver
                                if not data_limpa:
                                    try:
                                        date_editor = driver.find_element(By.XPATH, "//div[contains(@class, 'el-date-editor') or contains(@class, 'el-range-editor')]")
                                        if date_editor.is_displayed():
                                            texto_data = date_editor.text or ""
                                            inputs_data = date_editor.find_elements(By.TAG_NAME, "input")
                                            for inp in inputs_data:
                                                val = driver.execute_script("return arguments[0].value;", inp)
                                                if val:
                                                    texto_data += " " + str(val)
                                            
                                            import re
                                            if bool(re.search(r'\d', texto_data)):
                                                print("[Boot] Filtro de data ativo detectado no carregamento. Limpando...")
                                                date_editor.click()
                                                time.sleep(0.2)
                                                try:
                                                    btn_limpar = driver.find_element(By.XPATH, "//button[contains(., 'Limpar') or contains(text(), 'Limpar')]")
                                                    driver.execute_script("arguments[0].click();", btn_limpar)
                                                except Exception:
                                                    btn_limpar = driver.find_element(By.XPATH, "//*[contains(@class, 'el-picker-panel')]//button[contains(., 'Limpar') or contains(text(), 'Limpar')]")
                                                    driver.execute_script("arguments[0].click();", btn_limpar)
                                                print("[Boot] Filtro de data limpo com sucesso!")
                                                time.sleep(0.2)
                                                data_limpa = True
                                            else:
                                                data_limpa = True
                                    except Exception:
                                        pass

                        # 3. Verifica Aba 3: Input do Entregador (Imagem 3: 'el-select__input')
                        if not aba3_pronta and aba_atribuicao_anjun and aba_atribuicao_anjun in driver.window_handles:
                            driver.switch_to.window(aba_atribuicao_anjun)
                            fechar_possiveis_lembretes(driver)
                            tem_ent_aba3 = driver.execute_script("""
                                var ent = document.querySelector("input.el-select__input, input[role='combobox']");
                                return !!(ent && (ent.offsetWidth > 0 || ent.offsetHeight > 0 || ent.offsetParent !== null));
                            """)
                            if tem_ent_aba3:
                                aba3_pronta = True
                                print("[+] Aba 3 da Anjun 100% pronta (campo 'Entregador' detectado)!")

                        # Mantém sempre a Aba 1 focada
                        if aba_recebimento and aba_recebimento in driver.window_handles:
                            driver.switch_to.window(aba_recebimento)

                        # Se for Anjun e as 3 abas já carregaram seus elementos: ENCERRA IMEDIATAMENTE!
                        if plataforma_id == 'anjun' and aba1_pronta and aba2_pronta and aba3_pronta:
                            tempo_total_boot = time.time() - inicio
                            print(f"[+] Todas as 3 abas da Anjun confirmadas e 100% prontas em apenas {tempo_total_boot:.2f}s! Liberando sistema.")
                            break
                        elif plataforma_id != 'anjun' and aba1_pronta and aba2_pronta:
                            tempo_total_boot = time.time() - inicio
                            print(f"[+] Abas da plataforma confirmadas e prontas em {tempo_total_boot:.2f}s! Liberando sistema.")
                            break
                    finally:
                        driver_lock.release()
                except Exception:
                    try:
                        if aba_recebimento and aba_recebimento in driver.window_handles:
                            driver.switch_to.window(aba_recebimento)
                    except Exception:
                        pass
                time.sleep(0.3)
                
        import threading
        threading.Thread(target=monitorar_carregamento_anjun, daemon=True).start()
        
    print(f"\n⚠️ FAÇA LOGIN NO SITE DA {config['nome'].upper()} EM AMBAS AS ABAS E DEIXE PRONTO.")

# --- ENDPOINTS REST & LICENCIAMENTO ---

def requer_licenca_ativa(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        lic = validar_licenca()
        if not lic.get("valido", False):
            return jsonify({
                "status": "bloqueado_licenca",
                "mensagem": lic.get("motivo", "Licença do sistema inativa ou expirada. Realize a ativação para continuar."),
                "licenca": lic
            }), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/status-licenca', methods=['GET'])
def rota_status_licenca():
    return jsonify(validar_licenca())

@app.route('/ativar-licenca', methods=['POST'])
def rota_ativar_licenca():
    dados = request.json or {}
    chave = dados.get('chave', '').strip()
    if not chave:
        return jsonify({"sucesso": False, "mensagem": "A chave de ativação não pode ficar vazia!"}), 400
    ok, msg = salvar_licenca(chave)
    status_atual = validar_licenca()
    return jsonify({
        "sucesso": ok,
        "mensagem": msg,
        "status": status_atual
    }), (200 if ok else 400)

# --- ROTAS DE COBRANÇA E RENOVAÇÃO AUTOMÁTICA VIA PIX ---

@app.route('/api/pix/dados-cobranca', methods=['GET'])
def rota_pix_dados_cobranca():
    if not pix_service:
        return jsonify({"sucesso": False, "mensagem": "Módulo PIX não carregado."}), 500
    chave_param = request.args.get('chave')
    hwid_param = request.args.get('hwid')
    dados = pix_service.obter_cobranca_renovacao_atual(chave_licenca=chave_param, hwid=hwid_param)
    return jsonify(dados)

@app.route('/api/pix/checar-status', methods=['GET'])
def rota_pix_checar_status():
    if not pix_service:
        return jsonify({"pago": False, "mensagem": "Módulo PIX não carregado."}), 500
    fatura_id = request.args.get('fatura_id')
    resultado = pix_service.checar_status_pagamento_fatura(fatura_id)
    return jsonify(resultado)

@app.route('/api/pix/simular-pagamento', methods=['POST'])
def rota_pix_simular_pagamento():
    if not pix_service:
        return jsonify({"sucesso": False, "mensagem": "Módulo PIX não carregado."}), 500
    dados = request.json or {}
    fatura_id = dados.get('fatura_id')
    resultado = pix_service.confirmar_pagamento_e_renovar(fatura_id, codigo_transacao="PIX-SIMULADO-TESTE")
    return jsonify(resultado)

@app.route('/api/pix/config', methods=['GET', 'POST'])
def rota_pix_config():
    if not pix_service:
        return jsonify({"sucesso": False, "mensagem": "Módulo PIX não carregado."}), 500
    if request.method == 'POST':
        novos_dados = request.json or {}
        ok = pix_service.salvar_pix_config(novos_dados)
        return jsonify({"sucesso": ok, "config": pix_service.carregar_pix_config()})
    return jsonify(pix_service.carregar_pix_config())

@app.route('/checar-atualizacao', methods=['GET'])
def rota_checar_atualizacao():
    resultado = atualizador.verificar_atualizacao()
    return jsonify(resultado)

@app.route('/aplicar-atualizacao', methods=['POST'])
def rota_aplicar_atualizacao():
    ok, msg = atualizador.aplicar_atualizacao()
    if ok:
        # Agenda reinício do servidor após a resposta ser enviada ao navegador
        def reiniciar_depois():
            time.sleep(1.5)
            os._exit(42)
        import threading
        threading.Thread(target=reiniciar_depois, daemon=True).start()

    return jsonify({
        "sucesso": ok,
        "mensagem": msg
    }), (200 if ok else 400)

@app.route('/')
def rota_index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/dashboard')
def rota_dashboard():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')

@app.route('/ping', methods=['GET'])
def rota_ping():
    return jsonify({"status": "ok", "app": "galpao-monitored"})

@app.route('/configuracoes', methods=['GET'])
def obter_configuracoes():
    plat_id = request.args.get("plataforma")
    return jsonify({
        "plataformas": carregar_plataformas(),
        "motoristas": carregar_motoristas(plat_id),
        "cidades": carregar_cidades(),
        "plataforma_ativa": plataforma_ativa,
        "modo_consulta": modo_consulta,
        "licenca": validar_licenca()
    })

@app.route('/<path:filename>')
def rota_arquivos_estaticos(filename):
    diretorio = os.path.dirname(os.path.abspath(__file__))
    caminho = os.path.join(diretorio, filename)
    if os.path.isfile(caminho):
        return send_from_directory(diretorio, filename)
    return jsonify({"erro": "Arquivo nao encontrado"}), 404

@app.route('/configuracoes/modo-consulta', methods=['POST'])
def salvar_modo_consulta():
    global modo_consulta
    dados = request.json
    modo_consulta = dados.get("modo_consulta", False)
    print(f"[*] Modo de Consulta alterado pelo painel para: {modo_consulta}")
    return jsonify({"status": "sucesso", "modo_consulta": modo_consulta})

@app.route('/historico', methods=['GET'])
def obter_historico():
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")
    data_filtro = request.args.get("data")
    
    # Carrega o mapeamento de motoristas para traduzir na resposta do dashboard
    imile_map, anjun_map = carregar_mapeamento_motoristas()
    
    def traduzir_motorista(mot_name, plat):
        if not mot_name:
            return "Sem Motorista"
        mot_clean = mot_name.strip().lower()
        if plat == 'imile' and mot_clean in imile_map:
            return imile_map[mot_clean]
        elif plat == 'anjun' and mot_clean in anjun_map:
            return anjun_map[mot_clean]
        return mot_name
    
    if not data_inicio and not data_fim and data_filtro:
        data_inicio = data_filtro
        data_fim = data_filtro
        
    if data_inicio and data_fim:
        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            start = data_inicio + "T00:00:00"
            end = data_fim + "T23:59:59"
            cursor.execute("""
                SELECT timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, status_entrega, motorista_entrega, tempo_atraso 
                FROM historico
                WHERE timestamp >= ? AND timestamp <= ?
            """, (start, end))
            rows = cursor.fetchall()
            conn.close()
            
            historico = []
            for r in rows:
                plat = r[2]
                mot_original = r[4]
                mot_ent_original = r[15]
                
                historico.append({
                    "timestamp": r[0],
                    "codigo": r[1],
                    "plataforma": r[2],
                    "cidade": r[3],
                    "motorista": traduzir_motorista(mot_original, plat),
                    "status": r[5],
                    "recebedor": r[6],
                    "telefone": r[7],
                    "email": r[8],
                    "tempo_criacao": r[9],
                    "status_pacote": r[10],
                    "valor_declarado": r[11] if len(r) > 11 else "---",
                    "negocios": r[12] if len(r) > 12 else "---",
                    "bairro": r[13] if len(r) > 13 else "---",
                    "status_entrega": r[14] if len(r) > 14 and r[14] is not None else "",
                    "motorista_entrega": traduzir_motorista(mot_ent_original, plat) if (len(r) > 15 and r[15] is not None) else "",
                    "tempo_atraso": r[16] if len(r) > 16 and r[16] is not None else 0.0
                })
            return jsonify(historico)
        except Exception as e:
            return jsonify({"status": "erro", "mensagem": str(e)}), 500
    else:
        try:
            conn = conectar_banco()
            cursor = conn.cursor()
            import datetime
            cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S')
            cursor.execute("""
                SELECT timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, status_entrega, motorista_entrega, tempo_atraso 
                FROM historico
                WHERE timestamp >= ?
            """, (cutoff,))
            rows = cursor.fetchall()
            conn.close()
            
            historico = []
            for r in rows:
                plat = r[2]
                mot_original = r[4]
                mot_ent_original = r[15]
                
                historico.append({
                    "timestamp": r[0],
                    "codigo": r[1],
                    "plataforma": r[2],
                    "cidade": r[3],
                    "motorista": traduzir_motorista(mot_original, plat),
                    "status": r[5],
                    "recebedor": r[6],
                    "telefone": r[7],
                    "email": r[8],
                    "tempo_criacao": r[9],
                    "status_pacote": r[10],
                    "valor_declarado": r[11] if len(r) > 11 else "---",
                    "negocios": r[12] if len(r) > 12 else "---",
                    "bairro": r[13] if len(r) > 13 else "---",
                    "status_entrega": r[14] if len(r) > 14 and r[14] is not None else "",
                    "motorista_entrega": traduzir_motorista(mot_ent_original, plat) if (len(r) > 15 and r[15] is not None) else "",
                    "tempo_atraso": r[16] if len(r) > 16 and r[16] is not None else 0.0
                })
            return jsonify(historico)
        except Exception:
            return jsonify(carregar_historico())

def carregar_mapeamento_motoristas():
    imile_map = {}
    anjun_map = {}
    path = os.path.join(os.getcwd(), "Motoristas.xlsx")
    if os.path.exists(path):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            sheet = wb.active
            for r_idx, row in enumerate(sheet.iter_rows(values_only=True)):
                if r_idx == 0: # Cabeçalho
                    continue
                if not row:
                    continue
                # Mapeamento Imile: Usuario Imile -> Motorista Imile
                if len(row) > 1 and row[0] is not None and row[1] is not None:
                    user_imile = str(row[0]).strip().lower()
                    mot_imile = str(row[1]).strip()
                    imile_map[user_imile] = mot_imile
                # Mapeamento Anjun: Usuario Anjun -> Motorista Anjun
                if len(row) > 3 and row[2] is not None and row[3] is not None:
                    user_anjun = str(row[2]).strip().lower()
                    mot_anjun = str(row[3]).strip()
                    anjun_map[user_anjun] = mot_anjun
            wb.close()
        except Exception as e:
            print(f"[Map Motoristas] Erro ao carregar Motoristas.xlsx: {e}")
    return imile_map, anjun_map

@app.route('/atribuicao/atualizar-status-entrega', methods=['POST'])
def atualizar_status_entrega():
    dados = request.json
    if not dados or not isinstance(dados, list):
        return jsonify({"status": "erro", "mensagem": "Os dados fornecidos devem ser uma lista."}), 400
        
    try:
        imile_map, anjun_map = carregar_mapeamento_motoristas()
        conn = conectar_banco()
        cursor = conn.cursor()
        
        registros_atualizados = 0
        for item in dados:
            codigo = item.get("codigo", "").strip()
            status_ent = item.get("status_entrega", "").strip()
            motorista_ent = item.get("motorista_entrega", "").strip()
            
            # Padroniza o nome do motorista do site usando o mapeamento do Motoristas.xlsx
            if motorista_ent:
                mot_clean = motorista_ent.strip().lower()
                if mot_clean in imile_map:
                    motorista_ent = imile_map[mot_clean]
                elif mot_clean in anjun_map:
                    motorista_ent = anjun_map[mot_clean]
            
            if codigo:
                cursor.execute("""
                    UPDATE historico 
                    SET status_entrega = ?, motorista_entrega = ? 
                    WHERE codigo = ?
                """, (status_ent, motorista_ent, codigo))
                if cursor.rowcount > 0:
                    registros_atualizados += 1
                    
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": f"Status de {registros_atualizados} pacotes atualizados com sucesso!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/atribuicao/importar-local', methods=['POST'])
def importar_local():
    import datetime
    dados_requisicao = request.json or {}
    nome_arquivo = dados_requisicao.get("arquivo")
    if not nome_arquivo:
        return jsonify({"status": "erro", "mensagem": "Nome do arquivo nao especificado."}), 400
        
    path = os.path.join(os.getcwd(), nome_arquivo)
    if not os.path.exists(path):
        return jsonify({"status": "erro", "mensagem": f"O arquivo {nome_arquivo} nao foi encontrado na pasta do projeto."}), 404
        
    try:
        import openpyxl
        delivered_codes = set()
        imile_map, anjun_map = carregar_mapeamento_motoristas()
        
        # 1. Tenta carregar o Delivered.xlsx se existir para cruzar dados de entregas concluídas (seja importando Imile ou o próprio Delivered)
        delivered_path = os.path.join(os.getcwd(), "Delivered.xlsx")
        if os.path.exists(delivered_path) and nome_arquivo == "Imile.xlsx":
            try:
                wb_del = openpyxl.load_workbook(delivered_path, data_only=True)
                sheet_del = wb_del.active
                for r_idx, row in enumerate(sheet_del.iter_rows(values_only=True)):
                    if r_idx == 0:
                        continue
                    # Coluna B (index 1) é Waybill No.
                    if row and len(row) > 1 and row[1]:
                        delivered_codes.add(str(row[1]).strip())
                wb_del.close()
                print(f"[Import Local] Carregados {len(delivered_codes)} codigos entregues do Delivered.xlsx")
            except Exception as e_del:
                print(f"[Import Local] Erro ao ler Delivered.xlsx: {e_del}")

        pacotes = []
        registros_atualizados = 0
        
        # CASO A: Importando especificamente o Delivered.xlsx
        if nome_arquivo == "Delivered.xlsx":
            if not delivered_codes:
                return jsonify({"status": "erro", "mensagem": "Nenhum codigo de entrega valido foi encontrado no Delivered.xlsx."}), 400
                
            conn = conectar_banco()
            cursor = conn.cursor()
            
            # Busca todos os bips existentes no banco
            cursor.execute("SELECT codigo FROM historico WHERE status = 'OK'")
            bips_banco = [r[0] for r in cursor.fetchall()]
            
            for cod_banco in bips_banco:
                if cod_banco in delivered_codes:
                    cursor.execute("""
                        UPDATE historico 
                        SET status_entrega = 'ENTREGUE' 
                        WHERE codigo = ? AND (status_entrega IS NULL OR status_entrega != 'ENTREGUE')
                    """, (cod_banco,))
                    if cursor.rowcount > 0:
                        registros_atualizados += 1
                        
            conn.commit()
            conn.close()
            return jsonify({
                "status": "sucesso",
                "mensagem": f"Processado o Delivered.xlsx. Atualizados {registros_atualizados} pacotes no banco local para o status ENTREGUE."
            })
            
        # CASO B: Importando o Imile.xlsx (com as regras especiais da Coluna L e Delivered.xlsx)
        elif nome_arquivo == "Imile.xlsx":
            wb_imile = openpyxl.load_workbook(path, data_only=True)
            sheet_imile = wb_imile.active
            
            for r_idx, row in enumerate(sheet_imile.iter_rows(values_only=True)):
                if r_idx == 0: # Cabeçalho
                    continue
                if not row or len(row) < 1 or not row[0]:
                    continue
                    
                code = str(row[0]).strip()
                if len(code) < 5:
                    continue
                    
                # Coluna L (index 11) é Driver Name (Nome do Motorista no site)
                driver_name = ""
                if len(row) > 11 and row[11] is not None:
                    driver_name = str(row[11]).strip()
                    
                # Regra de Mapeamento de Motoristas: Usuario Imile -> Motorista Imile
                if driver_name:
                    mot_clean = driver_name.strip().lower()
                    if mot_clean in imile_map:
                        driver_name = imile_map[mot_clean]
                    
                # Regra: se Driver Name estiver em branco, está na Base (NA BASE). Se não, está Em Rota (EM ROTA)
                if not driver_name or driver_name == "":
                    status_final = "NA BASE"
                else:
                    status_final = "EM ROTA"
                    
                # Regra: se o código estiver no Delivered.xlsx, o status é ENTREGUE
                if code in delivered_codes:
                    status_final = "ENTREGUE"
                    
                # Coluna H (index 7) é Backlog time(Station) em horas -> converter para dias
                tempo_atraso_dias = 0.0
                if len(row) > 7 and row[7] is not None:
                    try:
                        tempo_atraso_dias = float(row[7]) / 24.0
                    except (ValueError, TypeError):
                        pass
                    
                pacotes.append({
                    "codigo": code,
                    "status_entrega": status_final,
                    "motorista_entrega": driver_name,
                    "tempo_atraso": tempo_atraso_dias
                })
            wb_imile.close()
            
        # CASO C: Outro arquivo (Anjun.xlsx, etc.)
        else:
            wb = openpyxl.load_workbook(path, data_only=True)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            wb.close()
            
            if len(rows) == 0:
                return jsonify({"status": "erro", "mensagem": "A planilha esta vazia."}), 400
                
            header_row_idx = -1
            col_idx_codigo = -1
            col_idx_status = -1
            col_idx_motorista = -1
            
            if nome_arquivo == "Anjun.xlsx":
                # Limpa registros antigos da Anjun no banco de dados para considerar apenas a planilha
                conn_del = conectar_banco()
                cursor_del = conn_del.cursor()
                cursor_del.execute("DELETE FROM historico WHERE plataforma = 'anjun'")
                conn_del.commit()
                conn_del.close()
                print("[Import Local] Registros antigos da Anjun excluídos para priorizar a planilha.")
                
                col_idx_codigo = 0
                col_idx_status = 5
                col_idx_motorista = 13
                col_idx_timestamp = 2
                col_idx_cidade = 30
                col_idx_recebedor = 26
                col_idx_cep = 31
                header_row_idx = 0
            else:
                for r in range(min(len(rows), 15)):
                    row = rows[r]
                    if not row:
                        continue
                    for c, val in enumerate(row):
                        if val is None:
                            continue
                        cell_val = str(val).lower().strip()
                        import unicodedata
                        cell_val_clean = "".join(ch for ch in unicodedata.normalize('NFKD', cell_val) if not unicodedata.combining(ch))
                        
                        if col_idx_codigo == -1 and any(kw in cell_val_clean for kw in ['codigo', 'waybill', 'tracking', 'pacote', 'etiqueta', 'barras', 'barcode', 'pedido', 'guia', 'nombill']):
                            col_idx_codigo = c
                        if col_idx_status == -1 and any(kw in cell_val_clean for kw in ['status', 'estado', 'situacao', 'fase', 'etapa', 'resultado']):
                            col_idx_status = c
                        if col_idx_motorista == -1 and any(kw in cell_val_clean for kw in ['motorista', 'entregador', 'driver', 'courier', 'operador', 'nome']):
                            col_idx_motorista = c
                            
                    if col_idx_codigo != -1:
                        header_row_idx = r
                        break
                    
            if col_idx_codigo == -1:
                return jsonify({"status": "erro", "mensagem": "Nao foi possivel localizar a coluna de Codigo de Rastreamento na planilha."}), 400
                
            for r in range(header_row_idx + 1, len(rows)):
                row = rows[r]
                if not row or len(row) <= col_idx_codigo or row[col_idx_codigo] is None:
                    continue
                    
                cod = str(row[col_idx_codigo]).strip()
                if len(cod) < 5:
                    continue
                    
                status_val = ""
                if col_idx_status != -1 and len(row) > col_idx_status and row[col_idx_status] is not None:
                    status_val = str(row[col_idx_status]).strip()
                    
                motorista_val = ""
                if col_idx_motorista != -1 and len(row) > col_idx_motorista and row[col_idx_motorista] is not None:
                    motorista_val = str(row[col_idx_motorista]).strip()
                    
                # Regra de Mapeamento de Motoristas: Usuario Anjun -> Motorista Anjun
                if motorista_val:
                    mot_clean = motorista_val.strip().lower()
                    if mot_clean in anjun_map:
                        motorista_val = anjun_map[mot_clean]
                    elif mot_clean in imile_map:
                        motorista_val = imile_map[mot_clean]
                        
                # Informações específicas para importação direta da Anjun.xlsx
                cidade_val = "Avaré"  # Default
                recebedor_val = ""
                cep_val = ""
                ts_val = ""
                
                if nome_arquivo == "Anjun.xlsx":
                    if len(row) > col_idx_cidade and row[col_idx_cidade] is not None:
                        cidade_val = str(row[col_idx_cidade]).strip()
                    if len(row) > col_idx_recebedor and row[col_idx_recebedor] is not None:
                        recebedor_val = str(row[col_idx_recebedor]).strip()
                    if len(row) > col_idx_cep and row[col_idx_cep] is not None:
                        cep_val = str(row[col_idx_cep]).strip()
                    if len(row) > col_idx_timestamp and row[col_idx_timestamp] is not None:
                        val_ts = row[col_idx_timestamp]
                        if isinstance(val_ts, datetime.datetime):
                            ts_val = val_ts.isoformat()
                        else:
                            ts_val = str(val_ts).replace(" ", "T").strip()
                    
                status_lower = status_val.lower()
                import unicodedata
                status_clean = "".join(ch for ch in unicodedata.normalize('NFKD', status_lower) if not unicodedata.combining(ch))
                
                status_final = "PENDENTE"
                if any(kw in status_clean for kw in ['entregue', 'delivered', 'concluido', 'sucesso', 'finalizado', 'entregou']):
                    status_final = "ENTREGUE"
                elif any(kw in status_clean for kw in ['rota', 'transito', 'rua', 'curso', 'despachado', 'out for delivery', 'delivery', 'distribuicao', 'em andamento']):
                    status_final = "EM ROTA"
                elif any(kw in status_clean for kw in ['problema', 'insucesso', 'falha', 'retornado', 'devolvido', 'anulado', 'cancelado', 'recusado', 'ausente', 'endereco', 'failure', 'returned', 'problem', 'ocorrencia', 'perda', 'roubo']):
                    status_final = "PROBLEMA"
                elif status_val != "":
                    status_final = status_val.upper()
                else:
                    status_final = "ENTREGUE"
                    
                # Calcula dias de atraso se for Anjun
                tempo_atraso_dias = 0.0
                if nome_arquivo == "Anjun.xlsx" and len(row) > 7 and row[7] is not None:
                    val_str = str(row[7]).strip()
                    import datetime
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y'):
                        try:
                            parsed_dt = datetime.datetime.strptime(val_str, fmt)
                            diff_days = (datetime.datetime.now() - parsed_dt).total_seconds() / (24.0 * 3600.0)
                            tempo_atraso_dias = max(0.0, diff_days)
                            break
                        except ValueError:
                            pass
                            
                pacotes.append({
                    "codigo": cod,
                    "status_entrega": status_final,
                    "motorista_entrega": motorista_val,
                    "tempo_atraso": tempo_atraso_dias,
                    "cidade": cidade_val,
                    "recebedor": recebedor_val,
                    "status_pacote": status_val,
                    "timestamp": ts_val if ts_val else datetime.datetime.now().isoformat()
                })
        
        # 4. Atualiza os registros de pacotes no SQLite (ou insere novos no caso da Anjun.xlsx)
        conn = conectar_banco()
        cursor = conn.cursor()
        for item in pacotes:
            if nome_arquivo == "Anjun.xlsx":
                # Insere os dados completos do pacote diretamente no histórico
                cursor.execute("""
                    INSERT INTO historico (
                        timestamp, codigo, plataforma, cidade, motorista, status, 
                        recebedor, status_pacote, status_entrega, motorista_entrega, tempo_atraso
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["timestamp"], item["codigo"], 'anjun', item["cidade"], item["motorista_entrega"], 'OK',
                    item["recebedor"], item["status_pacote"], item["status_entrega"], item["motorista_entrega"], item["tempo_atraso"]
                ))
                registros_atualizados += 1
            else:
                cursor.execute("""
                    UPDATE historico 
                    SET status_entrega = ?, motorista_entrega = ?, tempo_atraso = ? 
                    WHERE codigo = ?
                """, (item["status_entrega"], item["motorista_entrega"], item.get("tempo_atraso", 0.0), item["codigo"]))
                if cursor.rowcount > 0:
                    registros_atualizados += 1
                
        # 5. Se foi carregado o Delivered.xlsx, faz uma varredura extra no historico do banco para garantir que qualquer pacote bipeado que conste no Delivered vire ENTREGUE
        if delivered_codes and nome_arquivo == "Imile.xlsx":
            cursor.execute("SELECT codigo FROM historico WHERE status = 'OK'")
            bips_banco = [r[0] for r in cursor.fetchall()]
            for cod_banco in bips_banco:
                if cod_banco in delivered_codes:
                    cursor.execute("""
                        UPDATE historico 
                        SET status_entrega = 'ENTREGUE' 
                        WHERE codigo = ? AND (status_entrega IS NULL OR status_entrega != 'ENTREGUE')
                    """, (cod_banco,))
                    if cursor.rowcount > 0:
                        registros_atualizados += 1
                        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "sucesso",
            "mensagem": f"Sincronizados {len(pacotes)} pacotes do arquivo {nome_arquivo}. {registros_atualizados} correspondencias atualizadas no banco local."
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/debug-windows', methods=['GET'])
def debug_windows():
    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun
    if not driver:
        return jsonify({"status": "erro", "mensagem": "Selenium driver not initialized"})
    
    handles_info = []
    current_handle = None
    try:
        current_handle = driver.current_window_handle
    except Exception:
        pass
        
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            handles_info.append({
                "handle": h,
                "title": driver.title,
                "url": driver.current_url,
                "is_active": (h == current_handle)
            })
        except Exception as e:
            handles_info.append({
                "handle": h,
                "error": str(e)
            })
            
    if current_handle:
        try:
            driver.switch_to.window(current_handle)
        except Exception:
            pass
            
    return jsonify({
        "status": "sucesso",
        "current_handle": current_handle,
        "aba_recebimento": aba_recebimento,
        "aba_descarregamento": aba_descarregamento,
        "aba_atribuicao": aba_atribuicao,
        "aba_atribuicao_anjun": aba_atribuicao_anjun,
        "handles": handles_info
    })

@app.route('/debug-dom', methods=['GET'])
def debug_dom():
    global driver
    if not driver:
        return jsonify({"status": "erro", "mensagem": "Selenium driver not initialized"})
    
    dom_info = {}
    current_handle = None
    try:
        current_handle = driver.current_window_handle
    except Exception:
        pass
        
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            url = driver.current_url
            inputs = []
            for tag in ['input', 'textarea', 'button']:
                elements = driver.find_elements(By.TAG_NAME, tag)
                for el in elements:
                    try:
                        if el.is_displayed():
                            inputs.append({
                                "tag": tag,
                                "id": el.get_attribute("id"),
                                "name": el.get_attribute("name"),
                                "placeholder": el.get_attribute("placeholder"),
                                "class": el.get_attribute("class"),
                                "text": el.text.strip(),
                                "value": el.get_attribute("value"),
                                "type": el.get_attribute("type")
                            })
                    except Exception:
                        pass
            dom_info[h] = {
                "url": url,
                "title": driver.title,
                "elements": inputs
            }
        except Exception as e:
            dom_info[h] = {"error": str(e)}
            
    if current_handle:
        try:
            driver.switch_to.window(current_handle)
        except Exception:
            pass
            
    return jsonify(dom_info)

@app.route('/atribuicao/exportar-csv', methods=['GET'])
def exportar_csv():
    try:
        data_inicio = request.args.get("data_inicio")
        data_fim = request.args.get("data_fim")
        data_filtro = request.args.get("data")
        
        if not data_inicio and not data_fim:
            if data_filtro:
                data_inicio = data_filtro
                data_fim = data_filtro
            else:
                import datetime
                data_inicio = datetime.datetime.now().strftime('%Y-%m-%d')
                data_fim = data_inicio
                
        label_periodo = data_inicio if data_inicio == data_fim else f"{data_inicio}_a_{data_fim}"
        start = data_inicio + "T00:00:00"
        end = data_fim + "T23:59:59"
        
        conn = conectar_banco()
        cursor = conn.cursor()
        
        # 1. Busca os dados agrupados por motorista, cidade, plataforma
        query_agrupado = """
            SELECT motorista, cidade, plataforma, count(id)
            FROM historico
            WHERE status = 'OK'
              AND timestamp >= ?
              AND timestamp <= ?
              AND motorista IS NOT NULL
              AND motorista != '---'
              AND motorista != ''
            GROUP BY motorista, cidade, plataforma
            ORDER BY motorista, count(id) DESC
        """
        cursor.execute(query_agrupado, (start, end))
        linhas_agrupadas = cursor.fetchall()
        
        # 2. Busca a lista detalhada de todos os bips daquele dia
        query_detalhada = """
            SELECT timestamp, codigo, plataforma, cidade, motorista, recebedor
            FROM historico
            WHERE timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp DESC
        """
        cursor.execute(query_detalhada, (start, end))
        linhas_detalhadas = cursor.fetchall()
        
        conn.close()
        
        import io
        import csv
        import datetime
        
        output = io.StringIO()
        output.write('\ufeff') # BOM UTF-8
        
        writer = csv.writer(output, delimiter=';')
        
        # Cabeçalho do Resumo
        writer.writerow([f"RESUMO DE ATRIBUIÇÕES - PERÍODO: {label_periodo}"])
        writer.writerow([])
        writer.writerow(["Motorista", "Cidade", "Plataforma", "Quantidade de Pacotes"])
        
        for r in linhas_agrupadas:
            writer.writerow([r[0], r[1], r[2], r[3]])
            
        writer.writerow([])
        writer.writerow([])
        
        # Cabeçalho da Listagem Detalhada
        writer.writerow(["LISTAGEM DETALHADA DE PACOTES BIPADOS"])
        writer.writerow([])
        writer.writerow(["Horário", "Código de Rastreio", "Plataforma", "Cidade Destino", "Motorista Atribuído", "Recebedor"])
        
        for r in linhas_detalhadas:
            ts = r[0]
            if ts and len(ts) >= 19:
                try:
                    dt = datetime.datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                    ts = dt.strftime('%d/%m/%Y %H:%M:%S')
                except Exception:
                    pass
            writer.writerow([ts, r[1], r[2], r[3], r[4], r[5]])
            
        csv_data = output.getvalue()
        output.close()
        
        from flask import Response
        response = Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=Fechamento_Triagem_{label_periodo}.csv"}
        )
        return response
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/historico/limpar', methods=['POST'])
def limpar_historico():
    salvar_historico([])
    return jsonify({"status": "sucesso", "mensagem": "Histórico limpo com sucesso!"})

@app.route('/divergencias/pendentes', methods=['GET'])
def obter_divergencias_pendentes():
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT codigo, motorista_lote, motorista_esperado, timestamp FROM divergencias_pendentes WHERE status = 'pendente' AND timestamp >= datetime('now', '-18 hours')")
        linhas = cursor.fetchall()
        conn.close()
        
        resultado = []
        for r in linhas:
            resultado.append({
                "codigo": r[0],
                "motorista_lote": r[1],
                "motorista_esperado": r[2],
                "timestamp": r[3]
            })
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/atribuicao/lotes-finalizados', methods=['GET'])
def obter_lotes_finalizados():
    try:
        data_inicio = request.args.get("data_inicio")
        data_fim = request.args.get("data_fim")
        data_filtro = request.args.get("data")
        
        if not data_inicio and not data_fim and data_filtro:
            data_inicio = data_filtro
            data_fim = data_filtro
            
        conn = conectar_banco()
        cursor = conn.cursor()
        
        if data_inicio and data_fim:
            start = data_inicio + "T00:00:00"
            end = data_fim + "T23:59:59"
            query = """
                SELECT motorista, plataforma, count(id) 
                FROM historico 
                WHERE status = 'OK' 
                  AND timestamp >= ? 
                  AND timestamp <= ?
                  AND motorista IS NOT NULL 
                  AND motorista != '---' 
                  AND motorista != ''
                GROUP BY motorista, plataforma
                ORDER BY count(id) DESC
            """
            cursor.execute(query, (start, end))
        else:
            import datetime
            cutoff = datetime.datetime.now().strftime('%Y-%m-%dT00:00:00')
            query = """
                SELECT motorista, plataforma, count(id) 
                FROM historico 
                WHERE status = 'OK' 
                  AND timestamp >= ? 
                  AND motorista IS NOT NULL 
                  AND motorista != '---' 
                  AND motorista != ''
                GROUP BY motorista, plataforma
                ORDER BY count(id) DESC
            """
            cursor.execute(query, (cutoff,))
            
        linhas = cursor.fetchall()
        
        resultado = []
        for r in linhas:
            motorista_nome = r[0]
            plat = r[1]
            qtd = r[2]
            
            plat_display = "Outros"
            if plat:
                plat_lower = plat.lower()
                if 'anjun' in plat_lower:
                    plat_display = "Anjun"
                elif 'imile' in plat_lower:
                    plat_display = "iMile"
                else:
                    plat_display = plat.capitalize()
                    
            # Busca cidades ativas cadastradas para o motorista
            try:
                cursor.execute("SELECT cidade FROM motoristas_plataforma WHERE motorista = ?", (motorista_nome,))
                cidades_list = [row[0] for row in cursor.fetchall()]
                if not cidades_list:
                    cursor.execute("SELECT cidade FROM motoristas WHERE motorista = ?", (motorista_nome,))
                    cidades_list = [row[0] for row in cursor.fetchall()]
            except Exception:
                cidades_list = []
            cidades_str = ", ".join(cidades_list) if cidades_list else "Sem Cidades"
            
            resultado.append({
                "motorista": motorista_nome,
                "cidades": cidades_str,
                "quantidade": qtd,
                "plataforma": plat_display,
                "timestamp": ""
            })
            
        conn.close()
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/atribuicao/status', methods=['GET'])
def obter_atribuicao_status():
    global contagem_motoristas, motorista_atribuicao_ativa
    cont = contagem_motoristas.get(motorista_atribuicao_ativa, 0) if motorista_atribuicao_ativa else 0
    return jsonify({
        "motorista": motorista_atribuicao_ativa,
        "contagem": cont
    })

@app.route('/gerencia/alertas', methods=['GET'])
def obter_alertas_gerencia():
    return jsonify(alertas_gerencia)

@app.route('/gerencia/alertas/limpar', methods=['POST'])
def limpar_alertas_gerencia():
    global alertas_gerencia
    alertas_gerencia.clear()
    return jsonify({"status": "sucesso"})

@app.route('/atribuicao/iniciar', methods=['POST'])
@requer_licenca_ativa
def atribuicao_iniciar():
    global driver, aba_atribuicao_anjun, motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas
    dados = request.json
    motorista = dados.get("motorista")
    
    if not motorista:
        return jsonify({"status": "erro", "mensagem": "Motorista não especificado."}), 400
    if not driver or not aba_atribuicao_anjun:
        return jsonify({"status": "erro", "mensagem": "Navegador de atribuição não está ativo."}), 400
        
    driver_lock.acquire()
    try:
        print(f"[*] Focando aba 3 para iniciar atribuição do motorista: {motorista}...")
        driver.switch_to.window(aba_atribuicao_anjun)
        fechar_possiveis_lembretes(driver)
        
        # 1. Localiza e seleciona o Entregador na Aba 3 (com verificação de popups e auto-retry)
        selecionar_motorista_anjun(driver, motorista)
        
        # Tenta ler a contagem do site logo após iniciar
        contagem_site = None
        try:
            xpath_contagem = [
                "//span[contains(@class, 'hasScan')]//i",
                "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[2]/span/i"
            ]
            for xp in xpath_contagem:
                try:
                    el_cont = driver.find_element(By.XPATH, xp)
                    if el_cont.is_displayed():
                        val_str = el_cont.text.strip()
                        if val_str.isdigit():
                            contagem_site = int(val_str)
                            print(f"[+] Contagem inicial lida do site para {motorista}: {contagem_site}")
                            break
                except Exception:
                    continue
        except Exception:
            pass
            
        motorista_atribuicao_ativa = motorista
        if contagem_site is not None:
            contagem_motoristas[motorista] = contagem_site
            contagem_atribuicao_ativa = contagem_site
        else:
            contagem_atribuicao_ativa = contagem_motoristas.setdefault(motorista, 0)
            
        if aba_recebimento and driver:
            try:
                if aba_recebimento in driver.window_handles:
                    driver.switch_to.window(aba_recebimento)
                    fechar_possiveis_lembretes(driver)
            except Exception:
                pass
            
        return jsonify({"status": "sucesso", "contagem": contagem_atribuicao_ativa})
    except Exception as e:
        print(f"[Erro] Falha ao iniciar atribuição de {motorista}: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        if aba_recebimento and driver:
            try:
                if aba_recebimento in driver.window_handles:
                    driver.switch_to.window(aba_recebimento)
            except Exception:
                pass
        driver_lock.release()

def selecionar_motorista_imile(driver, motorista):
    """
    Seleciona com extrema rapidez e estabilidade o motorista no dropdown da tela de Atribuição da iMile (assignDA).
    Resolve o problema de 'debounce/filtro assíncrono' do campo de busca que fazia o elemento sumir
    e reaparecer alguns segundos depois.
    
    Estratégia:
    1. Resolução inteligente de mapeamento de nome (Motoristas.xlsx).
    2. Fast-Path: verifica se a opção do motorista já está visível no dropdown aberto antes de digitar (tempo: ~0.05s).
    3. Digitação rápida em lote único (sem loop caractere por caractere com delay) para acionar o filtro 1 única vez.
    4. Polling dinâmico via JavaScript que aguarda a lista atualizar e clica atomicamente no mesmo tick do DOM,
       eliminando completamente StaleElementReferenceException e falhas de clique.
    """
    import unicodedata
    import re
    
    def _norm(txt):
        return "".join(c for c in unicodedata.normalize('NFD', str(txt)) if unicodedata.category(c) != 'Mn').strip().lower()

    mot_clean = str(motorista).strip()
    if not mot_clean or mot_clean in ["---", "Apenas Entrada (Sem Atribuição)"]:
        return True, "Nenhum motorista a selecionar", ""

    # Carrega o mapeamento do Excel se disponível para pegar a grafia exata
    try:
        imile_map, _ = carregar_mapeamento_motoristas()
    except Exception:
        imile_map = {}

    mot_mapeado = imile_map.get(mot_clean.lower(), mot_clean)
    targets = [mot_mapeado, mot_clean]
    
    # Extrai tokens para busca e filtragem
    t_clean = _norm(mot_mapeado)
    raw_tokens = [t for t in re.split(r'[\s\-_|/]+', t_clean) if len(t) >= 2]
    stop_words = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'com', 'sem'}
    tokens = [t for t in raw_tokens if t not in stop_words or len(raw_tokens) == 1]
    if not tokens and raw_tokens:
        tokens = raw_tokens
        
    primeiro_nome = tokens[0] if tokens else t_clean[:5]
    termo_digitar = primeiro_nome

    js_buscar_e_clicar = """
        function norm(str) {
            return (str || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().trim();
        }

        var targets = arguments[0];
        var tokens = arguments[1];
        var primeiroNome = arguments[2] || "";

        var candidates = document.querySelectorAll(
            ".ImileMenuItem-primary, .ImileMenuItem-text, .ImileEllipsis-root, [role='menuitem'], .ImileMenuItem-root"
        );

        var visibleItems = [];
        for (var i = 0; i < candidates.length; i++) {
            var el = candidates[i];
            if (el && (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0)) {
                var txt = (el.innerText || el.textContent || "").trim();
                if (txt && !txt.includes("Por favor") && !txt.includes("Nenhum Dado") && !txt.includes("Atribuir") && txt.length > 2) {
                    visibleItems.push({ element: el, text: txt, normText: norm(txt) });
                }
            }
        }

        if (visibleItems.length === 0) {
            return { status: "loading" };
        }

        function triggerClick(el) {
            var clickTarget = el.closest ? (el.closest('[role="menuitem"]') || el.closest('.ImileMenuItem-root') || el) : el;
            try {
                clickTarget.click();
            } catch(e) {
                clickTarget.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }
        }

        // 1. Match direto
        for (var t = 0; t < targets.length; t++) {
            var tgtNorm = norm(targets[t]);
            if (!tgtNorm) continue;
            for (var j = 0; j < visibleItems.length; j++) {
                var item = visibleItems[j];
                var siteNomeSemId = item.normText.split('|')[0].trim();
                if (item.normText.includes(tgtNorm) || tgtNorm.includes(siteNomeSemId) || siteNomeSemId.includes(tgtNorm)) {
                    triggerClick(item.element);
                    return { status: "clicked", text: item.text, method: "direct" };
                }
            }
        }

        // 2. Match por tokens
        if (primeiroNome && primeiroNome.length >= 2) {
            var fnMatches = [];
            for (var j = 0; j < visibleItems.length; j++) {
                var item = visibleItems[j];
                if (item.normText.startsWith(primeiroNome) || item.normText.includes(primeiroNome)) {
                    fnMatches.push(item);
                }
            }
            
            if (fnMatches.length === 1) {
                triggerClick(fnMatches[0].element);
                return { status: "clicked", text: fnMatches[0].text, method: "single_fn" };
            } else if (fnMatches.length > 1) {
                var bestItem = null;
                var bestScore = 0;
                for (var k = 0; k < fnMatches.length; k++) {
                    var item = fnMatches[k];
                    var score = 0;
                    for (var tokIdx = 0; tokIdx < tokens.length; tokIdx++) {
                        if (item.normText.includes(tokens[tokIdx])) score++;
                    }
                    if (score > bestScore) {
                        bestScore = score;
                        bestItem = item;
                    }
                }
                if (bestItem && bestScore >= 1) {
                    triggerClick(bestItem.element);
                    return { status: "clicked", text: bestItem.text, method: "best_score" };
                }
            }
        }

        // 3. Fallback de 1 único item visível
        if (visibleItems.length === 1) {
            var unico = visibleItems[0];
            if (primeiroNome && unico.normText.includes(primeiroNome.substring(0, 3))) {
                triggerClick(unico.element);
                return { status: "clicked", text: unico.text, method: "unique_filtered" };
            }
        }

        return { status: "not_found", count: visibleItems.length };
    """

    for tentativa in range(1, 3):
        try:
            print(f"[*] Selecionando motorista na iMile (Tentativa {tentativa}): '{mot_clean}' (Busca: '{termo_digitar}')...")
            
            # 1. Verifica se o campo de busca do popover já está visível
            campo_busca = None
            candidatos_busca = [
                "//input[contains(@placeholder, 'insira') and not(@name='scanNumber')]",
                "//input[contains(@placeholder, 'Insira') and not(@name='scanNumber')]",
                "//*[contains(@class, 'popover') or contains(@class, 'popper') or contains(@class, 'dropdown')]//input[not(@name='scanNumber')]"
            ]
            for xp in candidatos_busca:
                try:
                    el = driver.find_element(By.XPATH, xp)
                    if el.is_displayed():
                        campo_busca = el
                        break
                except Exception:
                    continue

            # Se não estiver aberto, clica no trigger do dropdown
            if not campo_busca:
                candidatos_trigger = [
                    "//*[@id='daCode']/div[2]/div/div[1]/div/div",
                    "//*[@id='daCode']//*[contains(@class, 'ImileSelect-root')]",
                    "//*[@id='daCode']",
                    "//*[contains(@class, 'ImileSelect-root')]"
                ]
                for xp_tr in candidatos_trigger:
                    try:
                        el_tr = driver.find_element(By.XPATH, xp_tr)
                        if el_tr.is_displayed():
                            try:
                                el_tr.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", el_tr)
                            break
                    except Exception:
                        continue
                
                # Aguarda o campo de busca abrir
                t0_open = time.time()
                while time.time() - t0_open < 1.5:
                    for xp in candidatos_busca:
                        try:
                            el = driver.find_element(By.XPATH, xp)
                            if el.is_displayed():
                                campo_busca = el
                                break
                        except Exception:
                            continue
                    if campo_busca:
                        break
                    time.sleep(0.1)

            # 2. Fast-Path: se o motorista já estiver visível na lista aberta, clica imediatamente sem precisar digitar!
            res_fast = driver.execute_script(js_buscar_e_clicar, targets, tokens, primeiro_nome)
            if res_fast and res_fast.get("status") == "clicked":
                nome_sel = res_fast.get("text", mot_clean)
                print(f"[+] [Fast-Path] Motorista iMile selecionado instantaneamente: {nome_sel}")
                time.sleep(0.2)
                return True, "Motorista selecionado com sucesso (fast-path)", nome_sel

            # 3. Digitação rápida em lote único (evita tempestade de debounces)
            if campo_busca:
                try:
                    campo_busca.click()
                except Exception:
                    driver.execute_script("arguments[0].focus();", campo_busca)
                time.sleep(0.05)
                campo_busca.send_keys(Keys.CONTROL + "a")
                campo_busca.send_keys(Keys.BACKSPACE)
                time.sleep(0.05)
                campo_busca.send_keys(termo_digitar)
                try:
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_busca)
                except Exception:
                    pass

            # 4. Polling dinâmico aguardando a lista filtrar e reaparecer
            t_inicio_poll = time.time()
            clicado = False
            nome_sel = None
            while time.time() - t_inicio_poll < 4.5:
                res = driver.execute_script(js_buscar_e_clicar, targets, tokens, primeiro_nome)
                if res and res.get("status") == "clicked":
                    clicado = True
                    nome_sel = res.get("text", mot_clean)
                    print(f"[+] Motorista iMile selecionado com sucesso após filtro: {nome_sel} (método: {res.get('method')})")
                    break
                time.sleep(0.12)

            if clicado:
                time.sleep(0.2)
                return True, "Motorista selecionado com sucesso", nome_sel
            else:
                print(f"[Aviso] Tentativa {tentativa}: Motorista '{mot_clean}' não localizado no dropdown iMile.")

        except Exception as e_tent:
            print(f"[Aviso] Erro na tentativa {tentativa} de seleção iMile: {str(e_tent)}")

        # Preparação para tentativa 2
        if tentativa == 1:
            try:
                fechar_modais_imile(driver)
                webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
            time.sleep(0.3)

    return False, f"O motorista '{mot_clean}' não foi localizado no cadastro do site da iMile. Verifique se o nome está idêntico ao cadastrado no site da iMile.", None

def preparar_motorista_no_site(plataforma_id, motorista):
    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, motorista_atribuicao_ativa
    
    # 1. Garante que o navegador esteja aberto e na plataforma correta
    inicializar_selenium(plataforma_id)
    
    if not motorista or str(motorista).strip() in ["", "---", "Apenas Entrada (Sem Atribuição)"]:
        return {
            "status": "sucesso", 
            "mensagem": f"Navegador pronto para {plataforma_id} (sem motorista selecionado).",
            "motorista_selecionado": ""
        }
        
    mot_clean = str(motorista).strip()
    driver_lock.acquire()
    try:
        if plataforma_id == 'imile':
            print(f"[*] Posicionando motorista iMile no Chrome: {mot_clean}...")
            # Garante que a aba de atribuição (assignDA) esteja mapeada
            if not aba_atribuicao_anjun:
                for handle in driver.window_handles:
                    try:
                        driver.switch_to.window(handle)
                        if "assignda" in driver.current_url.lower():
                            aba_atribuicao_anjun = handle
                            break
                    except Exception:
                        continue
            if aba_atribuicao_anjun:
                mudar_aba_acelerado(driver, aba_atribuicao_anjun)
                time.sleep(0.4)
                fechar_modais_imile(driver)
                
                sucesso, msg_ret, nome_sel = selecionar_motorista_imile(driver, mot_clean)
                if sucesso:
                    motorista_atribuicao_ativa = mot_clean
                    print(f"[+] Motorista iMile posicionado no Chrome: {nome_sel or mot_clean}")
                    time.sleep(0.3)
                    return {
                        "status": "sucesso", 
                        "mensagem": f"Motorista '{nome_sel or mot_clean}' posicionado no Chrome com sucesso.",
                        "motorista_selecionado": mot_clean
                    }
                else:
                    print(f"[Aviso] Motorista '{mot_clean}' não localizado no dropdown iMile: {msg_ret}")
                    return {
                        "status": "aviso_motorista",
                        "mensagem": msg_ret,
                        "motorista_selecionado": mot_clean
                    }
                            
        elif plataforma_id == 'anjun':
            print(f"[*] Posicionando motorista Anjun no Chrome: {mot_clean}...")
            if not aba_atribuicao_anjun or aba_atribuicao_anjun not in driver.window_handles:
                for handle in driver.window_handles:
                    try:
                        driver.switch_to.window(handle)
                        url_cur = driver.current_url.lower()
                        if "taskassignment" in url_cur or "task" in url_cur or "operatingcenter" in url_cur:
                            aba_atribuicao_anjun = handle
                            break
                    except Exception:
                        continue
            if aba_atribuicao_anjun:
                mudar_aba_acelerado(driver, aba_atribuicao_anjun)
                time.sleep(0.3)
                fechar_possiveis_lembretes(driver)
                
                selecionar_motorista_anjun(driver, mot_clean)
                motorista_atribuicao_ativa = mot_clean
                if aba_recebimento and aba_recebimento in driver.window_handles:
                    try:
                        mudar_aba_acelerado(driver, aba_recebimento)
                        fechar_possiveis_lembretes(driver)
                    except Exception:
                        pass
                return {
                    "status": "sucesso", 
                    "mensagem": f"Motorista '{mot_clean}' selecionado no Chrome com sucesso.",
                    "motorista_selecionado": mot_clean
                }
                    
        elif plataforma_id == 'loggi':
            print(f"[*] Posicionando motorista/grupo Loggi no Chrome: {mot_clean}...")
            garantir_abas_loggi(driver)
            motorista_atribuicao_ativa = mot_clean
            if aba_recebimento and aba_recebimento in driver.window_handles:
                try:
                    mudar_aba_acelerado(driver, aba_recebimento)
                except Exception:
                    pass
            return {
                "status": "sucesso", 
                "mensagem": f"Loggi pronta para '{mot_clean}'.",
                "motorista_selecionado": mot_clean
            }
            
        return {
            "status": "sucesso", 
            "mensagem": f"Navegador pronto para {plataforma_id}.",
            "motorista_selecionado": mot_clean
        }
    except Exception as e:
        print(f"[Aviso] Falha ao posicionar motorista no Chrome: {str(e)}")
        return {
            "status": "aviso_motorista",
            "mensagem": f"Chrome aberto, aviso ao selecionar motorista: {str(e)}",
            "motorista_selecionado": mot_clean
        }
    finally:
        driver_lock.release()

@app.route('/recuperar-sessao-motorista', methods=['POST'])
def recuperar_sessao_motorista():
    dados = request.json or {}
    plat = (dados.get("plataforma") or "anjun").strip().lower()
    mot = dados.get("motorista")
    
    try:
        resultado = preparar_motorista_no_site(plat, mot)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/atribuicao/bip', methods=['POST'])
@requer_licenca_ativa
def atribuicao_bip():
    global driver, aba_atribuicao_anjun, motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas
    dados = request.json
    codigo = dados.get("codigo")
    
    if not codigo:
        return jsonify({"status": "erro", "mensagem": "Código vazio"}), 400
    if not motorista_atribuicao_ativa:
        return jsonify({"status": "erro", "mensagem": "Nenhum motorista ativo para atribuição."}), 400
    if not driver or not aba_atribuicao_anjun:
        return jsonify({"status": "erro", "mensagem": "Navegador de atribuição não está ativo."}), 400
        
    driver_lock.acquire()
    try:
        driver.switch_to.window(aba_atribuicao_anjun)
        
        # Localiza campo de bipe de pacote
        candidatos_pacote = [
            "//input[@placeholder='Favor digitalizar ou digitar']",
            "//label[contains(., 'Bipar o')]/following::input[1]",
            "//*[contains(text(), 'Bipar o')]/following::input[1]"
        ]
        campo_pacote = None
        for xpath in candidatos_pacote:
            try:
                campo_pacote = driver.find_element(By.XPATH, xpath)
                if campo_pacote.is_displayed():
                    break
            except Exception:
                continue
        
        if not campo_pacote:
            raise Exception("Não foi possível localizar o campo de input de bipe de pacote.")
        
        campo_pacote.click()
        campo_pacote.send_keys(Keys.CONTROL + "a")
        campo_pacote.send_keys(Keys.BACKSPACE)
        time.sleep(0.1)
        
        print(f"[*] Enviando bipe do pacote {codigo} para o motorista {motorista_atribuicao_ativa}...")
        campo_pacote.send_keys(codigo + Keys.ENTER)
        time.sleep(0.5)
        
        # Tenta ler a contagem do site após o bipe
        contagem_site = None
        try:
            xpath_contagem = [
                "//span[contains(@class, 'hasScan')]//i",
                "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[2]/span/i"
            ]
            for xp in xpath_contagem:
                try:
                    el_cont = driver.find_element(By.XPATH, xp)
                    if el_cont.is_displayed():
                        val_str = el_cont.text.strip()
                        if val_str.isdigit():
                            contagem_site = int(val_str)
                            print(f"[+] Contagem do site após bipe manual: {contagem_site}")
                            break
                except Exception:
                    continue
        except Exception:
            pass
            
        if contagem_site is not None:
            contagem_motoristas[motorista_atribuicao_ativa] = contagem_site
            contagem_atribuicao_ativa = contagem_site
        else:
            contagem_atribuicao_ativa = contagem_motoristas.get(motorista_atribuicao_ativa, 0) + 1
            contagem_motoristas[motorista_atribuicao_ativa] = contagem_atribuicao_ativa
            
        print(f"[+] Atribuição do pacote {codigo} realizada ({contagem_atribuicao_ativa}/200).")
        
        # Verifica se atingiu o limite de 200 para fechar automaticamente
        if contagem_atribuicao_ativa >= 200:
            print(f"[!] Limite de 200 pacotes atingido para {motorista_atribuicao_ativa}. Finalizando lote automaticamente...")
            candidatos_finalizar = [
                "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[1]/button[1]",
                "//button[contains(., 'Finalizar') or contains(., 'Concluir') or contains(., 'Gerar') or contains(., 'Emitir') or contains(., 'Emissão') or contains(., 'Tarefa')]",
                "//button[contains(@class, 'el-button--primary')]"
            ]
            for xpath in candidatos_finalizar:
                try:
                    btn = driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1.0)
                        break
                except Exception:
                    continue
            
            registrar_lote_finalizado(motorista_atribuicao_ativa, 200)
            contagem_motoristas[motorista_atribuicao_ativa] = 0
            motorista_atribuicao_ativa = None
            contagem_atribuicao_ativa = 0
            return jsonify({"status": "finalizado_limite", "contagem": 200})
            
        return jsonify({"status": "sucesso", "contagem": contagem_atribuicao_ativa})
    except Exception as e:
        print(f"[Erro] Falha ao enviar bipe de atribuição: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        driver_lock.release()

aba_atual_ativa = None

def mudar_aba_acelerado(driver, handle, delay=0.08):
    global aba_atual_ativa
    if not driver or not handle:
        return
    try:
        if aba_atual_ativa != handle:
            driver.switch_to.window(handle)
            aba_atual_ativa = handle
        try:
            driver.execute_script("if (document.visibilityState !== 'visible') { window.focus(); }")
        except Exception:
            pass
        if delay > 0:
            time.sleep(delay)
    except Exception:
        try:
            driver.switch_to.window(handle)
            aba_atual_ativa = handle
            if delay > 0:
                time.sleep(delay)
        except Exception:
            pass

def fechar_popups_finalizacao_anjun(driver):
    # 1. Fechar o popup "Sequência de etiqueta"
    try:
        dialog_seq = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog' and (contains(@aria-label, 'etiqueta') or contains(., 'Sequência de etiqueta'))]"))
        )
        btn_fechar_seq = None
        candidatos_fechar_seq = [
            ".//button[contains(., 'Fechar') or contains(., 'Close') or contains(., 'Confirmar') or contains(., 'Confirm')]",
            ".//button[contains(@class, 'el-button--primary')]",
            ".//button"
        ]
        for xpath_fechar in candidatos_fechar_seq:
            try:
                el_btn = dialog_seq.find_element(By.XPATH, xpath_fechar)
                if el_btn.is_displayed():
                    btn_fechar_seq = el_btn
                    break
            except Exception:
                continue
        if btn_fechar_seq:
            try:
                btn_fechar_seq.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_fechar_seq)
            print("[+] Popup 'Sequência de etiqueta' fechado!")
            time.sleep(0.5)
    except Exception as e_seq:
        print(f"[Aviso] Falha ao fechar popup de sequência: {str(e_seq)}")
        
    # 2. Clicar em "Confirmar" na janela de Dica
    try:
        btn_confirmar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Confirmar') or contains(., 'Confirm') or contains(., 'OK') or contains(., 'Ok') or contains(span, 'Confirmar')]"))
        )
        try:
            btn_confirmar.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn_confirmar)
        print("[+] Lote confirmado com sucesso na janela 'Dica'!")
        time.sleep(0.5)
    except Exception as e_conf:
        print(f"[Aviso] Falha ao clicar no botão Confirmar da dica: {str(e_conf)}")

def selecionar_motorista_anjun(driver, motorista):
    """
    Seleciona com extrema rapidez e estabilidade o motorista no dropdown da Aba 3 (TaskAssignment) da Anjun Express.
    Adota a mesma arquitetura de alto desempenho da iMile:
    1. Fast-Path: se a opção já estiver visível no dropdown aberto, clica imediatamente sem digitar (~0.05s).
    2. Digitação atômica em lote único (sem loop letra-a-letra nem dead sleeps de 1.2s).
    3. Polling em JavaScript nativo direto no DOM para encontrar e clicar no item correspondente em ~50-150ms.
    """
    import unicodedata
    import re

    def _norm(txt):
        return "".join(c for c in unicodedata.normalize('NFD', str(txt)) if unicodedata.category(c) != 'Mn').strip().lower()

    mot_clean = str(motorista).strip()
    if not mot_clean or mot_clean in ["---", "Apenas Entrada (Sem Atribuição)"]:
        return True

    # Suporte a mapeamento de nomes se existir
    try:
        _, anjun_map = carregar_mapeamento_motoristas()
    except Exception:
        anjun_map = {}

    mot_mapeado = anjun_map.get(mot_clean.lower(), mot_clean)
    targets = [mot_mapeado, mot_clean]

    # Extrai tokens para busca e filtragem inteligente
    t_clean = _norm(mot_mapeado)
    raw_tokens = [t for t in re.split(r'[\s\-_|/]+|(?<=[a-z])(?=[A-Z])', mot_mapeado) if len(t) >= 2]
    tokens = [_norm(t) for t in raw_tokens if len(t) >= 2]
    if not tokens:
        tokens = [t_clean]

    primeiro_nome = tokens[0] if tokens else t_clean[:5]
    termo_digitar = tokens[0] if tokens else mot_clean

    js_buscar_e_clicar_anjun = """
        function norm(str) {
            return (str || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "").trim();
        }

        var targets = arguments[0];
        var tokens = arguments[1];
        var primeiroNome = arguments[2] || "";

        var candidates = document.querySelectorAll(
            ".el-select-dropdown__item, .el-select-dropdown .el-scrollbar__view li, li.el-select-dropdown__item, .el-popper .el-select-dropdown__item, [role='option'], .el-select-dropdown li"
        );

        var visibleItems = [];
        for (var i = 0; i < candidates.length; i++) {
            var el = candidates[i];
            if (el && (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0)) {
                var txt = (el.innerText || el.textContent || "").trim();
                if (txt && !txt.includes("Sem dados") && !txt.includes("Nenhum") && txt.length >= 2) {
                    visibleItems.push({ element: el, text: txt, normText: norm(txt) });
                }
            }
        }

        if (visibleItems.length === 0) {
            return { status: "loading" };
        }

        function triggerClick(el) {
            try {
                el.scrollIntoView({ block: 'nearest' });
            } catch(e) {}
            try {
                el.click();
            } catch(e) {
                el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }
        }

        // 1. Match direto exato ou substring
        for (var t = 0; t < targets.length; t++) {
            var tgtNorm = norm(targets[t]);
            if (!tgtNorm) continue;
            for (var j = 0; j < visibleItems.length; j++) {
                var item = visibleItems[j];
                if (item.normText === tgtNorm || item.normText.includes(tgtNorm) || tgtNorm.includes(item.normText)) {
                    triggerClick(item.element);
                    return { status: "clicked", text: item.text, method: "direct" };
                }
            }
        }

        // 2. Match por tokens
        if (primeiroNome && primeiroNome.length >= 2) {
            var pNorm = norm(primeiroNome);
            var fnMatches = [];
            for (var j = 0; j < visibleItems.length; j++) {
                var item = visibleItems[j];
                if (item.normText.startsWith(pNorm) || item.normText.includes(pNorm)) {
                    fnMatches.push(item);
                }
            }
            
            if (fnMatches.length === 1) {
                triggerClick(fnMatches[0].element);
                return { status: "clicked", text: fnMatches[0].text, method: "single_fn" };
            } else if (fnMatches.length > 1) {
                var bestItem = null;
                var bestScore = 0;
                for (var k = 0; k < fnMatches.length; k++) {
                    var item = fnMatches[k];
                    var score = 0;
                    for (var tokIdx = 0; tokIdx < tokens.length; tokIdx++) {
                        var tkNorm = norm(tokens[tokIdx]);
                        if (tkNorm && item.normText.includes(tkNorm)) score++;
                    }
                    if (score > bestScore) {
                        bestScore = score;
                        bestItem = item;
                    }
                }
                if (bestItem && bestScore >= 1) {
                    triggerClick(bestItem.element);
                    return { status: "clicked", text: bestItem.text, method: "best_score" };
                }
            }
        }

        // 3. Fallback: se houver exatamente 1 opção visível na lista filtrada
        if (visibleItems.length === 1) {
            triggerClick(visibleItems[0].element);
            return { status: "clicked", text: visibleItems[0].text, method: "unique_filtered" };
        }

        return { status: "not_found", count: visibleItems.length };
    """

    js_abrir_e_preparar_anjun = """
        function findEntregadorComponents() {
            // 1. Procura por container com label Entregador ou Motorista
            var allLabels = document.querySelectorAll(".el-form-item__label, label, span, div");
            for (var i = 0; i < allLabels.length; i++) {
                var lbl = allLabels[i];
                var txt = (lbl.innerText || lbl.textContent || "").trim().toLowerCase();
                if (txt === 'entregador' || txt === 'entregador:' || txt === 'motorista' || txt === 'motorista:' || txt.includes('entregador') || txt.includes('motorista')) {
                    var formItem = lbl.closest ? (lbl.closest('.el-form-item') || lbl.closest('.filter-item') || lbl.parentElement) : lbl.parentElement;
                    if (formItem) {
                        var w = formItem.querySelector('.el-select__wrapper, .el-select, .select-trigger');
                        var inp = formItem.querySelector('input.el-select__input, input[role="combobox"], input.el-input__inner');
                        if (w || inp) {
                            return { wrapper: w || (inp ? inp.closest('.el-select__wrapper') || inp.parentElement : null), input: inp };
                        }
                    }
                }
            }

            // 2. Procura pelo input exato da imagem DevTools (el-select__input is-large)
            var isLargeInputs = document.querySelectorAll("input.el-select__input.is-large, input.el-select__input, input[role='combobox']");
            for (var j = 0; j < isLargeInputs.length; j++) {
                var el = isLargeInputs[j];
                if (el && (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0)) {
                    var wr = el.closest ? (el.closest('.el-select__wrapper') || el.closest('.el-select') || el.parentElement) : el.parentElement;
                    return { wrapper: wr, input: el };
                }
            }

            // 3. Fallback para qualquer .el-select__wrapper visível
            var wrappers = document.querySelectorAll(".el-select__wrapper, .el-select");
            for (var k = 0; k < wrappers.length; k++) {
                var wr2 = wrappers[k];
                if (wr2 && (wr2.offsetParent !== null || wr2.offsetWidth > 0 || wr2.offsetHeight > 0)) {
                    var inp2 = wr2.querySelector("input.el-select__input, input[role='combobox'], input");
                    return { wrapper: wr2, input: inp2 };
                }
            }

            return null;
        }

        var comp = findEntregadorComponents();
        if (!comp || (!comp.wrapper && !comp.input)) {
            return { status: "not_found" };
        }

        var wrapper = comp.wrapper || comp.input;
        var input = comp.input;

        // Se houver botão de limpar (X) de motorista anterior selecionado, clica para limpar
        try {
            var clearIcon = wrapper.querySelector(".el-select__clear, .el-icon.el-select__clear, .el-icon-circle-close");
            if (clearIcon && (clearIcon.offsetWidth > 0 || clearIcon.offsetHeight > 0 || clearIcon.offsetParent !== null)) {
                clearIcon.click();
            }
        } catch(e) {}

        // Rola até o elemento e clica no wrapper para expandir o combobox (aria-expanded="true")
        try { wrapper.scrollIntoView({ block: 'center', inline: 'center' }); } catch(e) {}
        try { wrapper.click(); } catch(e) {}
        try {
            wrapper.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            wrapper.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            wrapper.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        } catch(e) {}

        if (input) {
            try { input.focus(); } catch(e) {}
            try { input.click(); } catch(e) {}
        }

        return {
            status: "opened",
            expanded: input ? input.getAttribute("aria-expanded") : "unknown",
            hasInput: !!input
        };
    """

    js_digitar_e_disparar_anjun = """
        var termo = arguments[0];
        
        // Localiza o input do combobox ativo
        var input = document.activeElement;
        if (!input || input.tagName !== 'INPUT' || !input.classList.contains('el-select__input')) {
            input = document.querySelector("input.el-select__input.is-large, input.el-select__input, input[role='combobox']:focus");
        }
        if (!input) {
            input = document.querySelector("input.el-select__input.is-large, input.el-select__input, input[role='combobox']");
        }

        if (input) {
            try { input.focus(); } catch(e) {}

            // Injeta o valor via Native Setter (garante reatividade no Vue 3 / Element Plus)
            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
            if (nativeSetter && nativeSetter.set) {
                nativeSetter.set.call(input, termo);
            } else {
                input.value = termo;
            }

            // Dispara sequência completa de eventos que o Element Plus escuta para filtrar
            input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
            input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
            input.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true, cancelable: true, data: termo }));
            input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, cancelable: true, key: termo.slice(-1) }));

            return { status: "typed", value: input.value };
        }
        return { status: "no_input" };
    """

    for tentativa in range(1, 3):
        try:
            print(f"[*] Selecionando motorista na Anjun (Tentativa {tentativa}): '{mot_clean}' (Busca: '{termo_digitar}')...")
            # Garante que não há popups residuais
            fechar_possiveis_lembretes(driver)

            # 1. Abre o componente el-select de Entregador via JS clicando no wrapper e focando o input
            res_open = driver.execute_script(js_abrir_e_preparar_anjun)
            if res_open and res_open.get("status") == "not_found":
                raise Exception("Campo 'Entregador' não encontrado na tela da Aba 3.")

            time.sleep(0.12)

            # 2. FAST-PATH: Se a opção do motorista já estiver visível no dropdown aberto, clica imediatamente (~0.05s)!
            res_fast = driver.execute_script(js_buscar_e_clicar_anjun, targets, tokens, primeiro_nome)
            if res_fast and res_fast.get("status") == "clicked":
                nome_sel = res_fast.get("text", mot_clean)
                print(f"[+] [Fast-Path] Motorista Anjun selecionado instantaneamente: {nome_sel}")
                time.sleep(0.15)
                return True

            # 3. Digitação robusta no campo:
            # A) Injeta o termo via Native Prototype Setter e dispara os eventos 'input' e 'change' no Vue 3 / Element Plus
            driver.execute_script(js_digitar_e_disparar_anjun, termo_digitar)

            # B) Digitação nativa via Selenium ActionChains no elemento atualmente focado
            try:
                webdriver.ActionChains(driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.BACKSPACE).send_keys(termo_digitar).perform()
            except Exception:
                pass

            # C) Confirma eventos de input após digitação
            try:
                driver.execute_script(js_digitar_e_disparar_anjun, termo_digitar)
            except Exception:
                pass

            # 4. Polling dinâmico em JavaScript aguardando o dropdown filtrar (em ~50-200ms)
            t_inicio_poll = time.time()
            clicado = False
            nome_sel = None
            while time.time() - t_inicio_poll < 3.0:
                res = driver.execute_script(js_buscar_e_clicar_anjun, targets, tokens, primeiro_nome)
                if res and res.get("status") == "clicked":
                    clicado = True
                    nome_sel = res.get("text", mot_clean)
                    print(f"[+] Motorista Anjun selecionado com sucesso após filtro: {nome_sel} (método: {res.get('method')})")
                    break
                time.sleep(0.06)

            if clicado:
                time.sleep(0.15)
                return True
            else:
                raise Exception(f"Motorista '{mot_clean}' não encontrado nas opções do dropdown da Anjun.")

        except Exception as e_tent:
            print(f"[Aviso] Falha na tentativa {tentativa} de selecionar motorista '{mot_clean}': {str(e_tent)}")
            if tentativa == 1:
                fechar_possiveis_lembretes(driver)
                try:
                    fechar_popups_finalizacao_anjun(driver)
                except Exception:
                    pass
                time.sleep(0.2)
                continue
            else:
                raise Exception(f"Não foi possível selecionar o motorista '{mot_clean}' no site da Anjun: {str(e_tent)}. Verifique se o nome está idêntico ao cadastrado no site da Anjun.")

def registrar_lote_finalizado(motorista, quantidade, plataforma=None):
    global plataforma_ativa
    if not motorista:
        return
    try:
        plat = plataforma or plataforma_ativa
        plat_display = "Outros"
        if plat:
            plat_lower = plat.lower()
            if 'anjun' in plat_lower:
                plat_display = "Anjun"
            elif 'imile' in plat_lower:
                plat_display = "iMile"
            else:
                plat_display = plat.capitalize()
                
        conn = conectar_banco()
        cursor = conn.cursor()
        
        # Busca cidades do motorista
        cursor.execute("SELECT cidade FROM cidades WHERE motorista = ?", (motorista,))
        cidades_list = [row[0] for row in cursor.fetchall()]
        cidades_str = ", ".join(cidades_list) if cidades_list else "Sem Cidades"
        
        # Insere o lote
        cursor.execute(
            "INSERT INTO lotes_finalizados (motorista, cidades, quantidade, plataforma) VALUES (?, ?, ?, ?)",
            (motorista, cidades_str, quantidade, plat_display)
        )
        conn.commit()
        conn.close()
        print(f"[+] Lote finalizado registrado no banco: {motorista} | {cidades_str} | {quantidade} pacotes | Plat: {plat_display}")
    except Exception as e:
        print(f"[Erro] Falha ao registrar lote finalizado: {str(e)}")

@app.route('/atribuicao/finalizar', methods=['POST'])
@requer_licenca_ativa
def atribuicao_finalizar():
    global driver, aba_atribuicao_anjun, motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas, plataforma_ativa
    
    dados = request.json or {}
    motorista = dados.get("motorista") or motorista_atribuicao_ativa
    
    # Se for iMile, finaliza 100% de forma local no banco de dados e limpa o contador
    if plataforma_ativa == 'imile':
        contagem_lote = 0
        if motorista:
            contagem_lote = contagem_motoristas.get(motorista, 0)
            if contagem_lote == 0:
                contagem_lote = contagem_atribuicao_ativa
            registrar_lote_finalizado(motorista, contagem_lote, plataforma="imile")
            contagem_motoristas[motorista] = 0
        
        motorista_atribuicao_ativa = None
        contagem_atribuicao_ativa = 0
        print(f"[+] Lote iMile finalizado localmente no banco para {motorista} (Qtd: {contagem_lote}).")
        return jsonify({"status": "sucesso"})

    # Se for Loggi, realiza a finalização do grupo
    if plataforma_ativa == 'loggi':
        garantir_abas_loggi(driver)
        if not driver or not aba_atribuicao_anjun:
            return jsonify({"status": "erro", "mensagem": "Navegador de atribuição da Loggi não está ativo."}), 400
            
        driver_lock.acquire()
        try:
            driver.switch_to.window(aba_atribuicao_anjun)
            time.sleep(0.5)
            
            btn_move = driver.find_elements(By.XPATH, "//button[@data-testid='btn-move-packages-to-group']")
            btn_continue = driver.find_elements(By.XPATH, "//button[@data-testid='btn-set-keywords']")
            
            finalizou = False
            if btn_move and btn_move[0].is_displayed():
                # Grupo existente: clica em Mover
                driver.execute_script("arguments[0].click();", btn_move[0])
                print("[+] Lote Loggi finalizado com sucesso (Mover pacotes para o grupo)!")
                finalizou = True
                time.sleep(1.0)
            elif btn_continue and btn_continue[0].is_displayed():
                # Novo grupo: clica em Continuar
                driver.execute_script("arguments[0].click();", btn_continue[0])
                print("[*] Botão Continuar clicado. Aguardando a tela de palavras-chave...")
                time.sleep(0.8)
                
                # Digita a palavra-chave (motorista/cidade ativa em uppercase + dia/mês atual)
                data_atual = datetime.datetime.now().strftime('%d/%m')
                palavra_chave = f"{motorista.upper()} {data_atual}" if motorista else f"GRUPO {data_atual}"
                try:
                    # Espera dinamicamente a tela de palavra-chave carregar (máx 5s)
                    campo_palavra = None
                    candidatos_palavra = [
                        "//*[contains(text(), 'identificar o grupo')]/following::input[1]",
                        "//*[contains(text(), 'Palavras-chave')]/following::input[1]",
                        "//*[contains(text(), 'Adicione')]/preceding::input[1]",
                        "//input[contains(@id, '_r_')]",
                        "//input[@type='text' and not(contains(@placeholder, 'Buscar'))]"
                    ]
                    for path_kw in candidatos_palavra:
                        try:
                            el = WebDriverWait(driver, 1.5).until(
                                EC.visibility_of_element_located((By.XPATH, path_kw))
                            )
                            if el:
                                campo_palavra = el
                                break
                        except Exception:
                            continue
                            
                    if not campo_palavra:
                        raise Exception("Não foi possível localizar o campo de input de palavra-chave na tela.")
                            
                    campo_palavra.click()
                    campo_palavra.send_keys(Keys.CONTROL + "a")
                    campo_palavra.send_keys(Keys.BACKSPACE)
                    time.sleep(0.1)
                    campo_palavra.send_keys(palavra_chave + Keys.ENTER)
                    print(f"[+] Palavra-chave '{palavra_chave}' inserida com sucesso!")
                    time.sleep(0.5)
                    
                    # Clica em Agrupar pacotes no rodapé
                    btn_agrupar_final = driver.find_element(By.XPATH, "//button[@data-testid='btn-move-packages-to-group']")
                    driver.execute_script("arguments[0].click();", btn_agrupar_final)
                    print("[+] Lote Loggi finalizado com sucesso (Criar grupo e agrupar)!")
                    finalizou = True
                    time.sleep(1.5)
                    
                    # Clica no botão X (closed-drawer) para fechar a gaveta do grupo criado
                    try:
                        btn_close_drawer = WebDriverWait(driver, 3.0).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='closed-drawer']"))
                        )
                        driver.execute_script("arguments[0].click();", btn_close_drawer)
                        print("[+] Botão Fechar Gaveta (closed-drawer) clicado com sucesso!")
                        time.sleep(0.5)
                    except Exception as e_close:
                        print(f"[Aviso] Não foi possível clicar no botão de fechar gaveta: {str(e_close)}")
                except Exception as e_kw:
                    print(f"[Erro] Falha ao inserir palavra-chave ou agrupar novo lote Loggi: {str(e_kw)}")
            
            # Clica no botão Atualizar (async-refresh-btn) se finalizou
            if finalizou:
                try:
                    btn_refresh = driver.find_element(By.XPATH, "//button[@data-testid='async-refresh-btn']")
                    driver.execute_script("arguments[0].click();", btn_refresh)
                    print("[+] Botão Atualizar (async-refresh-btn) clicado com sucesso após finalização!")
                    time.sleep(0.8)
                except Exception as e_ref:
                    print(f"[Aviso] Falha ao clicar no botão de atualizar após finalizar lote Loggi: {str(e_ref)}")
                
            contagem_lote = 0
            if motorista:
                contagem_lote = contagem_motoristas.get(motorista, 0)
                if contagem_lote == 0:
                    contagem_lote = contagem_atribuicao_ativa
                    
            if motorista:
                registrar_lote_finalizado(motorista, contagem_lote, plataforma="loggi")
                contagem_motoristas[motorista] = 0
                
            motorista_atribuicao_ativa = None
            contagem_atribuicao_ativa = 0
            return jsonify({"status": "sucesso"})
        except Exception as e:
            print(f"[Erro] Falha ao finalizar lote Loggi: {str(e)}")
            return jsonify({"status": "erro", "mensagem": str(e)}), 500
        finally:
            driver_lock.release()

    # Para Anjun e outras plataformas, realiza a finalização física no site via Selenium
    if not driver or not aba_atribuicao_anjun:
        return jsonify({"status": "erro", "mensagem": "Navegador de atribuição não está ativo."}), 400
        
    driver_lock.acquire()
    try:
        driver.switch_to.window(aba_atribuicao_anjun)
        fechar_possiveis_lembretes(driver)
        
        # Tenta ler a contagem real do site antes de finalizar o lote
        contagem_lote = 0
        if motorista:
            try:
                xpath_contagem = [
                    "//span[contains(@class, 'hasScan')]//i",
                    "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[2]/span/i"
                ]
                for xp in xpath_contagem:
                    try:
                        el_cont = driver.find_element(By.XPATH, xp)
                        if el_cont.is_displayed():
                            val_str = el_cont.text.strip()
                            if val_str.isdigit():
                                contagem_lote = int(val_str)
                                print(f"[+] Contagem lida do site para {motorista} antes de finalizar: {contagem_lote}")
                                break
                    except Exception:
                        continue
            except Exception:
                pass
                
            if contagem_lote == 0:
                contagem_lote = contagem_motoristas.get(motorista, 0)
                if contagem_lote == 0:
                    contagem_lote = contagem_atribuicao_ativa
        
        print(f"[*] Finalizando lote do motorista: {motorista} (Qtd: {contagem_lote})...")
        candidatos_finalizar = [
            "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[1]/button[1]",
            "//button[contains(., 'Finalizar') or contains(., 'Concluir') or contains(., 'Gerar') or contains(., 'Emitir') or contains(., 'Emissão') or contains(., 'Tarefa')]",
            "//button[contains(@class, 'el-button--primary')]"
        ]
        finalizou = False
        for xpath in candidatos_finalizar:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    print("[+] Lote finalizado com sucesso!")
                    time.sleep(1.0)
                    fechar_popups_finalizacao_anjun(driver)
                    finalizou = True
                    break
            except Exception:
                continue
                
        if not finalizou:
            print("[Aviso] Botão de finalizar não pôde ser clicado ou não foi encontrado.")
            
        if motorista:
            registrar_lote_finalizado(motorista, contagem_lote)
            contagem_motoristas[motorista] = 0
            
        motorista_atribuicao_ativa = None
        contagem_atribuicao_ativa = 0
        return jsonify({"status": "sucesso"})
    except Exception as e:
        print(f"[Erro] Falha ao finalizar lote: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        driver_lock.release()

@app.route('/salvar-cidades', methods=['POST'])
def salvar_cidades():
    dados = request.json
    cidades = dados.get("cidades")
    
    if not isinstance(cidades, list):
        return jsonify({"status": "erro", "mensagem": "Formato de cidades inválido."}), 400
        
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cidades")
        for c in cidades:
            cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (c,))
        conn.commit()
        conn.close()
        
        # Sincroniza com o arquivo JSON legado para evitar perda de dados na inicialização
        try:
            with open(CONFIG_CIDADES, 'w', encoding='utf-8') as f:
                json.dump(cidades, f, indent=4, ensure_ascii=False)
            print("[Banco] config_cidades.json sincronizado com sucesso!")
        except Exception as e_json:
            print(f"[Aviso] Falha ao gravar no config_cidades.json: {str(e_json)}")
            
        return jsonify({"status": "sucesso", "mensagem": "Lista de cidades salva com sucesso!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/salvar-plataforma', methods=['POST'])
def salvar_plataforma():
    dados = request.json
    p_id = dados.get("id", "").strip().lower()
    p_nome = dados.get("nome", "").strip()
    
    if not p_id or not p_nome:
        return jsonify({"status": "erro", "mensagem": "ID e Nome são obrigatórios."}), 400
        
    plataformas = carregar_plataformas()
    plataformas[p_id] = {
        "id": p_id,
        "nome": p_nome,
        "recebimento_url": dados.get("recebimento_url", "").strip(),
        "recebimento_input_xpath": dados.get("recebimento_input_xpath", "").strip(),
        "recebimento_dados_xpath": dados.get("recebimento_dados_xpath", "").strip(),
        "atribuicao_url": dados.get("atribuicao_url", "").strip(),
        "atribuicao_motorista_xpath": dados.get("atribuicao_motorista_xpath", "").strip(),
        "atribuicao_bip_xpath": dados.get("atribuicao_bip_xpath", "").strip(),
        "login_usuario": dados.get("login_usuario", "").strip(),
        "login_senha": dados.get("login_senha", "").strip()
    }
    
    with open(CONFIG_PLATAFORMAS, 'w', encoding='utf-8') as f:
        json.dump(plataformas, f, indent=4, ensure_ascii=False)
    global _cache_plataformas
    _cache_plataformas = None
        
    return jsonify({"status": "sucesso", "mensagem": f"Plataforma '{p_nome}' salva com sucesso!"})

@app.route('/salvar-credenciais', methods=['POST'])
def salvar_credenciais():
    dados = request.json
    p_id = dados.get("id", "").strip().lower()
    usuario = dados.get("login_usuario", "").strip()
    senha = dados.get("login_senha", "").strip()
    
    if not p_id:
        return jsonify({"status": "erro", "mensagem": "ID da plataforma é obrigatório."}), 400
        
    plataformas = carregar_plataformas()
    if p_id not in plataformas:
        return jsonify({"status": "erro", "mensagem": "Plataforma não encontrada."}), 400
        
    # Salva na estrutura de credenciais locais
    cred_locais = {}
    if os.path.exists(CONFIG_LOCAL_CREDENTIALS):
        try:
            with open(CONFIG_LOCAL_CREDENTIALS, 'r', encoding='utf-8') as f:
                cred_locais = json.load(f)
        except Exception:
            pass
            
    if p_id not in cred_locais:
        cred_locais[p_id] = {}
        
    cred_locais[p_id]["login_usuario"] = usuario
    cred_locais[p_id]["login_senha"] = senha
    
    try:
        with open(CONFIG_LOCAL_CREDENTIALS, 'w', encoding='utf-8') as f:
            json.dump(cred_locais, f, indent=4, ensure_ascii=False)
        global _cache_plataformas
        _cache_plataformas = None
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Falha ao salvar arquivo de credenciais: {str(e)}"}), 500
        
    return jsonify({"status": "sucesso", "mensagem": "Credenciais salvas localmente com sucesso!"})

@app.route('/deletar-plataforma', methods=['POST'])
def deletar_plataforma():
    dados = request.json
    p_id = dados.get("id", "").strip().lower()
    
    plataformas = carregar_plataformas()
    if p_id in plataformas:
        # Se for a plataforma atualmente rodando no Selenium, encerra o browser
        global plataforma_ativa
        if plataforma_ativa == p_id:
            fechar_selenium()
            
        nome_removido = plataformas[p_id]['nome']
        del plataformas[p_id]
        
        with open(CONFIG_PLATAFORMAS, 'w', encoding='utf-8') as f:
            json.dump(plataformas, f, indent=4, ensure_ascii=False)
        global _cache_plataformas
        _cache_plataformas = None
            
        return jsonify({"status": "sucesso", "mensagem": f"Plataforma '{nome_removido}' excluída com sucesso."})
    return jsonify({"status": "erro", "mensagem": "Plataforma não encontrada."}), 404

@app.route('/selecionar-plataforma', methods=['POST'])
@requer_licenca_ativa
def selecionar_plataforma():
    dados = request.json
    p_id = dados.get("id", "").strip().lower()
    
    try:
        inicializar_selenium(p_id)
        if p_id == 'anjun':
            fechar_avisos_todas_abas_anjun(driver)
        return jsonify({"status": "sucesso", "mensagem": f"Browser inicializado para a plataforma {p_id}."})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/salvar-motoristas', methods=['POST'])
def salvar_motoristas():
    dados = request.json
    motoristas = dados.get("motoristas")
    plat_id = dados.get("plataforma")
    
    if not plat_id:
        plat_id = plataforma_ativa if plataforma_ativa else "anjun"
        
    lista_mapeamentos = []
    if isinstance(motoristas, list):
        for item in motoristas:
            if isinstance(item, dict):
                c = (item.get("cidade") or "").strip()
                m = (item.get("motorista") or "").strip()
                if c and m:
                    lista_mapeamentos.append((c, m))
    elif isinstance(motoristas, dict):
        for c, m in motoristas.items():
            c_clean = str(c).strip()
            if isinstance(m, list):
                for sub_m in m:
                    sub_m_clean = str(sub_m).strip()
                    if c_clean and sub_m_clean:
                        lista_mapeamentos.append((c_clean, sub_m_clean))
            else:
                m_clean = str(m).strip()
                if c_clean and m_clean:
                    lista_mapeamentos.append((c_clean, m_clean))
    else:
        return jsonify({"status": "erro", "mensagem": "Formato de motoristas inválido."}), 400
        
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        
        # 1. Atualiza na tabela multiplataforma
        cursor.execute("DELETE FROM motoristas_plataforma WHERE plataforma = ?", (plat_id,))
        for cid, mot in lista_mapeamentos:
            cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista) VALUES (?, ?, ?)", (cid, plat_id, mot))
            
        # 2. Se for a Anjun (ou se não houver plataforma ativa), mantém a tabela antiga sincronizada
        if plat_id == 'anjun':
            cursor.execute("DELETE FROM motoristas")
            for cid, mot in lista_mapeamentos:
                cursor.execute("INSERT OR IGNORE INTO motoristas (cidade, motorista) VALUES (?, ?)", (cid, mot))
                
        conn.commit()
        conn.close()
        
        # Sincroniza com o arquivo JSON no novo formato multi-plataforma com suporte a múltiplos motoristas
        try:
            conn_json = conectar_banco()
            cursor_json = conn_json.cursor()
            cursor_json.execute("SELECT cidade, plataforma, motorista FROM motoristas_plataforma ORDER BY plataforma, cidade, motorista")
            rows_json = cursor_json.fetchall()
            conn_json.close()
            
            mapeamento_completo = {}
            for r_json in rows_json:
                cid = r_json[0]
                plat = r_json[1]
                mot = r_json[2]
                if plat not in mapeamento_completo:
                    mapeamento_completo[plat] = []
                mapeamento_completo[plat].append({"cidade": cid, "motorista": mot})
                
            with open(CONFIG_MOTORISTAS, 'w', encoding='utf-8') as f:
                json.dump(mapeamento_completo, f, indent=4, ensure_ascii=False)
            print("[Banco] config_motoristas.json sincronizado com sucesso!")
        except Exception as e_json:
            print(f"[Aviso] Falha ao gravar no config_motoristas.json: {str(e_json)}")
            
        return jsonify({"status": "sucesso", "mensagem": f"Mapeamento de motoristas para a plataforma '{plat_id}' salvo com sucesso!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/motoristas/status-excel', methods=['GET'])
def rota_status_motoristas_excel():
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_MOTORISTAS)
        existe = os.path.exists(excel_path)
        info = {
            "existe": existe,
            "arquivo": EXCEL_MOTORISTAS,
            "caminho": excel_path,
            "tamanho_bytes": os.path.getsize(excel_path) if existe else 0,
            "modificado_em": datetime.datetime.fromtimestamp(os.path.getmtime(excel_path)).strftime('%d/%m/%Y %H:%M:%S') if existe else None
        }
        return jsonify({"status": "sucesso", "dados": info})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/motoristas/exportar-excel', methods=['GET'])
def rota_exportar_motoristas_excel():
    try:
        excel_path = gerar_planilha_motoristas_excel()
        if os.path.exists(excel_path):
            return send_file(excel_path, as_attachment=True, download_name=EXCEL_MOTORISTAS)
        return jsonify({"status": "erro", "mensagem": "Arquivo não encontrado."}), 404
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/motoristas/sincronizar-excel', methods=['POST'])
def rota_sincronizar_motoristas_excel():
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_MOTORISTAS)
        ok, c_qtd, m_qtd, msg = sincronizar_motoristas_excel(excel_path)
        if ok:
            try:
                mtime = os.path.getmtime(excel_path)
                meta_mtime_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.excel_sync_meta')
                with open(meta_mtime_file, 'w') as f_meta:
                    f_meta.write(str(mtime))
            except Exception:
                pass
            return jsonify({
                "status": "sucesso",
                "mensagem": msg,
                "cidades": c_qtd,
                "mapeamentos": m_qtd
            })
        else:
            return jsonify({"status": "erro", "mensagem": msg}), 400
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/motoristas/importar-excel', methods=['POST'])
def rota_importar_motoristas_excel():
    try:
        if 'planilha' not in request.files and 'file' not in request.files:
            return jsonify({"status": "erro", "mensagem": "Nenhum arquivo enviado. Selecione um arquivo .xlsx."}), 400
        
        file = request.files.get('planilha') or request.files.get('file')
        if not file or file.filename == '':
            return jsonify({"status": "erro", "mensagem": "Nome de arquivo inválido."}), 400
            
        if not (file.filename.lower().endswith('.xlsx') or file.filename.lower().endswith('.xls')):
            return jsonify({"status": "erro", "mensagem": "O arquivo deve estar no formato Excel (.xlsx)."}), 400
            
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), EXCEL_MOTORISTAS)
        file.save(excel_path)
        
        ok, c_qtd, m_qtd, msg = sincronizar_motoristas_excel(excel_path)
        if ok:
            try:
                mtime = os.path.getmtime(excel_path)
                meta_mtime_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.excel_sync_meta')
                with open(meta_mtime_file, 'w') as f_meta:
                    f_meta.write(str(mtime))
            except Exception:
                pass
            return jsonify({
                "status": "sucesso",
                "mensagem": f"Planilha importada e sincronizada com sucesso! {c_qtd} cidades e {m_qtd} mapeamentos atualizados.",
                "cidades": c_qtd,
                "mapeamentos": m_qtd
            })
        else:
            return jsonify({"status": "erro", "mensagem": msg}), 400
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/reiniciar-sistema', methods=['POST'])
def rota_reiniciar_sistema():
    print("\n" + "=" * 60)
    print(" [*] COMANDO DE REINICIALIZAÇÃO DO SISTEMA RECEBIDO DO PAINEL!")
    print("=" * 60)

    def executar_reinicio():
        time.sleep(0.6)  # Aguarda envio da resposta HTTP ao navegador
        
        # 1. Encerra o Selenium e o Chrome com segurança
        try:
            print("[*] Encerrando navegador Chrome e limpando tarefas...")
            fechar_selenium()
        except Exception as e_sel:
            print(f"[Aviso] Erro ao fechar Selenium: {str(e_sel)}")

        # 2. Mata processos residuais de chromedriver
        try:
            import subprocess
            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        # 3. Se o script estiver rodando dentro do loop do start_server.bat, sai com código 42
        if os.environ.get("GS_LOOP_ACTIVE") == "1":
            print("[*] Reiniciando via loop do CMD (código 42)...")
            os._exit(42)
        else:
            print("[*] Loop do CMD não detectado. Finalizando processo Python para reinicialização limpa pelo Electron...")
            os._exit(0)

    import threading
    threading.Thread(target=executar_reinicio, daemon=True).start()
    return jsonify({"status": "sucesso", "mensagem": "Sistema reiniciando..."})

@app.route('/bip', methods=['POST'])
@requer_licenca_ativa
def processar_bip():
    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, motorista_atribuicao_ativa, contagem_atribuicao_ativa, alertas_gerencia, modo_consulta, contagem_motoristas, ultimo_motorista_bipado, primeiro_bip_validado, total_bipes_processados
    
    tempo_inicio = time.time()
    dados = request.json
    codigo_qr = dados.get("codigo", "").strip()
    p_id = dados.get("plataforma", "").strip().lower()
    motorista_lote = dados.get("motorista")
    cidades_selecionadas = dados.get("cidades_selecionadas") or []
    if not isinstance(cidades_selecionadas, list):
        cidades_selecionadas = [cidades_selecionadas]
    cidades_selecionadas = [str(c).strip() for c in cidades_selecionadas if str(c).strip()]
    if not cidades_selecionadas and motorista_lote:
        cidades_selecionadas = [motorista_lote.strip()]
    if not motorista_lote and cidades_selecionadas:
        motorista_lote = cidades_selecionadas[0]
    pacote_solto = bool(dados.get("pacote_solto", False))
    
    # Inicializa variáveis auxiliares de logs para evitar UnboundLocalError nos tratamentos de exceções
    recebedor = "---"
    telefone = "---"
    email = "---"
    tempo_criacao = "---"
    status_pacote = "---"
    negocios = "---"
    valor_declarado = "---"
    bairro = "---"
    cidade_detectada = None
    contagem_site = None
    
    # Validação do primeiro bipe para novos motoristas mesmo em modo sem consulta
    deve_consultar_este_bip = modo_consulta
    if motorista_lote and motorista_lote not in ["", "---", "Apenas Entrada (Sem Atribuição)"]:
        if motorista_lote != ultimo_motorista_bipado:
            print(f"[*] Mudança de motorista detectada na triagem: {ultimo_motorista_bipado} -> {motorista_lote}. Forçando consulta no primeiro bip para validação de segurança.")
            ultimo_motorista_bipado = motorista_lote
            primeiro_bip_validado = False
            
        if not primeiro_bip_validado:
            deve_consultar_este_bip = True
        else:
            # Após o primeiro bip do motorista ser validado com sucesso, não consulta a aba 2 (aceleração máxima)
            deve_consultar_este_bip = False
            
    if p_id in ['loggi', 'imile', 'anjun'] or 'imile' in p_id or 'anjun' in p_id:
        deve_consultar_este_bip = False
    
    if not codigo_qr:
        return jsonify({"status": "erro", "mensagem": "Código vazio"}), 400
    if not p_id:
        return jsonify({"status": "erro", "mensagem": "Plataforma ativa não especificada"}), 400
        
    pacote_duplicado = False
    cidade_duplicada = None
    motorista_anterior = None
    timestamp_anterior = None
    import datetime
    limite_data = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
    
    # --- VERIFICAÇÃO DE DUPLICADOS (ÚLTIMOS 30 DIAS) ---
    try:
        conn_dup = conectar_banco()
        cursor_dup = conn_dup.cursor()
        cursor_dup.execute('''
            SELECT timestamp, motorista, cidade FROM historico
            WHERE codigo = ? AND status = 'OK' AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (codigo_qr, limite_data))
        res_dup = cursor_dup.fetchone()
        conn_dup.close()
        
        if res_dup:
            timestamp_raw, mot_dup, cid_dup = res_dup
            try:
                dt_obj = datetime.datetime.fromisoformat(timestamp_raw)
                dt_str = dt_obj.strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                dt_str = timestamp_raw
                
            print(f"[!] PACOTE DUPLICADO DETECTADO: {codigo_qr} (Bipado em {dt_str} para {mot_dup}). Prosseguindo para reatribuição...")
            salvar_entrada_historico(codigo_qr, p_id, cid_dup, mot_dup, "DUPLICADO")
            
            # Envia alerta em tempo real para a gerência
            alertas_gerencia.append({
                "id": str(time.time()),
                "tipo": "DUPLICADO",
                "codigo": codigo_qr,
                "motorista": mot_dup,
                "cidade": cid_dup,
                "timestamp": dt_str
            })
            
            pacote_duplicado = True
            cidade_duplicada = cid_dup
            cidade_detectada = cid_dup
            motorista_anterior = mot_dup
            timestamp_anterior = dt_str
    except Exception as e_dup:
        print(f"[Erro] Falha ao verificar duplicados no banco: {str(e_dup)}")
        
    if pacote_duplicado:
        print(f"[!] PACOTE DUPLICADO: {codigo_qr} (Bipado anteriormente para {motorista_anterior} em {timestamp_anterior}). Executando fluxo completo novamente no site (Entrada + Atribuição)...")
            
    driver_lock.acquire()
    try:
        # Se o navegador não estiver aberto para esta plataforma, verifica confirmação de motorista
        confirmado_reabertura = dados.get("confirmado_reabertura", False)
        tem_motorista = bool(motorista_lote and str(motorista_lote).strip() not in ["", "---", "Apenas Entrada (Sem Atribuição)"])
        if not is_driver_ativo() or plataforma_ativa != p_id:
            if (p_id in ['anjun', 'imile', 'loggi']) and tem_motorista and not confirmado_reabertura:
                print(f"[!] Chrome fechado detectado com motorista/destino ({motorista_lote}) para {p_id}. Solicitando confirmação do operador...")
                return jsonify({
                    "status": "chrome_fechado",
                    "mensagem": "O navegador Chrome está fechado. Confirme se o motorista está correto para continuar.",
                    "motorista": motorista_lote,
                    "plataforma": p_id
                }), 200

            try:
                inicializar_selenium(p_id)
            except Exception as e:
                return jsonify({"status": "erro", "mensagem": f"Erro ao iniciar navegador: {str(e)}"}), 500
                
        # Carrega configurações do Xpath do arquivo
        plataformas = carregar_plataformas()
        config = plataformas.get(p_id)
        if not config:
            return jsonify({"status": "erro", "mensagem": "Configurações da plataforma ausentes."}), 400
        # --- ETAPA 1: RECEBIMENTO (ENTRADA NO GALPÃO) ---
        print("\n" + "="*50)
        print(f"[*] INICIANDO TRIAÇÃO DO PACOTE: {codigo_qr}")
        print("="*50)
        
        if p_id == 'loggi':
            aba_recebimento_valida = bool(aba_recebimento and aba_recebimento in driver.window_handles)
            if not aba_recebimento_valida:
                print("[*] Aba 1 Loggi inválida ou ausente. Escaneando handles...")
                garantir_abas_loggi(driver)
                if aba_recebimento and aba_recebimento in driver.window_handles:
                    aba_recebimento_valida = True
            
            if not aba_recebimento_valida:
                aba_recebimento = None
                for handle in driver.window_handles:
                    try:
                        driver.switch_to.window(handle)
                        url_atual = driver.current_url.lower()
                        if "colecoes" in url_atual:
                            tem_rec = False
                            for xp in ["//input[@placeholder='Bipe para receber pacotes e sacas']", "//input[contains(@placeholder, 'Bipe para receber')]"]:
                                try:
                                    if driver.find_element(By.XPATH, xp).is_displayed():
                                        tem_rec = True
                                        break
                                except Exception:
                                    pass
                            if tem_rec:
                                aba_recebimento = handle
                                aba_recebimento_valida = True
                                print(f"[+] Aba 1 Loggi (Recebimento) identificada dinamicamente: {handle}")
                                break
                    except Exception:
                        continue
                        
            # Se não achou nenhuma aba 1 válida com o campo aberto, mas achou uma aba com 'colecoes' ou 'acompanhamento':
            if not aba_recebimento_valida:
                print("[*] Não encontramos nenhuma aba de Recebimento ativa. Tentando recuperar...")
                for handle in driver.window_handles:
                    try:
                        driver.switch_to.window(handle)
                        url_atual = driver.current_url.lower()
                        if "colecoes" in url_atual or "acompanhamento" in url_atual:
                            print(f"[*] Recuperando aba 1 no handle {handle} navegando para a URL de recebimento...")
                            driver.get(config['recebimento_url'])
                            time.sleep(1.0)
                            aba_recebimento = handle
                            aba_recebimento_valida = True
                            break
                    except Exception:
                        continue
                        
            print("[*] Mudando para a aba 1 (Recebimento Loggi)...")
            mudar_aba_acelerado(driver, aba_recebimento)
            
            print("[*] Localizando campo de input de entrada no galpão Loggi via HTML...")
            campo_rec = obter_input_loggi_html(driver, modo='recebimento')
            if not campo_rec:
                raise Exception("Não foi possível encontrar o campo de bipe da Loggi. Verifique se a aba de recebimento (colecoes) está aberta.")
                
            print(f"[*] Enviando bipe do pacote Loggi na Aba 1: {codigo_qr}...")
            enviar_bipe_loggi_html(driver, campo_rec, codigo_qr, modo='recebimento')
            
            # --- VERIFICAÇÃO DE CONFIRMAÇÃO DA LOGGI ---
            confirmado = False
            inicio_wait_toast = time.time()
            js_toast_loggi = """
                // 1. Botão de confirmação modal (ex: 'Beleza')
                const btns = Array.from(document.querySelectorAll("button")).filter(b => b.offsetParent !== null && (b.innerText || '').includes("Beleza"));
                if (btns.length > 0) {
                    try { btns[0].click(); } catch(e){}
                    return { status: 'confirmado', motivo: 'beleza' };
                }
                
                // 2. Alertas e toasts do Material UI / Loggi
                const toasts = document.querySelectorAll(".MuiAlert-message, .MuiSnackbar-root, [role='alert'], .toast, div[class*='alert'], div[class*='toast'], div[class*='notification']");
                for (var t = 0; t < toasts.length; t++) {
                    var elT = toasts[t];
                    if (elT && (elT.offsetWidth > 0 || elT.offsetHeight > 0 || elT.offsetParent !== null)) {
                        var tTxt = (elT.innerText || elT.textContent || '').trim().toLowerCase();
                        if (tTxt.includes("sucesso") || tTxt.includes("recebid") || tTxt.includes("bipad") || tTxt.includes("pronto") || tTxt.includes("adicionad")) {
                            return { status: 'confirmado', motivo: 'toast_sucesso' };
                        }
                    }
                }

                // 3. Texto geral da tela
                const bodyTxt = document.body.innerText || "";
                if (bodyTxt.includes("Pronto!") || bodyTxt.includes("bipada") || bodyTxt.includes("bipado") || bodyTxt.includes("recebido com sucesso")) {
                    return { status: 'confirmado', motivo: 'texto' };
                }
                
                return { status: 'esperando' };
            """
            while time.time() - inicio_wait_toast < 4.0:
                try:
                    res_toast = driver.execute_script(js_toast_loggi)
                    if res_toast and res_toast.get("status") == "confirmado":
                        confirmado = True
                        print(f"[+] Confirmação da Loggi detectada ({res_toast.get('motivo')})!")
                        break
                except Exception:
                    pass
                time.sleep(0.1)
                
            if not confirmado:
                # Verifica se o campo foi limpo pelo site da Loggi (sinal claro de envio processado)
                try:
                    val_pos = campo_rec.get_attribute('value')
                    if not val_pos or val_pos == '':
                        confirmado = True
                        print("[+] Loggi: Campo de bipe foi limpo pelo site, indicando recebimento processado!")
                except Exception:
                    pass
                    
            if not confirmado:
                if pacote_duplicado:
                    print(f"[*] Loggi: Pacote duplicado {codigo_qr} pode já ter recebimento prévio. Prosseguindo para atribuição...")
                else:
                    raise Exception("Código inválido para recebimento no site da Loggi (a mensagem de confirmação não apareceu). Tente ler outro código da etiqueta!")
            
        elif (p_id == 'imile' or 'imile' in config['recebimento_url'].lower()):
            garantir_abas_imile(driver)

            def bipar_descarregamento_imile():
                global aba_descarregamento
                garantir_abas_imile(driver)
                if not aba_descarregamento:
                    print("[Aviso] Aba de Descarregamento (dsOffloadingScan) iMile não encontrada.")
                    return
                print("[*] Mudando para a Aba 2 (Descarregamento - dsOffloadingScan) iMile...")
                mudar_aba_acelerado(driver, aba_descarregamento, delay=0.12)
                fechar_modais_imile(driver)
                
                # Localiza o input diretamente com tolerância a renderização e auto-start
                campo_desc = obter_input_imile_html(driver, timeout=2.0)
                if campo_desc:
                    print(f"[*] Enviando bipe do pacote na aba Descarregamento iMile: {codigo_qr}...")
                    sucesso_desc = enviar_bipe_imile_html(driver, campo_desc, codigo_qr)
                    if sucesso_desc:
                        print(f"[+] Bipe enviado na Aba 2 (Descarregamento) com sucesso!")
                    else:
                        print("[Aviso] Falha ao confirmar envio na Aba 2 (Descarregamento).")
                else:
                    print("[Aviso] Campo de input de descarregamento não encontrado na Aba 2.")

            def bipar_entrada_imile():
                global aba_recebimento
                garantir_abas_imile(driver)
                if not aba_recebimento:
                    print("[Aviso] Aba de Entrada (ArrivalScan) iMile não encontrada.")
                    return
                print("[*] Mudando para a Aba 1 (Entrada no Galpão - ArrivalScan) iMile...")
                mudar_aba_acelerado(driver, aba_recebimento, delay=0.12)
                fechar_modais_imile(driver)
                
                print("[*] Localizando campo de input de entrada no galpão iMile por HTML...")
                campo_rec = obter_input_imile_html(driver, timeout=2.0)
                if campo_rec:
                    print(f"[*] Enviando bipe do pacote iMile na Aba 1: {codigo_qr}...")
                    sucesso_rec = enviar_bipe_imile_html(driver, campo_rec, codigo_qr)
                    if sucesso_rec:
                        print(f"[+] Bipe enviado na Aba 1 (Entrada) com sucesso!")
                    else:
                        print("[Aviso] Falha ao confirmar envio na Aba 1 (Entrada).")
                else:
                    print("[Aviso] Campo de input de entrada iMile não encontrado na Aba 1.")

            if pacote_solto:
                print("[*] [iMile] Modo PACOTE SOLTO ativo! Executando: 1º Aba 2 (Descarregamento) -> 2º Aba 1 (Entrada)...")
                bipar_descarregamento_imile()
                bipar_entrada_imile()
            else:
                print("[*] [iMile] Modo PADRÃO (Saca) ativo! Executando apenas: Aba 1 (Entrada)...")
                bipar_entrada_imile()
        else:
            print("[*] Mudando para a aba 1 (Entrada no Galpão/Recebimento)...")
            mudar_aba_acelerado(driver, aba_recebimento)
            is_anjun = ("anjun" in p_id or "anjun" in config.get('recebimento_url', '').lower())
            
            print("[*] Localizando campo de input de entrada no galpão...")
            if is_anjun:
                campo_rec = obter_input_anjun_html(driver)
                if not campo_rec:
                    campo_rec = obter_input_recebimento(driver, config.get('recebimento_input_xpath'))
                print(f"[*] Enviando bipe do pacote Anjun na Aba 1: {codigo_qr}...")
                enviar_bipe_anjun_html(driver, campo_rec, codigo_qr)
            else:
                campo_rec = obter_input_recebimento(driver, config['recebimento_input_xpath'])
                campo_rec.click()
                campo_rec.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, codigo_qr + Keys.ENTER)
            
            # Envio na Aba 1 da Anjun: aguarda o pacote aparecer na tabela inferior e clica em 'Enviar'
            if is_anjun:
                print(f"[*] [Anjun] Aguardando pacote {codigo_qr} aparecer na tabela inferior (Aba 1)...")
                alerta_texto = None
                enviado_com_sucesso = False
                pacote_ja_recepcionado_aba1 = False
                inicio_wait = time.time()
                re_disparado = False
                
                script_anjun_aba1 = """
                    var cleanQr = (arguments[0] || '').trim().toLowerCase();
                    
                    function getFatalError() {
                        var alertElems = document.querySelectorAll(".el-message--error, .el-notification--error, .el-message-box__content, .error-message");
                        for (var j = 0; j < alertElems.length; j++) {
                            var el = alertElems[j];
                            if (el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.offsetParent !== null)) {
                                var msg = (el.innerText || el.textContent || '').trim();
                                if (msg && !msg.toLowerCase().includes("sucesso") && !msg.toLowerCase().includes("enviado")) {
                                    var msgLow = msg.toLowerCase();
                                    if (msgLow.includes("já escaneado") || msgLow.includes("já bipado") || msgLow.includes("já recepcionado") || msgLow.includes("duplicad")) {
                                        return { tipo: "duplicado", texto: msg };
                                    }
                                    // AVISOS DE TIMEOUT DE GATEWAY DA ANJUN SÃO IGNORADOS AQUI (NÃO SÃO ERROS FATAIS)
                                    if (msgLow.includes("网关超时") || msgLow.includes("gateway") || msgLow.includes("timeout") || msgLow.includes("504") || msgLow.includes("conexão")) {
                                        return { tipo: "timeout_gateway", texto: msg };
                                    }
                                    return { tipo: "erro_fatal", texto: msg };
                                }
                            }
                        }
                        return null;
                    }
                    
                    var err = getFatalError();
                    if (err) {
                        if (err.tipo === "duplicado") {
                            return { status: "alerta_duplicado", texto: err.texto };
                        }
                        if (err.tipo === "erro_fatal") {
                            return { status: "alerta_erro", texto: err.texto };
                        }
                    }
                    
                    // 2. Verifica se o pacote apareceu na tabela inferior (.firstOrder ou tr.el-table__row)
                    var pacoteNaTabela = false;
                    var firstOrders = document.querySelectorAll(".firstOrder");
                    for (var k = 0; k < firstOrders.length; k++) {
                        var foTxt = (firstOrders[k].innerText || firstOrders[k].textContent || '').trim().toLowerCase();
                        if (foTxt.includes(cleanQr) || cleanQr.includes(foTxt)) {
                            pacoteNaTabela = true;
                            break;
                        }
                    }
                    
                    if (!pacoteNaTabela) {
                        var rows = document.querySelectorAll(".el-table__body tr.el-table__row, .el-table__body tr");
                        for (var r = 0; r < rows.length; r++) {
                            var rTxt = (rows[r].innerText || rows[r].textContent || '').trim().toLowerCase();
                            if (rTxt.includes(cleanQr)) {
                                pacoteNaTabela = true;
                                break;
                            }
                        }
                    }
                    
                    // 3. O pacote apareceu na tabela! Clica no botão 'Enviar'
                    if (pacoteNaTabela) {
                        var btns = document.querySelectorAll("button, .el-button");
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || btns[i].textContent || '').trim();
                            if (t === 'Enviar' || t.includes('Enviar')) {
                                btns[i].click();
                                btns[i].dispatchEvent(new MouseEvent('click', { bubbles: true }));
                                return { status: "enviado_sucesso" };
                            }
                        }
                        return { status: "na_tabela_sem_botao" };
                    }
                    
                    return { status: "aguardando_tabela" };
                """
                
                while time.time() - inicio_wait < 12.0:
                    try:
                        res = driver.execute_script(script_anjun_aba1, codigo_qr)
                        if res:
                            st = res.get("status")
                            if st == "enviado_sucesso":
                                enviado_com_sucesso = True
                                print(f"[+] [Anjun] Pacote {codigo_qr} confirmado na tabela inferior! Botão 'Enviar' clicado com sucesso!")
                                break
                            elif st == "alerta_erro":
                                alerta_texto = res.get("texto")
                                break
                            elif st == "alerta_duplicado":
                                print(f"[*] [Anjun] Aviso de pacote já escaneado: '{res.get('texto')}'. Prosseguindo para Aba 3...")
                                enviado_com_sucesso = True
                                pacote_ja_recepcionado_aba1 = True
                                break
                            elif st == "na_tabela_sem_botao":
                                try:
                                    btn_s = driver.find_element(By.XPATH, "//button[contains(., 'Enviar') or contains(span, 'Enviar')]")
                                    driver.execute_script("arguments[0].click();", btn_s)
                                    enviado_com_sucesso = True
                                    print(f"[+] [Anjun] Botão 'Enviar' clicado via fallback após confirmação na tabela!")
                                    break
                                except Exception:
                                    pass
                    except Exception:
                        pass
                        
                    # Se passou 2.0s e ainda não apareceu na tabela, re-dispara Enter no campo de bipe
                    if not re_disparado and (time.time() - inicio_wait > 2.0):
                        re_disparado = True
                        print(f"[*] [Anjun] Pacote ainda não apareceu na tabela após 2s. Re-disparando Enter no input...")
                        try:
                            if campo_rec:
                                campo_rec.send_keys(Keys.ENTER)
                        except Exception:
                            pass
                            
                    time.sleep(0.08)
                
                # Se o timeout estourou mas o botão Enviar está visível, tenta clique final
                if not enviado_com_sucesso and not alerta_texto:
                    print("[*] [Anjun] Tempo de espera da tabela esgotado. Verificando botão 'Enviar'...")
                    try:
                        driver.execute_script("""
                            var btns = document.querySelectorAll("button, .el-button");
                            for (var i = 0; i < btns.length; i++) {
                                var t = (btns[i].innerText || btns[i].textContent || '').trim();
                                if (t === 'Enviar' || t.includes('Enviar')) {
                                    btns[i].click();
                                    break;
                                }
                            }
                        """)
                    except Exception:
                        pass
                
                if alerta_texto and not pacote_duplicado:
                    print(f"[!] [Anjun] Alerta impeditivo na Aba 1: '{alerta_texto}'. Cancelando processo.")
                    salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {alerta_texto}")
                    return jsonify({
                        "status": "erro",
                        "mensagem": f"Alerta da Anjun: {alerta_texto}"
                    }), 400
                    
                # SINCRONIZAÇÃO ROBUSTA PÓS-ENVIO NA ABA 1:
                # O site da Anjun pode ser lento. Enquanto o loading estiver ativo, o robô FICA ESPERANDO
                # e NÃO passa para atribuir em hipótese alguma.
                # Só passa quando o código sumir da tabela inferior e o site exibir 'Sem dados' ou 'Já bipado: 0'.
                if not pacote_ja_recepcionado_aba1:
                    print(f"[*] [Anjun] Aguardando envio: enquanto houver 'Loading', o robô aguarda antes de atribuir...")
                    inicio_pos_envio = time.time()
                    confirmado_limpo = False
                    alerta_pos_envio = None
                    ultimo_re_clique = time.time()
                    
                    script_pos_envio_anjun = """
                        var cleanQr = (arguments[0] || '').trim().toLowerCase();

                        // 1. Detecta Loading ativo (máscara, spinner ou texto 'Loading')
                        function checkLoading() {
                            var masks = document.querySelectorAll(".el-loading-mask, .el-loading-spinner, .el-loading-parent--relative > .el-loading-mask");
                            for (var m = 0; m < masks.length; m++) {
                                var mask = masks[m];
                                if (mask && (mask.offsetWidth > 0 || mask.offsetHeight > 0 || mask.offsetParent !== null)) {
                                    var compStyle = window.getComputedStyle(mask);
                                    if (compStyle && compStyle.display !== 'none' && compStyle.visibility !== 'hidden' && compStyle.opacity !== '0') {
                                        return true;
                                    }
                                }
                            }
                            var loadingTexts = document.querySelectorAll(".el-loading-text, .circular, [class*='loading']");
                            for (var lt = 0; lt < loadingTexts.length; lt++) {
                                var elLt = loadingTexts[lt];
                                if (elLt && (elLt.offsetWidth > 0 || elLt.offsetHeight > 0 || elLt.offsetParent !== null)) {
                                    var txt = (elLt.innerText || elLt.textContent || '').trim().toLowerCase();
                                    if (txt === 'loading' || elLt.classList.contains('is-loading')) {
                                        var sLt = window.getComputedStyle(elLt);
                                        if (sLt && sLt.display !== 'none' && sLt.visibility !== 'hidden') {
                                            return true;
                                        }
                                    }
                                }
                            }
                            var loadingBtns = document.querySelectorAll("button.is-loading, .el-button.is-loading");
                            if (loadingBtns.length > 0) {
                                return true;
                            }
                            return false;
                        }

                        var loadingAtivo = checkLoading();

                        // 2. Alertas de erro e mensagens
                        function checkAlerts() {
                            var alertElems = document.querySelectorAll(".el-message--error, .el-notification--error, .el-message-box__content, .error-message");
                            for (var j = 0; j < alertElems.length; j++) {
                                var el = alertElems[j];
                                if (el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.offsetParent !== null)) {
                                    var msg = (el.innerText || el.textContent || '').trim();
                                    if (msg && !msg.toLowerCase().includes("sucesso") && !msg.toLowerCase().includes("enviado")) {
                                        var msgLow = msg.toLowerCase();
                                        if (msgLow.includes("já escaneado") || msgLow.includes("já bipado") || msgLow.includes("já recepcionado") || msgLow.includes("duplicad")) {
                                            return { tipo: "duplicado", texto: msg };
                                        }
                                        // Avisos de timeout de gateway / lentidão não são fatais
                                        if (msgLow.includes("网关超时") || msgLow.includes("gateway") || msgLow.includes("timeout") || msgLow.includes("504") || msgLow.includes("conexão")) {
                                            return { tipo: "timeout_gateway", texto: msg };
                                        }
                                        return { tipo: "erro_fatal", texto: msg };
                                    }
                                }
                            }
                            return null;
                        }

                        var alerta = checkAlerts();
                        if (alerta && alerta.tipo === "duplicado") {
                            return { status: "duplicado", texto: alerta.texto };
                        }
                        if (alerta && alerta.tipo === "erro_fatal" && !loadingAtivo) {
                            return { status: "erro", texto: alerta.texto };
                        }

                        // 3. Verifica se o código do pacote ainda está presente na tabela inferior
                        var codigoNaTabela = false;
                        var totalLinhasTabela = 0;

                        var firstOrders = document.querySelectorAll(".firstOrder");
                        for (var k = 0; k < firstOrders.length; k++) {
                            var fo = firstOrders[k];
                            if (fo && (fo.offsetWidth > 0 || fo.offsetHeight > 0 || fo.offsetParent !== null)) {
                                var foTxt = (fo.innerText || fo.textContent || '').trim().toLowerCase();
                                if (foTxt.includes(cleanQr) || cleanQr.includes(foTxt)) {
                                    codigoNaTabela = true;
                                    totalLinhasTabela++;
                                }
                            }
                        }

                        var rows = document.querySelectorAll(".el-table__body tr.el-table__row, .el-table__body tr");
                        for (var r = 0; r < rows.length; r++) {
                            var row = rows[r];
                            if (row && (row.offsetWidth > 0 || row.offsetHeight > 0 || row.offsetParent !== null)) {
                                totalLinhasTabela++;
                                var rTxt = (row.innerText || row.textContent || '').trim().toLowerCase();
                                if (rTxt.includes(cleanQr)) {
                                    codigoNaTabela = true;
                                }
                            }
                        }

                        // 4. Indicadores de tabela vazia / sem dados
                        var temSemDados = false;
                        var emptyBlocks = document.querySelectorAll(".el-table__empty-block, .el-table__empty-text");
                        for (var e = 0; e < emptyBlocks.length; e++) {
                            var eb = emptyBlocks[e];
                            if (eb && (eb.offsetWidth > 0 || eb.offsetHeight > 0 || eb.offsetParent !== null)) {
                                var ebTxt = (eb.innerText || eb.textContent || '').trim().toLowerCase();
                                if (ebTxt.includes("sem dados") || ebTxt.includes("nenhum") || ebTxt.includes("no data")) {
                                    temSemDados = true;
                                    break;
                                }
                            }
                        }

                        // 5. Contador 'Já bipado:'
                        var contadorZerado = false;
                        var bodyText = document.body.innerText || '';
                        var matchBip = bodyText.match(/J[áa]\\s*bipado:\\s*(\\d+)/i);
                        if (matchBip && parseInt(matchBip[1], 10) === 0) {
                            contadorZerado = true;
                        }

                        // PRIORIDADE MÁXIMA DA USUÁRIA:
                        // Se o loading estiver ativo, FICA ESPERANDO! NÃO passa para atribuir!
                        if (loadingAtivo) {
                            return { status: "carregando", codigoNaTabela: codigoNaTabela };
                        }

                        // Se o loading NÃO está ativo:
                        // Verifica se o pacote sumiu da tabela
                        if (!codigoNaTabela && (temSemDados || contadorZerado || totalLinhasTabela === 0)) {
                            return { status: "confirmado_limpo" };
                        }

                        if (!codigoNaTabela && totalLinhasTabela === 0) {
                            return { status: "confirmado_limpo" };
                        }

                        // Se o código ainda está na tabela e não está em loading:
                        if (codigoNaTabela) {
                            return { status: "na_tabela_aguardando", alertaGateway: (alerta && alerta.tipo === "timeout_gateway") };
                        }

                        return { status: "aguardando" };
                    """
                    
                    while time.time() - inicio_pos_envio < 120.0:
                        try:
                            res_env = driver.execute_script(script_pos_envio_anjun, codigo_qr)
                            if res_env:
                                st_env = res_env.get("status")
                                if st_env == "confirmado_limpo":
                                    confirmado_limpo = True
                                    tempo_decorrido = time.time() - inicio_pos_envio
                                    print(f"[+] [Anjun] Confirmação detectada! Código {codigo_qr} sumiu da tabela inferior ('Sem dados' / 'Já bipado: 0') em {tempo_decorrido:.2f}s! Entrada concluída com sucesso!")
                                    break
                                elif st_env == "duplicado":
                                    print(f"[*] [Anjun] Aviso de pacote já recepcionado detectado ({res_env.get('texto')}). Prosseguindo para Aba 3...")
                                    confirmado_limpo = True
                                    break
                                elif st_env == "erro":
                                    alerta_pos_envio = res_env.get("texto")
                                    print(f"[!] [Anjun] Erro fatal detectado pós-envio na Aba 1: '{alerta_pos_envio}'")
                                    break
                                elif st_env == "carregando":
                                    # Robô permanece aguardando enquanto o loading estiver rodando na tela
                                    pass
                                elif st_env == "na_tabela_aguardando":
                                    # Se parou o loading mas o pacote ainda está na tabela (ex: 网关超时), re-tenta clicar em Enviar!
                                    if time.time() - ultimo_re_clique >= 3.0:
                                        ultimo_re_clique = time.time()
                                        motivo = "após 网关超时" if res_env.get("alertaGateway") else "sem loading ativo"
                                        print(f"[*] [Anjun] Pacote {codigo_qr} ainda na tabela ({motivo}). Re-clicando no botão 'Enviar'...")
                                        driver.execute_script("""
                                            var btns = document.querySelectorAll("button, .el-button");
                                            for (var i = 0; i < btns.length; i++) {
                                                var t = (btns[i].innerText || btns[i].textContent || '').trim();
                                                if (t === 'Enviar' || t.includes('Enviar')) {
                                                    btns[i].click();
                                                    btns[i].dispatchEvent(new MouseEvent('click', { bubbles: true }));
                                                    break;
                                                }
                                            }
                                        """)
                        except Exception:
                            pass
                        time.sleep(0.08)
                        
                    if alerta_pos_envio and not pacote_duplicado:
                        print(f"[!] [Anjun] Alerta impeditivo pós-envio na Aba 1: '{alerta_pos_envio}'. Cancelando processo.")
                        salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {alerta_pos_envio}")
                        return jsonify({
                            "status": "erro",
                            "mensagem": f"Erro Anjun no envio: {alerta_pos_envio}"
                        }), 400
                        
                    if not confirmado_limpo and not pacote_duplicado:
                        print(f"[Aviso] [Anjun] Limite de 120s atingido aguardando tabela limpar na Aba 1. Prosseguindo...")
        
        cidade_detectada = cidade_duplicada if pacote_duplicado else None
        cidade_resolvida = None
        recebedor = "---"
        telefone = "---"
        email = "---"
        tempo_criacao = "---"
        status_pacote = "---"

        # Se for a Anjun Express, processo 100% livre (sem consulta de cidade)
        if "anjun" in p_id or "anjun" in config['recebimento_url'].lower():
            print("[*] Plataforma Anjun Express detectada. Processo 100% livre (consulta de cidades desativada).")
            negocios = "---"
            recebedor = "---"
            telefone = "---"
            email = "---"
            bairro = "---"
            cep = ""
            status_pacote = "---"
            valor_declarado = "---"
            tempo_criacao = "---"
            cidade_detectada = cidade_duplicada if (pacote_duplicado and cidade_duplicada) else "Anjun"
            mot_print = motorista_lote
                        
        elif p_id == 'loggi':
            print("[*] Plataforma Loggi (Arco) detectada. Analisando modo de consulta...")
            negocios = "---"
            recebedor = "---"
            telefone = "---"
            email = "---"
            bairro = "---"
            cep = ""
            status_pacote = "---"
            valor_declarado = "---"
            tempo_criacao = "---"
            cidade_detectada = cidade_duplicada if (pacote_duplicado and cidade_duplicada) else (motorista_lote if motorista_lote else "Não Consultada")
            
            if deve_consultar_este_bip and not pacote_duplicado:
                try:
                    # Sempre verifica se o handle da aba 2 é válido
                    aba_2_valida = False
                    if aba_atribuicao and aba_atribuicao in driver.window_handles:
                        aba_2_valida = True
                            
                    if not aba_2_valida:
                        print("[*] Aba 2 Loggi inválida ou ausente na memória. Escaneando abas abertas...")
                        aba_atribuicao = None
                        for handle in driver.window_handles:
                            try:
                                if handle == aba_recebimento:
                                    continue # Não pode ser a aba de recebimento!
                                driver.switch_to.window(handle)
                                url_atual = driver.current_url.lower()
                                if "colecoes" in url_atual or "acompanhamento" in url_atual:
                                    aba_atribuicao = handle
                                    aba_2_valida = True
                                    print(f"[+] Aba 2 Loggi encontrada dinamicamente: {handle}")
                                    break
                            except Exception:
                                continue
                                
                    if aba_atribuicao:
                        print("[*] Alternando para a aba 2 (Consulta) Loggi...")
                        mudar_aba_acelerado(driver, aba_atribuicao)
                    
                    print("[*] Localizando campo de input de pesquisa Loggi via HTML...")
                    campo_pesq = obter_input_loggi_html(driver, modo='consulta')
                    if not campo_pesq:
                        raise Exception("Campo de pesquisa da Loggi não encontrado na Aba 2.")
                        
                    print(f"[*] Enviando busca do pacote Loggi na Aba 2: {codigo_qr}...")
                    enviar_bipe_loggi_html(driver, campo_pesq, codigo_qr, modo='consulta')
                    
                    print("[*] Aguardando o resultado da pesquisa Loggi...")
                    row_resultado = None
                    inicio_wait = time.time()
                    while time.time() - inicio_wait < 5.0:
                        try:
                            trs = driver.find_elements(By.XPATH, "//tbody[contains(@class, 'MuiTableBody-root')]/tr")
                            for tr in trs:
                                if tr.is_displayed():
                                    row_resultado = tr
                                    break
                            if row_resultado:
                                break
                        except Exception:
                            pass
                        time.sleep(0.2)
                        
                    if row_resultado:
                        print("[+] Resultado da pesquisa Loggi encontrado! Clicando para abrir detalhes...")
                        driver.execute_script("arguments[0].click();", row_resultado)
                        
                        print("[*] Aguardando o painel de detalhes abrir...")
                        recebedor_el = None
                        inicio_wait_details = time.time()
                        while time.time() - inicio_wait_details < 4.0:
                            try:
                                el = driver.find_element(By.XPATH, "//*[@id='root']/div[2]/div[2]/div/div/div[1]/div/div[2]/div/div/div/div[3]/div[2]/div[3]/p")
                                if el.is_displayed() and el.text.strip():
                                    recebedor_el = el
                                    break
                            except Exception:
                                pass
                            try:
                                el = driver.find_element(By.XPATH, "//*[contains(@data-testid, 'package-detail')]//p")
                                if el.is_displayed() and el.text.strip():
                                    recebedor_el = el
                                    break
                            except Exception:
                                pass
                            time.sleep(0.2)
                            
                        if recebedor_el:
                            recebedor = recebedor_el.text.strip()
                            print(f"[+] Recebedor Loggi detectado: {recebedor}")
                            
                        # Tenta extrair os dados específicos do endereço, bairro e CEP na Loggi
                        try:
                            # 1. CEP
                            try:
                                texto_cep = driver.find_element(By.XPATH, "//*[@id='root']/div[2]/div[2]/div/div/div[1]/div/div[2]/div/div/div/div[3]/div[2]/div[4]/p[3]").text.strip()
                                cep = texto_cep.replace("-", "").strip()
                                print(f"[+] CEP Loggi detectado por XPath: {cep}")
                            except Exception:
                                pass
                                
                            # 2. Bairro e Cidade
                            try:
                                texto_bairro_cidade = driver.find_element(By.XPATH, "//*[@id='root']/div[2]/div[2]/div/div/div[1]/div/div[2]/div/div/div/div[3]/div[2]/div[4]/p[2]").text.strip()
                                partes = [p.strip() for p in texto_bairro_cidade.split("•")]
                                if len(partes) >= 2:
                                    bairro = partes[0]
                                    cidade_texto_detectado = partes[1]
                                    print(f"[+] Dados Loggi - Bairro: {bairro}, Cidade extraída: {cidade_texto_detectado}")
                                    
                                    # Verifica se a cidade extraída bate com alguma cadastrada no banco cidades
                                    lista_cidades = carregar_cidades()
                                    cidade_detectada = encontrar_cidade_mapeada(cidade_texto_detectado, lista_cidades)
                                    if cidade_detectada:
                                        print(f"[+] Cidade correspondente mapeada via texto da gaveta: {cidade_detectada}")
                            except Exception as e_br:
                                print(f"[Aviso] Falha ao extrair bairro/cidade por XPath: {str(e_br)}")
                        except Exception:
                            pass

                        # Fallback 1: Se ainda não resolveu a cidade por texto da gaveta, tenta ViaCEP usando o CEP
                        if not cidade_detectada and cep:
                            cidade_resolvida = obter_cidade_por_cep(cep)
                            if cidade_resolvida:
                                print(f"[+] Cidade resolvida pela API ViaCEP: {cidade_resolvida}")
                                lista_cidades = carregar_cidades()
                                cidade_detectada = encontrar_cidade_mapeada(cidade_resolvida, lista_cidades)
                                if cidade_detectada:
                                    print(f"[+] Cidade correspondente mapeada via CEP/ViaCEP: {cidade_detectada}")
                                        
                        # Fallback 2: Busca clássica no corpo de texto
                        if not cidade_detectada:
                            try:
                                texto_dados = driver.find_element(By.TAG_NAME, "body").text
                            except Exception:
                                texto_dados = ""
                            lista_cidades = carregar_cidades()
                            cidade_detectada = encontrar_cidade_mapeada(texto_dados, lista_cidades)
                            if cidade_detectada:
                                print(f"[+] Cidade correspondente mapeada por texto corporal: {cidade_detectada}")
                                    
                        try:
                            btn_fechar = driver.find_element(By.XPATH, "//button[contains(@class, 'close') or .//*[local-name()='svg' and contains(@class, 'close')] or contains(@class, 'MuiBox-root') or contains(@class, 'MuiIconButton')]")
                            btn_fechar.click()
                        except Exception:
                            try:
                                btn_fechar = driver.find_element(By.XPATH, "//*[@id='root']/div[2]/div[2]/div/div/div[1]/div/div[1]/button")
                                btn_fechar.click()
                            except Exception:
                                pass
                    else:
                        print("[-] Nenhum resultado encontrado na pesquisa Loggi.")
                except Exception as e_lo:
                    print(f"[Aviso] Erro na consulta rápida Loggi: {str(e_lo)}")
            else:
                print("[*] Consulta rápida na Aba 2 Loggi DESATIVADA.")
                
        elif p_id == 'imile' or 'imile' in config['recebimento_url'].lower():
            print("[*] Plataforma iMile Express detectada. Consulta rápida DESATIVADA.")
            negocios = "---"
            recebedor = "---"
            telefone = "---"
            email = "---"
            bairro = "---"
            cep = ""
            status_pacote = "---"
            valor_declarado = "---"
            tempo_criacao = "---"
            cidade_detectada = "iMile"
            mot_print = motorista_lote

        else:
            # Fluxo Padrão
            print("[*] Plataforma padrão detectada. Aguardando 1.5s para carregamento...")
            time.sleep(1.5)
            try:
                WebDriverWait(driver, 5).until(
                    lambda d: d.find_element(By.TAG_NAME, "body").text.find("CEP") != -1 or d.find_element(By.TAG_NAME, "body").text.find("Endereço") != -1
                )
                print("[+] Detalhes do destinatário carregados.")
            except Exception:
                print("[Aviso] Timeout ao esperar carregamento dos detalhes do destinatário. Continuando...")

            # 1. Tentar obter pelo CEP (Prioridade)
            cep = extrair_cep_da_pagina(driver)
            if cep:
                print(f"[+] CEP encontrado: {cep}. Consultando localidade no ViaCEP...")
                cidade_resolvida = obter_cidade_por_cep(cep)
                if cidade_resolvida:
                    print(f"[+] Cidade resolvida pela API: {cidade_resolvida}")
                    lista_cidades = carregar_cidades()
                    cidade_detectada = encontrar_cidade_mapeada(cidade_resolvida, lista_cidades)
                    if cidade_detectada:
                        print(f"[+] Cidade correspondente mapeada: {cidade_detectada}")
            
            # 2. Fallback: Se não encontrou o CEP ou a API falhou, busca pelo método clássico
            if not cidade_detectada:
                print("[*] CEP não pôde ser resolvido. Usando fallback de texto na página...")
                try:
                    texto_dados = driver.find_element(By.XPATH, config['recebimento_dados_xpath']).text
                except Exception:
                    try:
                        texto_dados = driver.find_element(By.TAG_NAME, "body").text
                    except Exception:
                        texto_dados = ""

                lista_cidades = carregar_cidades()
                cidade_detectada = encontrar_cidade_mapeada(texto_dados, lista_cidades)
                if cidade_detectada:
                    print(f"[+] Fallback: Cidade encontrada no texto: {cidade_detectada}")
                        
        if p_id in ['imile', 'anjun'] or 'imile' in p_id or 'anjun' in p_id or 'imile' in config['recebimento_url'].lower() or 'anjun' in config['recebimento_url'].lower():
            if not cidade_detectada or cidade_detectada in ["Não Consultada", "---", "Desconhecida", "Não Encontrada"]:
                cidade_detectada = "Anjun" if ("anjun" in p_id or "anjun" in config['recebimento_url'].lower()) else "iMile"

        print(f"[*] Resultado final da detecção: Cidade='{cidade_detectada}'")
        if not cidade_detectada:
            cidade_exibida = cidade_resolvida if cidade_resolvida else "Desconhecida"
            salvar_entrada_historico(codigo_qr, p_id, cidade_exibida, "---", "NÃO PERTENCE À BASE", recebedor, telefone, email, tempo_criacao, status_pacote)
            return jsonify({
                "status": "fora_de_rota",
                "mensagem": "Pacote não pertence a esta Base",
                "cidade": cidade_exibida,
                "recebedor": recebedor
            }), 400
            
        if p_id in ['imile', 'anjun', 'loggi'] or 'imile' in config['recebimento_url'].lower() or 'anjun' in config['recebimento_url'].lower() or 'loggi' in config['recebimento_url'].lower():
            motorista = motorista_lote
        else:
            mots_cidade = carregar_motoristas_cidade(cidade_detectada, p_id)
            motorista = mots_cidade[0] if mots_cidade else ""
        
        # --- ETAPA 2: ATRIBUIR (INTEGRADA E SEQUENCIAL) ---
        if motorista_lote:
            # Se for apenas entrada, encerra o processo por aqui sem fazer atribuição no site
            if motorista_lote in ["", "---", "Apenas Entrada (Sem Atribuição)"]:
                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) + 1
                contagem_motoristas[motorista_lote] = contagem_atribuicao_ativa
                
                print(f"[+] Modo Apenas Entrada ativo. Bip registrado localmente. Concluindo sem fazer atribuição no site.")
                # Se for duplicado, anula a atribuição anterior para corrigir a contagem
                if pacote_duplicado:
                    if motorista_anterior and motorista_anterior in contagem_motoristas:
                        contagem_motoristas[motorista_anterior] = max(0, contagem_motoristas[motorista_anterior] - 1)
                        print(f"[+] Modo Apenas Entrada: Contagem do motorista anterior {motorista_anterior} decrementada para {contagem_motoristas[motorista_anterior]}.")
                    try:
                        conn_up = conectar_banco()
                        cursor_up = conn_up.cursor()
                        cursor_up.execute('''
                            UPDATE historico 
                            SET status = 'REATRIBUIDO' 
                            WHERE codigo = ? AND status = 'OK' AND timestamp >= ?
                        ''', (codigo_qr, limite_data))
                        conn_up.commit()
                        cursor_up.close()
                        conn_up.close()
                        print(f"[+] Modo Apenas Entrada: Bip anterior do pacote {codigo_qr} marcado como REATRIBUIDO para corrigir contagens.")
                    except Exception as e_up:
                        print(f"[Erro] Falha ao anular bipe anterior: {str(e_up)}")
                        
                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista_lote, "OK", recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro)
                
                # Otimizador de memória a cada 100 bipes
                total_bipes_processados += 1
                if total_bipes_processados % 100 == 0:
                    otimizar_memoria()
                
                return jsonify({
                    "status": "sucesso",
                    "cidade": cidade_detectada,
                    "motorista": motorista_lote,
                    "recebedor": recebedor,
                    "contagem": contagem_atribuicao_ativa,
                    "contagem_site": None,
                    "duplicado": pacote_duplicado,
                    "motorista_anterior": motorista_anterior,
                    "timestamp_anterior": timestamp_anterior
                })
                
            # Resolve os motoristas esperados (mapeados no banco) para esta cidade se ela foi consultada
            motoristas_esperados = []
            houve_divergencia = False
            motorista_esperado_display = ""
            
            if p_id in ['imile', 'anjun'] or 'imile' in p_id or 'anjun' in p_id:
                # Processo 100% livre para iMile e Anjun: sem bloqueios ou divergência de cidade!
                houve_divergencia = False
            elif p_id == 'loggi':
                # Na Loggi, a entrada na base (Aba 1) não exibe a cidade destino na tela.
                # A validação infalível da cidade da Loggi ocorre na gaveta da Aba 3 ("Editar grupo").
                houve_divergencia = False
            else:
                if cidade_detectada and cidade_detectada not in ["Não Consultada", "---", "Desconhecida", "Não Encontrada"]:
                    motoristas_esperados = carregar_motoristas_cidade(cidade_detectada, p_id)
                    if motoristas_esperados:
                        # Se o motorista_lote estiver entre os motoristas mapeados para essa cidade, é VÁLIDO!
                        motoristas_lower = [m.lower() for m in motoristas_esperados]
                        if motorista_lote.lower() not in motoristas_lower:
                            houve_divergencia = True
                            motorista_esperado_display = " / ".join(motoristas_esperados)
                    else:
                        motorista_esperado_display = "Sem Motorista Mapeado"
                else:
                    # Se não foi consultada ou é desconhecida, assume válido para não dar divergência falsa
                    houve_divergencia = False

            if houve_divergencia:
                print(f"[!] DIVERGÊNCIA DETECTADA! Pacote de {cidade_detectada} pertence a {motorista_esperado_display}, mas o lote ativo é de {motorista_lote}.")
                
                # Registra a divergência pendente no banco de dados SQLite
                try:
                    conn_div = conectar_banco()
                    cursor_div = conn_div.cursor()
                    cursor_div.execute("""
                        INSERT OR REPLACE INTO divergencias_pendentes (codigo, motorista_lote, motorista_esperado, status)
                        VALUES (?, ?, ?, 'pendente')
                    """, (codigo_qr, motorista_lote, motorista_esperado_display))
                    conn_div.commit()
                    conn_div.close()
                except Exception as ed:
                    print(f"[Erro] Falha ao registrar pendência de divergência: {str(ed)}")

                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista_esperado_display, "DIVERGENTE", recebedor, telefone, email, tempo_criacao, status_pacote)
                return jsonify({
                    "status": "divergente",
                    "mensagem": f"Pacote de {cidade_detectada} pertence ao(s) motorista(s) {motorista_esperado_display}, mas o lote ativo é de {motorista_lote}!",
                    "cidade": cidade_detectada,
                    "recebedor": recebedor,
                    "motorista_esperado": motorista_esperado_display
                }), 400
                
            # Pertence ao lote atual! Resolve qualquer pendência anterior deste pacote
            try:
                conn_div = conectar_banco()
                cursor_div = conn_div.cursor()
                cursor_div.execute("UPDATE divergencias_pendentes SET status = 'resolvido' WHERE codigo = ?", (codigo_qr,))
                conn_div.commit()
                conn_div.close()
            except Exception as ed:
                print(f"[Erro] Falha ao resolver pendência de divergência: {str(ed)}")

            # Faz a atribuição física na aba 3
            if p_id == 'loggi':
                aba_3_valida = bool(aba_atribuicao_anjun and aba_atribuicao_anjun in driver.window_handles)
                if not aba_3_valida:
                    print("[*] Aba 3 Loggi inválida ou ausente. Mapeando abas...")
                    garantir_abas_loggi(driver)
                
                if aba_atribuicao_anjun:
                    mudar_aba_acelerado(driver, aba_atribuicao_anjun)
                    
                    candidatos_drawer = [
                        "//input[@placeholder='Bipe ou digite o código']",
                        "//input[contains(@placeholder, 'Bipe')]",
                        "//input[contains(@placeholder, 'código') or contains(@placeholder, 'codigo')]",
                        "//div[contains(@class, 'Drawer') or contains(@class, 'drawer') or contains(@role, 'dialog')]//input[@type='text']",
                        "//aside//input[@type='text']"
                    ]
                    
                    # 1. Verifica se a gaveta de bipes está aberta (campo de input visível)
                    gaveta_aberta = False
                    campo_bip_drawer = None
                    try:
                        el_fast = driver.execute_script("""
                            return document.querySelector("input[placeholder*='Bipe ou digite'], aside input, [role='dialog'] input, div[class*='Drawer'] input");
                        """)
                        if el_fast and el_fast.is_displayed():
                            campo_bip_drawer = el_fast
                            gaveta_aberta = True
                    except Exception:
                        pass
                        
                    if not gaveta_aberta:
                        for path_dr in candidatos_drawer:
                            try:
                                el = driver.find_element(By.XPATH, path_dr)
                                if el.is_displayed():
                                    campo_bip_drawer = el
                                    gaveta_aberta = True
                                    print("[+] Gaveta de bipes já está aberta na tela.")
                                    break
                            except Exception:
                                pass
                        
                    # 2. Se não estiver aberta, faz o fluxo de filtro de cidades e entra no grupo/cria grupo
                    if not gaveta_aberta:
                        print("[*] Gaveta não está aberta. Iniciando fluxo de filtros e seleção de grupo...")
                        
                        # 2.1 Filtro de cidades: Clica no botão Cidades
                        try:
                            btn_cidades = driver.find_element(By.XPATH, "//button[@data-testid='btn-filter-Cidades'] | //button[contains(., 'Cidades')]")
                            driver.execute_script("arguments[0].click();", btn_cidades)
                            time.sleep(0.5)
                            
                            cidades_motorista = cidades_selecionadas if cidades_selecionadas else ([motorista_lote] if motorista_lote else [])
                            if not cidades_motorista:
                                raise Exception("Por favor, selecione as cidades de atribuição ativas no painel antes de bipar.")
                                
                            print(f"[*] Cidades Loggi a filtrar: {cidades_motorista}")
                            
                            candidatos_chk = driver.find_elements(By.XPATH, "//div[contains(@role, 'button') and .//input[@type='checkbox']]")
                            for el_chk in candidatos_chk:
                                texto_chk = el_chk.text.strip().lower()
                                input_chk = el_chk.find_element(By.XPATH, ".//input[@type='checkbox']")
                                
                                matched = False
                                for cid in cidades_motorista:
                                    if cid.strip().lower() in texto_chk or texto_chk in cid.strip().lower():
                                        matched = True
                                        break
                                        
                                is_checked = input_chk.get_attribute("checked") or input_chk.is_selected()
                                if matched and not is_checked:
                                    driver.execute_script("arguments[0].click();", el_chk)
                                elif not matched and is_checked:
                                    driver.execute_script("arguments[0].click();", el_chk)
                                    
                            # Aplica os filtros
                            btn_aplicar = driver.find_element(By.XPATH, "//button[@data-testid='apply-filter-Cidades'] | //button[contains(., 'Aplicar')]")
                            driver.execute_script("arguments[0].click();", btn_aplicar)
                            time.sleep(1.0)
                        except Exception as e_filt:
                            print(f"[Aviso] Falha ao aplicar filtros de cidades: {str(e_filt)}")
                            
                        # 2.2 Procura se há um grupo em "Processamento"
                        grupo_detectado = False
                        grupo_aberto = False
                        
                        # Se for a cidade de Itapeva na Loggi, sempre criamos um grupo novo (ignorando grupos existentes)
                        eh_itapeva = any(normalizar_texto(c) == "itapeva" for c in cidades_motorista)
                        
                        try:
                            if eh_itapeva:
                                print("[*] Cidade Itapeva detectada na Loggi. Forçando criação de novo grupo...")
                            else:
                                print("[*] Aguardando linhas da tabela carregarem...")
                                WebDriverWait(driver, 2.5).until(
                                    lambda d: len(d.find_elements(By.XPATH, "//*[contains(@class, 'row') or contains(@id, 'row') or contains(@class, 'TableRow') or self::tr][contains(., 'Processamento')]")) > 0
                                )
                        except Exception:
                            if not eh_itapeva:
                                print("[*] Nenhuma linha com 'Processamento' apareceu após o tempo limite.")
                                
                        try:
                            rows = []
                            if not eh_itapeva:
                                candidatos_linhas = [
                                    "//*[contains(@class, 'row') or contains(@id, 'row') or contains(@class, 'TableRow') or self::tr][contains(., 'Processamento')]",
                                    "//tr[contains(., 'Processamento')]",
                                    "//*[contains(text(), 'Processamento')]/ancestor::tr[1]",
                                    "//*[contains(text(), 'Processamento')]/ancestor::*[contains(@class, 'row') or contains(@id, 'row') or contains(@class, 'TableRow')][1]"
                                ]
                                for path_row in candidatos_linhas:
                                    found = driver.find_elements(By.XPATH, path_row)
                                    if found:
                                        rows = found
                                        break
                                        
                            if rows:
                                grupo_detectado = True
                                # Procura a linha correspondente e clica no botão "Ações do grupo"
                                for row in rows:
                                    if row.is_displayed():
                                        try:
                                            # 1. Procura se o botão "Ações do grupo" já está visível na linha
                                            btn_acoes = None
                                            candidatos_acoes = [
                                                ".//button[contains(@data-testid, '-clickable-action-button')]",
                                                ".//button[contains(., 'Ações') or contains(., 'ações') or contains(., 'acoes') or contains(., 'grup')]",
                                                ".//button[contains(@class, 'MuiButton-root')]"
                                            ]
                                            for xpath_ac in candidatos_acoes:
                                                try:
                                                    el_ac = row.find_element(By.XPATH, xpath_ac)
                                                    if el_ac.is_displayed():
                                                        btn_acoes = el_ac
                                                        break
                                                except Exception:
                                                    continue
                                            
                                            # 2. Se não estiver visível, clica no código/célula para expandir o grupo e revelar o botão
                                            if not btn_acoes:
                                                print("[*] Botão 'Ações do grupo' não visível. Tentando expandir a linha...")
                                                cell_clicavel = None
                                                candidatos_celula = [
                                                    ".//*[contains(@data-testid, '-collapsible')]",
                                                    ".//*[contains(text(), 'AV3')]",
                                                    ".//th[contains(., 'AV3')]",
                                                    ".//td[contains(., 'AV3')]"
                                                ]
                                                for xpath_cel in candidatos_celula:
                                                    try:
                                                        el_cel = row.find_element(By.XPATH, xpath_cel)
                                                        if el_cel.is_displayed():
                                                            cell_clicavel = el_cel
                                                            break
                                                    except Exception:
                                                        continue
                                                if cell_clicavel:
                                                    driver.execute_script("arguments[0].click();", cell_clicavel)
                                                    time.sleep(0.5)
                                                    
                                                # Procura novamente o botão de ações após expandir
                                                for xpath_ac in candidatos_acoes:
                                                    try:
                                                        el_ac = row.find_element(By.XPATH, xpath_ac)
                                                        if el_ac.is_displayed():
                                                            btn_acoes = el_ac
                                                            break
                                                    except Exception:
                                                        continue
                                                        
                                            if btn_acoes:
                                                print("[+] Clicando no botão 'Ações do grupo'...")
                                                driver.execute_script("arguments[0].click();", btn_acoes)
                                            else:
                                                raise Exception("Botão 'Ações do grupo' não pôde ser localizado na linha.")
                                        except Exception as e_ac:
                                            print(f"[Aviso] Falha ao clicar no botão de ações: {str(e_ac)}. Clicando na linha...")
                                            driver.execute_script("arguments[0].click();", row)
                                            
                                        time.sleep(1.0) # Aguarda a gaveta de ações abrir
                                        
                                        # Clica no botão/item "Editar pacotes" na gaveta que abriu
                                        btn_ed = None
                                        candidatos_editar = [
                                            "//div[contains(@role, 'button') and contains(., 'Editar pacotes')]",
                                            "//*[contains(text(), 'Editar pacotes')]",
                                            "//li[contains(., 'Editar pacotes')]",
                                            "//button[contains(., 'Editar pacotes')]"
                                        ]
                                        for path_ed in candidatos_editar:
                                            try:
                                                el_ed = WebDriverWait(driver, 1.5).until(
                                                    EC.visibility_of_element_located((By.XPATH, path_ed))
                                                )
                                                if el_ed:
                                                    btn_ed = el_ed
                                                    break
                                            except Exception:
                                                continue
                                                
                                        if btn_ed:
                                            driver.execute_script("arguments[0].click();", btn_ed)
                                            grupo_aberto = True
                                            print("[+] Editar pacotes clicado com sucesso!")
                                            time.sleep(0.8)
                                            break
                        except Exception as e_gr:
                            print(f"[Aviso] Falha ao abrir grupo existente: {str(e_gr)}")
                            
                        # 2.3 Se não encontrou grupo aberto, clica em "Agrupar" para criar um novo
                        if not grupo_detectado:
                            try:
                                print("[+] Nenhum grupo aberto em 'Processamento'. Criando novo grupo...")
                                btn_agrupar = driver.find_element(By.XPATH, "//button[@data-testid='grouping-button-others'] | //button[contains(., 'Agrupar')]")
                                driver.execute_script("arguments[0].click();", btn_agrupar)
                                time.sleep(0.8)
                            except Exception as e_agr:
                                print(f"[Aviso] Falha ao clicar em Agrupar no topo: {str(e_agr)}")
                        elif not grupo_aberto:
                            # Se o grupo existe mas não conseguimos abrir a gaveta de edição, interrompe para evitar duplicados
                            raise Exception("Um grupo em Processamento já existe para esta rota no site, mas o robô não conseguiu abrir a gaveta de edição. Por favor, abra-o manualmente no site.")
                                
                        # 2.4 Localiza o campo de input na gaveta recém-aberta via HTML
                        campo_bip_drawer = obter_input_loggi_html(driver, modo='atribuicao')
                            
                    # 3. Executa a bipagem de fato
                    if not campo_bip_drawer:
                        campo_bip_drawer = obter_input_loggi_html(driver, modo='atribuicao')

                    if not campo_bip_drawer:
                        raise Exception("Não foi possível encontrar a caixa de bipes da gaveta Loggi na aba 3. Verifique se a aba de Grupos está aberta.")
                        
                    # 3.1 Captura a contagem atual de pacotes da gaveta antes de bipar (via JS ultra-rápido)
                    contagem_inicial_gaveta = None
                    try:
                        contagem_inicial_gaveta = driver.execute_script("""
                            const h4s = document.querySelectorAll("h4");
                            for (const h of h4s) {
                                const txt = (h.innerText || h.textContent || "").toLowerCase();
                                if (txt.includes("pacote")) {
                                    const m = txt.match(/\\d+/);
                                    if (m) return parseInt(m[0], 10);
                                }
                            }
                            const el = document.querySelector("h4.MuiTypography-h4, .MuiTypography-root.MuiTypography-h4");
                            if (el) {
                                const m = (el.innerText || el.textContent || "").match(/\\d+/);
                                if (m) return parseInt(m[0], 10);
                            }
                            return null;
                        """)
                        if contagem_inicial_gaveta is not None:
                            print(f"[*] Contagem inicial na gaveta Loggi: {contagem_inicial_gaveta} pacotes")
                    except Exception:
                        pass

                    print(f"[*] Código {codigo_qr} enviado para a gaveta Loggi via HTML! Aguardando incremento do contador...")
                    enviar_bipe_loggi_html(driver, campo_bip_drawer, codigo_qr, modo='atribuicao')

                    # 3.2 Loop ultra-rápido: O milissegundo que o número aumentar, prossegue imediatamente!
                    sucesso_gaveta = False
                    erro_gaveta_msg = None
                    inicio_validacao = time.time()
                    
                    script_valida_gaveta = """
                        const qtd_ini = arguments[0];
                        const cod_qr = (arguments[1] || "").trim().toLowerCase();
                        const permitidas = (arguments[2] || []).map(c => (c || "").trim().toLowerCase());

                        // Função auxiliar para extrair a cidade do pacote no DOM da gaveta Loggi
                        function extrairCidade(cod) {
                            const drawer = document.querySelector(".MuiDrawer-paper, aside, [role='dialog'], [data-testid*='drawer']") || document;
                            const ems = drawer.querySelectorAll("em");
                            for (let i = 0; i < ems.length; i++) {
                                const emTxt = (ems[i].innerText || ems[i].textContent || "").trim().toLowerCase();
                                if (emTxt === cod || (cod && (emTxt.includes(cod) || cod.includes(emTxt)))) {
                                    const pParent = ems[i].closest('p');
                                    const container = pParent ? pParent.parentElement : null;
                                    if (container) {
                                        // Filtra parágrafos excluindo datas/prazos de entrega
                                        const ps = Array.from(container.querySelectorAll("p")).filter(p => {
                                            const t = (p.innerText || p.textContent || "").trim().toLowerCase();
                                            return t && !t.includes("entregar") && !t.includes("set") && !t.includes("out") && !t.includes("nov") && !t.includes("dez") && !t.includes("jan") && !t.includes("fev") && !t.includes("mar") && !t.includes("abr") && !t.includes("mai") && !t.includes("jun") && !t.includes("jul") && !t.includes("ago");
                                        });

                                        // 1. PRIORIDADE MÁXIMA: se qualquer parágrafo do card for uma das cidades permitidas, retorna imediatamente!
                                        for (let p of ps) {
                                            if (p === pParent) continue;
                                            const txt = (p.innerText || p.textContent || "").trim();
                                            const txtL = txt.toLowerCase();
                                            for (let c of permitidas) {
                                                if (c && (txtL === c || txtL.includes(c) || c.includes(txtL))) {
                                                    return txt;
                                                }
                                            }
                                        }

                                        // 2. Se nenhuma cidade bateu, a cidade na Loggi é SEMPRE o ÚLTIMO parágrafo da coluna (abaixo do cliente)
                                        // ps[0] = código (em)
                                        // ps[1] = cliente (ex: ZARA, LWSA, EBAZAR)
                                        // ps[ps.length - 1] = cidade destino (ex: Sorocaba, Itapeva, Ourinhos)
                                        const psNaoCodigo = ps.filter(p => p !== pParent && !(p.querySelector("em")) && !(p.innerText || "").toLowerCase().includes(cod));
                                        if (psNaoCodigo.length >= 2) {
                                            return (psNaoCodigo[psNaoCodigo.length - 1].innerText || "").trim();
                                        } else if (psNaoCodigo.length === 1) {
                                            return (psNaoCodigo[0].innerText || "").trim();
                                        }
                                    }
                                }
                            }

                            // Fallback: se não achou pelo código exato no em, procura se alguma cidade permitida aparece em parágrafo da gaveta
                            for (let c of permitidas) {
                                if (!c) continue;
                                const allPs = drawer.querySelectorAll("p");
                                for (let p of allPs) {
                                    const txt = (p.innerText || p.textContent || "").trim();
                                    if (txt.toLowerCase() === c || txt.toLowerCase().includes(c)) return txt;
                                }
                            }
                            return null;
                        }

                        // 1. PRIORIDADE MÁXIMA: Checagem instantânea se o número de pacotes no h4 aumentou
                        const h4s = document.querySelectorAll("h4");
                        for (const h of h4s) {
                            const txt = (h.innerText || h.textContent || "").toLowerCase();
                            if (txt.includes("pacote")) {
                                const m = txt.match(/\\d+/);
                                if (m) {
                                    const qtd_atual = parseInt(m[0], 10);
                                    if (qtd_ini !== null && qtd_atual > qtd_ini) {
                                        return { status: 'aumentou', nova_qtd: qtd_atual, cidade_detectada: extrairCidade(cod_qr) };
                                    }
                                }
                            }
                        }
                        const elH4 = document.querySelector("h4.MuiTypography-h4, .MuiTypography-root.MuiTypography-h4");
                        if (elH4) {
                            const m = (elH4.innerText || elH4.textContent || "").match(/\\d+/);
                            if (m) {
                                const qtd_atual = parseInt(m[0], 10);
                                if (qtd_ini !== null && qtd_atual > qtd_ini) {
                                    return { status: 'aumentou', nova_qtd: qtd_atual, cidade_detectada: extrairCidade(cod_qr) };
                                }
                            }
                        }

                        // 2. Box-alert de erro da Loggi
                        const alerts = document.querySelectorAll("[data-testid='box-alert-validation-component'], .MuiAlert-root");
                        for (const al of alerts) {
                            if (al.offsetParent !== null && al.innerText.trim()) {
                                const em = al.querySelector("em, h6, .MuiAlert-message");
                                const msg = (em ? em.innerText : al.innerText).trim();
                                if (msg) return { status: 'erro', mensagem: msg };
                            }
                        }

                        // 3. Fallback: código presente na lista da gaveta
                        if (cod_qr) {
                            const drawer = document.querySelector(".MuiDrawer-paper, aside, [role='dialog'], [data-testid*='drawer']");
                            if (drawer && drawer.innerText && drawer.innerText.includes(cod_qr)) {
                                return { status: 'confirmado_lista', cidade_detectada: extrairCidade(cod_qr) };
                            }
                        }

                        return { status: 'esperando' };
                    """
                    
                    cidade_gaveta_extraida = None
                    while time.time() - inicio_validacao < 2.0:
                        try:
                            res_val = driver.execute_script(script_valida_gaveta, contagem_inicial_gaveta, codigo_qr, cidades_selecionadas)
                            if res_val:
                                st = res_val.get("status")
                                if res_val.get("cidade_detectada"):
                                    cidade_gaveta_extraida = res_val.get("cidade_detectada")
                                if st == "aumentou":
                                    sucesso_gaveta = True
                                    contagem_site = res_val.get("nova_qtd")
                                    print(f"[+] [Loggi Aba 3] Número de pacotes aumentou: {contagem_inicial_gaveta} -> {contagem_site}! Prosseguindo imediatamente!")
                                    break
                                elif st == "erro":
                                    erro_gaveta_msg = res_val.get("mensagem")
                                    break
                                elif st == "confirmado_lista":
                                    sucesso_gaveta = True
                                    print(f"[+] [Loggi Aba 3] Pacote {codigo_qr} confirmado na lista da gaveta! Prosseguindo imediatamente!")
                                    break
                        except Exception:
                            pass
                        time.sleep(0.02)

                    # Se detectou a box-alert de erro da Loggi, interrompe e cancela a contagem
                    if erro_gaveta_msg:
                        print(f"[!] Erro retornado pela gaveta Loggi: '{erro_gaveta_msg}'")
                        salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista_lote, f"FALHA: {erro_gaveta_msg}", recebedor, telefone, email, tempo_criacao, status_pacote)
                        return jsonify({
                            "status": "erro",
                            "mensagem": f"Erro Loggi: {erro_gaveta_msg}"
                        }), 400

                    if not sucesso_gaveta:
                        print("[Aviso] Contador não aumentou no intervalo esperado, prosseguindo com o fluxo.")

                    # Tenta capturar a cidade da gaveta caso o texto tenha tido um breve delay de renderização
                    if not cidade_gaveta_extraida and sucesso_gaveta:
                        try:
                            cidade_gaveta_extraida = driver.execute_script("""
                                const cod = (arguments[0] || "").trim().toLowerCase();
                                const permitidas = (arguments[1] || []).map(c => (c || "").trim().toLowerCase());
                                const drawer = document.querySelector(".MuiDrawer-paper, aside, [role='dialog'], [data-testid*='drawer']") || document;
                                const ems = drawer.querySelectorAll("em");
                                for (let i = 0; i < ems.length; i++) {
                                    const emTxt = (ems[i].innerText || ems[i].textContent || "").trim().toLowerCase();
                                    if (emTxt === cod || (cod && (emTxt.includes(cod) || cod.includes(emTxt)))) {
                                        const pParent = ems[i].closest('p');
                                        const container = pParent ? pParent.parentElement : null;
                                        if (container) {
                                            const ps = Array.from(container.querySelectorAll("p")).filter(p => {
                                                const t = (p.innerText || p.textContent || "").trim().toLowerCase();
                                                return t && !t.includes("entregar") && !t.includes("set") && !t.includes("out") && !t.includes("nov") && !t.includes("dez") && !t.includes("jan") && !t.includes("fev") && !t.includes("mar") && !t.includes("abr") && !t.includes("mai") && !t.includes("jun") && !t.includes("jul") && !t.includes("ago");
                                            });
                                            for (let p of ps) {
                                                if (p === pParent) continue;
                                                const txt = (p.innerText || p.textContent || "").trim();
                                                const txtL = txt.toLowerCase();
                                                for (let c of permitidas) {
                                                    if (c && (txtL === c || txtL.includes(c) || c.includes(txtL))) {
                                                        return txt;
                                                    }
                                                }
                                            }
                                            const psNaoCodigo = ps.filter(p => p !== pParent && !(p.querySelector("em")) && !(p.innerText || "").toLowerCase().includes(cod));
                                            if (psNaoCodigo.length >= 2) {
                                                return (psNaoCodigo[psNaoCodigo.length - 1].innerText || "").trim();
                                            } else if (psNaoCodigo.length === 1) {
                                                return (psNaoCodigo[0].innerText || "").trim();
                                            }
                                        }
                                    }
                                }
                                for (let c of permitidas) {
                                    if (!c) continue;
                                    const allPs = drawer.querySelectorAll("p");
                                    for (let p of allPs) {
                                        const txt = (p.innerText || p.textContent || "").trim();
                                        if (txt.toLowerCase() === c || txt.toLowerCase().includes(c)) return txt;
                                    }
                                }
                                return null;
                            """, codigo_qr, cidades_selecionadas)
                        except Exception:
                            pass

                    # Validação de Divergência de Cidade na Aba 3 da Loggi
                    if cidade_gaveta_extraida:
                        print(f"[+] [Loggi Aba 3] Cidade detectada no card da gaveta: '{cidade_gaveta_extraida}'")
                        cidades_permitidas_norm = [normalizar_texto(c) for c in cidades_selecionadas] if cidades_selecionadas else ([normalizar_texto(motorista_lote)] if motorista_lote else [])
                        cid_gaveta_norm = normalizar_texto(cidade_gaveta_extraida)

                        cidade_bateu = any((cid_gaveta_norm == c_norm or c_norm in cid_gaveta_norm or cid_gaveta_norm in c_norm) for c_norm in cidades_permitidas_norm)

                        if cidades_permitidas_norm and not cidade_bateu:
                            cidades_esperadas_display = ", ".join(cidades_selecionadas) if cidades_selecionadas else (motorista_lote or "Grupo Ativo")
                            print(f"[!] DIVERGÊNCIA LOGGI DETECTADA NA ABA 3! Pacote é de '{cidade_gaveta_extraida}', mas o grupo de cidades é: '{cidades_esperadas_display}'.")

                            try:
                                conn_div = conectar_banco()
                                cursor_div = conn_div.cursor()
                                cursor_div.execute("""
                                    INSERT OR REPLACE INTO divergencias_pendentes (codigo, motorista_lote, motorista_esperado, status)
                                    VALUES (?, ?, ?, 'pendente')
                                """, (codigo_qr, motorista_lote, cidades_esperadas_display))
                                conn_div.commit()
                                conn_div.close()
                            except Exception as ed:
                                print(f"[Erro] Falha ao registrar pendência de divergência Loggi: {str(ed)}")

                            salvar_entrada_historico(codigo_qr, p_id, cidade_gaveta_extraida, cidades_esperadas_display, "DIVERGENTE", recebedor, telefone, email, tempo_criacao, status_pacote)

                            return jsonify({
                                "status": "divergente",
                                "mensagem": f"Pacote de {cidade_gaveta_extraida} não pertence ao grupo de {cidades_esperadas_display}!",
                                "cidade": cidade_gaveta_extraida,
                                "recebedor": recebedor if recebedor != "---" else "Loggi",
                                "motorista_esperado": cidades_esperadas_display
                            }), 400
                        else:
                            # Cidade autorizada no grupo! Atualiza cidade_detectada com o nome real
                            cidade_detectada = cidade_gaveta_extraida
                        
                # Incrementa contagem local e no banco
                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) + 1
                contagem_motoristas[motorista_lote] = contagem_atribuicao_ativa
                
                # Se for duplicado, anula a atribuição anterior para corrigir a contagem
                if pacote_duplicado:
                    if motorista_anterior and motorista_anterior in contagem_motoristas:
                        contagem_motoristas[motorista_anterior] = max(0, contagem_motoristas[motorista_anterior] - 1)
                        print(f"[+] Contagem do motorista anterior {motorista_anterior} decrementada para {contagem_motoristas[motorista_anterior]}.")
                    try:
                        conn_up = conectar_banco()
                        cursor_up = conn_up.cursor()
                        cursor_up.execute('''
                            UPDATE historico 
                            SET status = 'REATRIBUIDO' 
                            WHERE codigo = ? AND status = 'OK' AND timestamp >= ?
                        ''', (codigo_qr, limite_data))
                        conn_up.commit()
                        conn_up.close()
                        print(f"[+] Bip anterior do pacote {codigo_qr} marcado como REATRIBUIDO para corrigir contagens.")
                    except Exception as e_up:
                        print(f"[Erro] Falha ao anular bipe anterior: {str(e_up)}")
                        
                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista, "OK", recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro)
                
                # Otimizador de memória a cada 100 bipes
                total_bipes_processados += 1
                if total_bipes_processados % 100 == 0:
                    otimizar_memoria()
                    
                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0)
                return jsonify({
                    "status": "sucesso",
                    "cidade": cidade_detectada,
                    "motorista": motorista_lote,
                    "recebedor": recebedor,
                    "contagem": contagem_atribuicao_ativa,
                    "contagem_site": None,
                    "duplicado": pacote_duplicado,
                    "motorista_anterior": motorista_anterior,
                    "timestamp_anterior": timestamp_anterior,
                    "mesmo_motorista": bool(motorista_lote and motorista_anterior and motorista_lote.strip().lower() == motorista_anterior.strip().lower())
                })
                
            elif "anjun" in p_id or "anjun" in config['recebimento_url'].lower():
                # Garante que a aba_atribuicao_anjun esteja mapeada nas abas abertas caso tenha sido perdida
                if not aba_atribuicao_anjun:
                    print("[*] Referência da aba 3 ausente. Escaneando abas abertas...")
                    for handle in driver.window_handles:
                        try:
                            driver.switch_to.window(handle)
                            if "TaskAssignment" in driver.current_url:
                                aba_atribuicao_anjun = handle
                                print(f"[+] Aba 3 encontrada dinamicamente: {handle}")
                                break
                        except Exception:
                            continue
                
                if aba_atribuicao_anjun:
                    print(f"[*] Acessando aba 3 para atribuir o pacote {codigo_qr} ao motorista {motorista_lote}...")
                    mudar_aba_acelerado(driver, aba_atribuicao_anjun)
                    
                    # 0. Finaliza lote se já atingiu o limite de 200 pacotes
                    if contagem_motoristas.get(motorista_lote, 0) >= 200:
                        print(f"[!] Lote de {motorista_lote} já está cheio (200/200). Finalizando lote antes de atribuir...")
                        candidatos_finalizar = [
                            "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[1]/button[1]",
                            "//button[contains(., 'Finalizar') or contains(., 'Concluir') or contains(., 'Gerar') or contains(., 'Emitir') or contains(., 'Emissão') or contains(., 'Tarefa')]",
                            "//button[contains(@class, 'el-button--primary')]"
                        ]
                        for xpath_fin in candidatos_finalizar:
                            try:
                                btn_fin = driver.find_element(By.XPATH, xpath_fin)
                                if btn_fin.is_displayed():
                                    driver.execute_script("arguments[0].click();", btn_fin)
                                    time.sleep(0.8)
                                    fechar_popups_finalizacao_anjun(driver)
                                    print("[+] Lote cheio finalizado com sucesso antes do novo bipe.")
                                    contagem_motoristas[motorista_lote] = 0
                                    registrar_lote_finalizado(motorista_lote, 200)
                                    break
                            except Exception as e_fin:
                                print(f"[Aviso] Falha ao tentar finalizar lote cheio pré-bipe: {str(e_fin)}")
                        
                    # VERIFICAÇÃO AUTOMÁTICA DE DRIVER EM ABA 3 (Apenas na troca de motorista)
                    global motorista_atribuicao_ativa
                    if motorista_atribuicao_ativa != motorista_lote:
                        print(f"[*] Troca de motorista detectada na Aba 3! De {motorista_atribuicao_ativa} para {motorista_lote}.")
                        try:
                            selecionar_motorista_anjun(driver, motorista_lote)
                            motorista_atribuicao_ativa = motorista_lote
                            print(f"[+] Motorista alterado com sucesso na Aba 3 para: {motorista_atribuicao_ativa}")
                        except Exception as e_sel:
                            print(f"[Erro] Falha ao selecionar motorista na Aba 3: {str(e_sel)}")
                            raise Exception(f"Falha ao alterar o motorista no site para '{motorista_lote}': {str(e_sel)}")
                    
                    campo_pacote = obter_input_anjun_html(driver)
                    if not campo_pacote:
                        candidatos_pacote = [
                            "//input[@placeholder='Favor digitalizar ou digitar']",
                            "//label[contains(., 'Bipar o')]/following::input[1]",
                            "//*[contains(text(), 'Bipar o')]/following::input[1]"
                        ]
                        for xpath in candidatos_pacote:
                            try:
                                el = driver.find_element(By.XPATH, xpath)
                                if el.is_displayed():
                                    campo_pacote = el
                                    break
                            except Exception:
                                continue
                    
                    if not campo_pacote:
                        raise Exception("Não foi possível localizar o campo de input de bipe de pacote na aba de atribuição.")
                    
                    # Envia o bipe do pacote de forma instantânea (sem conferências prévias no DOM)
                    enviar_bipe_anjun_html(driver, campo_pacote, codigo_qr)
                    
                    # Se for pacote duplicado, confirma o modal de reatribuição se houver
                    if pacote_duplicado:
                        try:
                            driver.execute_script("""
                                var dialogs = document.querySelectorAll("div[role='dialog'], .el-dialog, .el-message-box, .el-overlay-dialog");
                                for (var d = 0; d < dialogs.length; d++) {
                                    var dlg = dialogs[d];
                                    if (dlg && (dlg.offsetWidth > 0 || dlg.offsetHeight > 0 || dlg.offsetParent !== null)) {
                                        var btn = dlg.querySelector(".el-button--primary, button.el-button--primary");
                                        if (btn) { btn.click(); return; }
                                        var allBtns = dlg.querySelectorAll("button");
                                        for (var b = 0; b < allBtns.length; b++) {
                                            var txt = (allBtns[b].innerText || allBtns[b].textContent || '').toLowerCase().trim();
                                            if (txt === 'confirmar' || txt === 'sim' || txt === 'ok') {
                                                allBtns[b].click();
                                                return;
                                            }
                                        }
                                    }
                                }
                            """)
                        except Exception:
                            pass
                    
                    contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) + 1
                    contagem_motoristas[motorista_lote] = contagem_atribuicao_ativa
                    print(f"[+] Lote atribuído: {contagem_atribuicao_ativa}/200")
                    
                    if contagem_atribuicao_ativa >= 200:
                        print("[!] Limite de 200 pacotes atingido. Finalizando lote automaticamente no site...")
                        candidatos_finalizar = [
                            "//*[@id='app']/section/section/main/div/div[2]/div/div[1]/div/div[1]/button[1]",
                            "//button[contains(., 'Finalizar') or contains(., 'Concluir') or contains(., 'Gerar') or contains(., 'Emitir') or contains(., 'Emissão') or contains(., 'Tarefa')]",
                            "//button[contains(@class, 'el-button--primary')]"
                        ]
                        for xpath_fin in candidatos_finalizar:
                            try:
                                btn_fin = driver.find_element(By.XPATH, xpath_fin)
                                if btn_fin.is_displayed():
                                    driver.execute_script("arguments[0].click();", btn_fin)
                                    time.sleep(1.0)
                                    fechar_popups_finalizacao_anjun(driver)
                                    break
                            except Exception:
                                continue
                        
                        # Re-seleciona o mesmo motorista para continuar a pilha sem interromper
                        print(f"[*] Re-selecionando o motorista {motorista_lote} para novo lote...")
                        try:
                            selecionar_motorista_anjun(driver, motorista_lote)
                            print("[+] Motorista re-selecionado com sucesso!")
                        except Exception as ere:
                            print(f"[Aviso] Erro ao re-selecionar motorista: {str(ere)}")
                        
                        registrar_lote_finalizado(motorista_lote, 200)
                        contagem_motoristas[motorista_lote] = 0
                        contagem_atribuicao_ativa = 0
                        motorista_atribuicao_ativa = motorista_lote
                        
                        tempo_total = time.time() - tempo_inicio
                        print(f"[+] PROCESSO CONCLUÍDO (LIMITE ATINGIDO) EM {tempo_total:.2f} SEGUNDOS!")
                        
                        if pacote_duplicado:
                            if motorista_anterior and motorista_anterior != motorista_lote and motorista_anterior in contagem_motoristas:
                                contagem_motoristas[motorista_anterior] = max(0, contagem_motoristas[motorista_anterior] - 1)
                            try:
                                conn_up = conectar_banco()
                                cursor_up = conn_up.cursor()
                                cursor_up.execute('''
                                    UPDATE historico 
                                    SET status = 'REATRIBUIDO' 
                                    WHERE codigo = ? AND status = 'OK' AND timestamp >= ?
                                ''', (codigo_qr, limite_data))
                                conn_up.commit()
                                conn_up.close()
                            except Exception:
                                pass
                                
                        salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista, "OK", recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro)
                        return jsonify({
                            "status": "finalizado_limite",
                            "cidade": cidade_detectada,
                            "recebedor": recebedor,
                            "contagem": 0,
                            "motorista": motorista_lote,
                            "duplicado": pacote_duplicado,
                            "motorista_anterior": motorista_anterior,
                            "timestamp_anterior": timestamp_anterior,
                            "mesmo_motorista": bool(motorista_lote and motorista_anterior and motorista_lote.strip().lower() == motorista_anterior.strip().lower())
                        })
            elif p_id == 'imile' or 'imile' in config['recebimento_url'].lower():
                print("[*] Acessando aba de atribuição para atribuir o pacote iMile ao motorista...")
                garantir_abas_imile(driver)
                if aba_atribuicao_anjun:
                    mudar_aba_acelerado(driver, aba_atribuicao_anjun, delay=0.12)
                    fechar_modais_imile(driver)
                    
                    # TROCA DE MOTORISTA IMILE (Apenas se o motorista tiver mudado)
                    if motorista_atribuicao_ativa != motorista_lote:
                        print(f"[*] Troca de motorista detectada na Aba 4 iMile! De {motorista_atribuicao_ativa} para {motorista_lote}.")
                        try:
                            sucesso_imile, msg_imile, nome_sel_imile = selecionar_motorista_imile(driver, motorista_lote)
                            if not sucesso_imile:
                                raise Exception(msg_imile)
                                
                            motorista_atribuicao_ativa = motorista_lote
                            print(f"[+] Motorista iMile alterado com sucesso para: {nome_sel_imile or motorista_lote}")
                            time.sleep(0.2)
                        except Exception as e_da:
                            print(f"[Erro] Falha ao selecionar motorista iMile: {str(e_da)}")
                            raise Exception(f"Falha ao alterar o motorista no site para '{motorista_lote}': {str(e_da)}")
                    
                    # Bipa o pacote na Aba Atribuição iMile (instantâneo, sem esperas de conferência)
                    try:
                        fechar_modais_imile(driver)
                        campo_pacote = obter_input_imile_html(driver, timeout=2.0)
                        if campo_pacote:
                            sucesso_bip = enviar_bipe_imile_html(driver, campo_pacote, codigo_qr)
                            if sucesso_bip:
                                print(f"[+] Pacote {codigo_qr} bipeado na Aba Atribuição iMile com sucesso!")
                            else:
                                print(f"[Aviso] Falha ao confirmar envio na Aba Atribuição iMile.")
                            
                            # Confirma modal de reatribuição se for pacote duplicado
                            if pacote_duplicado:
                                try:
                                    driver.execute_script("""
                                        var dialogs = document.querySelectorAll("div[role='dialog'], .MuiDialog-root, .MuiModal-root, .ImileDialog-root");
                                        for (var d = 0; d < dialogs.length; d++) {
                                            var dlg = dialogs[d];
                                            if (dlg && (dlg.offsetParent !== null || dlg.offsetWidth > 0 || dlg.offsetHeight > 0)) {
                                                var btn = dlg.querySelector(".ImileDialogFooter-confirm, button.MuiButton-contained, button.MuiButton-containedPrimary");
                                                if (btn) { btn.click(); return; }
                                                var allBtns = dlg.querySelectorAll("button, [role='button']");
                                                for (var b = 0; b < allBtns.length; b++) {
                                                    var txt = (allBtns[b].innerText || allBtns[b].textContent || '').toLowerCase().trim();
                                                    if (txt === 'confirmar' || txt === 'confirm' || txt === 'sim' || txt === 'yes' || txt === 'ok') {
                                                        allBtns[b].click();
                                                        return;
                                                    }
                                                }
                                            }
                                        }
                                    """)
                                except Exception:
                                    pass

                            # Incrementa a contagem de bipes para o motorista no iMile localmente
                            if motorista_lote:
                                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) + 1
                                contagem_motoristas[motorista_lote] = contagem_atribuicao_ativa
                        else:
                            print(f"[Erro] Campo de bipe na Aba Atribuição iMile não encontrado!")
                    except Exception as e_bip_da:
                        print(f"[Erro] Falha ao bipar pacote na Aba Atribuição iMile: {str(e_bip_da)}")
                        
        tempo_total = time.time() - tempo_inicio
        print(f"[+] PROCESSO CONCLUÍDO COM SUCESSO EM {tempo_total:.2f} SEGUNDOS!")
        
        # Se for duplicado, anula a atribuição anterior para corrigir a contagem
        if pacote_duplicado:
            if motorista_anterior and motorista_anterior in contagem_motoristas:
                contagem_motoristas[motorista_anterior] = max(0, contagem_motoristas[motorista_anterior] - 1)
                print(f"[+] iMile: Contagem do motorista anterior {motorista_anterior} decrementada para {contagem_motoristas[motorista_anterior]}.")
            try:
                conn_up = conectar_banco()
                cursor_up = conn_up.cursor()
                cursor_up.execute('''
                    UPDATE historico 
                    SET status = 'REATRIBUIDO' 
                    WHERE codigo = ? AND status = 'OK' AND timestamp >= ?
                ''', (codigo_qr, limite_data))
                conn_up.commit()
                conn_up.close()
                print(f"[+] Bip anterior do pacote {codigo_qr} marcado como REATRIBUIDO para corrigir contagens.")
            except Exception as e_up:
                print(f"[Erro] Falha ao anular bipe anterior: {str(e_up)}")

        salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista, "OK", recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro)
        
        # O primeiro bipe foi validado com sucesso!
        primeiro_bip_validado = True
        
        # Otimizador de memória a cada 100 bipes
        total_bipes_processados += 1
        if total_bipes_processados % 100 == 0:
            otimizar_memoria()
        
        if contagem_site is not None:
            contagem_atribuicao_ativa = contagem_site
        elif motorista_lote:
            contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0)
            
        return jsonify({
            "status": "sucesso", 
            "cidade": cidade_detectada, 
            "motorista": motorista if motorista else "Sem Motorista",
            "recebedor": recebedor,
            "contagem": contagem_atribuicao_ativa,
            "contagem_site": contagem_site,
            "duplicado": pacote_duplicado,
            "motorista_anterior": motorista_anterior,
            "timestamp_anterior": timestamp_anterior,
            "mesmo_motorista": bool(motorista_lote and motorista_anterior and motorista_lote.strip().lower() == motorista_anterior.strip().lower())
        })
        
    except (NoSuchElementException, TimeoutException) as nse:
        print(f"\n[Aviso] Elemento ou página não carregou a tempo: {str(nse)}")
        salvar_entrada_historico(codigo_qr, p_id, "---", "---", "FALHA: Elemento não encontrado", recebedor, telefone, email, tempo_criacao, status_pacote)
        return jsonify({"status": "erro", "mensagem": "Não foi possível localizar o campo ou os dados do pacote. Verifique se o Chrome está na tela correta e logado."}), 400
    except WebDriverException as wde:
        if is_driver_ativo():
            print(f"\n[Aviso WebDriver] Erro na interação com a página (Chrome permanece aberto): {str(wde)}")
            salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"AVISO: {str(wde)[:100]}", recebedor, telefone, email, tempo_criacao, status_pacote)
            return jsonify({"status": "erro", "mensagem": f"Aviso na página: {str(wde)}"}), 400
            
        print(f"\n[Erro] Conexão com o Chrome perdida ou fechada: {str(wde)}")
        fechar_selenium()
        salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: Conexão perdida com Chrome", recebedor, telefone, email, tempo_criacao, status_pacote)
        tem_motorista = bool(motorista_lote and str(motorista_lote).strip() not in ["", "---", "Apenas Entrada (Sem Atribuição)"])
        if (p_id in ['anjun', 'imile', 'loggi']) and tem_motorista:
            return jsonify({
                "status": "chrome_fechado",
                "mensagem": "Conexão com o navegador Chrome perdida ou fechada.",
                "motorista": motorista_lote,
                "plataforma": p_id
            }), 200
        return jsonify({"status": "erro", "mensagem": f"Erro de comunicação com o navegador Chrome: {str(wde)}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[Erro Geral] Ocorreu uma exceção inesperada: {str(e)}")
        salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {str(e)}", recebedor, telefone, email, tempo_criacao, status_pacote)
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        if driver:
            try:
                # Retorna IMEDIATAMENTE para a aba onde o próximo pacote da fila começará:
                # Para iMile no modo pacote solto, o próximo pacote inicia na Aba 2 (Descarregamento).
                # Para iMile modo padrão, Anjun e Loggi, inicia na Aba 1 (Entrada/Recebimento).
                aba_destino_fim = aba_recebimento
                if (p_id == 'imile' or 'imile' in str(p_id)) and pacote_solto and aba_descarregamento:
                    aba_destino_fim = aba_descarregamento
                
                if aba_destino_fim:
                    mudar_aba_acelerado(driver, aba_destino_fim)
                    if p_id == 'anjun' or 'anjun' in str(p_id):
                        try:
                            driver.execute_script("""
                                var inp = document.querySelector("input[placeholder*='digitalizar'], input[placeholder*='digitar'], input.el-input__inner:not([readonly])");
                                if (inp) { inp.focus(); }
                            """)
                        except Exception:
                            pass
                    elif p_id == 'imile' or 'imile' in str(p_id):
                        try:
                            driver.execute_script("""
                                var inp = document.querySelector("#scanNumber input, input[name='scanNumber'], input#scanNumber");
                                if (inp) { inp.focus(); }
                            """)
                        except Exception:
                            pass
            except Exception:
                pass
        driver_lock.release()

if __name__ == '__main__':
    # Inicializa o banco de dados SQLite e realiza migração dos JSONs legados
    inicializar_db()
    
    # Mantém a inicialização das configurações de plataformas
    carregar_plataformas()
    
    print("=" * 60)
    print(" SERVIDOR MULTI-PLATAFORMA DA TRIAGEM LOGÍSTICA INICIADO")
    print(" Porta: 5055 | CORS Habilitado")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5055, threaded=True)
