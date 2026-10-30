import os

import sys



def get_base_dir():

    raw_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

    try:

        test_file = os.path.join(raw_dir, ".write_test_app.tmp")

        with open(test_file, "w") as f:

            f.write("1")

        os.remove(test_file)

        return raw_dir

    except Exception:

        import shutil

        appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")

        fallback_dir = os.path.join(appdata, "TurboScan", "core-engine")

        os.makedirs(fallback_dir, exist_ok=True)

        for cfg_name in ["config_plataformas.json", "cloud_config.json", "pix_config.json", "versao.json"]:

            src_cfg = os.path.join(raw_dir, cfg_name)

            dst_cfg = os.path.join(fallback_dir, cfg_name)

            if os.path.exists(src_cfg) and not os.path.exists(dst_cfg):

                try:

                    shutil.copy2(src_cfg, dst_cfg)

                except Exception:

                    pass

        return fallback_dir



BASE_DIR = get_base_dir()

try:

    os.chdir(BASE_DIR)

except Exception:

    pass



# Garante saída UTF-8 no Windows e redireciona para log se executado sem console

if sys.platform.startswith('win'):

    try:

        log_file_path = os.path.join(BASE_DIR, 'app_engine.log')

        if sys.stdout is None:

            sys.stdout = open(log_file_path, 'a', encoding='utf-8', buffering=1)

        elif hasattr(sys.stdout, 'reconfigure'):

            sys.stdout.reconfigure(encoding='utf-8', errors='replace')

            

        if sys.stderr is None:

            sys.stderr = open(log_file_path, 'a', encoding='utf-8', buffering=1)

        elif hasattr(sys.stderr, 'reconfigure'):

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

from licenca import obter_hwid, validar_licenca, salvar_licenca, salvar_override_plataformas_local, _obter_config_supabase

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

    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)

    try:

        conn.execute("PRAGMA journal_mode=WAL;")

        conn.execute("PRAGMA synchronous=NORMAL;")

        conn.execute("PRAGMA busy_timeout=30000;")

    except Exception:

        pass

    return conn



# Estado Global do Selenium

driver = None

aba_recebimento = None

aba_descarregamento = None

aba_atribuicao = None

aba_atribuicao_anjun = None

plataforma_ativa = None

conta_ativa = None



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

bipes_ok_sessao = {}



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

            bairro TEXT,

            cep TEXT,

            endereco TEXT,

            produto TEXT

        )

    ''')

    

    # Executa de forma segura a adição de colunas caso elas não existam

    for col_sql in [

        "ALTER TABLE historico ADD COLUMN email TEXT",

        "ALTER TABLE historico ADD COLUMN valor_declarado TEXT",

        "ALTER TABLE historico ADD COLUMN negocios TEXT",

        "ALTER TABLE historico ADD COLUMN bairro TEXT",

        "ALTER TABLE historico ADD COLUMN status_entrega TEXT",

        "ALTER TABLE historico ADD COLUMN motorista_entrega TEXT",

        "ALTER TABLE historico ADD COLUMN tempo_atraso REAL",

        "ALTER TABLE historico ADD COLUMN cep TEXT",

        "ALTER TABLE historico ADD COLUMN endereco TEXT",

        "ALTER TABLE historico ADD COLUMN produto TEXT"

    ]:

        try:

            cursor.execute(col_sql)

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

            faixa_cep TEXT DEFAULT '',

            PRIMARY KEY (cidade, plataforma, motorista)

        )

    ''')

    try:

        cursor.execute("ALTER TABLE motoristas_plataforma ADD COLUMN faixa_cep TEXT DEFAULT ''")

    except Exception:

        pass

    try:

        cursor.execute("ALTER TABLE motoristas_plataforma ADD COLUMN bairros TEXT DEFAULT ''")

    except Exception:

        pass

    

    # 5. Tabela Divergências Pendentes

    cursor.execute('''

        CREATE TABLE IF NOT EXISTS divergencias_pendentes (

            codigo TEXT PRIMARY KEY,

            motorista_lote TEXT,

            motorista_esperado TEXT,

            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

            status TEXT DEFAULT 'pendente',

            cidade TEXT

        )

    ''')

    try:

        cursor.execute("ALTER TABLE divergencias_pendentes ADD COLUMN cidade TEXT")

    except Exception:

        pass

    

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



    # 7. Tabela Lote Pendente Anjun

    cursor.execute('''

        CREATE TABLE IF NOT EXISTS lote_pendente_anjun (

            waybill TEXT PRIMARY KEY,

            motorista TEXT,

            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP

        )

    ''')

    # 8. Tabela de Coletores Autorizados (Limite de PDAs / Celulares por Licença)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coletores_autorizados (
            device_id TEXT PRIMARY KEY,
            nome_dispositivo TEXT,
            ip TEXT,
            primeiro_acesso DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultimo_acesso DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'AUTORIZADO'
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

                    faixa_cep TEXT DEFAULT '',

                    PRIMARY KEY (cidade, plataforma, motorista)

                )

            ''')

            cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma_temp (cidade, plataforma, motorista) SELECT cidade, plataforma, motorista FROM motoristas_plataforma")

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

            # Novo: {"anjun": [{"cidade": "...", "motorista": "...", "faixa_cep": "..."}, ...]}

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

                                f_cep = (item.get("faixa_cep") or "").strip()

                                if cid and mot:

                                    cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid,))

                                    cursor.execute("INSERT OR IGNORE INTO motoristas_plataforma (cidade, plataforma, motorista, faixa_cep) VALUES (?, ?, ?, ?)", (cid, plat, mot, f_cep))

                                    if f_cep:

                                        cursor.execute("UPDATE motoristas_plataforma SET faixa_cep = ? WHERE LOWER(cidade) = LOWER(?) AND LOWER(plataforma) = LOWER(?) AND LOWER(motorista) = LOWER(?) AND (faixa_cep IS NULL OR faixa_cep = '')", (f_cep, cid, plat, mot))

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

    # Auto-limpeza silenciosa: preserva os últimos 90 dias de histórico e compacta o arquivo com VACUUM

    try:

        import datetime

        limite_90_dias = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y-%m-%d')

        cursor.execute("SELECT COUNT(*) FROM historico WHERE timestamp < ?", (limite_90_dias,))

        antigos_qtd = cursor.fetchone()[0]

        if antigos_qtd > 0:

            cursor.execute("DELETE FROM historico WHERE timestamp < ?", (limite_90_dias,))

            conn.commit()

            cursor.execute("VACUUM")

            print(f"[+] [Banco de Dados] Auto-limpeza concluída: {antigos_qtd} pacotes antigos (>90 dias) limpos e banco compactado!")

    except Exception as e_clean:

        print(f"[Aviso] Rotina de auto-limpeza do banco: {e_clean}")



    conn.close()



def obter_caminho_excel():

    caminho_padrao = os.path.join(BASE_DIR, EXCEL_MOTORISTAS)

    if os.path.exists(caminho_padrao):

        return caminho_padrao



    candidatos = [

        caminho_padrao,

        os.path.abspath(os.path.join(BASE_DIR, '..', '..', EXCEL_MOTORISTAS)),

        os.path.join(os.getcwd(), EXCEL_MOTORISTAS),

        os.path.abspath(os.path.join(BASE_DIR, '..', EXCEL_MOTORISTAS))

    ]

    if 'sistema de bipagem' in BASE_DIR.lower():

        candidatos.extend([

            os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', EXCEL_MOTORISTAS)),

            os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', '..', EXCEL_MOTORISTAS)),

            os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', '..', 'core-engine', EXCEL_MOTORISTAS)),

            os.path.join(os.path.expanduser('~'), 'Desktop', 'Sistema de Bipagem', 'core-engine', EXCEL_MOTORISTAS),

            os.path.join(os.path.expanduser('~'), 'Desktop', 'Sistema de Bipagem', EXCEL_MOTORISTAS)

        ])

    existentes = []

    vistos = set()

    for c in candidatos:

        c_abs = os.path.normcase(os.path.abspath(c))

        if c_abs not in vistos and os.path.exists(c):

            vistos.add(c_abs)

            existentes.append(c)

    if existentes:

        existentes.sort(key=lambda p: (os.path.getsize(p) > 6500, os.path.getmtime(p)), reverse=True)

        return existentes[0]

    return caminho_padrao



def sincronizar_excel_na_inicializacao():

    """

    Garante que a planilha Motoristas_Cidades.xlsx exista na pasta e seja sincronizada

    automaticamente no boot (especialmente em instalações novas ou quando editada).

    """

    excel_path = obter_caminho_excel()

    if not os.path.exists(excel_path):

        modelo_path = os.path.join(BASE_DIR, "Motoristas_Cidades_Modelo.xlsx")

        if os.path.exists(modelo_path):

            try:

                import shutil

                shutil.copy2(modelo_path, excel_path)

                print(f"[+] Inicialização: Planilha modelo criada em {excel_path} a partir de Motoristas_Cidades_Modelo.xlsx!")

            except Exception as e_cp:

                print(f"[Aviso] Falha ao copiar modelo de planilha: {e_cp}")

        if not os.path.exists(excel_path):

            try:

                gerar_planilha_motoristas_excel(excel_path)

            except Exception as e_gen:

                print(f"[Aviso] Não foi possível gerar planilha inicial: {e_gen}")

                return



    if os.path.exists(excel_path):

        try:

            mtime = os.path.getmtime(excel_path)

            meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

            deve_sincronizar = True



            if os.path.exists(meta_mtime_file):

                try:

                    with open(meta_mtime_file, 'r') as f_meta:

                        if abs(float(f_meta.read().strip()) - mtime) < 1.0:

                            deve_sincronizar = False

                except Exception:

                    pass

            if deve_sincronizar:

                ok, c_qtd, m_qtd, msg = sincronizar_motoristas_excel(excel_path)

                try:

                    with open(meta_mtime_file, 'w') as f_meta:

                        f_meta.write(str(mtime))

                except Exception:

                    pass

                if ok:

                    print(f"[+] Inicialização: Motoristas_Cidades.xlsx sincronizado automaticamente ({c_qtd} cidades, {m_qtd} mapeamentos) de {excel_path}!")

        except Exception as e_boot_excel:

            print(f"[Aviso] Sincronização automática do Excel no boot: {str(e_boot_excel)}")



def sincronizar_motoristas_excel(caminho_arquivo=None):

    """

    Importa cidades e motoristas a partir de uma planilha Excel (Motoristas_Cidades.xlsx).

    Se caminho_arquivo for None, busca pelo arquivo na pasta do sistema.

    Garante sincronização total entre o Excel, o banco SQLite e os arquivos JSON de compatibilidade.

    """

    if not caminho_arquivo:

        caminho_arquivo = obter_caminho_excel()

        

    if not os.path.exists(caminho_arquivo):

        return False, 0, 0, f"Planilha '{EXCEL_MOTORISTAS}' não encontrada na pasta."

        

    import openpyxl

    try:

        wb = openpyxl.load_workbook(caminho_arquivo, data_only=True)

        ws = wb.active

        

        cidades_para_inserir = set()

        mapeamentos_para_inserir = []

        col_cidade = -1

        col_motorista = -1

        col_plat = -1

        col_cep = -1

        col_bairro = -1

        col_plat_map = {}

        

        primeira_linha = [str(cell.value or '').strip() for cell in next(ws.iter_rows(min_row=1, max_row=1))]

        primeira_linha_upper = [v.upper() for v in primeira_linha]

        

        # 1. Suporte especial se o usuário importar a planilha de mapeamento de nomes (Motoristas.xlsx)

        if any('USUARIO IMILE' in v or 'MOTORISTA IMILE' in v or 'USUARIO ANJUN' in v for v in primeira_linha_upper):

            path_map = os.path.join(BASE_DIR, "Motoristas.xlsx")

            if os.path.abspath(caminho_arquivo) != os.path.abspath(path_map):

                import shutil

                shutil.copyfile(caminho_arquivo, path_map)

            imile_m, anjun_m = carregar_mapeamento_motoristas()

            return True, 0, len(imile_m) + len(anjun_m), f"Planilha de nomes de motoristas (Motoristas.xlsx) sincronizada com sucesso ({len(imile_m) + len(anjun_m)} mapeamentos)!"



        # 2. Busca aba dedicada de Cidades caso exista na planilha

        for sheetname in wb.sheetnames:

            if sheetname.strip().upper() in ['CIDADE', 'CIDADES']:

                try:

                    ws_cid = wb[sheetname]

                    for r in ws_cid.iter_rows(min_row=1, values_only=True):

                        if r and len(r) > 0 and r[0]:

                            val_c = str(r[0]).strip()

                            if val_c and val_c.upper() not in ['CIDADE', 'CIDADES', 'MUNICÍPIO', 'MUNICIPIO', 'NOME DA CIDADE', 'NONE', 'CIDADE CADASTRADA', 'SEM CIDADE', 'GERAL']:

                                cidades_para_inserir.add(val_c)

                except Exception:

                    pass



        # 3. Busca colunas padrão de Cidade, Motorista, Plataforma e CEP (Opcional) na aba ativa

        for idx, val in enumerate(primeira_linha_upper):

            if any(k in val for k in ['CIDADE', 'MUNICIP', 'DESTINO', 'PRAÇA', 'ROTA']):

                col_cidade = idx

            elif any(k in val for k in ['MOTORISTA', 'ENTREGADOR', 'CONDUTOR', 'NOME DO MOTORISTA']):

                col_motorista = idx

            elif any(k in val for k in ['PLATAFORMA', 'PLAT', 'EMPRESA', 'TRANSPORTADORA']):

                col_plat = idx

            elif any(k in val for k in ['CEP', 'FAIXA']):

                col_cep = idx

            elif any(k in val for k in ['BAIRRO', 'BAIRROS']):

                col_bairro = idx



        # 4. Se não tem coluna única 'MOTORISTA', mas tem colunas por plataforma ('ANJUN', 'IMILE', 'LOGGI')

        if col_cidade != -1 and col_motorista == -1:

            for idx, val in enumerate(primeira_linha_upper):

                if idx == col_cidade:

                    continue

                if 'ANJUN' in val:

                    col_plat_map['anjun'] = idx

                elif 'IMILE' in val:

                    col_plat_map['imile'] = idx

                elif 'LOGGI' in val:

                    col_plat_map['loggi'] = idx



        if col_cidade != -1:

            for row in ws.iter_rows(min_row=2, values_only=True):

                if not row or not any(row):

                    continue

                cidade = str(row[col_cidade] or '').strip() if col_cidade < len(row) and row[col_cidade] is not None else ''

                if not cidade or cidade.upper() in ['NONE', 'CIDADE', 'SEM CIDADE', 'GERAL']:

                    continue

                    

                cidades_para_inserir.add(cidade)

                faixa_cep_row = str(row[col_cep] or '').strip() if col_cep != -1 and col_cep < len(row) and row[col_cep] is not None else ''

                if faixa_cep_row.upper() == 'NONE':

                    faixa_cep_row = ''

                bairros_row = str(row[col_bairro] or '').strip() if col_bairro != -1 and col_bairro < len(row) and row[col_bairro] is not None else ''

                if bairros_row.upper() == 'NONE':

                    bairros_row = ''

                

                if col_plat_map:

                    for p_nome, c_idx in col_plat_map.items():

                        if c_idx < len(row) and row[c_idx]:

                            m_val = str(row[c_idx]).strip()

                            if m_val and m_val.upper() != 'NONE':

                                mapeamentos_para_inserir.append((cidade, p_nome, m_val, faixa_cep_row, bairros_row))

                elif col_motorista != -1:

                    motorista = str(row[col_motorista] or '').strip() if col_motorista < len(row) and row[col_motorista] is not None else ''

                    plat_raw = str(row[col_plat] or '').strip().lower() if col_plat != -1 and col_plat < len(row) and row[col_plat] is not None else 'todas'

                    

                    if not motorista or motorista.upper() == 'NONE':

                        continue

                        

                    if plat_raw in ['todas', 'geral', 'ambas', '', 'todos', 'none']:

                        platas = ['anjun', 'imile', 'loggi']

                    elif 'anjun' in plat_raw:

                        platas = ['anjun']

                    elif 'imile' in plat_raw:

                        platas = ['imile']

                    elif 'loggi' in plat_raw:

                        platas = ['loggi']

                    else:

                        platas = [plat_raw]

                        

                    for p in platas:

                        mapeamentos_para_inserir.append((cidade, p, motorista, faixa_cep_row, bairros_row))



        # 5. Suporte extra: se existir um arquivo Cidades.xlsx separado na pasta do sistema

        path_cidades_avulso = os.path.join(BASE_DIR, "Cidades.xlsx")

        if os.path.exists(path_cidades_avulso) and os.path.abspath(caminho_arquivo) != os.path.abspath(path_cidades_avulso):

            try:

                wb_c = openpyxl.load_workbook(path_cidades_avulso, data_only=True)

                for sheet in wb_c.worksheets:

                    for r in sheet.iter_rows(min_row=1, values_only=True):

                        if r and len(r) > 0 and r[0]:

                            c_val = str(r[0]).strip()

                            if c_val and c_val.upper() not in ['CIDADE', 'CIDADES', 'MUNICÍPIO', 'MUNICIPIO', 'NONE', 'SEM CIDADE', 'GERAL']:

                                cidades_para_inserir.add(c_val)

                wb_c.close()

            except Exception as e_cid_avulso:

                print(f"[Aviso] Leitura de Cidades.xlsx avulso: {str(e_cid_avulso)}")

                

        if not cidades_para_inserir and not mapeamentos_para_inserir:

            return False, 0, 0, "A planilha não contém registros válidos de Cidade ou Motorista."

            

        conn = conectar_banco()

        cursor = conn.cursor()

        

        if cidades_para_inserir:

            cursor.execute("DELETE FROM cidades")

            for cid in sorted(cidades_para_inserir):

                cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid,))

            

        if mapeamentos_para_inserir:

            # Preserva faixas de CEP existentes caso a planilha importada não tenha coluna de CEP

            faixas_existentes = {}

            bairros_existentes = {}

            if col_cep == -1 or col_bairro == -1:

                try:

                    cursor.execute("SELECT LOWER(cidade), LOWER(plataforma), LOWER(motorista), COALESCE(faixa_cep, ''), COALESCE(bairros, '') FROM motoristas_plataforma")

                    for c_old, p_old, m_old, f_old, b_old in cursor.fetchall():

                        faixas_existentes[(c_old, p_old, m_old)] = f_old or ""

                        bairros_existentes[(c_old, p_old, m_old)] = b_old or ""

                except Exception:

                    pass

            cursor.execute("DELETE FROM motoristas_plataforma")

            cursor.execute("DELETE FROM motoristas")

            for item_ins in mapeamentos_para_inserir:

                cid = item_ins[0]

                plat = item_ins[1]

                mot = item_ins[2]

                f_cep = item_ins[3] if len(item_ins) > 3 else ""

                b_val = item_ins[4] if len(item_ins) > 4 else ""

                f_final = f_cep if col_cep != -1 else faixas_existentes.get((cid.lower(), plat.lower(), mot.lower()), "")

                b_final = b_val if col_bairro != -1 else bairros_existentes.get((cid.lower(), plat.lower(), mot.lower()), "")

                cursor.execute("""

                    INSERT OR REPLACE INTO motoristas_plataforma (cidade, plataforma, motorista, faixa_cep, bairros)

                    VALUES (?, ?, ?, ?, ?)

                """, (cid, plat, mot, f_final, b_final))

                if plat == 'anjun':

                    cursor.execute("INSERT OR REPLACE INTO motoristas (cidade, motorista) VALUES (?, ?)", (cid, mot))

                

        conn.commit()

        conn.close()

        

        try:

            if cidades_para_inserir:

                with open(CONFIG_CIDADES, 'w', encoding='utf-8') as f_c:

                    json.dump(sorted(list(cidades_para_inserir)), f_c, indent=4, ensure_ascii=False)

                    

            if mapeamentos_para_inserir:

                mapeamento_completo = {}

                for cid, plat, mot, f_cep in mapeamentos_para_inserir:

                    if plat not in mapeamento_completo:

                        mapeamento_completo[plat] = []

                    item_json = {"cidade": cid, "motorista": mot}

                    if f_cep:

                        item_json["faixa_cep"] = f_cep

                    mapeamento_completo[plat].append(item_json)

                    

                with open(CONFIG_MOTORISTAS, 'w', encoding='utf-8') as f_m:

                    json.dump(mapeamento_completo, f_m, indent=4, ensure_ascii=False)

        except Exception as e_json_sync:

            print(f"[Aviso] Falha ao atualizar JSONs no sync do Excel: {str(e_json_sync)}")

            

        invalidar_cache_ram_cidades_motoristas()

        print(f"[+] Sincronização Excel: {len(cidades_para_inserir)} cidades e {len(mapeamentos_para_inserir)} mapeamentos sincronizados com sucesso!")

        return True, len(cidades_para_inserir), len(mapeamentos_para_inserir), f"{len(cidades_para_inserir)} cidades e {len(mapeamentos_para_inserir)} mapeamentos sincronizados com sucesso!"

    except Exception as e:

        print(f"[Erro] Falha ao sincronizar planilha Excel: {str(e)}")

        return False, 0, 0, f"Erro ao processar planilha: {str(e)}"



def gerar_planilha_motoristas_excel(caminho_destino=None):

    """

    Gera/atualiza o arquivo Motoristas_Cidades.xlsx com:

    Aba 1: 'Motoristas e Cidades' -> Lista de cidades e motoristas (incluindo motoristas sem cidade para o usuário preencher).

    Aba 2: 'Nomes de Motoristas do Sistema' -> Todos os nomes exatos do sistema (iMile e Anjun) prontos para copiar e colar.

    """

    if not caminho_destino:

        caminho_destino = obter_caminho_excel()

        

    import openpyxl

    from openpyxl.styles import Font, PatternFill, Alignment

    

    conn = conectar_banco()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT cidade, motorista, plataforma, COALESCE(faixa_cep, ''), COALESCE(bairros, '')

        FROM motoristas_plataforma 

        WHERE cidade NOT IN ('iMile', 'Anjun', 'Geral', 'Sem Cidade', '')

        ORDER BY plataforma ASC, cidade ASC, motorista ASC

    """)

    rows_mapeados = cursor.fetchall()

    conn.close()



    # Coleta todos os motoristas oficiais conhecidos de cada plataforma (cache em memória + bases salvas em disco)

    todos_motoristas_imile = []

    todos_motoristas_anjun = []

    try:

        for m in (globals().get('cache_motoristas_imile', {}).get("lista") or []):

            if m.get("daName"):

                todos_motoristas_imile.append(m["daName"].strip())

    except Exception:

        pass

    try:

        for m in (globals().get('cache_motoristas_anjun', {}).get("lista") or []):

            if m.get("username"):

                todos_motoristas_anjun.append(m["username"].strip())

    except Exception:

        pass

    try:

        dados_bases = carregar_motoristas_por_base_disco()

        for k_base, v_base in (dados_bases or {}).items():

            if not isinstance(v_base, dict):

                continue

            mots_b = v_base.get("motoristas") or []

            if str(k_base).startswith("imile:"):

                for mb in mots_b:

                    if mb and str(mb).strip():

                        todos_motoristas_imile.append(str(mb).strip())

            elif str(k_base).startswith("anjun:"):

                for mb in mots_b:

                    if mb and str(mb).strip():

                        todos_motoristas_anjun.append(str(mb).strip())

    except Exception:

        pass



    # Carrega também os do Motoristas.xlsx caso as APIs não tenham retornado tudo

    path_xlsx = os.path.join(BASE_DIR, "Motoristas.xlsx")

    if os.path.exists(path_xlsx):

        try:

            wb_ref = openpyxl.load_workbook(path_xlsx, data_only=True)

            ws_ref = wb_ref.active

            for r in list(ws_ref.iter_rows(values_only=True))[1:]:

                if r and len(r) > 0 and r[0] and str(r[0]).strip() and str(r[0]).strip() not in todos_motoristas_imile:

                    todos_motoristas_imile.append(str(r[0]).strip())

                if r and len(r) > 2 and r[2] and str(r[2]).strip() and str(r[2]).strip() not in todos_motoristas_anjun:

                    todos_motoristas_anjun.append(str(r[2]).strip())

            wb_ref.close()

        except Exception:

            pass



    todos_motoristas_imile = sorted(list(set(todos_motoristas_imile)), key=lambda s: s.lower())

    todos_motoristas_anjun = sorted(list(set(todos_motoristas_anjun)), key=lambda s: s.lower())



    wb = openpyxl.Workbook()

    

    # ----------------------------------------------------

    # ABA 1: Motoristas e Cidades (Planilha Principal)

    # ----------------------------------------------------

    ws1 = wb.active

    ws1.title = "Motoristas e Cidades"

    

    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")

    header_fill = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")

    

    ws1.append(["CIDADE", "MOTORISTA", "PLATAFORMA", "FAIXA DE CEP (OPCIONAL)", "BAIRROS (OPCIONAL)"])

    for cell in ws1[1]:

        cell.font = header_font

        cell.fill = header_fill

        cell.alignment = Alignment(horizontal="center", vertical="center")



    mots_imile_mapeados = set()

    mots_anjun_mapeados = set()

    

    for r_map in rows_mapeados:

        cid = r_map[0]

        mot = r_map[1]

        plat = r_map[2]

        f_cep = r_map[3] if len(r_map) > 3 else ""

        b_val = r_map[4] if len(r_map) > 4 else ""

        plat_cap = (plat or "TODAS").capitalize()

        ws1.append([cid, mot, plat_cap, f_cep or "", b_val or ""])

        if (plat or '').lower() == 'imile':

            mots_imile_mapeados.add(mot.strip().lower())

        elif (plat or '').lower() == 'anjun':

            mots_anjun_mapeados.add(mot.strip().lower())



    # Motoristas do sistema que ainda NÃO têm cidade definida

    # Adiciona com a coluna de cidade vazia para o usuário apenas digitar a cidade correspondente!

    mots_pendentes_imile = [m for m in todos_motoristas_imile if m.lower() not in mots_imile_mapeados]

    mots_pendentes_anjun = [m for m in todos_motoristas_anjun if m.lower() not in mots_anjun_mapeados]



    fill_pendente = PatternFill(start_color="FFFBEB", end_color="FFFBEB", fill_type="solid")



    for mot in mots_pendentes_imile:

        row_idx = ws1.max_row + 1

        ws1.append(["", mot, "Imile", ""])

        ws1.cell(row=row_idx, column=1).fill = fill_pendente



    for mot in mots_pendentes_anjun:

        row_idx = ws1.max_row + 1

        ws1.append(["", mot, "Anjun", ""])

        ws1.cell(row=row_idx, column=1).fill = fill_pendente



    ws1.column_dimensions['A'].width = 32

    ws1.column_dimensions['B'].width = 34

    ws1.column_dimensions['C'].width = 18

    ws1.column_dimensions['D'].width = 28

    ws1.column_dimensions['E'].width = 36



    # ----------------------------------------------------

    # ABA 2: Lista Completa de Motoristas do Sistema

    # ----------------------------------------------------

    ws2 = wb.create_sheet(title="Nomes do Sistema")

    ws2.append(["NOME EXATO NO SISTEMA", "PLATAFORMA", "STATUS NO SISTEMA"])

    for cell in ws2[1]:

        cell.font = header_font

        cell.fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")

        cell.alignment = Alignment(horizontal="center", vertical="center")



    for mot in todos_motoristas_imile:

        tem_cid = mot.lower() in mots_imile_mapeados

        status = "Cidade Já Vinculada" if tem_cid else "Pendente de Cidade"

        ws2.append([mot, "iMile", status])



    for mot in todos_motoristas_anjun:

        tem_cid = mot.lower() in mots_anjun_mapeados

        status = "Cidade Já Vinculada" if tem_cid else "Pendente de Cidade"

        ws2.append([mot, "Anjun", status])



    ws2.column_dimensions['A'].width = 36

    ws2.column_dimensions['B'].width = 18

    ws2.column_dimensions['C'].width = 24



    # ----------------------------------------------------

    # ABA 3: Lista de Cidades Cadastradas (Edição e Inclusão Fácil)

    # ----------------------------------------------------

    ws3 = wb.create_sheet(title="Cidades")

    ws3.append(["CIDADE CADASTRADA"])

    for cell in ws3[1]:

        cell.font = header_font

        cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")

        cell.alignment = Alignment(horizontal="center", vertical="center")



    try:

        conn_c = conectar_banco()

        cursor_c = conn_c.cursor()

        cursor_c.execute("SELECT cidade FROM cidades WHERE cidade NOT IN ('Sem Cidade', 'Geral', 'iMile', 'Anjun', '') ORDER BY cidade ASC")

        cidades_todas = [r[0] for r in cursor_c.fetchall() if r[0]]

        conn_c.close()

        for c_item in cidades_todas:

            ws3.append([c_item])

    except Exception as e_c_tab:

        print(f"[Aviso] Falha ao preencher aba Cidades no Excel: {e_c_tab}")



    ws3.column_dimensions['A'].width = 38



    wb.save(caminho_destino)



    # Espelha automaticamente a planilha salva em todos os caminhos do projeto para facilitar cópia para outros computadores

    try:

        import shutil

        espelhos = [

            os.path.join(BASE_DIR, EXCEL_MOTORISTAS),

            os.path.abspath(os.path.join(BASE_DIR, '..', '..', EXCEL_MOTORISTAS))

        ]

        if 'sistema de bipagem' in BASE_DIR.lower():

            espelhos.extend([

                os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', '..', EXCEL_MOTORISTAS)),

                os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', '..', 'core-engine', EXCEL_MOTORISTAS)),

                os.path.join(os.path.expanduser('~'), 'Desktop', 'Sistema de Bipagem', EXCEL_MOTORISTAS),

                os.path.join(os.path.expanduser('~'), 'Desktop', 'Sistema de Bipagem', 'core-engine', EXCEL_MOTORISTAS)

            ])

        orig_abs = os.path.normcase(os.path.abspath(caminho_destino))

        vistos_esp = {orig_abs}

        for esp in espelhos:

            esp_abs = os.path.normcase(os.path.abspath(esp))

            if esp_abs not in vistos_esp and os.path.isdir(os.path.dirname(esp)):

                vistos_esp.add(esp_abs)

                try:

                    shutil.copy2(caminho_destino, esp)

                except Exception:

                    pass

        meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

        with open(meta_mtime_file, 'w') as f_meta:

            f_meta.write(str(os.path.getmtime(caminho_destino)))

    except Exception as e_esp:

        print(f"[Aviso] Espelhamento de planilha Excel: {e_esp}")



    return caminho_destino





# --- CACHE DE ULTRA-ALTA VELOCIDADE EM MEMÓRIA RAM (0.0001ms de latência) ---

_CACHE_RAM_CIDADES = None

_CACHE_RAM_CIDADES_NORM_DICT = None

_CACHE_RAM_CIDADES_ORDENADAS = None

_CACHE_RAM_MOTORISTAS_CIDADE = {}

_CACHE_RAM_CEP = None



def invalidar_cache_ram_cidades_motoristas():

    global _CACHE_RAM_CIDADES, _CACHE_RAM_CIDADES_NORM_DICT, _CACHE_RAM_CIDADES_ORDENADAS, _CACHE_RAM_MOTORISTAS_CIDADE

    _CACHE_RAM_CIDADES = None

    _CACHE_RAM_CIDADES_NORM_DICT = None

    _CACHE_RAM_CIDADES_ORDENADAS = None

    _CACHE_RAM_MOTORISTAS_CIDADE = {}

    print("[Cache RAM] Cache de Cidades e Motoristas invalidado e atualizado.")



def remover_acentos(txt):

    if not txt:

        return ""

    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')



def normalizar_cidade_estrita(nome):

    """

    Normaliza um nome de cidade ou tag de grupo para comparação estrita:

    - Remove acentos, colchetes/parênteses (ex: [Placa: ...]), datas/números (ex: 06-10) e sufixo de UF (ex: - SP, /SP).

    - Preserva o nome completo da cidade para nunca confundir 'Itararé' com 'Bom Sucesso de Itararé' ou 'Ribeira' com 'Ribeirão Branco'.

    """

    if not nome:

        return ""

    s = remover_acentos(str(nome).strip().lower())

    s = re.sub(r'\[.*?\]|\(.*?\)', ' ', s)

    s = re.sub(r'\b\d{1,4}(?:[-/]\d{1,4})*\b', ' ', s)

    s = re.sub(r'(?:[\s,\-/]+)(?:sp|pr|mg|rj|sc|rs|ms|mt|go|df|ba|pe|ce|pa|am|ma|es|pb|rn|al|pi|se|ro|to|ac|ap|rr)$', '', s)

    s = re.sub(r'[\s\-_]+', ' ', s).strip()

    return s



def cidades_sao_iguais(cid_a, cid_b):

    """

    Compara se duas cidades (ou cidade e tag de grupo Loggi) são exatamente a mesma cidade,

    suportando múltiplas cidades separadas por vírgula ou barra, sem falsos positivos por substring.

    """

    if not cid_a or not cid_b:

        return False

    partes_a = [normalizar_cidade_estrita(p) for p in re.split(r'[,/;]+', str(cid_a)) if normalizar_cidade_estrita(p)]

    partes_b = [normalizar_cidade_estrita(p) for p in re.split(r'[,/;]+', str(cid_b)) if normalizar_cidade_estrita(p)]

    if not partes_a or not partes_b:

        return False

    return any(pa == pb for pa in partes_a for pb in partes_b)



def encontrar_cidade_mapeada(cidade_resolvida, lista_cidades=None):

    if not cidade_resolvida:

        return None

        

    global _CACHE_RAM_CIDADES_NORM_DICT, _CACHE_RAM_CIDADES_ORDENADAS

    if _CACHE_RAM_CIDADES_NORM_DICT is None or _CACHE_RAM_CIDADES_ORDENADAS is None:

        carregar_cidades()

        

    texto_raw = str(cidade_resolvida).strip()

    cidade_res_clean = remover_acentos(texto_raw.lower())

    cidade_res_estrita = normalizar_cidade_estrita(texto_raw)

    

    # 1. Correspondência exata instantânea via Dicionário Hash O(1) na Memória RAM (0.00001ms!)

    if _CACHE_RAM_CIDADES_NORM_DICT:

        if cidade_res_clean in _CACHE_RAM_CIDADES_NORM_DICT:

            return _CACHE_RAM_CIDADES_NORM_DICT[cidade_res_clean]

        if cidade_res_estrita and cidade_res_estrita in _CACHE_RAM_CIDADES_NORM_DICT:

            return _CACHE_RAM_CIDADES_NORM_DICT[cidade_res_estrita]

        

    # 2. Se a lista de cidades recebida por parâmetro for diferente da do banco, usa ela ordenada

    cidades_ordenadas = _CACHE_RAM_CIDADES_ORDENADAS

    if not cidades_ordenadas:

        cidades_ordenadas = sorted(lista_cidades or [], key=lambda c: len(c), reverse=True)

        

    # 3. Correspondência exata na lista ordenada

    for cidade in cidades_ordenadas:

        cidade_clean = remover_acentos(cidade.strip().lower())

        cidade_est = normalizar_cidade_estrita(cidade)

        if cidade_clean == cidade_res_clean or (cidade_est and cidade_est == cidade_res_estrita):

            return cidade

            

    # 4. Se a entrada já é o nome isolado de uma cidade (sem quebras de linha e curta),

    # NÃO faz busca parcial por palavra interna para jamais confundir 'Bom Sucesso de Itararé' com 'Itararé'!

    if "\n" not in texto_raw and len(texto_raw) <= 45:

        return None



    # 5. Apenas quando texto_raw é um bloco longo de endereço (fallback Selenium):

    # procura com limites de palavra, mas ignorando ocorrências precedidas de preposição ('de ', 'do ', 'da ', 'dos ', 'das ')

    for cidade in cidades_ordenadas:

        cidade_clean = remover_acentos(cidade.strip().lower())

        padrao = r'(?<!\bde\s)(?<!\bdo\s)(?<!\bda\s)(?<!\bdos\s)(?<!\bdas\s)(?:\b|^)' + re.escape(cidade_clean) + r'(?:\b|$)'

        if re.search(padrao, cidade_res_clean):

            return cidade

            

    return None



# --- HELPERS PARA CONSULTA DE CEP E VIA CEP (OTIMIZADO COM CACHE LOCAL NA RAM) ---

def carregar_cep_cache():

    global _CACHE_RAM_CEP

    if _CACHE_RAM_CEP is not None:

        return _CACHE_RAM_CEP

    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("SELECT cep, cidade FROM cep_cache")

        rows = cursor.fetchall()

        conn.close()

        _CACHE_RAM_CEP = {str(r[0]).strip(): str(r[1]).strip() for r in rows if r[0] and r[1]}

        return _CACHE_RAM_CEP

    except Exception:

        _CACHE_RAM_CEP = {}

        return _CACHE_RAM_CEP



def salvar_cep_cache(cache):

    global _CACHE_RAM_CEP

    _CACHE_RAM_CEP = dict(cache)

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

    cep_limpo = "".join(filter(str.isdigit, str(cep or "")))

    if len(cep_limpo) == 7:

        cep_limpo = "0" + cep_limpo

    if len(cep_limpo) != 8:

        return None

        

    # 1. Tenta obter do cache em memória RAM (Instantâneo 0.00001ms!)

    cache = carregar_cep_cache()

    if cep_limpo in cache:

        return cache[cep_limpo]

    cep_geral_municipio = cep_limpo[:5] + "000"

    if cep_geral_municipio in cache:

        return cache[cep_geral_municipio]

        

    def _consultar_apis_cep(c_alvo):

        # API 1: BrasilAPI (Super rápida via CDN Cloudflare)

        try:

            url = f"https://brasilapi.com.br/api/cep/v1/{c_alvo}"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

            with urllib.request.urlopen(req, timeout=1.0) as response:

                dados = json.loads(response.read().decode('utf-8'))

                if dados.get("city"):

                    print(f"[API] CEP {c_alvo} resolvido pela BrasilAPI: {dados['city']}")

                    return dados["city"]

        except Exception:

            pass



        # API 2: ViaCEP

        try:

            url = f"https://viacep.com.br/ws/{c_alvo}/json/"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

            with urllib.request.urlopen(req, timeout=1.0) as response:

                dados = json.loads(response.read().decode('utf-8'))

                if dados.get("localidade"):

                    print(f"[API] CEP {c_alvo} resolvido pelo ViaCEP: {dados['localidade']}")

                    return dados["localidade"]

        except Exception:

            pass



        # API 3: AwesomeAPI

        try:

            url = f"https://cep.awesomeapi.com.br/json/{c_alvo}"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

            with urllib.request.urlopen(req, timeout=1.0) as response:

                dados = json.loads(response.read().decode('utf-8'))

                if dados.get("city"):

                    print(f"[API] CEP {c_alvo} resolvido pela AwesomeAPI: {dados['city']}")

                    return dados["city"]

        except Exception:

            pass



        # API 4: OpenCEP (CDN estática ultra-rápida)

        try:

            url = f"https://opencep.com/v1/{c_alvo}.json"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

            with urllib.request.urlopen(req, timeout=1.0) as response:

                dados = json.loads(response.read().decode('utf-8'))

                if dados.get("localidade"):

                    print(f"[API] CEP {c_alvo} resolvido pelo OpenCEP: {dados['localidade']}")

                    return dados["localidade"]

        except Exception:

            pass

        return None



    # 2. Consulta o CEP exato nas APIs de alta velocidade

    cidade = _consultar_apis_cep(cep_limpo)



    # 3. Se for uma rua nova ainda não indexada nas APIs, consulta o CEP geral da cidade (XXXXX-000)

    if not cidade and cep_geral_municipio != cep_limpo:

        cidade = _consultar_apis_cep(cep_geral_municipio)



    # 4. Fallback local pelas faixas de CEP cadastradas nos motoristas

    if not cidade:

        try:

            conn_f = conectar_banco()

            cur_f = conn_f.cursor()

            cur_f.execute("SELECT cidade, faixa_cep FROM motoristas_plataforma WHERE faixa_cep IS NOT NULL AND faixa_cep != ''")

            for cid_db, f_cep_db in cur_f.fetchall():

                if cid_db and f_cep_db and cep_bate_com_regra(cep_limpo, f_cep_db):

                    cidade = str(cid_db).strip()

                    print(f"[+] CEP {cep_limpo} resolvido pela faixa de CEP local: {cidade}")

                    break

            conn_f.close()

        except Exception:

            pass



    if cidade:

        # Salva imediatamente no Cache RAM e persiste no SQLite em background

        cache[cep_limpo] = cidade

        import threading

        try:

            threading.Thread(target=salvar_cep_cache, args=(cache,), daemon=True).start()

        except Exception:

            salvar_cep_cache(cache)

    return cidade





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

    Evita estritamente inputs do dropdown de motorista (#daCode, menus e popovers).

    """

    if not driver:

        return None

        

    inicio_busca = time.time()

    while time.time() - inicio_busca < max(0.5, timeout):

        try:

            # 1. Busca o input diretamente no DOM via JS com seletores robustos

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

                    if (el.closest && (el.closest("#daCode") || el.closest(".popover") || el.closest(".popper") || el.closest(".dropdown") || el.closest(".Language") || el.closest("header") || el.closest(".MuiAutocomplete-root"))) {

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

                    if (elM.closest && (elM.closest("#daCode") || elM.closest(".popover") || elM.closest(".popper") || elM.closest(".dropdown") || elM.closest(".Language") || elM.closest("header") || elM.closest(".MuiAutocomplete-root"))) {

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

        except Exception:

            pass



        # 2. Fallbacks clássicos por XPath dentro do loop de tolerância

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

    Insere o código e envia exatamente 1 único Enter no campo de input da iMile (Aba 1, Aba 2, Aba 4).

    1. Reseta o _valueTracker e injeta o código via protótipo nativo para o React 18 / Material-UI.

    2. Dispara eventos input e change para atualizar o estado interno do componente.

    3. Envia 1 único Enter nativo via Selenium (sem disparos paralelos de Enter no JS),

       garantindo que o site processe a leitura com sucesso e sem submissão dupla.

    4. Conclui instantaneamente (50ms) sem travas ou esperas artificiais.

    """

    if not driver:

        return False

    if not campo:

        campo = obter_input_imile_html(driver, timeout=1.5)

    if not campo:

        print("[Aviso] Campo de bipe iMile não encontrado para envio.")

        return False



    codigo_limpo = str(codigo_qr or '').strip()

    if not codigo_limpo:

        return False



    # 1. Injeção direta reativa com suporte a React / Material-UI _valueTracker e eventos input/change

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



            // Reseta o _valueTracker do React para garantir que a mudança seja detectada

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



            // Dispara evento InputEvent para o React atualizar seu estado interno

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



            return (el.value === codigo);

        """, campo, codigo_limpo)

        print(f"[*] [iMile] Inserção reativa no campo: valor={codigo_limpo}, conferido={sucesso_js}")

    except Exception as e_js:

        print(f"[Aviso] Falha no preenchimento JS iMile: {str(e_js)}")



    # 2. Confirmação nativa via Selenium se o valor não foi retido pelo JS

    try:

        val_atual = campo.get_attribute('value')

        if not val_atual:

            print("[*] [iMile] Valor não retido via JS. Digitando via Selenium nativo...")

            campo.click()

            campo.send_keys(codigo_limpo)

    except Exception as e_sel:

        print(f"[Aviso] Falha na digitação Selenium iMile: {str(e_sel)}")



    # 3. Dispara exatamente 1 único Enter nativo (sem disparos concorrentes no JS para evitar bipe duplo)

    try:

        campo.send_keys(Keys.ENTER)

        print("[+] [iMile] Tecla Enter única enviada com sucesso!")

    except Exception:

        try:

            webdriver.ActionChains(driver).send_keys(Keys.ENTER).perform()

            print("[+] [iMile] Tecla Enter única enviada via ActionChains!")

        except Exception as e_ent:

            print(f"[Aviso] Falha ao enviar Enter iMile: {str(e_ent)}")



    # 4. Breve margem ultra-rápida (50ms) sem atraso artificial

    time.sleep(0.05)

    return True



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



def bipar_pacote_atribuicao_anjun(driver, codigo_qr):

    """

    Localiza o campo de bipe de pacote na Aba 3 (TaskAssignment) da Anjun Express,

    garantindo que não seja confundido com o dropdown do entregador.

    Digita o código nativamente e via Native Setter, submete com Enter,

    trata popups de reatribuição e aguarda confirmação.

    Retorna (sucesso: bool, contagem_site: int or None, erro_msg: str or None).

    """

    if not driver:

        return False, None, "Driver Selenium ausente."



    # 1. Garante que qualquer dropdown residual do entregador esteja fechado e sem foco

    try:

        driver.execute_script("""

            if (document.activeElement && (document.activeElement.classList.contains('el-select__input') || document.activeElement.getAttribute('role') === 'combobox')) {

                document.activeElement.blur();

            }

            var poppers = document.querySelectorAll('.el-select__popper, .el-popper');

            for (var p = 0; p < poppers.length; p++) {

                if (poppers[p].querySelector('.el-select-dropdown')) {

                    poppers[p].style.display = 'none';

                }

            }

        """)

    except Exception:

        pass



    # 2. Localiza o input de pacote com espera ativa de até 2.5s

    campo_pacote = None

    t0_find = time.time()

    while time.time() - t0_find < 2.5:

        try:

            campo_pacote = driver.execute_script("""

                function getAba3Input() {

                    // 1. Procura por placeholder específico de bipe (que NÃO seja do entregador)

                    var inputs = document.querySelectorAll("input:not([type='hidden'])");

                    for (var j = 0; j < inputs.length; j++) {

                        var el = inputs[j];

                        if (el.classList.contains('el-select__input') || el.getAttribute('role') === 'combobox') continue;

                        if (el.closest && (el.closest('.el-select') || el.closest('.el-select__wrapper'))) continue;

                        

                        var ph = (el.getAttribute('placeholder') || '').toLowerCase();

                        if (ph.includes('digitalizar') || ph.includes('digitar') || ph.includes('favor') || ph.includes('pacote') || ph.includes('rastreio')) {

                            if (el.offsetWidth > 0 || el.offsetHeight > 0 || el.offsetParent !== null) {

                                return el;

                            }

                        }

                    }



                    // 2. Procura por qualquer input.el-input__inner visível fora de el-select

                    var elInners = document.querySelectorAll("input.el-input__inner, input[type='text']:not([readonly])");

                    for (var k = 0; k < elInners.length; k++) {

                        var el2 = elInners[k];

                        if (el2.classList.contains('el-select__input') || el2.getAttribute('role') === 'combobox') continue;

                        if (el2.closest && (el2.closest('.el-select') || el2.closest('.el-select__wrapper') || el2.closest('.el-date-editor'))) continue;

                        if (el2.offsetWidth > 0 || el2.offsetHeight > 0 || el2.offsetParent !== null) {

                            return el2;

                        }

                    }

                    return null;

                }

                return getAba3Input();

            """)

        except Exception:

            pass



        if campo_pacote:

            break

        time.sleep(0.08)



    # Fallback via seletores Selenium clássicos

    if not campo_pacote:

        candidatos_pacote = [

            "//input[contains(@placeholder, 'digitalizar') or contains(@placeholder, 'digitar')][not(@role='combobox') and not(contains(@class, 'el-select__input'))]",

            "//input[@placeholder='Favor digitalizar ou digitar']",

            "//input[contains(@class, 'el-input__inner') and not(ancestor::*[contains(@class, 'el-select')])]",

            "//div[not(contains(@class, 'el-select'))]//input[contains(@class, 'el-input__inner') and not(@readonly)]"

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

        return False, None, "Não foi possível localizar o campo de input de bipe de pacote na Aba 3 da Anjun."



    # 3. Foco seguro no campo de pacote

    try:

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", campo_pacote)

    except Exception:

        pass



    try:

        campo_pacote.click()

    except Exception:

        try:

            driver.execute_script("arguments[0].click();", campo_pacote)

        except Exception:

            pass



    # 4. Envio do pacote: DIGITAÇÃO NATIVA + DISPARO DE EVENTOS VUE 3 / ELEMENT PLUS

    print(f"[*] Digitando e enviando pacote {codigo_qr} na Aba 3 da Anjun...")

    try:

        campo_pacote.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, codigo_qr + Keys.ENTER)

    except Exception as e_send_err:

        print(f"[Aviso] Falha no send_keys nativo da Aba 3: {e_send_err}")



    # Garante injeção direta no modelo do Vue e disparos de teclado (Enter keyCode: 13)

    try:

        driver.execute_script("""

            var el = arguments[0];

            var cod = arguments[1];

            if (el) {

                var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;

                if (nativeSetter) { nativeSetter.call(el, cod); } else { el.value = cod; }

                el.dispatchEvent(new Event('input', { bubbles: true }));

                el.dispatchEvent(new Event('change', { bubbles: true }));

                

                var keDown = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });

                el.dispatchEvent(keDown);

                var kePress = new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });

                el.dispatchEvent(kePress);

                var keUp = new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });

                el.dispatchEvent(keUp);

            }

        """, campo_pacote, codigo_qr)

    except Exception as e_typ:

        print(f"[Aviso] Falha ao disparar eventos JS na Aba 3: {e_typ}")



    # 5. Confirma modais de reatribuição se houverem (ex: pacote já em outra tarefa)

    time.sleep(0.2)

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

                        if (txt === 'confirmar' || txt === 'sim' || txt === 'ok' || txt === '确定') {

                            allBtns[b].click();

                            return;

                        }

                    }

                }

            }

        """)

    except Exception:

        pass



    # 6. Espera ativa para o site registrar o pacote e ler a contagem real

    time.sleep(0.3)

    contagem_site = None

    try:

        for _ in range(5):

            el_cont = driver.execute_script("""

                var el = document.querySelector("span.hasScan i, .hasScan, span[class*='hasScan'] i");

                if (el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.offsetParent !== null)) {

                    var txt = (el.innerText || el.textContent || '').trim();

                    var match = txt.match(/\\d+/);

                    if (match) return parseInt(match[0], 10);

                }

                return null;

            """)

            if el_cont is not None:

                contagem_site = int(el_cont)

                break

            time.sleep(0.08)

    except Exception:

        pass



    return True, contagem_site, None



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

        cursor.execute("SELECT timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, status_entrega, motorista_entrega, tempo_atraso, cep, endereco FROM historico")

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

                "tempo_atraso": r[16] if len(r) > 16 and r[16] is not None else 0.0,

                "cep": r[17] if len(r) > 17 and r[17] is not None else "",

                "endereco": r[18] if len(r) > 18 and r[18] is not None else ""

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

        

        backup_dir = os.path.join(BASE_DIR, 'backups')

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



detalhes_extras_pacote = {}



def formatar_nome_empresa_remetente(empresa_raw, codigo="", plataforma=""):

    emp = str(empresa_raw or "").strip()

    if emp in ["---", "None", "null", "****"]:

        emp = ""

    emp_up = emp.upper()

    # Traduz siglas corporativas conhecidas da Loggi / iMile / Anjun para nomes claros

    mapa_siglas = {

        "SHPS": "Shopee (SHPS)",

        "SHOPEE": "Shopee",

        "EBAZAR": "Mercado Livre (EBAZAR)",

        "MELI": "Mercado Livre",

        "MERCADO LIVRE": "Mercado Livre",

        "MERCADOLIVRE": "Mercado Livre",

        "TIKTOK": "TikTok Shop",

        "TIK TOK": "TikTok Shop",

        "TTS": "TikTok Shop",

        "SHEIN": "Shein",

        "SHN": "Shein",

        "TEMU": "Temu",

        "ALIEXPRESS": "AliExpress",

        "CN": "AliExpress / Cainiao",

        "CAINIAO": "AliExpress / Cainiao",

        "MAGALU": "Magazine Luiza",

        "MAGAZINE LUIZA": "Magazine Luiza",

        "AMAZON": "Amazon"

    }

    if emp_up in mapa_siglas:

        return mapa_siglas[emp_up]

    for k, v in mapa_siglas.items():

        if k in emp_up and len(k) >= 4:

            return f"{v} ({emp})" if emp.upper() != v.upper() else v

    if emp and emp.lower() not in ["loggi", "imile", "anjun"]:

        return emp

    # Inferência pelo prefixo do código de rastreio quando a API omite o remetente

    cod_up = str(codigo or "").strip().upper()

    if cod_up.startswith("TT"):

        return "TikTok Shop"

    return emp



def registrar_detalhes_extras_pacote(codigos, bairro="", telefone="", negocios="", produto="", valor_declarado="", recebedor="", cep="", endereco=""):

    if isinstance(codigos, (str, int)):

        codigos = [codigos]

    def _limpar(val):

        s = str(val or "").strip()

        return "" if s in ["---", "None", "null", "****"] else s

    b_val = _limpar(bairro)

    t_val = _limpar(telefone)

    n_val = _limpar(negocios)

    p_val = _limpar(produto)

    v_val = _limpar(valor_declarado)

    r_val = _limpar(recebedor)

    c_val = _limpar(cep)

    e_val = _limpar(endereco)

    for cod in (codigos or []):

        chave = str(cod or "").strip().upper()

        if not chave:

            continue

        atual = detalhes_extras_pacote.get(chave, {})

        detalhes_extras_pacote[chave] = {

            "bairro": b_val or atual.get("bairro", ""),

            "telefone": t_val or atual.get("telefone", ""),

            "negocios": formatar_nome_empresa_remetente(n_val or atual.get("negocios", ""), chave),

            "produto": p_val or atual.get("produto", ""),

            "valor_declarado": v_val or atual.get("valor_declarado", ""),

            "recebedor": r_val or atual.get("recebedor", ""),

            "cep": c_val or atual.get("cep", ""),

            "endereco": e_val or atual.get("endereco", "")

        }



def salvar_entrada_historico(codigo, plataforma, cidade, motorista, status, recebedor="---", telefone="---", email="---", tempo_criacao="---", status_pacote="---", valor_declarado="---", negocios="---", bairro="---", cep="", endereco="", produto="---"):

    global bipes_ok_sessao

    import datetime

    agora = datetime.datetime.now().isoformat()

    mot_salvar = motorista if motorista else "Sem Motorista"

    chave_cod = str(codigo or "").strip().upper()

    if str(status or "").upper() == "OK" and chave_cod:

        bipes_ok_sessao[chave_cod] = (agora, mot_salvar, cidade or "---")



    # Enriquecimento automático a partir dos detalhes capturados na API da transportadora

    extras = detalhes_extras_pacote.get(chave_cod, {})

    if extras:

        if (not recebedor or recebedor in ["---", "****"]) and extras.get("recebedor"):

            recebedor = extras["recebedor"]

        if (not telefone or telefone in ["---", "****"]) and extras.get("telefone"):

            telefone = extras["telefone"]

        if (not valor_declarado or valor_declarado == "---") and extras.get("valor_declarado"):

            valor_declarado = extras["valor_declarado"]

        if (not negocios or negocios == "---") and extras.get("negocios"):

            negocios = extras["negocios"]

        if (not bairro or bairro == "---") and extras.get("bairro"):

            bairro = extras["bairro"]

        if (not produto or produto == "---") and extras.get("produto"):

            produto = extras["produto"]

        if not cep and extras.get("cep"):

            cep = extras["cep"]

        if not endereco and extras.get("endereco"):

            endereco = extras["endereco"]



    negocios_fmt = formatar_nome_empresa_remetente(negocios if negocios != "---" else "", chave_cod, plataforma)

    if negocios_fmt:

        negocios = negocios_fmt



    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        try:

            cursor.execute('''

                INSERT INTO historico (timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, cep, endereco, produto)

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ''', (agora, codigo, plataforma, cidade, mot_salvar, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, cep, endereco, produto))

        except sqlite3.OperationalError:

            for col_add in ["cep", "endereco", "produto", "bairro", "negocios", "valor_declarado", "telefone"]:

                try:

                    cursor.execute(f"ALTER TABLE historico ADD COLUMN {col_add} TEXT")

                except Exception:

                    pass

            cursor.execute('''

                INSERT INTO historico (timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, cep, endereco, produto)

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ''', (agora, codigo, plataforma, cidade, mot_salvar, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, cep, endereco, produto))

        conn.commit()

        conn.close()

    except Exception as e:

        print(f"[Erro] Falha ao salvar entrada de histórico no SQLite: {str(e)}")



def carregar_cidades():

    global _CACHE_RAM_CIDADES, _CACHE_RAM_CIDADES_NORM_DICT, _CACHE_RAM_CIDADES_ORDENADAS

    if _CACHE_RAM_CIDADES is not None and len(_CACHE_RAM_CIDADES) > 0:

        return _CACHE_RAM_CIDADES

        

    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("SELECT cidade FROM cidades WHERE LOWER(TRIM(cidade)) NOT IN ('sem cidade', 'geral', 'imile', 'anjun', '') ORDER BY cidade COLLATE NOCASE ASC")

        rows = cursor.fetchall()

        if not rows:

            conn.close()

            try:

                sincronizar_motoristas_excel(obter_caminho_excel())

            except Exception:

                pass

            conn = conectar_banco()

            cursor = conn.cursor()

            cursor.execute("INSERT OR IGNORE INTO cidades (cidade) SELECT DISTINCT cidade FROM motoristas_plataforma WHERE cidade IS NOT NULL AND LOWER(TRIM(cidade)) NOT IN ('sem cidade', 'geral', 'imile', 'anjun', '')")

            conn.commit()

            cursor.execute("SELECT cidade FROM cidades WHERE LOWER(TRIM(cidade)) NOT IN ('sem cidade', 'geral', 'imile', 'anjun', '') ORDER BY cidade COLLATE NOCASE ASC")

            rows = cursor.fetchall()

        conn.close()

        cidades_unicas = []

        norm_dict = {}

        for r in rows:

            if r[0] and r[0].strip():

                cid = r[0].strip()

                chave_norm = remover_acentos(cid.lower())

                if cid.lower() not in ('sem cidade', 'geral', 'imile', 'anjun') and chave_norm not in norm_dict:

                    cidades_unicas.append(cid)

                    norm_dict[chave_norm] = cid

        _CACHE_RAM_CIDADES = cidades_unicas

        _CACHE_RAM_CIDADES_NORM_DICT = norm_dict

        _CACHE_RAM_CIDADES_ORDENADAS = sorted(cidades_unicas, key=lambda c: len(c), reverse=True)

        return _CACHE_RAM_CIDADES

    except Exception:

        return []



CONFIG_MOTORISTAS_POR_BASE = os.path.join(BASE_DIR, 'config_motoristas_por_base.json')

CONFIG_IMILE_TOKENS = os.path.join(BASE_DIR, 'config_imile_tokens.json')

cache_motoristas_anjun_por_conta = {}

cache_motoristas_imile_por_conta = {}



def obter_conta_ativa_plataforma(plataforma_id, conta_id_override=None):

    plat_key = str(plataforma_id or plataforma_ativa or "anjun").strip().lower()

    todas_contas = carregar_contas_plataformas()

    plat_info = todas_contas.get(plat_key, {})

    contas = plat_info.get("contas", [])

    c_id = str(conta_id_override or "").strip()

    if not c_id or c_id == "padrao":

        if plat_key == str(plataforma_ativa or "").strip().lower() and conta_ativa:

            c_id = conta_ativa

        else:

            c_id = plat_info.get("conta_ativa") or ""

    conta_obj = None

    for c in contas:

        if c.get("id") == c_id:

            conta_obj = c

            break

    if not conta_obj and contas:

        conta_obj = contas[0]

        c_id = conta_obj.get("id") or "conta_1"

    if not c_id:

        c_id = "conta_1"

    return c_id, (conta_obj or {})



def carregar_motoristas_por_base_disco():

    try:

        if os.path.exists(CONFIG_MOTORISTAS_POR_BASE):

            with open(CONFIG_MOTORISTAS_POR_BASE, 'r', encoding='utf-8') as f:

                return json.load(f) or {}

    except Exception:

        pass

    return {}



def salvar_motoristas_da_base(plat_id, conta_id, lista_nomes):

    try:

        if not plat_id or not conta_id or not isinstance(lista_nomes, list):

            return

        plat_clean = str(plat_id).strip().lower()

        conta_clean = str(conta_id).strip()

        chave = f"{plat_clean}:{conta_clean}"

        dados = carregar_motoristas_por_base_disco()

        atuais_salvos = []

        if isinstance(dados.get(chave), dict) and isinstance(dados[chave].get("motoristas"), list):

            atuais_salvos = dados[chave]["motoristas"]

        nomes_limpos = []

        vistos = set()

        for n in (list(lista_nomes) + list(atuais_salvos)):

            ns = str(n or "").strip()

            if ns and ns.lower() not in vistos:

                vistos.add(ns.lower())

                nomes_limpos.append(ns)

        dados[chave] = {

            "plataforma": plat_clean,

            "conta_id": conta_clean,

            "motoristas": nomes_limpos,

            "timestamp": time.time()

        }

        with open(CONFIG_MOTORISTAS_POR_BASE, 'w', encoding='utf-8') as f:

            json.dump(dados, f, ensure_ascii=False, indent=2)

    except Exception as e:

        print(f"[Aviso] Falha ao salvar motoristas da base {plat_id}:{conta_id}: {e}")



def obter_motoristas_da_base_salvos(plat_id, conta_id):

    chave = f"{str(plat_id).strip().lower()}:{str(conta_id).strip()}"

    dados = carregar_motoristas_por_base_disco()

    item = dados.get(chave)

    if isinstance(item, dict) and isinstance(item.get("motoristas"), list):

        return item["motoristas"]

    return []



def _normalizar_nome_base_comp(nome):

    return remover_acentos(str(nome or "").strip().lower()).replace('-', '').replace('_', '').replace(' ', '')



def obter_nomes_oficiais_base_ativa(plat_id, conta_id=None, forcar=False):

    plat_key = str(plat_id or plataforma_ativa or "anjun").strip().lower()

    cid, _ = obter_conta_ativa_plataforma(plat_key, conta_id)

    nomes_oficiais = []



    if not forcar:

        nomes_oficiais = obter_motoristas_da_base_salvos(plat_key, cid)



    if not nomes_oficiais and (forcar or driver is not None):

        if plat_key == 'anjun':

            try:

                fn_an = globals().get('carregar_motoristas_anjun_api')

                if fn_an:

                    lista_an, _ = fn_an(forcar=forcar, conta_id=cid)

                    nomes_oficiais = [(m.get("username") or "").strip() for m in (lista_an or []) if (m.get("username") or "").strip()]

            except Exception as e_an:

                print(f"[Aviso] Erro ao obter motoristas Anjun da base {cid}: {e_an}")

        elif plat_key == 'imile':

            try:

                fn_im = globals().get('carregar_motoristas_imile_api')

                if fn_im:

                    lista_im, _ = fn_im(forcar=forcar, conta_id=cid)

                    nomes_oficiais = [(m.get("daName") or "").strip() for m in (lista_im or []) if (m.get("daName") or "").strip()]

            except Exception as e_im:

                print(f"[Aviso] Erro ao obter motoristas iMile da base {cid}: {e_im}")



    if not nomes_oficiais:

        nomes_oficiais = obter_motoristas_da_base_salvos(plat_key, cid)



    # Também coleta nomes das OUTRAS bases da mesma plataforma para exclusão caso a base atual ainda não tenha sincronizado

    dados_disco = carregar_motoristas_por_base_disco()

    prefixo = f"{plat_key}:"

    nomes_outras_bases = []

    for k, v in dados_disco.items():

        if k.startswith(prefixo) and k != f"{plat_key}:{cid}" and isinstance(v, dict):

            nomes_outras_bases.extend(v.get("motoristas") or [])



    return cid, nomes_oficiais, nomes_outras_bases



def motorista_pertence_a_base_ativa(mot_nome, nomes_base_oficiais, nomes_outras_bases, plat_key):

    mot_norm = _normalizar_nome_base_comp(mot_nome)

    if not mot_norm:

        return False

    if not nomes_base_oficiais and not nomes_outras_bases:

        return True



    # Se a plataforma tem apenas 1 conta configurada (ou nenhuma outra base registrada), todos os motoristas mapeados pertencem a ela

    try:

        todas_contas = carregar_contas_plataformas()

        contas_plat = (todas_contas.get(str(plat_key or "").strip().lower(), {}) or {}).get("contas", [])

        if len(contas_plat) <= 1 and not nomes_outras_bases:

            return True

    except Exception:

        pass



    # Carrega apelidos da planilha Motoristas.xlsx caso haja tradução

    apelidos_norm = {mot_norm}

    try:

        imile_map, anjun_map = carregar_mapeamento_motoristas()

        mapa_plat = anjun_map if plat_key == 'anjun' else (imile_map if plat_key == 'imile' else {})

        for k_orig, v_trad in mapa_plat.items():

            kn = _normalizar_nome_base_comp(k_orig)

            vn = _normalizar_nome_base_comp(v_trad)

            if mot_norm in (kn, vn):

                apelidos_norm.add(kn)

                apelidos_norm.add(vn)

    except Exception:

        pass



    if nomes_base_oficiais:

        set_base = {_normalizar_nome_base_comp(x) for x in nomes_base_oficiais if x}

        for ap in apelidos_norm:

            if ap in set_base:

                return True

        if nomes_outras_bases:

            set_outras = {_normalizar_nome_base_comp(x) for x in nomes_outras_bases if x}

            for ap in apelidos_norm:

                if ap in set_outras:

                    return False

            return True

        return False



    if nomes_outras_bases:

        set_outras = {_normalizar_nome_base_comp(x) for x in nomes_outras_bases if x}

        for ap in apelidos_norm:

            if ap in set_outras:

                return False



    return True



def normalizar_faixa_cep(texto):

    """

    Padroniza qualquer formato digitado de CEP ou faixa de CEPs (com ou sem hífen, com 'a', 'ate', '-', etc.)

    para o formato padrão canônico (ex: '18873-000 a 18873-460' ou '18873-000').

    """

    if not texto:

        return ""

    partes = re.split(r'[,;]+', str(texto).strip())

    partes_norm = []

    padrao_range = re.compile(r'^\s*(\d{5}-?\d{3}|\d{2,5})\s*(?:a|ate|até|to|~|-)\s*(\d{5}-?\d{3}|\d{2,5})\s*$', re.IGNORECASE)

    for p in partes:

        p = p.strip()

        if not p:

            continue

        digitos_p = re.sub(r'\D', '', p)

        if len(digitos_p) == 8 and (re.match(r'^\d{8}$', p) or re.match(r'^\d{5}-\d{3}$', p)):

            partes_norm.append(f"{digitos_p[:5]}-{digitos_p[5:8]}")

            continue

        m = padrao_range.match(p)

        if m:

            ini_raw = re.sub(r'\D', '', m.group(1))

            fim_raw = re.sub(r'\D', '', m.group(2))

            ini_fmt = f"{ini_raw[:5]}-{ini_raw[5:8]}" if len(ini_raw) == 8 else ini_raw

            fim_fmt = f"{fim_raw[:5]}-{fim_raw[5:8]}" if len(fim_raw) == 8 else fim_raw

            partes_norm.append(f"{ini_fmt} a {fim_fmt}")

        else:

            if len(digitos_p) == 8:

                partes_norm.append(f"{digitos_p[:5]}-{digitos_p[5:8]}")

            else:

                partes_norm.append(p)

    return ", ".join(partes_norm)



def normalizar_bairro(txt):

    if not txt:

        return ""

    s = remover_acentos(str(txt).lower()).strip()

    s = re.sub(r'\bjd\.?\s*', 'jardim ', s)

    s = re.sub(r'\bvl\.?\s*', 'vila ', s)

    s = re.sub(r'\bpq\.?\s*', 'parque ', s)

    s = re.sub(r'\bres\.?\s*', 'residencial ', s)

    s = re.sub(r'\bconj\.?\s*', 'conjunto ', s)

    s = re.sub(r'\bbairro\s*', '', s)

    s = re.sub(r'[^a-z0-9\s]', ' ', s)

    return ' '.join(s.split())



def bairro_bate_com_regra(bairro_pacote, regra_bairros):

    """

    Verifica se o bairro do pacote bate com a lista de bairros permitidos para o motorista

    (ex: 'Centro, Jardim Europa, Vila Nova'). Suporta abreviações comuns (Jd., Vl., Pq.).

    """

    if not bairro_pacote or not regra_bairros:

        return False

    norm_pct = normalizar_bairro(bairro_pacote)

    if not norm_pct:

        return False

    partes = [b.strip() for b in re.split(r'[,;/]+', str(regra_bairros)) if b.strip()]

    for parte in partes:

        norm_r = normalizar_bairro(parte)

        if not norm_r:

            continue

        if norm_pct == norm_r:

            return True

        if len(norm_r) >= 3 and (norm_r in norm_pct or norm_pct in norm_r):

            return True

        words_r = set(norm_r.split())

        words_pct = set(norm_pct.split())

        if words_r and words_r.issubset(words_pct):

            return True

    return False



def cep_bate_com_regra(cep_pacote, regra_cep):

    """

    Verifica se o CEP do pacote (ex: '18701-700' ou '18701700') bate com a regra configurada

    para o motorista (ex: '18700-000 a 18705-999', '18700 a 18705', '070, 071', '18701-700').

    Retorna True se bater, False caso contrário.

    """

    if not cep_pacote or not regra_cep:

        return False

    cep_limpo = re.sub(r'\D', '', str(cep_pacote))

    if not cep_limpo:

        return False

    cep_8 = cep_limpo.ljust(8, '0')[:8]

    try:

        cep_num = int(cep_8)

    except Exception:

        return False



    # Primeiro unifica hifens de formato de CEP padrão (ex: 18700-000 -> 18700000)

    # para não confundir com hífen separador de faixa (ex: 18700000 - 18705999)

    regra_norm = re.sub(r'\b(\d{5})\s*-\s*(\d{3})\b', r'\1\2', str(regra_cep).lower())



    # Divide por vírgula, ponto-e-vírgula, barra ou quebra de linha

    partes = re.split(r'[,;/\n]+', regra_norm)

    for parte in partes:

        parte = parte.strip()

        if not parte:

            continue

        # Verifica se é uma faixa (ex: "18700000 a 18705999", "18700 ate 18705", "070 - 072")

        m_range = re.match(r'^(\d+)\s*(?:a|ate|até|-|~)\s*(\d+)$', parte)

        if m_range:

            ini_str, fim_str = m_range.group(1), m_range.group(2)

            ini_num = int(ini_str.ljust(8, '0')[:8])

            fim_num = int(fim_str.ljust(8, '9')[:8])

            if ini_num > fim_num:

                ini_num, fim_num = fim_num, ini_num

            if ini_num <= cep_num <= fim_num:

                return True

        else:

            # Prefixo ou CEP exato (ex: "070", "18701", "18701700")

            digitos = re.sub(r'\D', '', parte)

            if digitos and cep_8.startswith(digitos):

                return True

    return False





def carregar_motoristas(plataforma=None, conta_id=None):

    if not plataforma:

        plataforma = plataforma_ativa if plataforma_ativa else "anjun"

    plat_key = str(plataforma).strip().lower()



    cid_ativo, nomes_base_oficiais, nomes_outras_bases = (None, [], [])

    if plat_key in ('anjun', 'imile'):

        cid_ativo, nomes_base_oficiais, nomes_outras_bases = obter_nomes_oficiais_base_ativa(plat_key, conta_id)



    resultado = []

    motoristas_vistos = set()



    # 1. Carrega os mapeamentos reais de Cidade -> Motorista do banco de dados, filtrando pela Base Ativa!

    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("""

            SELECT cidade, motorista, COALESCE(faixa_cep, ''), COALESCE(bairros, '')

            FROM motoristas_plataforma

            WHERE LOWER(plataforma) = LOWER(?) AND cidade NOT IN ('iMile', 'Anjun', 'Geral', 'Sem Cidade', '')

            ORDER BY cidade COLLATE NOCASE ASC, motorista COLLATE NOCASE ASC

        """, (plat_key,))

        rows = cursor.fetchall()

        conn.close()



        for r in rows:

            cid = (r[0] or "").strip()

            mot = (r[1] or "").strip()

            f_cep = (r[2] or "").strip() if len(r) > 2 else ""

            bairros_val = (r[3] or "").strip() if len(r) > 3 else ""

            if cid and mot:

                if plat_key in ('anjun', 'imile') and not motorista_pertence_a_base_ativa(mot, nomes_base_oficiais, nomes_outras_bases, plat_key):

                    continue

                resultado.append({"cidade": cid, "motorista": mot, "faixa_cep": f_cep, "bairros": bairros_val})

                motoristas_vistos.add(mot.lower())

    except Exception as e_db:

        print(f"[Aviso] Erro ao carregar motoristas do banco: {e_db}")



    # Fallback para tabela antiga caso não haja registros e seja anjun

    if not resultado and plat_key == 'anjun':

        try:

            conn = conectar_banco()

            cursor = conn.cursor()

            cursor.execute("SELECT cidade, motorista FROM motoristas WHERE cidade NOT IN ('Anjun', 'Geral', '') ORDER BY cidade COLLATE NOCASE ASC, motorista COLLATE NOCASE ASC")

            rows = cursor.fetchall()

            conn.close()

            for r in rows:

                cid = (r[0] or "").strip()

                mot = (r[1] or "").strip()

                if cid and mot:

                    if not motorista_pertence_a_base_ativa(mot, nomes_base_oficiais, nomes_outras_bases, plat_key):

                        continue

                    resultado.append({"cidade": cid, "motorista": mot, "faixa_cep": ""})

                    motoristas_vistos.add(mot.lower())

        except Exception:

            pass



    # 2. Complementa com motoristas oficiais da BASE ATIVA que ainda NÃO estão vinculados a nenhuma cidade

    if plat_key in ('imile', 'anjun') and nomes_base_oficiais:

        for nome_da in nomes_base_oficiais:

            nome_limpo = str(nome_da or "").strip()

            if nome_limpo and nome_limpo.lower() not in motoristas_vistos:

                resultado.append({"cidade": "Sem Cidade", "motorista": nome_limpo, "faixa_cep": ""})

                motoristas_vistos.add(nome_limpo.lower())



    return resultado





def carregar_motoristas_cidade_detalhado(cidade, plataforma=None, cep=None, bairro=None):

    if not cidade:

        return [], False, False

    if not plataforma:

        plataforma = plataforma_ativa if plataforma_ativa else "anjun"

        

    plataforma_key = str(plataforma).strip().lower()

    cidade_clean = remover_acentos(str(cidade).strip().lower())

    cep_clean = re.sub(r'\D', '', str(cep or ''))

    bairro_clean = str(bairro or '').strip()

    

    global _CACHE_RAM_MOTORISTAS_CIDADE

    cache_key = (cidade_clean, plataforma_key)

    rows_cidade = _CACHE_RAM_MOTORISTAS_CIDADE.get(cache_key)

    

    if rows_cidade is None:

        try:

            conn = conectar_banco()

            cursor = conn.cursor()

            cursor.execute("""

                SELECT motorista, cidade, COALESCE(faixa_cep, ''), COALESCE(bairros, '')

                FROM motoristas_plataforma 

                WHERE LOWER(plataforma) = ?

                ORDER BY motorista COLLATE NOCASE ASC

            """, (plataforma_key,))

            rows = cursor.fetchall()

            conn.close()

            

            rows_cidade = [

                (r[0].strip(), (r[2] or "").strip(), (r[3] or "").strip() if len(r) > 3 else "")

                for r in rows

                if r[0] and r[0].strip() and remover_acentos(r[1].strip().lower()) == cidade_clean

            ]

            

            if not rows_cidade and plataforma_key == 'anjun':

                try:

                    conn2 = conectar_banco()

                    cursor2 = conn2.cursor()

                    cursor2.execute("SELECT motorista, cidade FROM motoristas")

                    rows2 = cursor2.fetchall()

                    conn2.close()

                    rows_cidade = [

                        (r[0].strip(), "", "")

                        for r in rows2

                        if r[0] and r[0].strip() and remover_acentos(r[1].strip().lower()) == cidade_clean

                    ]

                except Exception:

                    pass

                    

            _CACHE_RAM_MOTORISTAS_CIDADE[cache_key] = rows_cidade

        except Exception:

            return [], False, False



    if not rows_cidade:

        return [], False, False



    todos_motoristas = []

    for m_nome, _, _ in rows_cidade:

        if m_nome not in todos_motoristas:

            todos_motoristas.append(m_nome)



    tem_regra_cep = any(bool(f_cep) for _, f_cep, _ in rows_cidade)

    tem_regra_bairro = any(bool(b_str) for _, _, b_str in rows_cidade)

    tem_alguma_regra = tem_regra_cep or tem_regra_bairro



    if not tem_alguma_regra:

        return todos_motoristas, False, False



    candidatos_especificos = []

    candidatos_gerais = []



    for m_nome, f_cep, b_str in rows_cidade:

        tem_restricao_mot = bool(f_cep) or bool(b_str)

        if not tem_restricao_mot:

            if m_nome not in candidatos_gerais:

                candidatos_gerais.append(m_nome)

            continue



        bateu_cep = bool(cep_clean and f_cep and cep_bate_com_regra(cep_clean, f_cep))

        bateu_bairro = bool(bairro_clean and b_str and bairro_bate_com_regra(bairro_clean, b_str))



        if f_cep and b_str:

            if cep_clean and bairro_clean:

                if bateu_cep or bateu_bairro:

                    if m_nome not in candidatos_especificos:

                        candidatos_especificos.append(m_nome)

            elif cep_clean and bateu_cep:

                if m_nome not in candidatos_especificos:

                    candidatos_especificos.append(m_nome)

            elif bairro_clean and bateu_bairro:

                if m_nome not in candidatos_especificos:

                    candidatos_especificos.append(m_nome)

        elif f_cep and bateu_cep:

            if m_nome not in candidatos_especificos:

                candidatos_especificos.append(m_nome)

        elif b_str and bateu_bairro:

            if m_nome not in candidatos_especificos:

                candidatos_especificos.append(m_nome)



    if candidatos_especificos:

        return candidatos_especificos, True, tem_alguma_regra

    if candidatos_gerais:

        return candidatos_gerais, False, tem_alguma_regra



    return [], True, tem_alguma_regra



def carregar_motoristas_cidade(cidade, plataforma=None, cep=None, bairro=None):

    mots, _, _ = carregar_motoristas_cidade_detalhado(cidade, plataforma, cep, bairro)

    return mots



def obter_cidades_motorista(mot_clean, plataforma_key, da_nome_oficial=None):

    """

    Retorna a lista de cidades mapeadas especificamente para este motorista nesta plataforma.

    Ignora rótulos genéricos como 'iMile', 'Anjun', 'Geral', 'Sem Cidade'.

    """

    if not mot_clean or mot_clean in ["---", "Apenas Entrada (Sem Atribuição)"]:

        return []

    

    plat_key = str(plataforma_key or "").strip().lower()

    norm_mot = normalizar_cidade_estrita(mot_clean)

    norm_da = normalizar_cidade_estrita(da_nome_oficial) if da_nome_oficial else norm_mot



    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("""

            SELECT DISTINCT cidade, motorista

            FROM motoristas_plataforma

            WHERE LOWER(plataforma) = LOWER(?) AND cidade NOT IN ('iMile', 'Anjun', 'Geral', 'Sem Cidade', '')

        """, (plat_key,))

        rows = cursor.fetchall()

        conn.close()

    except Exception:

        return []



    cidades = []

    for cid, m in rows:

        cid_str = (cid or "").strip()

        m_str = (m or "").strip()

        if not cid_str or not m_str:

            continue

        m_norm = normalizar_cidade_estrita(m_str)

        if (norm_mot == m_norm or norm_da == m_norm or 

            (len(m_norm) >= 4 and (m_norm in norm_mot or norm_mot in m_norm)) or

            (len(norm_da) >= 4 and (m_norm in norm_da or norm_da in m_norm))):

            if cid_str not in cidades:

                cidades.append(cid_str)

    return cidades



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



    # Oculta Magalog enquanto não estiver liberada comercialmente

    plataformas.pop("magalog", None)

            

    # Mescla as credenciais locais e contas caso existam

    try:

        todas_contas = carregar_contas_plataformas()

        for p_id, info_contas in todas_contas.items():

            if p_id in plataformas:

                c_ativa = info_contas.get("conta_ativa")

                contas_list = info_contas.get("contas", [])

                conta_obj = None

                for c in contas_list:

                    if c.get("id") == c_ativa:

                        conta_obj = c

                        break

                if not conta_obj and contas_list:

                    conta_obj = contas_list[0]

                    c_ativa = conta_obj.get("id")

                if conta_obj:

                    plataformas[p_id]["login_usuario"] = conta_obj.get("login_usuario", "")

                    plataformas[p_id]["login_senha"] = conta_obj.get("login_senha", "")

                    plataformas[p_id]["conta_ativa_apelido"] = conta_obj.get("apelido", "")

                    plataformas[p_id]["conta_ativa_id"] = conta_obj.get("id", "")

                plataformas[p_id]["contas"] = contas_list

                plataformas[p_id]["conta_ativa"] = c_ativa

    except Exception as e_cred:

        print(f"[Aviso] Falha ao carregar credenciais locais: {str(e_cred)}")

            

    _cache_plataformas = plataformas

    return plataformas





def carregar_plataformas_licenciadas(lic=None):

    """Retorna apenas as plataformas liberadas na licença ativa desta máquina."""

    todas = carregar_plataformas()

    if lic is None:

        lic = validar_licenca()

    liberadas = [str(p).strip().lower() for p in (lic.get("plataformas_liberadas") or ["anjun", "imile", "loggi"]) if str(p).strip() and str(p).strip().lower() != "magalog"]

    if not liberadas:

        liberadas = ["anjun", "imile", "loggi"]

    filtradas = {}

    for k, v in todas.items():

        if k.lower() in liberadas:

            filtradas[k] = v

    return filtradas





# --- CONTROLE MULTI-LOGIN E PERFIS ISOLADOS ---

def carregar_contas_plataformas():

    """

    Carrega a lista de contas/logins de cada plataforma a partir de credenciais_locais.json.

    Garante suporte a múltiplas contas por plataforma mantendo compatibilidade com formato legado.

    """

    contas_por_plat = {}

    if os.path.exists(CONFIG_LOCAL_CREDENTIALS):

        try:

            with open(CONFIG_LOCAL_CREDENTIALS, 'r', encoding='utf-8') as f:

                dados_raw = json.load(f)

                

            for p_id, item in dados_raw.items():

                if not isinstance(item, dict):

                    continue

                    

                # Se já estiver no formato novo com lista de contas

                if "contas" in item and isinstance(item["contas"], list):

                    contas_validas = []

                    for c in item["contas"]:

                        if isinstance(c, dict):

                            c_id = str(c.get("id") or "").strip()

                            c_usr = str(c.get("login_usuario") or "").strip()

                            c_pass = str(c.get("login_senha") or "").strip()

                            c_apelido = str(c.get("apelido") or "").strip() or (c_usr or f"Conta {len(contas_validas)+1}")

                            if not c_id:

                                c_id = f"conta_{len(contas_validas)+1}"

                            contas_validas.append({

                                "id": c_id,

                                "apelido": c_apelido,

                                "login_usuario": c_usr,

                                "login_senha": c_pass

                            })

                    

                    c_ativa = item.get("conta_ativa")

                    if not c_ativa and contas_validas:

                        c_ativa = contas_validas[0]["id"]

                        

                    contas_por_plat[p_id] = {

                        "conta_ativa": c_ativa,

                        "contas": contas_validas

                    }

                else:

                    # Formato legado simples {"login_usuario": "...", "login_senha": "..."}

                    usr = str(item.get("login_usuario") or "").strip()

                    pwd = str(item.get("login_senha") or "").strip()

                    apelido = f"Conta Principal ({usr})" if usr else "Conta Principal"

                    contas_por_plat[p_id] = {

                        "conta_ativa": "conta_1",

                        "contas": [

                            {

                                "id": "conta_1",

                                "apelido": apelido,

                                "login_usuario": usr,

                                "login_senha": pwd

                            }

                        ]

                    }

        except Exception as e:

            print(f"[Aviso] Falha ao carregar credenciais locais: {e}")

            

    return contas_por_plat



def salvar_contas_plataformas(contas_dict):

    try:

        with open(CONFIG_LOCAL_CREDENTIALS, 'w', encoding='utf-8') as f:

            json.dump(contas_dict, f, indent=4, ensure_ascii=False)

        global _cache_plataformas

        _cache_plataformas = None

        return True

    except Exception as e:

        print(f"[Erro] Falha ao gravar credenciais locais: {e}")

        return False



def obter_perfil_e_porta_conta(plataforma_id, conta_id=None):

    diretorio_projeto = BASE_DIR

    porta_base = PORTAS_DEBUG.get(plataforma_id, 9222)

    

    todas_contas = carregar_contas_plataformas()

    plat_info = todas_contas.get(plataforma_id, {})

    contas = plat_info.get("contas", [])

    

    if not conta_id:

        conta_id = plat_info.get("conta_ativa")

        

    conta_obj = None

    indice = 0

    for idx, c in enumerate(contas):

        if c.get("id") == conta_id:

            conta_obj = c

            indice = idx

            break

            

    if not conta_obj and contas:

        conta_obj = contas[0]

        conta_id = conta_obj.get("id")

        indice = 0

        

    if indice == 0:

        # Primeira conta / Conta padrão: usa perfil e porta originais (preserva login existente no Chrome!)

        caminho_perfil = os.path.join(diretorio_projeto, f"perfil_robo_{plataforma_id}")

        porta = porta_base

    else:

        # Contas secundárias: perfil isolado e porta única

        caminho_perfil = os.path.join(diretorio_projeto, f"perfil_robo_{plataforma_id}_{conta_id}")

        offset_plat = {"imile": 10, "anjun": 20, "loggi": 30}.get(plataforma_id, 40)

        porta = 9240 + offset_plat + indice

        

    return caminho_perfil, porta, conta_id, conta_obj



# --- CONTROLE SELENIUM & SESSÃO PERSISTENTE ---

PORTAS_DEBUG = {

    "imile": 9222,

    "anjun": 9223,

    "loggi": 9224

}

CONFIG_SESSAO = os.path.join(BASE_DIR, 'config_sessao.json')



def salvar_sessao_ativa(plataforma, motorista=None, contagem=0, conta_id=None):

    global conta_ativa

    if conta_id:

        conta_ativa = conta_id

    try:

        dados = {

            "plataforma_ativa": plataforma,

            "conta_ativa": conta_ativa or "",

            "motorista_ativo": motorista if motorista else (motorista_atribuicao_ativa or ""),

            "contagem": contagem if contagem else (contagem_atribuicao_ativa or 0)

        }

        with open(CONFIG_SESSAO, 'w', encoding='utf-8') as f:

            json.dump(dados, f, indent=4, ensure_ascii=False)

    except Exception as e:

        print(f"[Aviso] Falha ao salvar sessão ativa: {e}")



def carregar_sessao_ativa():

    if os.path.exists(CONFIG_SESSAO):

        try:

            with open(CONFIG_SESSAO, 'r', encoding='utf-8') as f:

                return json.load(f)

        except Exception:

            pass

    return {}



def is_chrome_debug_active(port):

    if not port:

        return False

    try:

        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.8) as resp:

            return resp.status == 200

    except Exception:

        return False



def desconectar_selenium():

    """

    Apenas desconecta a referência do Python ao Chrome SEM fechar a janela do Chrome.

    Permite alternar entre contas e reiniciar servidor mantendo navegadores 100% abertos e logados.

    """

    global driver

    driver = None



def obter_pids_porta(porta):

    """Retorna o conjunto de PIDs que estão escutando (LISTENING) na porta local informada."""

    pids = set()

    if not porta:

        return pids

    try:

        import subprocess

        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if os.name == 'nt' else 0

        out = subprocess.check_output(

            f'netstat -ano | findstr :{porta}',

            shell=True,

            creationflags=flags,

            stderr=subprocess.DEVNULL

        ).decode('utf-8', errors='ignore')

        for line in out.splitlines():

            parts = line.strip().split()

            if len(parts) >= 5 and f":{porta}" in parts[1] and "LISTENING" in line.upper():

                try:

                    pid = int(parts[-1])

                    if pid > 0:

                        pids.add(pid)

                except Exception:

                    pass

    except Exception:

        pass

    return pids



def chrome_tem_janela_visivel_na_tela(porta):

    """

    Verifica se o processo Chrome que está escutando na porta de debug possui de fato

    uma janela de navegador real (Chrome_WidgetWin) na área de trabalho interativa atual (WinSta0\\Default).

    Evita conectar em processos Chrome zumbis/invisíveis ou iniciados em sessão oculta.

    """

    if os.name != 'nt':

        return True

    pids_porta = obter_pids_porta(porta)

    if not pids_porta:

        return False

    try:

        import ctypes

        user32 = ctypes.windll.user32

        encontrou = [False]

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)



        def enum_cb(hwnd, lparam):

            try:

                pid = ctypes.c_ulong()

                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                if pid.value in pids_porta:

                    if user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):

                        cls_buff = ctypes.create_unicode_buffer(64)

                        user32.GetClassNameW(hwnd, cls_buff, 64)

                        length = user32.GetWindowTextLengthW(hwnd)

                        if 'Chrome_WidgetWin' in cls_buff.value and length > 0:

                            encontrou[0] = True

                            return False

            except Exception:

                pass

            return True



        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        return encontrou[0]

    except Exception:

        return True



def matar_chrome_na_porta(porta):

    """Encerra processos Chrome órfãos/invisíveis que estejam prendendo a porta de debug."""

    pids = obter_pids_porta(porta)

    for pid in pids:

        try:

            import subprocess

            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if os.name == 'nt' else 0

            print(f"[*] Encerrando processo Chrome órfão/invisível na porta {porta} (PID {pid})...")

            subprocess.run(

                f"taskkill /F /T /PID {pid}",

                shell=True,

                creationflags=flags,

                stdout=subprocess.DEVNULL,

                stderr=subprocess.DEVNULL

            )

        except Exception:

            pass

    if pids:

        time.sleep(0.4)



def forcar_janela_chrome_visivel(porta=None, plat_alvo=None):

    """

    Garante que as janelas reais do navegador Chrome da transportadora selecionada

    estejam visiveis, restauradas, maximizadas e em primeiro plano, minimizando

    as janelas de outras transportadoras para evitar sobreposicao na tela.

    """

    try:

        import ctypes

        user32 = ctypes.windll.user32

        kernel32 = ctypes.windll.kernel32

        SW_HIDE = 0

        SW_MAXIMIZE = 3

        SW_SHOW = 5

        SW_MINIMIZE = 6

        SW_RESTORE = 9

        HWND_TOPMOST = -1

        HWND_NOTOPMOST = -2

        SWP_NOSIZE = 0x0001

        SWP_NOMOVE = 0x0002

        SWP_SHOWWINDOW = 0x0040



        p_resolvida = plat_alvo

        if not p_resolvida:

            if porta == 9222:

                p_resolvida = 'imile'

            elif porta == 9223:

                p_resolvida = 'anjun'

            elif porta == 9224:

                p_resolvida = 'loggi'

            elif plataforma_ativa:

                p_resolvida = str(plataforma_ativa).strip().lower()



        palavras_alvo = []

        palavras_outras = []

        if p_resolvida == 'loggi':

            palavras_alvo = ['loggi', 'arco']

            palavras_outras = ['anjun', 'newsupplier', 'imile', 'ds -', 'ds.imile']

        elif p_resolvida == 'anjun':

            palavras_alvo = ['anjun', 'newsupplier']

            palavras_outras = ['loggi', 'arco', 'imile', 'ds -', 'ds.imile']

        elif p_resolvida == 'imile':

            palavras_alvo = ['imile', 'ds -', 'ds.imile']

            palavras_outras = ['loggi', 'arco', 'anjun', 'newsupplier']



        pids_alvo = obter_pids_porta(porta) if porta else set()

        if not pids_alvo and p_resolvida:

            try:

                _, p_porta, _, _ = obter_perfil_e_porta_conta(p_resolvida, conta_ativa)

                if p_porta:

                    pids_alvo = obter_pids_porta(p_porta)

            except Exception:

                pass



        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        janelas_chrome = []



        def enum_cb(hwnd, lparam):

            try:

                length = user32.GetWindowTextLengthW(hwnd)

                if length <= 0:

                    return True

                buff = ctypes.create_unicode_buffer(length + 1)

                user32.GetWindowTextW(hwnd, buff, length + 1)

                title = buff.value.lower()



                if 'chromedriver' in title or 'cmd.exe' in title:

                    user32.ShowWindow(hwnd, SW_HIDE)

                    return True



                if 'turboscan' in title:

                    return True



                cls_buff = ctypes.create_unicode_buffer(64)

                user32.GetClassNameW(hwnd, cls_buff, 64)

                cls_name = cls_buff.value

                if 'Chrome_WidgetWin' not in cls_name:

                    return True



                pid = ctypes.c_ulong()

                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))



                if palavras_outras and any(k in title for k in palavras_outras):

                    try:

                        user32.ShowWindow(hwnd, SW_MINIMIZE)

                    except Exception:

                        pass

                    return True



                e_janela_alvo = False

                if pids_alvo and pid.value in pids_alvo:

                    e_janela_alvo = True

                elif palavras_alvo and any(k in title for k in palavras_alvo):

                    e_janela_alvo = True

                elif not pids_alvo and not palavras_alvo and any(k in title for k in [

                    'ds -', 'anjun', 'loggi', 'imile', 'google chrome', 'chrome', 'arco', 'newsupplier'

                ]):

                    e_janela_alvo = True



                if e_janela_alvo:

                    janelas_chrome.append(hwnd)

            except Exception:

                pass

            return True



        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)



        for hwnd in janelas_chrome:

            try:

                if user32.IsIconic(hwnd):

                    user32.ShowWindow(hwnd, SW_RESTORE)

                else:

                    user32.ShowWindow(hwnd, SW_SHOW)

                user32.ShowWindow(hwnd, SW_MAXIMIZE)



                fg_hwnd = user32.GetForegroundWindow()

                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

                target_tid = user32.GetWindowThreadProcessId(hwnd, None)

                cur_tid = kernel32.GetCurrentThreadId()



                if fg_tid and fg_tid != cur_tid:

                    user32.AttachThreadInput(cur_tid, fg_tid, True)

                if target_tid and target_tid != cur_tid:

                    user32.AttachThreadInput(cur_tid, target_tid, True)



                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

                user32.BringWindowToTop(hwnd)

                user32.SetForegroundWindow(hwnd)



                if fg_tid and fg_tid != cur_tid:

                    user32.AttachThreadInput(cur_tid, fg_tid, False)

                if target_tid and target_tid != cur_tid:

                    user32.AttachThreadInput(cur_tid, target_tid, False)

            except Exception:

                pass

    except Exception:

        pass



def conectar_chrome_existente(plataforma_id, conta_id=None):

    """

    Conecta instantaneamente ao Chrome existente via porta de debug sem abrir nova janela.

    """

    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, conta_ativa

    _, porta, cid_final, _ = obter_perfil_e_porta_conta(plataforma_id, conta_id)

    from selenium.webdriver.chrome.options import Options

    from selenium.webdriver.chrome.service import Service

    import subprocess

    attach_options = Options()

    attach_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{porta}")

    chrome_service = Service()

    chrome_service.creation_flags = subprocess.CREATE_NO_WINDOW

    driver = webdriver.Chrome(service=chrome_service, options=attach_options)

    try:

        driver.maximize_window()

        driver.execute_cdp_cmd("Page.bringToFront", {})

    except Exception:

        pass

    forcar_janela_chrome_visivel(porta, plat_alvo=plataforma_id)

    plataforma_ativa = plataforma_id

    conta_ativa = cid_final

    

    if plataforma_id == 'imile':

        cache_sessao_imile["access_token"] = None

        cache_sessao_imile["timestamp"] = 0

        garantir_abas_imile(driver)

        try:

            atualizar_sessao_imile(driver, forcar=True, conta_id=cid_final)

            carregar_motoristas_imile_api(forcar=True, conta_id=cid_final)

        except Exception:

            pass

    elif plataforma_id == 'anjun':

        cache_sessao_anjun["token"] = None

        cache_sessao_anjun["timestamp"] = 0

        cache_motoristas_anjun["lista"] = []

        cache_motoristas_anjun["timestamp"] = 0

        garantir_abas_anjun(driver)

        try:

            atualizar_sessao_anjun(driver, forcar=True)

            carregar_motoristas_anjun_api(forcar=True, conta_id=cid_final)

        except Exception:

            pass

    elif plataforma_id == 'loggi':

        if verificar_tela_login_loggi(driver):

            plataformas = carregar_plataformas()

            config_loggi = plataformas.get('loggi', {})

            fluxo_login_loggi(driver, config_loggi, seq_id=_init_seq_id)

        else:

            garantir_abas_loggi(driver)

    forcar_janela_chrome_visivel(porta, plat_alvo=plataforma_id)

    print(f"[+] Conectado com sucesso ao Chrome da plataforma '{plataforma_id}' (Conta: {conta_ativa}, porta {porta})!")



def is_driver_ativo(rapido=True):

    global driver, plataforma_ativa, conta_ativa

    if plataforma_ativa:

        try:

            _, _chk_porta, _chk_cid, _ = obter_perfil_e_porta_conta(plataforma_ativa, conta_ativa)

            if not is_chrome_debug_active(_chk_porta) or not chrome_tem_janela_visivel_na_tela(_chk_porta):

                driver = None

                return False

            if not driver:

                conectar_chrome_existente(plataforma_ativa, _chk_cid)

                return True

        except Exception:

            pass

    if not driver:

        # Se não há driver em memória, mas o Chrome está aberto e visível na porta de debug da plataforma/conta ativa:

        if plataforma_ativa:

            _, porta, cid, _ = obter_perfil_e_porta_conta(plataforma_ativa, conta_ativa)

            if porta and is_chrome_debug_active(porta) and chrome_tem_janela_visivel_na_tela(porta):

                try:

                    print(f"[*] Reconectando ao Chrome ativo na porta {porta}...")

                    conectar_chrome_existente(plataforma_ativa, cid)

                    return True

                except Exception:

                    pass

        return False

    try:

        if rapido:

            # Em modo rápido (fluxo contínuo de bipes), validação em memória instantânea (~0ms)

            return bool(getattr(driver, 'session_id', None))

        # Acesso completo para testar se a sessão ainda responde

        _ = driver.window_handles

        return True

    except Exception:

        # Sessão do WebDriver teve interrupção (ex: suspensão ou hibernação do Windows)

        # NÃO fecha o Chrome! Tenta reconectar diretamente ao Chrome existente na porta de debug!

        driver = None

        if plataforma_ativa:

            _, porta, cid, _ = obter_perfil_e_porta_conta(plataforma_ativa, conta_ativa)

            if porta and is_chrome_debug_active(porta) and chrome_tem_janela_visivel_na_tela(porta):

                try:

                    print(f"[*] Sessão Selenium perdida pós-hibernação. Reconectando à porta {porta}...")

                    conectar_chrome_existente(plataforma_ativa, cid)

                    return True

                except Exception:

                    pass

        return False



def fechar_selenium():

    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, motorista_atribuicao_ativa, contagem_atribuicao_ativa, switches_imile_ativados

    if driver:

        try:

            driver.quit()

        except Exception:

            pass

        time.sleep(0.5)  # Aguarda liberação de locks no Windows

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



def verificar_tela_login_loggi(drv):

    """

    Retorna True se o navegador estiver na tela de login da Loggi (Arco)

    """

    if not drv:

        return False

    try:

        url = (drv.current_url or '').lower()

        if not url or url.startswith("data:") or url.startswith("about:"):

            return True

        if "login" in url or "auth" in url or "accounts.google.com" in url:

            return True

        if "arco.loggi.com" in url:

            if url.rstrip('/') in ["https://arco.loggi.com", "http://arco.loggi.com"]:

                return True

            res = drv.execute_script("""

                var txt = (document.body ? document.body.innerText : '').toLowerCase();

                if (txt.includes('acesse o arco') || txt.includes('entrar com o google') || txt.includes('esqueceu sua senha')) {

                    return true;

                }

                var btns = document.querySelectorAll("button");

                for (var i = 0; i < btns.length; i++) {

                    var bTxt = (btns[i].innerText || btns[i].textContent || '').toLowerCase();

                    if (bTxt.includes('entrar com o google')) return true;

                }

                return false;

            """)

            if res:

                return True

    except Exception:

        pass

    return False



def tentar_clicar_login_google_loggi(drv):

    """

    Tenta clicar automaticamente no botão 'Entrar com o Google' da Loggi no Chrome.

    """

    if not drv:

        return False

    try:

        res = drv.execute_script("""

            var btns = document.querySelectorAll("button, [role='button'], a");

            for (var i = 0; i < btns.length; i++) {

                var btn = btns[i];

                var txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();

                if (txt.includes('entrar com o google') || (txt.includes('google') && txt.includes('entrar'))) {

                    try { btn.focus(); } catch(e){}

                    btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));

                    btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));

                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

                    btn.click();

                    return true;

                }

            }

            return false;

        """)

        if res:

            return True

            

        xpaths = [

            "//button[contains(., 'Entrar com o Google') or contains(., 'com o Google')]",

            "//button[contains(span, 'Google') or contains(., 'Google')]",

            "//button[contains(@class, 'MuiButton-fullWidth') and contains(., 'Google')]"

        ]

        for xp in xpaths:

            try:

                elems = drv.find_elements(By.XPATH, xp)

                for el in elems:

                    if el.is_displayed():

                        drv.execute_script("arguments[0].click();", el)

                        return True

            except Exception:

                continue

    except Exception as e:

        print(f"[!] Erro ao tentar clicar 'Entrar com o Google': {e}")

    return False



def extrair_codigo_base_loggi(driver_ou_url):

    """

    Extrai dinamicamente o código da base da Loggi (ex: 'ERE', 'AV3', 'POA') da URL ou abas.

    """

    ignorar = {'login', 'auth', 'signin', 'static', 'api', 'logout', 'oauth', 'token'}

    if isinstance(driver_ou_url, str):

        urls = [driver_ou_url]

    elif driver_ou_url:

        urls = []

        orig_handle = None

        try:

            orig_handle = driver_ou_url.current_window_handle

            urls.append(driver_ou_url.current_url or '')

        except Exception:

            pass

        try:

            for h in driver_ou_url.window_handles:

                if h != orig_handle:

                    try:

                        driver_ou_url.switch_to.window(h)

                        urls.append(driver_ou_url.current_url or '')

                    except Exception:

                        pass

            if orig_handle:

                driver_ou_url.switch_to.window(orig_handle)

        except Exception:

            pass

    else:

        urls = []

        

    for u in urls:

        if 'arco.loggi.com' in u.lower():

            m = re.search(r'arco\.loggi\.com/([a-zA-Z0-9_-]+)', u)

            if m:

                code = m.group(1).upper()

                if code.lower() not in ignorar:

                    return code

    return 'AV3'



def garantir_abas_loggi(driver):

    global aba_recebimento, aba_atribuicao, aba_atribuicao_anjun

    if not driver:

        return

    try:

        handles = driver.window_handles

        if not handles:

            return

            

        # Se estiver na tela de login, NÃO tenta abrir novas abas!

        if verificar_tela_login_loggi(driver):

            if handles:

                aba_recebimento = handles[0]

            return



        base_code = extrair_codigo_base_loggi(driver)

        recebimento_url = f'https://arco.loggi.com/{base_code}/na-base/colecoes'

        hoje_url = f'https://arco.loggi.com/{base_code}/hoje'

        grupos_url = f'https://arco.loggi.com/{base_code}/na-base/grupos'



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

            driver.execute_script(f"window.open('{grupos_url}', '_blank');")

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

                        aba_rec_ok = True

                        break

                except Exception:

                    continue



        if not aba_rec_ok:

            for h in handles:

                if h != aba_atribuicao_anjun:

                    aba_recebimento = h

                    break

            if aba_recebimento:

                try:

                    driver.switch_to.window(aba_recebimento)

                    if "colecoes" not in driver.current_url.lower():

                        driver.get(recebimento_url)

                        time.sleep(1.0)

                except Exception:

                    pass

                    

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

            print("[*] Aba Hoje da Loggi ausente. Abrindo nova aba de hoje...")

            driver.execute_script(f"window.open('{hoje_url}', '_blank');")

            time.sleep(1.0)

            for h in driver.window_handles:

                try:

                    driver.switch_to.window(h)

                    if "hoje" in driver.current_url.lower():

                        aba_atribuicao = h

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



def fluxo_login_loggi(driver, config, seq_id=None):

    """

    Executa o fluxo de inicialização e autenticação da Loggi:

    1. Mantém estritamente apenas 1 aba aberta durante o login

    2. Acessa a URL de coleções/recebimento

    3. Clica automaticamente em 'Entrar com o Google'

    4. Aguarda a autenticação ser concluída (URL contendo /AV3/ e sem tela de login)

    5. Somente após a autenticação confirmada, abre a Aba 2 (Hoje) e Aba 3 (Grupos)

    """

    print("[*] Iniciando fluxo de login para a Loggi...")

    

    # 1. Fecha qualquer aba extra para manter estritamente apenas a primeira aba

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

        

    recebimento_url = config.get('recebimento_url', 'https://arco.loggi.com/')

    

    # 2. Navega até a página

    curr_url = (driver.current_url or '').lower()

    esta_na_area_operacional = "arco.loggi.com" in curr_url and not verificar_tela_login_loggi(driver)

    if not esta_na_area_operacional or verificar_tela_login_loggi(driver):

        driver.get(recebimento_url)

        time.sleep(2.0)

        

        # Tenta auto-clicar em "Entrar com o Google" de imediato

        tentar_clicar_login_google_loggi(driver)

        

        print("[*] Aguardando o login ser concluído no navegador para Loggi...")

        login_concluido = False

        inicio_login = time.time()

        while time.time() - inicio_login < 20.0:

            if seq_id and _init_seq_id != seq_id:

                return

            try:

                if not driver or not driver.window_handles:

                    break

                current_url = driver.current_url.lower()

                if "arco.loggi.com" in current_url and not verificar_tela_login_loggi(driver):

                    base_detectada = extrair_codigo_base_loggi(driver)

                    print(f"[+] Login Loggi detectado com sucesso: {current_url} | Base: {base_detectada}")

                    login_concluido = True

                    break

                else:

                    tentar_clicar_login_google_loggi(driver)

            except Exception:

                pass

            time.sleep(1.0)

            

        if not login_concluido:

            print("[Aviso] Login da Loggi ainda não concluído. Janela aberta para o operador.")

            return

            

    # 3. Detecta a base da unidade (ex: ERE, AV3, etc.)

    base_code = extrair_codigo_base_loggi(driver) or 'AV3'

    print(f"[*] Base Loggi identificada: {base_code}")

    recebimento_url = f"https://arco.loggi.com/{base_code}/na-base/colecoes"

    hoje_url = f"https://arco.loggi.com/{base_code}/hoje"

    grupos_url = f"https://arco.loggi.com/{base_code}/na-base/grupos"

            

    # 4. Garante que a primeira aba esteja na tela de coleções/recebimento da base detectada

    try:

        if "colecoes" not in driver.current_url.lower():

            driver.get(recebimento_url)

            time.sleep(1.5)

    except Exception:

        pass



    # 4. Somente após login confirmado, abre as abas 2 e 3

    print("[*] Autenticação confirmada! Abrindo abas operacionais da Loggi...")

    handles_atuais = driver.window_handles

    

    # Aba 2 (Hoje)

    tem_hoje = False

    for h in handles_atuais:

        try:

            driver.switch_to.window(h)

            if "hoje" in driver.current_url.lower():

                tem_hoje = True

                break

        except Exception:

            pass

    if not tem_hoje:

        driver.execute_script(f"window.open('{hoje_url}', '_blank');")

        time.sleep(0.8)

        

    # Aba 3 (Grupos)

    handles_atuais = driver.window_handles

    tem_grupos = False

    for h in handles_atuais:

        try:

            driver.switch_to.window(h)

            if "grupos" in driver.current_url.lower():

                tem_grupos = True

                break

        except Exception:

            pass

    if not tem_grupos:

        driver.execute_script(f"window.open('{grupos_url}', '_blank');")

        time.sleep(0.8)

        

    garantir_abas_loggi(driver)

    

    global aba_recebimento

    try:

        if aba_recebimento and aba_recebimento in driver.window_handles:

            driver.switch_to.window(aba_recebimento)

    except Exception:

        pass



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



def garantir_abas_anjun(driver):

    """

    Garante que as 3 abas da Anjun Express estejam abertas, válidas e mapeadas:

    Aba 1 (aba_recebimento): netEntryScanning (Entrada / Recebimento de Pacotes)

    Aba 2 (aba_atribuicao): packageQuery (Consulta de Pacotes)

    Aba 3 (aba_atribuicao_anjun): TaskAssignment (Atribuição de Tarefas / Motoristas)

    Se alguma aba foi fechada, recarregada ou perdida, recupera ou reabre automaticamente.

    """

    global aba_recebimento, aba_atribuicao, aba_atribuicao_anjun

    if not driver:

        return

    try:

        handles = driver.window_handles

        if not handles:

            return



        # 1. Verifica e valida Aba 3 (Atribuição de Motoristas / TaskAssignment)

        aba3_ok = False

        if aba_atribuicao_anjun and aba_atribuicao_anjun in handles:

            try:

                driver.switch_to.window(aba_atribuicao_anjun)

                u = (driver.current_url or '').lower()

                tit = (driver.title or '').lower()

                if "taskassignment" in u or ("operatingcenter" in u and "netentry" not in u) or "atribuir" in tit or "tarefa" in tit:

                    aba3_ok = True

            except Exception:

                pass



        if not aba3_ok:

            aba_atribuicao_anjun = None

            for h in handles:

                try:

                    driver.switch_to.window(h)

                    u = (driver.current_url or '').lower()

                    tit = (driver.title or '').lower()

                    if "taskassignment" in u or ("operatingcenter" in u and "netentry" not in u) or "atribuir" in tit or "tarefa" in tit:

                        aba_atribuicao_anjun = h

                        aba3_ok = True

                        print(f"[+] Aba 3 Anjun (Atribuição/TaskAssignment) mapeada dinamicamente: {h}")

                        break

                except Exception:

                    continue



        # Se a Aba 3 não existe, abre-a em nova aba

        if not aba3_ok:

            print("[*] Aba 3 da Anjun (TaskAssignment) ausente. Abrindo nova aba...")

            driver.execute_script("window.open('https://newsupplier.anjunexpress.com/#/views/operatingCenter/TaskAssignment', '_blank');")

            time.sleep(1.2)

            for h in driver.window_handles:

                try:

                    driver.switch_to.window(h)

                    u = (driver.current_url or '').lower()

                    tit = (driver.title or '').lower()

                    if "taskassignment" in u or "atribuir" in tit or "tarefa" in tit:

                        aba_atribuicao_anjun = h

                        aba3_ok = True

                        print(f"[+] Nova Aba 3 da Anjun criada e mapeada: {h}")

                        break

                except Exception:

                    continue



        # 2. Garante Aba 1 (Entrada / netEntryScanning)

        aba1_ok = False

        if aba_recebimento and aba_recebimento in handles and aba_recebimento != aba_atribuicao_anjun:

            try:

                driver.switch_to.window(aba_recebimento)

                u = (driver.current_url or '').lower()

                tit = (driver.title or '').lower()

                if "netentryscanning" in u or "recebimento" in u or "recepcionar" in tit:

                    aba1_ok = True

            except Exception:

                pass



        if not aba1_ok:

            for h in handles:

                if h == aba_atribuicao_anjun:

                    continue

                try:

                    driver.switch_to.window(h)

                    u = (driver.current_url or '').lower()

                    tit = (driver.title or '').lower()

                    if "netentryscanning" in u or "recebimento" in u or "recepcionar" in tit:

                        aba_recebimento = h

                        aba1_ok = True

                        print(f"[+] Aba 1 Anjun (Recebimento) mapeada dinamicamente: {h}")

                        break

                except Exception:

                    continue



        # 3. Garante Aba 2 (Consulta / packageQuery)

        aba2_ok = False

        if aba_atribuicao and aba_atribuicao in handles and aba_atribuicao not in [aba_recebimento, aba_atribuicao_anjun]:

            try:

                driver.switch_to.window(aba_atribuicao)

                u = (driver.current_url or '').lower()

                tit = (driver.title or '').lower()

                if "packagequery" in u or "consulta" in tit or "consulta" in u:

                    aba2_ok = True

            except Exception:

                pass



        if not aba2_ok:

            for h in handles:

                if h in [aba_recebimento, aba_atribuicao_anjun]:

                    continue

                try:

                    driver.switch_to.window(h)

                    u = (driver.current_url or '').lower()

                    tit = (driver.title or '').lower()

                    if "packagequery" in u or "consulta" in tit or "consulta" in u:

                        aba_atribuicao = h

                        aba2_ok = True

                        print(f"[+] Aba 2 Anjun (Consulta) mapeada dinamicamente: {h}")

                        break

                except Exception:

                    continue



        # Fallbacks finais seguros caso as URLs não tenham carregado totalmente

        if not aba_recebimento and len(driver.window_handles) > 0:

            aba_recebimento = driver.window_handles[0]

        if not aba_atribuicao and len(driver.window_handles) > 1:

            aba_atribuicao = driver.window_handles[1]

        if not aba_atribuicao_anjun and len(driver.window_handles) > 2:

            aba_atribuicao_anjun = driver.window_handles[2]



    except Exception as e:

        print(f"[Aviso] Falha ao garantir abas da Anjun: {str(e)}")



_init_seq_id = 0



def inicializar_selenium(plataforma_id, conta_id=None):

    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, conta_ativa, motorista_atribuicao_ativa, contagem_atribuicao_ativa, _init_seq_id

    

    _init_seq_id += 1

    meu_seq_id = _init_seq_id

    caminho_perfil, porta, conta_id_resolvido, conta_obj = obter_perfil_e_porta_conta(plataforma_id, conta_id)

    

    # 1. Se o Chrome para esta plataforma + conta JÁ estiver em execução no Windows (porta debug respondendo):

    if is_chrome_debug_active(porta):

        if not chrome_tem_janela_visivel_na_tela(porta):

            print(f"[!] Chrome na porta {porta} está oculto/órfão sem janela visível na tela. Reiniciando janela do Chrome...")

            desconectar_selenium()

            matar_chrome_na_porta(porta)

        else:

            print(f"[*] Chrome para '{plataforma_id}' (Conta: {conta_id_resolvido}) já está em execução no Windows (porta {porta}). Trazendo para frente...")

            try:

                conectar_chrome_existente(plataforma_id, conta_id_resolvido)

                if driver and len(driver.window_handles) > 0:

                    try:

                        driver.maximize_window()

                        driver.execute_cdp_cmd("Page.bringToFront", {})

                    except Exception:

                        pass

                    forcar_janela_chrome_visivel(porta, plat_alvo=plataforma_id)

                    salvar_sessao_ativa(plataforma_id, motorista_atribuicao_ativa, contagem_atribuicao_ativa, conta_id_resolvido)

                    return

            except Exception as e_att:

                print(f"[Aviso] Falha ao reconectar ao Chrome existente ({e_att}). Abrindo novo Chrome...")

                desconectar_selenium()

                matar_chrome_na_porta(porta)



    # 2. Desconecta o driver anterior em memória SEM fechar o Chrome dele no Windows!

    desconectar_selenium()

    

    plataformas = carregar_plataformas()

    config_base = plataformas.get(plataforma_id)

    if not config_base:

        raise Exception(f"Configurações para a plataforma '{plataforma_id}' não encontradas.")

    config = dict(config_base)

    if isinstance(conta_obj, dict):

        if conta_obj.get("login_usuario"):

            config["login_usuario"] = conta_obj["login_usuario"]

        if conta_obj.get("login_senha"):

            config["login_senha"] = conta_obj["login_senha"]

        

    print(f"[*] Iniciando Chrome para a plataforma: {config['nome']} (Conta: {conta_id_resolvido}, porta {porta})...")

    

    from selenium.webdriver.chrome.options import Options

    chrome_options = Options()

    

    # Aponta para um diretório de perfil exclusivo do robô dentro da pasta do projeto (específico por conta e plataforma)

    chrome_options.add_argument(f"--user-data-dir={caminho_perfil}")

    chrome_options.add_argument(f"--remote-debugging-port={porta}")

    chrome_options.add_argument("--start-maximized")

    chrome_options.add_argument("--window-position=0,0")

    chrome_options.add_argument("--disable-session-crashed-bubble")

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

    from selenium.webdriver.chrome.service import Service

    import subprocess

    chrome_service = Service()

    chrome_service.creation_flags = subprocess.CREATE_NO_WINDOW



    try:

        driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

        

        # Oculta o navigator.webdriver para permitir login com o Google (OAuth)

        try:

            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {

                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"

            })

            print("[+] navigator.webdriver ocultado com sucesso via CDP.")

        except Exception as e_cdp:

            print(f"[Aviso] Falha ao ocultar navigator.webdriver via CDP: {str(e_cdp)}")

            

        try:

            driver.set_window_position(0, 0)

            driver.maximize_window()

            driver.execute_cdp_cmd("Page.bringToFront", {})

        except Exception:

            pass

        forcar_janela_chrome_visivel(porta)

        

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

        forcar_janela_chrome_visivel(porta)

        fluxo_login_loggi(driver, config, seq_id=meu_seq_id)

        forcar_janela_chrome_visivel(porta, plat_alvo='loggi')

        plataforma_ativa = plataforma_id

        conta_ativa = conta_id_resolvido

            

    elif plataforma_id == 'imile':

        print("[*] Iniciando fluxo de login para a iMile...")

        # Abre primeiro a página de login

        driver.get("https://ds-login.imile.com/")

        time.sleep(1.0)

        try:

            driver.set_window_position(0, 0)

            driver.maximize_window()

            driver.execute_cdp_cmd("Page.bringToFront", {})

        except Exception:

            pass

        forcar_janela_chrome_visivel(porta)

        

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

        while time.time() - inicio_login < 20.0:

            # Limite de espera de login

            if _init_seq_id != meu_seq_id:

                return

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

        conta_ativa = conta_id_resolvido

        try:

            atualizar_sessao_imile(driver, forcar=True, conta_id=conta_id_resolvido)

            carregar_motoristas_imile_api(forcar=True, conta_id=conta_id_resolvido)

        except Exception:

            pass

        

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

        forcar_janela_chrome_visivel(porta)

        

        # Se for Anjun Express e cair na tela de login

        current_url = driver.current_url

        if plataforma_id == 'anjun' and ("login" in current_url.lower() or "newsupplier.anjunexpress.com/#/login" in current_url):

            print("[*] Tela de login da Anjun detectada. Aguardando login...")

            forcar_janela_chrome_visivel(porta)

            usuario = config.get("login_usuario", "").strip()

            senha = config.get("login_senha", "").strip()

            autofill_feito = False

            

            login_concluido = False

            inicio_login = time.time()

            while time.time() - inicio_login < 20.0:

                if _init_seq_id != meu_seq_id:

                    return

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

        if not aba_recebimento and len(driver.window_handles) > 0: aba_recebimento = driver.window_handles[0]

        if not aba_atribuicao and len(driver.window_handles) > 1: aba_atribuicao = driver.window_handles[1]

        if plataforma_id == 'anjun' and not aba_atribuicao_anjun and len(driver.window_handles) > 2:

            aba_atribuicao_anjun = driver.window_handles[2]

            

        plataforma_ativa = plataforma_id

        conta_ativa = conta_id_resolvido

        

        if plataforma_id == 'anjun':

            cache_sessao_anjun["token"] = None

            cache_sessao_anjun["timestamp"] = 0

            cache_motoristas_anjun["lista"] = []

            cache_motoristas_anjun["timestamp"] = 0

            fechar_avisos_todas_abas_anjun(driver)

            try:

                atualizar_sessao_anjun(driver, forcar=True)

            except Exception:

                pass

        

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

    forcar = request.args.get("forcar") in ("1", "true", "True")

    return jsonify(validar_licenca(forcar_rede=forcar))



@app.route('/ativar-licenca', methods=['POST'])

def rota_ativar_licenca():

    dados = request.json or {}

    chave = dados.get('chave', '').strip()

    if not chave:

        return jsonify({"sucesso": False, "mensagem": "A chave de ativação não pode ficar vazia!"}), 400

    ok, msg = salvar_licenca(chave)

    status_atual = validar_licenca(forcar_rede=True)

    return jsonify({

        "sucesso": ok,

        "mensagem": msg,

        "status": status_atual

    }), (200 if ok else 400)



@app.route('/licenca/plataformas', methods=['POST'])

def rota_atualizar_plataformas_licenca():

    """

    Permite atualizar quais empresas (anjun, imile, loggi, magalog) estão liberadas

    nesta licença (salva localmente e sincroniza na nuvem Supabase caso seja chave GM-...).

    """

    dados = request.json or {}

    plataformas = dados.get('plataformas') or []

    ok, res_plats = salvar_override_plataformas_local(plataformas)

    if not ok:

        return jsonify({"sucesso": False, "mensagem": res_plats}), 400



    # Se a licença ativa for GM-... no Supabase, sincroniza a tag [PLATS:...] na nuvem também

    try:

        lic_atual = validar_licenca(forcar_rede=True)

        lic_id = lic_atual.get("licenca_id")

        if lic_id:

            url_base, anon_key = _obter_config_supabase()

            headers = {

                "apikey": anon_key,

                "Authorization": f"Bearer {anon_key}",

                "Content-Type": "application/json",

                "Prefer": "return=minimal"

            }

            tag_plats = f"[PLATS:{','.join(res_plats)}]"

            payload_patch = json.dumps({"observacoes": tag_plats}).encode("utf-8")

            req_patch = urllib.request.Request(

                f"{url_base}/rest/v1/licencas?id=eq.{lic_id}",

                data=payload_patch,

                headers=headers,

                method="PATCH"

            )

            urllib.request.urlopen(req_patch, timeout=4.0).close()

    except Exception as e_sync:

        print(f"[Aviso] Falha ao sincronizar plataformas na nuvem: {e_sync}")



    status_atual = validar_licenca(forcar_rede=True)

    return jsonify({

        "sucesso": True,

        "mensagem": "Empresas liberadas na licença atualizadas com sucesso!",

        "plataformas_liberadas": res_plats,

        "status": status_atual

    })



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



@app.route('/versao-sistema', methods=['GET'])

def rota_versao_sistema():

    return jsonify(atualizador.obter_versao_local())



def obter_env_limpo_pyinstaller():

    """

    Remove variáveis de ambiente internas do bootloader PyInstaller (_MEIPASS2, _PYI_*, etc.)

    e reseta SetDllDirectoryW para que o novo processo app_engine.exe faça sua própria extração

    limpa em vez de buscar python312.dll na pasta _MEI antiga que será apagada ao sair.

    """

    try:

        if os.name == 'nt':

            import ctypes

            ctypes.windll.kernel32.SetDllDirectoryW(None)

    except Exception:

        pass



    env = os.environ.copy()

    chaves_remover = [

        k for k in list(env.keys())

        if k.upper().startswith('_MEI')

        or k.upper().startswith('_PYI')

        or k.upper() in ('TCL_LIBRARY', 'TK_LIBRARY', 'PYTHONHOME', 'PYTHONPATH')

    ]

    for k in chaves_remover:

        env.pop(k, None)



    meipass_atual = getattr(sys, '_MEIPASS', None)

    if 'PATH' in env:

        partes_path = env['PATH'].split(os.pathsep)

        partes_limpas = []

        for p in partes_path:

            if not p:

                continue

            if meipass_atual and os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(meipass_atual)):

                continue

            if '_mei' in p.lower():

                continue

            partes_limpas.append(p)

        env['PATH'] = os.pathsep.join(partes_limpas)



    return env



@app.route('/aplicar-atualizacao', methods=['POST'])

def rota_aplicar_atualizacao():

    ok, msg = atualizador.aplicar_atualizacao()

    if ok:

        # Agenda reinício do servidor após a resposta ser enviada ao navegador

        def reiniciar_depois():

            time.sleep(1.5)

            try:

                import subprocess

                env_limpo = obter_env_limpo_pyinstaller()

                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if os.name == 'nt' else 0

                if getattr(sys, 'frozen', False):

                    cmd_str = f'cmd /c "ping 127.0.0.1 -n 3 > nul && \"{sys.executable}\""'

                    subprocess.Popen(cmd_str, cwd=BASE_DIR, env=env_limpo, shell=True, creationflags=flags, close_fds=True)

                else:

                    subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=BASE_DIR, env=env_limpo)

            except Exception:

                pass

            os._exit(0)

        import threading

        threading.Thread(target=reiniciar_depois, daemon=True).start()



    return jsonify({

        "sucesso": ok,

        "mensagem": msg

    }), (200 if ok else 400)



@app.route('/')

def rota_index():

    resp = send_from_directory(BASE_DIR, 'index.html', max_age=0)

    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'

    return resp



@app.route('/dashboard')

def rota_dashboard():

    resp = send_from_directory(BASE_DIR, 'dashboard.html', max_age=0)

    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'

    return resp



@app.route('/ping', methods=['GET'])

def rota_ping():

    return jsonify({"status": "ok", "app": "galpao-monitored"})



@app.route('/configuracoes', methods=['GET'])

def obter_configuracoes():

    plat_id = (request.args.get("plataforma") or "").strip().lower()

    cid_req = request.args.get("conta_id")

    lic = validar_licenca()

    plats_licenciadas = carregar_plataformas_licenciadas(lic)

    plat_ativa_ret = plataforma_ativa if (plataforma_ativa and plataforma_ativa.lower() in plats_licenciadas) else ""

    plat_consulta_mot = plat_id or plat_ativa_ret

    if not plat_consulta_mot:

        try:

            conn_p = conectar_banco()

            cur_p = conn_p.cursor()

            cur_p.execute("""

                SELECT LOWER(plataforma), COUNT(*)

                FROM motoristas_plataforma

                WHERE LOWER(TRIM(cidade)) NOT IN ('sem cidade', 'geral', 'imile', 'anjun', '')

                GROUP BY LOWER(plataforma)

                ORDER BY COUNT(*) DESC

            """)

            for p_db, _ in cur_p.fetchall():

                if p_db and p_db in plats_licenciadas:

                    plat_consulta_mot = p_db

                    break

            conn_p.close()

        except Exception:

            pass

    if not plat_consulta_mot and plats_licenciadas:

        plat_consulta_mot = "anjun" if "anjun" in plats_licenciadas else next(iter(plats_licenciadas.keys()), "anjun")

    return jsonify({

        "plataformas": plats_licenciadas,

        "todas_plataformas_sistema": carregar_plataformas(),

        "contas_plataformas": carregar_contas_plataformas(),

        "conta_ativa": cid_req or conta_ativa,

        "motoristas": carregar_motoristas(plat_consulta_mot, conta_id=cid_req),

        "cidades": carregar_cidades(),

        "plataforma_ativa": plat_ativa_ret,

        "plataforma_motoristas": plat_consulta_mot,

        "motorista_lote": motorista_atribuicao_ativa,

        "contagem": contagem_atribuicao_ativa,

        "modo_consulta": modo_consulta,

        "licenca": lic

    })



@app.route('/motoristas/lista-site', methods=['GET'])

def obter_lista_motoristas_site():

    plat_id = (request.args.get("plataforma") or plataforma_ativa or "anjun").strip().lower()

    cid_req = request.args.get("conta_id") or obter_conta_ativa_plataforma(plat_id)[0]

    forcar = request.args.get("forcar") in ("1", "true", "True")

    nomes_set = set()



    try:

        if plat_id == 'anjun':

            fn_an = globals().get('carregar_motoristas_anjun_api')

            if fn_an:

                lista_an, _ = fn_an(forcar=forcar, conta_id=cid_req)

                for m in (lista_an or []):

                    un = (m.get("username") or "").strip()

                    if un:

                        nomes_set.add(un)

        elif plat_id == 'imile':

            fn_im = globals().get('carregar_motoristas_imile_api')

            if fn_im:

                lista_im, _ = fn_im(forcar=forcar, conta_id=cid_req)

                for m in (lista_im or []):

                    dn = (m.get("daName") or "").strip()

                    if dn:

                        nomes_set.add(dn)

    except Exception as e:

        print(f"[Aviso] Falha ao consultar API de motoristas para {plat_id} ({cid_req}): {e}")



    if not nomes_set and plat_id in ('anjun', 'imile'):

        salvos = obter_motoristas_da_base_salvos(plat_id, cid_req)

        for s in salvos:

            if s and str(s).strip():

                nomes_set.add(str(s).strip())



    _, nomes_base_oficiais, nomes_outras_bases = obter_nomes_oficiais_base_ativa(plat_id, cid_req, forcar=False)

    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT motorista FROM motoristas_plataforma WHERE LOWER(plataforma) = ?", (plat_id,))

        for (m_db,) in cursor.fetchall():

            if m_db and str(m_db).strip() and str(m_db).strip() not in ("---", "Sem Motorista"):

                m_str = str(m_db).strip()

                if motorista_pertence_a_base_ativa(m_str, nomes_base_oficiais, nomes_outras_bases, plat_id):

                    nomes_set.add(m_str)

        conn.close()

    except Exception:

        pass



    lista_ordenada = sorted(list(nomes_set), key=lambda s: remover_acentos(s.lower()))

    return jsonify({

        "status": "sucesso",

        "plataforma": plat_id,

        "conta_id": cid_req,

        "motoristas": lista_ordenada

    })



@app.route('/<path:filename>')

def rota_arquivos_estaticos(filename):

    diretorio = BASE_DIR

    caminho = os.path.join(diretorio, filename)

    if os.path.isfile(caminho):

        resp = send_from_directory(diretorio, filename, max_age=0)

        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'

        return resp

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

                SELECT timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, status_entrega, motorista_entrega, tempo_atraso, cep, endereco 

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

                    "tempo_atraso": r[16] if len(r) > 16 and r[16] is not None else 0.0,

                    "cep": r[17] if len(r) > 17 and r[17] is not None else "",

                    "endereco": r[18] if len(r) > 18 and r[18] is not None else ""

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

                SELECT timestamp, codigo, plataforma, cidade, motorista, status, recebedor, telefone, email, tempo_criacao, status_pacote, valor_declarado, negocios, bairro, status_entrega, motorista_entrega, tempo_atraso, cep, endereco 

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

                    "tempo_atraso": r[16] if len(r) > 16 and r[16] is not None else 0.0,

                    "cep": r[17] if len(r) > 17 and r[17] is not None else "",

                    "endereco": r[18] if len(r) > 18 and r[18] is not None else ""

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



@app.route('/debug-eval', methods=['POST'])

def debug_eval():

    global driver

    if not driver:

        return jsonify({"erro": "sem driver"})

    dados = request.get_json(force=True) or {}

    script = dados.get("script")

    handle = dados.get("handle")

    if handle:

        driver.switch_to.window(handle)

    try:

        res = driver.execute_script(script)

        return jsonify({"sucesso": True, "resultado": res})

    except Exception as e:

        return jsonify({"sucesso": False, "erro": str(e)})



@app.route('/debug-test-bipe', methods=['POST'])

def debug_test_bipe():

    global driver

    if not driver:

        return jsonify({"erro": "sem driver"})

    dados = request.get_json(force=True) or {}

    codigo = dados.get("codigo", "TEST123456")

    handle = dados.get("handle")

    if handle:

        driver.switch_to.window(handle)

    campo = obter_input_imile_html(driver)

    if not campo:

        return jsonify({"erro": "campo não encontrado"})

    sucesso = enviar_bipe_imile_html(driver, campo, codigo)

    val_final = campo.get_attribute("value")

    return jsonify({"sucesso": sucesso, "val_final": val_final})



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

        

        # Garante que a coluna produto exista antes do SELECT

        try:

            cursor.execute("ALTER TABLE historico ADD COLUMN produto TEXT")

        except Exception:

            pass



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

        

        # 2. Busca a lista detalhada de todos os bips daquele período com todas as colunas extras

        query_detalhada = """

            SELECT timestamp, codigo, plataforma, cidade, motorista, recebedor,

                   cep, endereco, bairro, telefone, negocios, produto, valor_declarado

            FROM historico

            WHERE timestamp >= ?

              AND timestamp <= ?

            ORDER BY timestamp DESC

        """

        cursor.execute(query_detalhada, (start, end))

        linhas_detalhadas = cursor.fetchall()

        

        conn.close()

        

        import io

        import datetime

        from flask import Response



        def _limpar_campo(v):

            s = str(v or "").strip()

            return "" if s in ["---", "None", "null", "****"] else s



        linhas_processadas = []

        for r in linhas_detalhadas:

            ts = r[0] or ""

            if ts and len(ts) >= 19:

                try:

                    dt = datetime.datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')

                    ts = dt.strftime('%d/%m/%Y %H:%M:%S')

                except Exception:

                    pass

            cod_val = str(r[1] or "").strip()

            plat_val = str(r[2] or "").strip()

            cid_val = _limpar_campo(r[3])

            mot_val = _limpar_campo(r[4])

            rec_val = _limpar_campo(r[5])

            cep_val = _limpar_campo(r[6]) if len(r) > 6 else ""

            end_val = _limpar_campo(r[7]) if len(r) > 7 else ""

            bairro_val = _limpar_campo(r[8]) if len(r) > 8 else ""

            tel_val = _limpar_campo(r[9]) if len(r) > 9 else ""

            emp_val = _limpar_campo(r[10]) if len(r) > 10 else ""

            prod_val = _limpar_campo(r[11]) if len(r) > 11 else ""

            valor_val = _limpar_campo(r[12]) if len(r) > 12 else ""



            # Compatibilidade com registros antigos da Loggi onde a empresa ficava salva em 'recebedor'

            if not emp_val and plat_val.lower() == "loggi" and rec_val:

                emp_val = formatar_nome_empresa_remetente(rec_val, cod_val, plat_val)

            else:

                emp_val = formatar_nome_empresa_remetente(emp_val, cod_val, plat_val)



            linhas_processadas.append([

                ts, cod_val, plat_val.upper(), emp_val, cid_val, bairro_val,

                cep_val, end_val, mot_val, rec_val, tel_val, prod_val, valor_val

            ])



        try:

            import openpyxl

            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            from openpyxl.utils import get_column_letter



            wb = openpyxl.Workbook()

            ws = wb.active

            ws.title = "Fechamento Triagem"



            font_title = Font(name="Calibri", size=13, bold=True, color="FFFFFF")

            fill_title = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")

            font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

            fill_header_resumo = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")

            fill_header_detalhe = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")

            fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

            font_cell = Font(name="Calibri", size=10)

            thin_side = Side(border_style="thin", color="CBD5E1")

            border_cell = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)



            # Bloco 1: Resumo de Atribuições

            ws.append([f"RESUMO DE ATRIBUIÇÕES - PERÍODO: {label_periodo}"])

            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)

            c_t1 = ws.cell(row=1, column=1)

            c_t1.font = font_title

            c_t1.fill = fill_title

            c_t1.alignment = Alignment(vertical="center", horizontal="left")

            ws.row_dimensions[1].height = 24



            ws.append([])

            headers_resumo = ["Motorista", "Cidade", "Plataforma", "Quantidade de Pacotes"]

            ws.append(headers_resumo)

            row_h_res = ws.max_row

            ws.row_dimensions[row_h_res].height = 20

            for col_i in range(1, len(headers_resumo) + 1):

                c = ws.cell(row=row_h_res, column=col_i)

                c.font = font_header

                c.fill = fill_header_resumo

                c.alignment = Alignment(vertical="center", horizontal="center" if col_i == 4 else "left")

                c.border = border_cell



            for idx_r, r in enumerate(linhas_agrupadas):

                ws.append([r[0], r[1], str(r[2] or "").upper(), int(r[3] or 0)])

                curr_r = ws.max_row

                for col_i in range(1, 5):

                    c = ws.cell(row=curr_r, column=col_i)

                    c.font = font_cell

                    c.border = border_cell

                    if idx_r % 2 == 1:

                        c.fill = fill_zebra

                    if col_i == 4:

                        c.alignment = Alignment(horizontal="center")



            ws.append([])

            ws.append([])



            # Bloco 2: Listagem Detalhada de Pacotes Bipados

            ws.append(["LISTAGEM DETALHADA DE PACOTES BIPADOS"])

            row_t2 = ws.max_row

            headers_detalhe = [

                "Horário", "Código de Rastreio", "Plataforma", "Empresa / Loja",

                "Cidade Destino", "Bairro", "CEP", "Endereço",

                "Motorista Atribuído", "Recebedor", "Telefone", "Produto", "Valor"

            ]

            ws.merge_cells(start_row=row_t2, start_column=1, end_row=row_t2, end_column=len(headers_detalhe))

            c_t2 = ws.cell(row=row_t2, column=1)

            c_t2.font = font_title

            c_t2.fill = fill_title

            c_t2.alignment = Alignment(vertical="center", horizontal="left")

            ws.row_dimensions[row_t2].height = 24



            ws.append(headers_detalhe)

            row_h_det = ws.max_row

            ws.row_dimensions[row_h_det].height = 22

            for col_i in range(1, len(headers_detalhe) + 1):

                c = ws.cell(row=row_h_det, column=col_i)

                c.font = font_header

                c.fill = fill_header_detalhe

                c.alignment = Alignment(vertical="center", horizontal="left")

                c.border = border_cell



            for idx_d, row_vals in enumerate(linhas_processadas):

                ws.append(row_vals)

                curr_r = ws.max_row

                for col_i in range(1, len(headers_detalhe) + 1):

                    c = ws.cell(row=curr_r, column=col_i)

                    c.font = font_cell

                    c.border = border_cell

                    if idx_d % 2 == 1:

                        c.fill = fill_zebra

                    # Força formato texto em Código de Rastreio (2), CEP (7) e Telefone (11) para nunca virar 3,32E+12

                    if col_i in (2, 7, 11):

                        c.number_format = '@'

                        c.value = str(c.value or "")



            # Larguras ideais mínimas por coluna para nunca aparecer '#######' no Horário nem cortar textos

            larguras_minimas = {

                1: 21,  # Horário

                2: 24,  # Código de Rastreio

                3: 13,  # Plataforma

                4: 24,  # Empresa / Loja

                5: 22,  # Cidade Destino

                6: 20,  # Bairro

                7: 13,  # CEP

                8: 38,  # Endereço

                9: 24,  # Motorista Atribuído

                10: 26, # Recebedor

                11: 17, # Telefone

                12: 25, # Produto

                13: 14  # Valor

            }

            for col_idx in range(1, len(headers_detalhe) + 1):

                col_letter = get_column_letter(col_idx)

                max_len = larguras_minimas.get(col_idx, 16)

                for row_idx in range(row_h_det, min(ws.max_row + 1, row_h_det + 300)):

                    val_str = str(ws.cell(row=row_idx, column=col_idx).value or "")

                    if len(val_str) + 3 > max_len:

                        max_len = min(len(val_str) + 3, 52)

                ws.column_dimensions[col_letter].width = max_len



            bio = io.BytesIO()

            wb.save(bio)

            bio.seek(0)

            return Response(

                bio.getvalue(),

                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

                headers={"Content-disposition": f"attachment; filename=Fechamento_Triagem_{label_periodo}.xlsx"}

            )

        except Exception as e_xlsx:

            print(f"[Aviso] Falha ao gerar .xlsx com openpyxl ({e_xlsx}), gerando .csv de fallback...")

            import csv

            output = io.StringIO()

            output.write('\ufeff')

            writer = csv.writer(output, delimiter=';')

            writer.writerow([f"RESUMO DE ATRIBUIÇÕES - PERÍODO: {label_periodo}"])

            writer.writerow([])

            writer.writerow(["Motorista", "Cidade", "Plataforma", "Quantidade de Pacotes"])

            for r in linhas_agrupadas:

                writer.writerow([r[0], r[1], r[2], r[3]])

            writer.writerow([])

            writer.writerow([])

            writer.writerow(["LISTAGEM DETALHADA DE PACOTES BIPADOS"])

            writer.writerow([])

            writer.writerow([

                "Horário", "Código de Rastreio", "Plataforma", "Empresa / Loja",

                "Cidade Destino", "Bairro", "CEP", "Endereço",

                "Motorista Atribuído", "Recebedor", "Telefone", "Produto", "Valor"

            ])

            for row_vals in linhas_processadas:

                writer.writerow(row_vals)

            csv_data = output.getvalue()

            output.close()

            return Response(

                csv_data,

                mimetype="text/csv",

                headers={"Content-disposition": f"attachment; filename=Fechamento_Triagem_{label_periodo}.csv"}

            )

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/historico/limpar', methods=['POST'])

def limpar_historico():

    salvar_historico([])

    return jsonify({"status": "sucesso", "mensagem": "Histórico limpo com sucesso!"})



@app.route('/divergencias/pendentes', methods=['GET'])

def obter_divergencias_pendentes():

    try:

        import datetime

        hoje_str = datetime.datetime.now().strftime('%Y-%m-%d')

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("""

            SELECT d.codigo, 

                   d.motorista_lote,

                   d.motorista_esperado, 

                   d.timestamp,

                   COALESCE(NULLIF(d.cidade, ''), NULLIF(h.cidade, ''), '---') AS cidade_destino

            FROM divergencias_pendentes d

            LEFT JOIN (

                SELECT codigo, cidade 

                FROM historico 

                WHERE cidade IS NOT NULL AND cidade != '' AND cidade != '---'

                GROUP BY codigo

            ) h ON d.codigo = h.codigo

            WHERE d.status = 'pendente' 

              AND (d.timestamp LIKE ? OR date(d.timestamp) = ? OR date(d.timestamp, 'localtime') = ?)

            ORDER BY d.timestamp DESC

        """, (hoje_str + '%', hoje_str, hoje_str))

        linhas = cursor.fetchall()

        

        resultado = []

        for r in linhas:

            codigo = r[0]

            mot_lote = r[1] or ""

            mot_esperado = r[2] or ""

            timestamp = r[3]

            cidade_destino = r[4]

            

            deveria_ir = mot_esperado if mot_esperado else (cidade_destino or "---")

            estava_em = mot_lote if mot_lote else "---"

                

            resultado.append({

                "codigo": codigo,

                "estava_em": estava_em,

                "motorista_lote": mot_lote,

                "cidade_destino": cidade_destino,

                "motorista_esperado": mot_esperado,

                "deveria_ir_para": deveria_ir,

                "timestamp": timestamp

            })

            

        conn.close()

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



        # Sincroniza lotes abertos diretamente da API da Anjun (se houver sessão ativa)

        try:

            if not data_inicio and not data_fim:

                sincronizar_lotes_pendentes_anjun_api()

        except Exception:

            pass

            

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

        

        # Consulta lotes pendentes (grupos abertos) na Anjun

        pendentes_map = {}

        try:

            cursor.execute("SELECT motorista, count(*) FROM lote_pendente_anjun GROUP BY motorista")

            pendentes_map = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # Filtra estritamente para manter apenas motoristas pertencentes à base ativa desta máquina (evita contaminação entre Base 176 e Base Avaré)

            cid_ativa, _ = obter_conta_ativa_plataforma("anjun")

            cid_key = f"anjun:{cid_ativa}"

            m_base_disco = carregar_motoristas_por_base_disco()

            mots_base_ativa = set(m_base_disco.get(cid_key, {}).get("motoristas", []))

            if mots_base_ativa:

                norm_mots_base = {remover_acentos(m.lower()).replace('-', '').replace('_', '').replace(' ', '') for m in mots_base_ativa}

                pendentes_map = {m: q for m, q in pendentes_map.items() if remover_acentos(m.lower()).replace('-', '').replace('_', '').replace(' ', '') in norm_mots_base}

        except Exception as e_pend:

            print(f"[Aviso] Erro ao buscar lotes pendentes Anjun: {e_pend}")

            

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

            

            # Detalhamento de pacotes por cidade para este motorista no período

            detalhes_cidades = []

            try:

                if data_inicio and data_fim:

                    cursor.execute("""

                        SELECT cidade, count(*) 

                        FROM historico 

                        WHERE status = 'OK' 

                          AND timestamp >= ? 

                          AND timestamp <= ? 

                          AND motorista = ?

                        GROUP BY cidade 

                        ORDER BY count(*) DESC

                    """, (start, end, motorista_nome))

                else:

                    cursor.execute("""

                        SELECT cidade, count(*) 

                        FROM historico 

                        WHERE status = 'OK' 

                          AND timestamp >= ? 

                          AND motorista = ?

                        GROUP BY cidade 

                        ORDER BY count(*) DESC

                    """, (cutoff, motorista_nome))

                linhas_cid = cursor.fetchall()

                for cid_row in linhas_cid:

                    c_nome = cid_row[0] or "Não Informada"

                    if c_nome.strip() in ("", "---"):

                        c_nome = "Não Informada"

                    detalhes_cidades.append({

                        "cidade": c_nome,

                        "quantidade": cid_row[1]

                    })

            except Exception as e_cid:

                print(f"[Aviso] Erro ao buscar detalhamento de cidades para {motorista_nome}: {e_cid}")

                detalhes_cidades = []

            

            # Lista individual de códigos de pacotes deste motorista no período

            pacotes_motorista = []

            try:

                if data_inicio and data_fim:

                    cursor.execute("""

                        SELECT codigo, cidade, timestamp

                        FROM historico

                        WHERE status = 'OK'

                          AND timestamp >= ?

                          AND timestamp <= ?

                          AND motorista = ?

                        ORDER BY id DESC

                    """, (start, end, motorista_nome))

                else:

                    cursor.execute("""

                        SELECT codigo, cidade, timestamp

                        FROM historico

                        WHERE status = 'OK'

                          AND timestamp >= ?

                          AND motorista = ?

                        ORDER BY id DESC

                    """, (cutoff, motorista_nome))

                vistos_cod = set()

                for row_p in cursor.fetchall():

                    cod_p = str(row_p[0] or "").strip()

                    if not cod_p or cod_p in vistos_cod:

                        continue

                    vistos_cod.add(cod_p)

                    cid_p = str(row_p[1] or "Não Informada").strip()

                    if cid_p in ("", "---"):

                        cid_p = "Não Informada"

                    ts_p = str(row_p[2] or "")

                    hora_p = ts_p.split("T")[1][:8] if "T" in ts_p else ts_p[-8:]

                    pacotes_motorista.append({

                        "codigo": cod_p,

                        "cidade": cid_p,

                        "horario": hora_p

                    })

            except Exception as e_pkg:

                print(f"[Aviso] Erro ao buscar pacotes de {motorista_nome}: {e_pkg}")



            # Qtd pendente no lote aberto Anjun (exclusivamente da tabela lote_pendente_anjun, sem misturar contadores de iMile/Loggi em memória)

            qtd_pend = 0

            if plat_display == "Anjun":

                norm_m_row = remover_acentos(motorista_nome.lower()).replace('-', '').replace('_', '').replace(' ', '')

                for m_p, q_p in pendentes_map.items():

                    norm_mp = remover_acentos(m_p.lower()).replace('-', '').replace('_', '').replace(' ', '')

                    if norm_mp == norm_m_row or norm_mp in norm_m_row or norm_m_row in norm_mp:

                        qtd_pend += q_p

                if qtd > 0 and qtd_pend > qtd:

                    qtd_pend = qtd



            resultado.append({

                "motorista": motorista_nome,

                "cidades": cidades_str,

                "quantidade": qtd,

                "qtd_pendente": qtd_pend,

                "grupo_aberto": bool(qtd_pend > 0),

                "plataforma": plat_display,

                "timestamp": "",

                "detalhes_cidades": detalhes_cidades,

                "pacotes": pacotes_motorista

            })

            

        # Adiciona motoristas que têm lote aberto na Anjun mas ainda não tinham pacotes no histórico

        motoristas_em_resultado = [remover_acentos(r["motorista"].lower()).replace('-', '').replace('_', '').replace(' ', '') for r in resultado if r.get("plataforma") == "Anjun"]

        for mot_pend, qtd_pend in pendentes_map.items():

            norm_mp = remover_acentos(mot_pend.lower()).replace('-', '').replace('_', '').replace(' ', '')

            if not any(norm_mp == m_res or norm_mp in m_res or m_res in norm_mp for m_res in motoristas_em_resultado):

                try:

                    cursor.execute("SELECT cidade FROM motoristas_plataforma WHERE motorista = ?", (mot_pend,))

                    cidades_list = [row[0] for row in cursor.fetchall()]

                except Exception:

                    cidades_list = []

                cidades_str = ", ".join(cidades_list) if cidades_list else "Sem Cidades"

                resultado.append({

                    "motorista": mot_pend,

                    "cidades": cidades_str,

                    "quantidade": qtd_pend,

                    "qtd_pendente": qtd_pend,

                    "grupo_aberto": True,

                    "plataforma": "Anjun",

                    "timestamp": "",

                    "detalhes_cidades": [],

                    "pacotes": []

                })

                motoristas_em_resultado.append(norm_mp)

            

        conn.close()

        return jsonify(resultado)

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/atribuicao/transferir-motorista', methods=['POST'])

def transferir_pacotes_motorista():

    """

    Transfere todos os pacotes (ou apenas os de uma cidade específica ou códigos selecionados) bipados hoje

    de um motorista de origem para um novo motorista de destino, reatribuindo

    automaticamente no site da Anjun / iMile via API ultra-rápida e atualizando o banco local.

    """

    global contagem_motoristas

    try:

        dados = request.get_json(force=True) or {}

        mot_origem = str(dados.get("motorista_origem") or "").strip()

        mot_destino = str(dados.get("motorista_destino") or "").strip()

        plat_raw = str(dados.get("plataforma") or "").strip().lower()

        cidade_filtro = str(dados.get("cidade_filtro") or "").strip()

        codigos_selecionados = dados.get("codigos_selecionados")

        if isinstance(codigos_selecionados, list):

            codigos_selecionados = [str(c).strip() for c in codigos_selecionados if str(c).strip()]

        else:

            codigos_selecionados = []

        if cidade_filtro.upper().startswith("COD:"):

            cod_esp = cidade_filtro[4:].strip()

            if cod_esp and cod_esp not in codigos_selecionados:

                codigos_selecionados = [cod_esp]

            cidade_filtro = "TODAS"



        lancar_no_site = bool(dados.get("lancar_no_site", True))

        data_inicio = str(dados.get("data_inicio") or "").strip()

        data_fim = str(dados.get("data_fim") or "").strip()



        if not mot_origem or not mot_destino:

            return jsonify({"status": "erro", "mensagem": "Informe o motorista de origem e o novo motorista de destino."}), 400



        mesmo_motorista = (mot_origem.lower() == mot_destino.lower())



        import datetime

        import concurrent.futures



        hoje_str = datetime.datetime.now().strftime('%Y-%m-%d')

        start_ts = (data_inicio if data_inicio else hoje_str) + "T00:00:00"

        end_ts = (data_fim if data_fim else hoje_str) + "T23:59:59"



        conn = conectar_banco()

        cursor = conn.cursor()



        params = [start_ts, end_ts, mot_origem]

        sql_busca = """

            SELECT id, codigo, plataforma, cidade

            FROM historico

            WHERE status = 'OK'

              AND timestamp >= ?

              AND timestamp <= ?

              AND motorista = ?

        """

        if codigos_selecionados:

            placeholders_sel = ",".join(["?"] * len(codigos_selecionados))

            sql_busca += f" AND codigo IN ({placeholders_sel})"

            params.extend(codigos_selecionados)

        elif cidade_filtro and cidade_filtro.upper() != "TODAS":

            if cidade_filtro == "Não Informada":

                sql_busca += " AND (cidade IS NULL OR cidade = '' OR cidade = '---' OR cidade = 'Não Informada')"

            else:

                sql_busca += " AND cidade = ?"

                params.append(cidade_filtro)



        cursor.execute(sql_busca, tuple(params))

        registros_hist = cursor.fetchall()



        ids_hist = [r[0] for r in registros_hist]

        codigos_unicos = []

        plat_detectada = plat_raw

        for r in registros_hist:

            cod_c = str(r[1] or "").strip()

            if cod_c and cod_c not in codigos_unicos:

                codigos_unicos.append(cod_c)

            if not plat_detectada and r[2]:

                plat_detectada = str(r[2]).strip().lower()



        eh_anjun = "anjun" in plat_detectada

        eh_imile = "imile" in plat_detectada



        # Se for Anjun e não houver filtro de cidade restritivo, também inclui pacotes que estejam no lote_pendente_anjun

        if eh_anjun and (not cidade_filtro or cidade_filtro.upper() == "TODAS"):

            try:

                cursor.execute("SELECT waybill FROM lote_pendente_anjun WHERE motorista = ?", (mot_origem,))

                for row_p in cursor.fetchall():

                    c_p = str(row_p[0] or "").strip()

                    if c_p and c_p not in codigos_unicos:

                        if not codigos_selecionados or c_p in codigos_selecionados:

                            codigos_unicos.append(c_p)

            except Exception:

                pass



        if not codigos_unicos and not ids_hist:

            conn.close()

            return jsonify({"status": "erro", "mensagem": f"Nenhum pacote encontrado hoje para o motorista '{mot_origem}'."}), 404



        mot_final_destino = mot_destino

        ok_site_count = 0

        erros_site = []



        # 1. Lançamento / Reatribuição automática no site (Anjun ou iMile)

        if lancar_no_site and codigos_unicos and (eh_anjun or eh_imile):

            if eh_imile:

                sessao = atualizar_sessao_imile()

                token = sessao.get("token")

                if not token:

                    conn.close()

                    return jsonify({

                        "status": "erro",

                        "mensagem": "Sessão da iMile não encontrada no Chrome. Abra a iMile no sistema antes de transferir no site (ou desmarque a opção de lançar no site)."

                    }), 400



                da_obj = resolver_motorista_imile_api(mot_destino)

                if not da_obj:

                    conn.close()

                    return jsonify({

                        "status": "erro",

                        "mensagem": f"Motorista '{mot_destino}' não encontrado na lista oficial da iMile."

                    }), 400



                da_code = da_obj["daCode"]

                da_name = da_obj["daName"]

                mot_final_destino = da_name

                station_code = sessao.get("currentStationCode", "S210570001")

                station_name = sessao.get("stationName", "DS AVR")



                def _reatribuir_imile(cod_pkg):

                    payload_assign = {

                        "daCode": da_code,

                        "scanNumber": cod_pkg,

                        "ocCode": station_code,

                        "forceOperate": True,

                        "fromAssign": 1,

                        "daName": da_name,

                        "currentStationCode": station_code,

                        "currentStationName": station_name,

                        "isRefactor": True,

                        "usePreSorting": False

                    }

                    ok_da, msg_da, _ = executar_post_imile("/lm/express/ops/v1/biz/ofdAndReturnOfd/submit", payload_assign)

                    if not ok_da:

                        msg_low = (msg_da or "").lower()

                        if any(k in msg_low for k in ["success", "sucesso", "já atribuído", "já atribuido", "repetido", "duplicad", "repeat"]):

                            ok_da = True

                    return cod_pkg, ok_da, msg_da



                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:

                    for cod_pkg, ok_da, msg_da in executor.map(_reatribuir_imile, codigos_unicos):

                        if ok_da:

                            ok_site_count += 1

                        else:

                            erros_site.append(f"{cod_pkg}: {msg_da}")



            elif eh_anjun:

                sessao = atualizar_sessao_anjun()

                token = sessao.get("token")

                if not token:

                    conn.close()

                    return jsonify({

                        "status": "erro",

                        "mensagem": "Sessão da Anjun não encontrada no Chrome. Abra a Anjun no sistema antes de transferir no site (ou desmarque a opção de lançar no site)."

                    }), 400



                da_obj = resolver_motorista_anjun_api(mot_destino)

                if not da_obj:

                    conn.close()

                    return jsonify({

                        "status": "erro",

                        "mensagem": f"Motorista '{mot_destino}' não localizado na lista de DAs da Anjun."

                    }), 400



                da_id = da_obj["id"]

                da_username = da_obj["username"]

                mot_final_destino = da_username



                def _reatribuir_anjun(cod_pkg):

                    payload_assign = {

                        "waybillNumber": str(cod_pkg).strip().upper(),

                        "dispatchUserId": da_id,

                        "dispatchUserName": da_username

                    }

                    ok_da, msg_da, _ = executar_post_anjun("/api/wms/console/v1/storage/dispatch/taskAllocation", payload_assign)

                    if not ok_da:

                        msg_low = (msg_da or "").lower()

                        if any(k in msg_low for k in ["sucesso", "success", "já atribuído", "já atribuido", "atribuído", "atribuido", "já alocado", "ja alocado", "já vinculado", "aguardando entrega", "não repita", "duplicad", "repetid"]):

                            ok_da = True

                    return cod_pkg, ok_da, msg_da



                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:

                    for cod_pkg, ok_da, msg_da in executor.map(_reatribuir_anjun, codigos_unicos):

                        if ok_da:

                            ok_site_count += 1

                        else:

                            erros_site.append(f"{cod_pkg}: {msg_da}")



        # 2. Atualiza banco de dados local (historico e lote_pendente_anjun)

        if ids_hist:

            placeholders = ",".join(["?"] * len(ids_hist))

            cursor.execute(

                f"UPDATE historico SET motorista = ?, motorista_entrega = ? WHERE id IN ({placeholders})",

                tuple([mot_final_destino, mot_final_destino] + ids_hist)

            )



        if eh_anjun and codigos_unicos:

            try:

                if mesmo_motorista:
                    novos_lote = [(c, mot_final_destino) for c in codigos_unicos]
                    cursor.executemany("INSERT OR REPLACE INTO lote_pendente_anjun (waybill, motorista, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", novos_lote)
                else:
                    placeholders_cod = ",".join(["?"] * len(codigos_unicos))
                    cursor.execute(
                        f"UPDATE lote_pendente_anjun SET motorista = ? WHERE motorista = ? AND waybill IN ({placeholders_cod})",
                        tuple([mot_final_destino, mot_origem] + codigos_unicos)
                    )

            except Exception:

                pass



        conn.commit()

        conn.close()



        # Atualiza contadores em memória (apenas se mudou de motorista)
        if not mesmo_motorista:
            try:
                qtd_movida = len(codigos_unicos)
                if mot_origem in contagem_motoristas:
                    contagem_motoristas[mot_origem] = max(0, contagem_motoristas[mot_origem] - qtd_movida)
                contagem_motoristas[mot_final_destino] = contagem_motoristas.get(mot_final_destino, 0) + qtd_movida
            except Exception:
                pass

        if mesmo_motorista:
            msg_resumo = f"{len(codigos_unicos)} pacote(s) relançado(s) com sucesso para '{mot_final_destino}'!"
        else:
            msg_resumo = f"{len(codigos_unicos)} pacote(s) transferido(s) de '{mot_origem}' para '{mot_final_destino}'!"

        if lancar_no_site and (eh_anjun or eh_imile):

            msg_resumo += f" ({ok_site_count}/{len(codigos_unicos)} reatribuídos direto no site)."



        return jsonify({

            "status": "sucesso",

            "total_pacotes": len(codigos_unicos),

            "lancados_site": ok_site_count,

            "erros_site": erros_site[:10],

            "motorista_origem": mot_origem,

            "motorista_destino": mot_final_destino,

            "mensagem": msg_resumo

        })

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



@app.route('/sessao/status', methods=['GET'])

def verificar_sessao_status():

    """

    Verifica se a plataforma ativa no Chrome está conectada e autenticada.

    Suporta Anjun e Loggi com auto-reconexão e detecção de tela de login.

    """

    global driver, cache_sessao_anjun, plataforma_ativa

    plat = request.args.get("plataforma", plataforma_ativa or "anjun").lower()

    

    if not driver:

        return jsonify({"status": "erro", "logado": False, "mensagem": "Chrome não iniciado."})

        

    if "anjun" in plat:

        try:

            curr_url = ""

            try:

                curr_url = driver.current_url.lower()

            except Exception:

                pass

            

            if "login" in curr_url:

                return jsonify({"status": "desconectado", "logado": False, "mensagem": "Na tela de login da Anjun."})

                

            cache_sessao_anjun["token"] = None

            sessao = atualizar_sessao_anjun(forcar=True)

            token = sessao.get("token")

            if token and len(token) > 20:

                print(f"[+] [Anjun] Sessão revalidada pós-login/captcha! Token: {token[:12]}...")

                return jsonify({"status": "conectado", "logado": True, "token": token[:10]})

            else:

                return jsonify({"status": "desconectado", "logado": False, "mensagem": "Aguardando token da Anjun."})

        except Exception as e:

            return jsonify({"status": "erro", "logado": False, "mensagem": str(e)})



    elif "imile" in plat:

        try:

            curr_url = ""

            try:

                curr_url = driver.current_url.lower()

            except Exception:

                pass

            if "login" in curr_url:

                return jsonify({"status": "desconectado", "logado": False, "mensagem": "Na tela de login da iMile."})



            cache_sessao_imile["token"] = None

            sessao = atualizar_sessao_imile(forcar=True)

            token = sessao.get("token")

            if token and len(token) > 20:

                print(f"[+] [iMile] Sessão revalidada! Token: {token[:12]}...")

                return jsonify({"status": "conectado", "logado": True, "token": token[:10]})

            else:

                return jsonify({"status": "desconectado", "logado": False, "mensagem": "Aguardando login na iMile no Chrome."})

        except Exception as e:

            return jsonify({"status": "erro", "logado": False, "mensagem": str(e)})



    elif "loggi" in plat:

        try:

            # 1. Verifica se alguma aba está na tela de login

            na_tela_login = False

            for h in driver.window_handles:

                try:

                    driver.switch_to.window(h)

                    if verificar_tela_login_loggi(driver):

                        na_tela_login = True

                        clicou = tentar_clicar_login_google_loggi(driver)

                        if clicou:

                            print("[*] [Loggi] Botão 'Entrar com o Google' clicado automaticamente!")

                        break

                except Exception:

                    continue

                    

            if na_tela_login:

                return jsonify({

                    "status": "desconectado",

                    "logado": False,

                    "mensagem": "Na tela de login da Loggi. Clique em 'Entrar com o Google'."

                })

                

            # 2. Se nenhuma aba está na tela de login, verifica se temos acesso às abas Loggi (/AV3/...)

            tem_aba_ativa = False

            for h in driver.window_handles:

                try:

                    driver.switch_to.window(h)

                    u = driver.current_url.lower()

                    if "arco.loggi.com" in u and not verificar_tela_login_loggi(driver):

                        tem_aba_ativa = True

                        break

                except Exception:

                    continue

                    

            if tem_aba_ativa:

                garantir_abas_loggi(driver)

                ctx = obter_contexto_loggi(forcar=True)

                token = ctx.get("token")

                exp = ctx.get("exp", 0)

                if not token:

                    return jsonify({"status": "desconectado", "logado": False, "mensagem": "Token da Loggi não encontrado. Verifique se o login foi concluído."})

                if exp > 0 and time.time() >= exp:

                    return jsonify({"status": "desconectado", "logado": False, "mensagem": "Sessão da Loggi expirada. Renovando..."})

                return jsonify({"status": "conectado", "logado": True, "token": token[:10]})

            else:

                return jsonify({"status": "desconectado", "logado": False, "mensagem": "Aguardando conclusão do login no Google."})

        except Exception as e:

            return jsonify({"status": "erro", "logado": False, "mensagem": str(e)})



    return jsonify({"status": "conectado", "logado": True})



@app.route('/atribuicao/iniciar', methods=['POST'])

@requer_licenca_ativa

def atribuicao_iniciar():

    global driver, aba_atribuicao_anjun, motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas

    dados = request.json

    motorista = dados.get("motorista")

    

    if not motorista:

        return jsonify({"status": "erro", "mensagem": "Motorista não especificado."}), 400

    if not driver:

        return jsonify({"status": "erro", "mensagem": "Navegador não está ativo."}), 400

    garantir_abas_anjun(driver)

    if not aba_atribuicao_anjun:

        return jsonify({"status": "erro", "mensagem": "Aba de atribuição não está ativa."}), 400

        

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



# ==============================================================================

# ENGINE DIRETA DE API DA IMILE (REQUEST & RESPONSE - MODO ULTRA-RÁPIDO ~80ms)

# ==============================================================================



cache_sessao_imile = {

    "token": "376ea814-8b8a-4790-8d65-27cb9905c885",

    "currentStationCode": "S210570001",

    "userCode": "2106085001",

    "orgId": 10,

    "stationName": "DS AVR",

    "timestamp": 0

}



cache_motoristas_imile = {

    "lista": [],

    "mapa": {},

    "timestamp": 0

}



def carregar_tokens_imile_salvos():

    try:

        if os.path.exists(CONFIG_IMILE_TOKENS):

            with open(CONFIG_IMILE_TOKENS, 'r', encoding='utf-8') as f:

                return json.load(f) or {}

    except Exception:

        pass

    return {}



def salvar_token_imile_conta(sess_dict, conta_id=None):

    try:

        if not sess_dict or not sess_dict.get("token"):

            return

        ucode = str(sess_dict.get("userCode") or "").strip()

        cid_alvo = str(conta_id or "").strip()

        todas_contas = carregar_contas_plataformas().get("imile", {}).get("contas", [])

        if ucode:

            for c in todas_contas:

                if str(c.get("login_usuario") or "").strip().lower() == ucode.lower():

                    cid_alvo = c.get("id")

                    break

        if not cid_alvo:

            cid_alvo, _ = obter_conta_ativa_plataforma("imile")

        dados = carregar_tokens_imile_salvos()

        dados[cid_alvo] = {

            "conta_id": cid_alvo,

            "token": sess_dict.get("token"),

            "currentStationCode": sess_dict.get("currentStationCode"),

            "userCode": ucode,

            "orgId": sess_dict.get("orgId", 10),

            "stationName": sess_dict.get("stationName", ""),

            "cookie_str": sess_dict.get("cookie_str", ""),

            "timestamp": time.time()

        }

        with open(CONFIG_IMILE_TOKENS, 'w', encoding='utf-8') as f:

            json.dump(dados, f, ensure_ascii=False, indent=2)

    except Exception as e:

        print(f"[Aviso] Falha ao salvar token iMile por conta: {e}")



def atualizar_sessao_imile(drv=None, forcar=False, conta_id=None):

    """

    Captura automaticamente o token de autorização, cookies e dados do galpão

    a partir da janela do Chrome onde o usuário está logado na iMile, isolando por base/conta.

    """

    global cache_sessao_imile, driver

    cid, conta_obj = obter_conta_ativa_plataforma("imile", conta_id)

    login_esperado = str(conta_obj.get("login_usuario") or "").strip()



    # Se não for forçado e o cache atual pertencer à mesma conta/userCode

    if not forcar and cache_sessao_imile.get("token") and (time.time() - cache_sessao_imile.get("timestamp", 0) < 600):

        uc_cache = str(cache_sessao_imile.get("userCode") or "").strip()

        if not login_esperado or not uc_cache or uc_cache.lower() == login_esperado.lower():

            return cache_sessao_imile



    alvo_driver = drv if drv else (driver if (not plataforma_ativa or 'imile' in str(plataforma_ativa).lower()) else None)

    aba_imile_encontrada = False



    if alvo_driver and (not conta_id or cid == conta_ativa or not conta_ativa):

        try:

            if hasattr(alvo_driver, 'window_handles') and alvo_driver.window_handles:

                try:

                    curr_url = alvo_driver.current_url.lower()

                except Exception:

                    curr_url = ""

                if "imile" in curr_url:

                    aba_imile_encontrada = True

                else:

                    for h in alvo_driver.window_handles:

                        try:

                            alvo_driver.switch_to.window(h)

                            if "imile" in alvo_driver.current_url.lower():

                                aba_imile_encontrada = True

                                break

                        except Exception:

                            pass

            if aba_imile_encontrada:

                cookies = alvo_driver.get_cookies()

                token = None

                current_oc = None

                user_info = None



                for c in cookies:

                    name = c.get('name', '')

                    val = c.get('value', '')

                    if name == 'IMILE_ACCESS_TOKEN' and val:

                        token = val

                    elif name == 'ACCESS_TOKEN' and val and not token:

                        token = val.replace('Bearer ', '').replace('Bearer%20', '').strip()

                    elif name == 'currentOcCode' and val:

                        current_oc = val

                    elif name == 'UserInfo' and val:

                        try:

                            import urllib.parse

                            user_info = json.loads(urllib.parse.unquote(val))

                        except Exception:

                            pass



                if not token:

                    try:

                        ls_token = alvo_driver.execute_script(

                            "return window.localStorage.getItem('token') || "

                            "window.localStorage.getItem('ACCESS_TOKEN') || "

                            "window.localStorage.getItem('IMILE_ACCESS_TOKEN');"

                        )

                        if ls_token:

                            token = ls_token.replace('Bearer ', '').strip()

                    except Exception:

                        pass



                if token:

                    uc_capturado = (user_info.get("userCode") if isinstance(user_info, dict) else None) or login_esperado or cache_sessao_imile.get("userCode")

                    if not login_esperado or not uc_capturado or str(uc_capturado).strip().lower() == login_esperado.lower():

                        cache_sessao_imile["token"] = token

                        cache_sessao_imile["cookie_str"] = "; ".join([f"{c['name']}={c['value']}" for c in cookies if c.get('name') and c.get('value')])

                        cache_sessao_imile["timestamp"] = time.time()

                        if current_oc:

                            cache_sessao_imile["currentStationCode"] = current_oc

                        if isinstance(user_info, dict):

                            cache_sessao_imile["userCode"] = user_info.get("userCode", uc_capturado)

                            cache_sessao_imile["orgId"] = user_info.get("orgId", cache_sessao_imile.get("orgId", 10))

                            cache_sessao_imile["stationName"] = user_info.get("stationName", cache_sessao_imile.get("stationName", ""))

                        elif uc_capturado:

                            cache_sessao_imile["userCode"] = uc_capturado

                        salvar_token_imile_conta(cache_sessao_imile, cid)

                        print(f"[+] [iMile API] Sessão capturada do Chrome (Base {cid})! Estação: {cache_sessao_imile.get('currentStationCode')} | Token: {token[:8]}...")

                        return cache_sessao_imile

        except Exception as e:

            print(f"[Aviso] [iMile API] Não foi possível extrair sessão do navegador: {str(e)}")



    # Fallback para token salvo especificamente desta base/conta em config_imile_tokens.json

    salvos = carregar_tokens_imile_salvos()

    sess_salva = salvos.get(cid)

    if not sess_salva and login_esperado:

        for v in salvos.values():

            if isinstance(v, dict) and str(v.get("userCode") or "").strip().lower() == login_esperado.lower():

                sess_salva = v

                break



    if sess_salva and sess_salva.get("token"):

        cache_sessao_imile.update(sess_salva)

        cache_sessao_imile["timestamp"] = time.time()

        return dict(sess_salva)



    # Se a conta ativa tem login_esperado diferente do userCode em cache_sessao_imile, não usa token de outra base!

    if login_esperado and str(cache_sessao_imile.get("userCode") or "").strip().lower() != login_esperado.lower():

        return {"token": None, "currentStationCode": "", "userCode": login_esperado}



    return cache_sessao_imile



def carregar_motoristas_imile_api(forcar=False, conta_id=None):

    """

    Obtém via API oficial da iMile (/hrms/user/associate/list) os entregadores

    ativos cadastrados especificamente na BASE ATIVA (conta_id), com seus respectivos daCode e daName.

    """

    global cache_motoristas_imile, cache_motoristas_imile_por_conta

    cid, conta_obj = obter_conta_ativa_plataforma("imile", conta_id)

    

    cache_conta = cache_motoristas_imile_por_conta.get(cid)

    if not forcar and cache_conta and cache_conta.get("lista") and (time.time() - cache_conta.get("timestamp", 0) < 600):

        return cache_conta["lista"], cache_conta["mapa"]



    sessao = atualizar_sessao_imile(forcar=forcar, conta_id=cid)

    token = sessao.get("token")

    station_code = sessao.get("currentStationCode", "S210570001")

    

    if not token or not station_code:

        if cache_conta and cache_conta.get("lista"):

            return cache_conta["lista"], cache_conta["mapa"]

        salvos_base = obter_motoristas_da_base_salvos("imile", cid)

        if salvos_base:

            lista_fb = [{"daCode": "", "daName": n, "id": idx} for idx, n in enumerate(salvos_base)]

            mapa_fb = {remover_acentos(n.lower()): obj for n, obj in zip(salvos_base, lista_fb)}

            return lista_fb, mapa_fb

        return [], {}



    url = "https://ds.imile.com/hrms/user/associate/list"

    headers = {

        "accept": "application/json, text/plain, */*",

        "authorization": f"Bearer {token}",

        "content-type": "application/json",

        "hubcode": station_code,

        "lang": "pt_BR",

        "origin": "https://ds.imile.com",

        "referer": "https://ds.imile.com/",

        "sys-name": "DS",

        "sys-portal": "DS",

        "timezone": "-3",

        "front-sec": json.dumps({"orgId": sessao.get("orgId", 10), "entId": 10, "userCode": sessao.get("userCode", "2106085001"), "moduleId": 10007, "client": "pc"}),

        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"

    }

    if sessao.get("cookie_str"):

        headers["cookie"] = sessao["cookie_str"]

    data = json.dumps({"ocCodeList": [station_code], "isDriver": 1, "status": "ACTIVE"}).encode('utf-8')



    try:

        req = urllib.request.Request(url, data=data, headers=headers)

        with urllib.request.urlopen(req, timeout=4.0) as resp:

            res = json.loads(resp.read().decode('utf-8'))

            drivers_raw = res.get("resultObject", [])

            

            # Se atingiu o limite de 50 da iMile, complementa com busca por letras para capturar 100% dos motoristas cadastrados

            if len(drivers_raw) >= 50:

                vistos_codes = {d.get("userCode") for d in drivers_raw if d.get("userCode")}

                letras = ['a', 'e', 'i', 'o', 'u', 'b', 'c', 'd', 'f', 'g', 'j', 'l', 'm', 'p', 'r', 's', 't', 'v']

                for let in letras:

                    try:

                        data_let = json.dumps({"ocCodeList": [station_code], "isDriver": 1, "status": "ACTIVE", "keyword": let}).encode('utf-8')

                        req_let = urllib.request.Request(url, data=data_let, headers=headers)

                        with urllib.request.urlopen(req_let, timeout=2.0) as resp_let:

                            res_let = json.loads(resp_let.read().decode('utf-8'))

                            for d_sub in res_let.get("resultObject", []):

                                uc_sub = d_sub.get("userCode")

                                if uc_sub and uc_sub not in vistos_codes:

                                    vistos_codes.add(uc_sub)

                                    drivers_raw.append(d_sub)

                    except Exception:

                        pass

            

            lista = []

            mapa = {}

            for d in drivers_raw:

                nome_oficial = (d.get("userName") or "").strip()

                da_code = (d.get("userCode") or "").strip()

                if not nome_oficial or not da_code:

                    continue

                

                obj = {

                    "daCode": da_code,

                    "daName": nome_oficial,

                    "id": d.get("id")

                }

                lista.append(obj)

                

                # Normalização para busca

                norm_nome = remover_acentos(nome_oficial.lower())

                mapa[norm_nome] = obj

                

                partes = norm_nome.split()

                if len(partes) >= 2:

                    mapa[" ".join(partes[:2])] = obj

                    mapa[partes[-1]] = obj

                    mapa[partes[0]] = obj



            if lista:

                cache_motoristas_imile["lista"] = lista

                cache_motoristas_imile["mapa"] = mapa

                cache_motoristas_imile["timestamp"] = time.time()

                cache_motoristas_imile_por_conta[cid] = {

                    "lista": lista,

                    "mapa": mapa,

                    "timestamp": time.time()

                }

                salvar_motoristas_da_base("imile", cid, [m["daName"] for m in lista])

                print(f"[+] [iMile API] {len(lista)} motoristas ativos sincronizados da base {cid} ({station_code})!")

                

                # Sincroniza também no banco de dados SQLite caso ainda não tenha cidade vinculada

                try:

                    conn = conectar_banco()

                    cursor = conn.cursor()

                    for mot in lista:

                        nome = mot["daName"]

                        cursor.execute(

                            "SELECT 1 FROM motoristas_plataforma WHERE LOWER(motorista) = LOWER(?) AND LOWER(plataforma) = 'imile' LIMIT 1",

                            (nome,)

                        )

                        if cursor.fetchone():

                            continue

                        cidade_cand = "Geral"

                        for c_item in carregar_cidades():

                            if c_item and remover_acentos(c_item.lower()) in remover_acentos(nome.lower()):

                                cidade_cand = c_item

                                break

                        cursor.execute("""

                            INSERT OR IGNORE INTO motoristas_plataforma (cidade, motorista, plataforma)

                            VALUES (?, ?, 'imile')

                        """, (cidade_cand, nome))

                    conn.commit()

                    conn.close()

                    invalidar_cache_ram_cidades_motoristas()

                    try:

                        excel_path = obter_caminho_excel()

                        gerar_planilha_motoristas_excel(excel_path)

                        if os.path.exists(excel_path):

                            meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

                            with open(meta_mtime_file, 'w') as f_meta:

                                f_meta.write(str(os.path.getmtime(excel_path)))

                    except Exception:

                        pass

                except Exception:

                    pass

                

            return lista, mapa

    except Exception as e:

        print(f"[Aviso] [iMile API] Falha ao sincronizar motoristas da API ({cid}): {str(e)}")

        if cache_conta and cache_conta.get("lista"):

            return cache_conta["lista"], cache_conta["mapa"]

        salvos_base = obter_motoristas_da_base_salvos("imile", cid)

        if salvos_base:

            lista_fb = [{"daCode": "", "daName": n, "id": idx} for idx, n in enumerate(salvos_base)]

            mapa_fb = {remover_acentos(n.lower()): obj for n, obj in zip(salvos_base, lista_fb)}

            return lista_fb, mapa_fb

        return [], {}



def resolver_motorista_imile_api(mot_clean):

    """

    Localiza o objeto do motorista {daCode, daName} por aproximação inteligente.

    """

    if not mot_clean:

        return None

        

    lista, mapa = carregar_motoristas_imile_api()

    if not lista:

        lista, mapa = carregar_motoristas_imile_api(forcar=True)

        

    if not lista:

        return None



    try:

        imile_map, _ = carregar_mapeamento_motoristas()

        mot_clean = imile_map.get(mot_clean.lower(), mot_clean)

    except Exception:

        pass



    nb = remover_acentos(mot_clean.strip().lower())



    # 1. Match exato no mapa

    if nb in mapa:

        return mapa[nb]



    # 2. Match exato no userName

    for d in lista:

        if remover_acentos(d["daName"].lower()) == nb:

            return d



    # 3. Match por substring

    for d in lista:

        dn = remover_acentos(d["daName"].lower())

        if nb in dn or dn in nb:

            return d



    # 4. Match por pontuação de palavras (Tokens)

    tokens = [t for t in re.split(r'[\s\-_]+', nb) if len(t) >= 2]

    best = None

    best_score = 0

    for d in lista:

        dn = remover_acentos(d["daName"].lower())

        score = sum(1 for t in tokens if t in dn)

        if score > best_score:

            best_score = score

            best = d

    if best and best_score >= 1:

        return best



    # 5. Busca sob demanda direta na API iMile com keyword (para motoristas recém-adicionados ou fora do top 50)

    try:

        sessao = atualizar_sessao_imile()

        token = sessao.get("token")

        station_code = sessao.get("currentStationCode", "S210570001")

        if token and station_code:

            headers_busca = {

                "accept": "application/json, text/plain, */*",

                "authorization": f"Bearer {token}",

                "content-type": "application/json",

                "hubcode": station_code,

                "lang": "pt_BR",

                "origin": "https://ds.imile.com",

                "referer": "https://ds.imile.com/",

                "sys-name": "DS",

                "sys-portal": "DS",

                "timezone": "-3",

                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"

            }

            body_busca = json.dumps({"ocCodeList": [station_code], "isDriver": 1, "status": "ACTIVE", "keyword": mot_clean}).encode('utf-8')

            req_b = urllib.request.Request("https://ds.imile.com/hrms/user/associate/list", data=body_busca, headers=headers_busca)

            with urllib.request.urlopen(req_b, timeout=3.0) as resp_b:

                data_b = json.loads(resp_b.read().decode('utf-8'))

                for item_b in data_b.get("resultObject", []):

                    nm_b = (item_b.get("userName") or "").strip()

                    cd_b = (item_b.get("userCode") or "").strip()

                    if nm_b and cd_b:

                        obj_novo = {"daCode": cd_b, "daName": nm_b, "id": item_b.get("id")}

                        lista.append(obj_novo)

                        mapa[remover_acentos(nm_b.lower())] = obj_novo

                        cache_motoristas_imile["lista"] = lista

                        cache_motoristas_imile["mapa"] = mapa

                        cid_ativo, _ = obter_conta_ativa_plataforma("imile")

                        salvar_motoristas_da_base("imile", cid_ativo, [m["daName"] for m in lista])

                        return obj_novo

    except Exception as e_busca:

        print(f"[Aviso] [iMile API] Busca sob demanda por '{mot_clean}' falhou: {e_busca}")



    return None



def executar_post_imile(endpoint_path, payload, sessao_override=None):

    """

    Executa POST na API da iMile em ~25ms com os headers e token de sessão.

    Retorna (sucesso: bool, mensagem: str, dados_resposta: dict)

    """

    sessao = sessao_override if sessao_override else atualizar_sessao_imile()

    token = sessao.get("token")

    if not token and not sessao_override:

        sessao = atualizar_sessao_imile(forcar=True)

        token = sessao.get("token")

    station_code = sessao.get("currentStationCode", "S210570001")

    

    if not token:

        return False, "Sessão da iMile não encontrada no navegador Chrome", {}



    url = f"https://ds.imile.com{endpoint_path}"

    headers = {

        "accept": "application/json, text/plain, */*",

        "authorization": f"Bearer {token}",

        "content-type": "application/json",

        "hubcode": station_code,

        "lang": "pt_BR",

        "origin": "https://ds.imile.com",

        "referer": "https://ds.imile.com/",

        "sys-name": "DS",

        "sys-portal": "DS",

        "timezone": "-3",

        "front-sec": json.dumps({"orgId": sessao.get("orgId", 10), "entId": 10, "userCode": sessao.get("userCode", "2106085001"), "moduleId": 10007, "client": "pc"}),

        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"

    }

    if sessao.get("cookie_str"):

        headers["cookie"] = sessao["cookie_str"]

    if "track/query" in endpoint_path:

        headers["resource-code"] = "dsTrackQuery"

        headers["x-page-path"] = "https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery"



    data = json.dumps(payload).encode('utf-8')

    ultimo_erro = ""

    for tentativa in range(1, 4):

        try:

            req = urllib.request.Request(url, data=data, headers=headers)

            with urllib.request.urlopen(req, timeout=8.0) as resp:

                raw = resp.read().decode('utf-8')

                res = json.loads(raw) if raw else {}

                if not isinstance(res, dict):

                    res = {}

                

                st = res.get("status") or res.get("resultCode") or res.get("code")

                msg = res.get("message") or res.get("msg") or ""

                

                # Validação do resultObject da iMile

                obj = res.get("resultObject")

                if isinstance(obj, dict):

                    voice_type = str(obj.get("voiceType", "")).lower()

                    block_info = (obj.get("blockInfo") or obj.get("warnMsg") or obj.get("interceptReason") or obj.get("problemDesc") or obj.get("problemReason") or "").strip()

                    

                    # Só é erro se a iMile expressamente rejeitar com voiceType='fail' ou mensagem de bloqueio

                    if voice_type == "fail" or (block_info and not obj.get("repeat") and not any(k in block_info.lower() for k in ["success", "sucesso", "ok", "operacao realizada"])):

                        err_msg = block_info if block_info else (msg or "Pacote recusado pela iMile")

                        return False, err_msg.strip(), res



                if st in ["success", 200, "200"] or "success" in str(msg).lower():

                    return True, msg or "Operação realizada com sucesso", res

                elif str(res.get("resultCode")) in ["44882", "50000", "20000"] or any(k in str(msg).lower() for k in ["system is busy", "system abnormality", "tente novamente"]):

                    # Oscilação momentânea de carga do servidor da iMile - aguarda 120ms e retenta na próxima tentativa do loop

                    if tentativa < 3:

                        time.sleep(0.12 * tentativa)

                        continue

                    return False, msg or "Sistema iMile temporariamente ocupado", res

                elif st in [401, "401", 403, "403"] or any(k in str(msg).lower() for k in ["sessão", "sessao", "token", "unauthorized", "login", "expired"]):

                    cache_sessao_imile["token"] = None

                    if tentativa == 1:

                        sessao_nova = atualizar_sessao_imile(forcar=True)

                        tk_novo = sessao_nova.get("token")

                        if tk_novo:

                            headers["authorization"] = f"Bearer {tk_novo}"

                            print("[*] [iMile API] Token renovado automaticamente! Retentando requisição...")

                            continue

                    return False, f"Sessão expirada: {msg}", res

                else:

                    return False, msg or "Erro retornado pela iMile", res

        except urllib.error.HTTPError as he:

            if he.code in (401, 403):

                cache_sessao_imile["token"] = None

                if tentativa == 1:

                    sessao_nova = atualizar_sessao_imile(forcar=True)

                    tk_novo = sessao_nova.get("token")

                    if tk_novo:

                        headers["authorization"] = f"Bearer {tk_novo}"

                        print(f"[*] [iMile API] HTTP {he.code} recebido. Token renovado automaticamente, retentando...")

                        continue

            try:

                err_body = he.read().decode('utf-8')

                err_json = json.loads(err_body) if err_body else {}

                if not isinstance(err_json, dict):

                    err_json = {}

                msg = err_json.get("message") or err_json.get("msg") or str(he)

                return False, f"Sessão expirada ({he.code}): {msg}" if he.code in (401, 403) else msg, err_json

            except Exception:

                return False, f"Erro HTTP {he.code}: {str(he)}", {}

        except Exception as e:

            ultimo_erro = str(e)

            print(f"[!] [iMile API] Oscilação de internet em {endpoint_path} (Tentativa {tentativa}/3): {ultimo_erro}")

            if tentativa < 3:

                time.sleep(0.4)

                continue

    return False, f"Internet lenta / oscilação na iMile ({ultimo_erro})", {}



def bipar_pacote_imile_api(codigo_qr, motorista, pacote_solto=False, modo_triagem_direta=False, conta_id=None):

    """

    Executa a bipagem ultra-rápida via API na iMile em ~80-150ms:

    1. Descarregamento (se modo pacote solto)

    2. Entrada / Chegada no Galpão (inbound/submit)

    3. Consulta de Dados de Destino (track/query -> Cidade, CEP, Endereço)

    4. Conferência Anti-Divergência Automática (Cidade vs Motorista)

    5. Atribuição ao Entregador (ofdAndReturnOfd/submit)

    Retorna (sucesso: bool/str, mensagem: str, motorista_atribuido: str, cidade: str, cep: str, destinatario: str, endereco: str)

    """

    if conta_id and str(conta_id).strip() not in ["", "padrao"]:

        sessao = atualizar_sessao_imile(conta_id=conta_id)

    else:

        sessao = atualizar_sessao_imile()

    token = sessao.get("token")

    if not token:

        sessao = atualizar_sessao_imile(forcar=True, conta_id=conta_id if (conta_id and str(conta_id).strip() not in ["", "padrao"]) else None)

        token = sessao.get("token")

    if not token:

        return "aguardando_login", "Sessão da iMile desconectada. Faça o login na iMile no Chrome.", "", "", "", "", ""

        

    station_code = sessao.get("currentStationCode", "S210570001")

    codigo_limpo = str(codigo_qr).strip()



    # 1. Descarregamento (se modo pacote solto)

    if pacote_solto:

        payload_desc = {

            "currentStationCode": station_code,

            "unloadingPictureUrls": [],

            "scanNumber": codigo_limpo

        }

        ok_desc, msg_desc, _ = executar_post_imile("/lm/express/ops/v1/biz/unloading/submit", payload_desc)

        if not ok_desc:

            msg_low = (msg_desc or "").lower()

            if any(k in msg_low for k in ["success", "sucesso", "já descarregado", "ja descarregado", "repetido", "duplicad", "já existe"]):

                ok_desc = True

            elif any(k in msg_low for k in ["sessão", "sessao", "token", "401", "unauthorized"]):

                cache_sessao_imile["token"] = None

                return "aguardando_login", f"Sessão da iMile expirada: {msg_desc}", "", "", "", "", ""

            else:

                print(f"[!] [iMile API] Erro no Descarregamento: {msg_desc}")

                return False, f"Descarregamento: {msg_desc}", "", "", "", "", ""



    # 2. Entrada / Chegada (ArrivalScan)

    from datetime import datetime

    hoje_str = datetime.now().strftime("%Y-%m-%d")

    payload_inbound = {

        "currentStationCode": station_code,

        "nextWorkDay": hoje_str,

        "autoGetDa": True,

        "scanNumber": codigo_limpo

    }

    ok_in, msg_in, res_in = executar_post_imile("/lm/express/ops/v1/biz/inbound/submit", payload_inbound)

    if not ok_in:

        msg_low = (msg_in or "").lower()

        ro_in = (res_in.get("resultObject") or {}) if isinstance(res_in, dict) else {}

        if not isinstance(ro_in, dict):

            ro_in = {}

        block_code = str(ro_in.get("blockCode") or ro_in.get("msgCode") or "")

        scan_desc = str(ro_in.get("scanTypeDesc") or "").lower()

        if (block_code in ["1121"] or "recebido no ds" in scan_desc or 

            any(k in msg_low for k in ["success", "sucesso", "já escaneado", "já bipado", "já recepcionado", "repetido", "duplicad", "já existe", "ja existe", "motivo não registrado", "motivo nao registrado"])):

            print(f"[*] [iMile API] Pacote {codigo_limpo} já possui entrada no galpão ({msg_in} / code: {block_code}). Prosseguindo para atribuição...")

            ok_in = True

        elif any(k in msg_low for k in ["sessão", "sessao", "token", "401", "unauthorized"]):

            cache_sessao_imile["token"] = None

            return "aguardando_login", f"Sessão da iMile expirada: {msg_in}", "", "", "", "", ""

        else:

            print(f"[!] [iMile API] Erro na Entrada: {msg_in}")

            return False, f"Entrada: {msg_in}", "", "", "", "", ""



    # 3. Consulta de Dados de Destino (Cidade, CEP, Endereço, Bairro, Telefone, Loja, Produto, Valor via track/query)

    cidade_pacote = ""

    cep_pacote = ""

    endereco_pacote = ""

    destinatario_pacote = ""

    waybill_pacote = ""

    try:

        # Se for código de referência ou alfanumérico (ex: KW..., BR..., LP...), prioriza referenceNo; caso numérico puro, prioriza waybillNo

        cod_upper = codigo_limpo.upper()

        if cod_upper.startswith(("KW", "BR", "LP", "NL", "BZ")) or not codigo_limpo.isdigit():

            tipos_busca = ["referenceNo", "waybillNo"]

        else:

            tipos_busca = ["waybillNo", "referenceNo"]



        for stype in tipos_busca:

            ok_query, _, res_query = executar_post_imile("/saastms/v1/biz/track/query", {

                "searchType": stype,

                "searchValue": codigo_limpo

            })

            if ok_query and isinstance(res_query, dict):

                ro = res_query.get("resultObject")

                if isinstance(ro, dict):

                    ci = ro.get("consigneeInfo") or {}

                    si = ro.get("shipperInfo") or {}

                    wi = ro.get("waybillInfo") or ro.get("orderInfo") or {}

                    base = ro.get("baseInfo") or {}



                    waybill_pacote = str(base.get("waybillNo") or ro.get("waybillNo") or "").strip()

                    cidade_pacote = (ci.get("consigneeCity") or base.get("consigneeCity") or "").strip()

                    cep_pacote = (ci.get("consigneeZipCode") or base.get("consigneeZipCode") or "").strip()

                    endereco_pacote = (ci.get("consigneeAddress") or base.get("consigneeAddress") or "").strip()

                    destinatario_pacote = (ci.get("consignee") or base.get("consigneeName") or "").strip()

                    bairro_pacote = (ci.get("consigneeArea") or ci.get("consigneeDistrict") or ci.get("consigneeTown") or "").strip()

                    if destinatario_pacote == "****" or not destinatario_pacote:

                        destinatario_pacote = bairro_pacote

                    tel_pacote = str(ci.get("consigneePhone") or ci.get("consigneeMobile") or ci.get("consigneeTel") or ro.get("consigneePhone") or "").strip()

                    emp_pacote = str(ro.get("customerName") or ro.get("clientName") or ro.get("platformSource") or si.get("shipperCompany") or si.get("shipperName") or wi.get("customerName") or wi.get("sellerName") or "").strip()

                    prod_pacote = str(ro.get("goodsName") or ro.get("skuName") or ro.get("itemName") or wi.get("goodsName") or wi.get("itemName") or "").strip()

                    val_pacote = str(ro.get("declaredValue") or ro.get("goodsValue") or wi.get("declaredValue") or wi.get("goodsValue") or "").strip()

                    registrar_detalhes_extras_pacote(

                        [codigo_qr, codigo_limpo, waybill_pacote],

                        bairro=bairro_pacote,

                        telefone=tel_pacote,

                        negocios=emp_pacote,

                        produto=prod_pacote,

                        valor_declarado=val_pacote,

                        recebedor=destinatario_pacote,

                        cep=cep_pacote,

                        endereco=endereco_pacote

                    )

                    if cidade_pacote or cep_pacote:

                        print(f"[+] [iMile API] Consulta de rastreio exitosa via {stype} ({codigo_limpo}): Cidade='{cidade_pacote}', CEP='{cep_pacote}'")

                        break



        # Se a cidade veio em branco mas a iMile informou o CEP, descobre a cidade instantaneamente pelo CEP!

        if not cidade_pacote and cep_pacote:

            cid_por_cep = obter_cidade_por_cep(cep_pacote)

            if cid_por_cep:

                cidade_pacote = cid_por_cep

                print(f"[+] [iMile API] Cidade resolvida instantaneamente pelo CEP {cep_pacote}: {cidade_pacote}")



        if cidade_pacote:

            print(f"[+] [iMile API] Informações obtidas: Cidade: {cidade_pacote} | CEP: {cep_pacote} | Endereço: {endereco_pacote}")

    except Exception as e_q:

        print(f"[Aviso] [iMile API] Não foi possível consultar detalhes do pacote: {e_q}")



    # 4. Verificação de Divergência de Cidade / CEP vs Motorista (Anti-Divergência Automático)

    mot_clean = str(motorista).strip() if motorista else ""

    if modo_triagem_direta:

        if not cidade_pacote:

            return "divergente", "Divergência: Pacote sem cidade de destino informada pelo rastreio!", "Sem Cidade", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote



        lista_cidades = carregar_cidades()

        cidade_map = encontrar_cidade_mapeada(cidade_pacote, lista_cidades) or cidade_pacote

        mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_map, "imile", cep=cep_pacote, bairro=bairro_pacote)

        if not mots_esperados and cidade_map != cidade_pacote:

            mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_pacote, "imile", cep=cep_pacote, bairro=bairro_pacote)



        if not mots_esperados:

            detalhe_loc = f"Bairro {bairro_pacote}" if bairro_pacote else (f"CEP {cep_pacote}" if cep_pacote else "")

            detalhe_info = f" ({detalhe_loc})" if detalhe_loc else ""

            msg_alerta = f"Divergência: Nenhum motorista cadastrado para {cidade_pacote}{detalhe_info}!"

            print(f"[!] [iMile API] DIVERGÊNCIA MODO TRIAGEM DIRETA! {msg_alerta}")

            return "divergente", msg_alerta, "Sem Motorista", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote



        mot_clean = mots_esperados[0]

        print(f"[+] [iMile API] MODO TRIAGEM DIRETA: {cidade_pacote} -> Atribuindo automaticamente para {mot_clean}!")

    elif mot_clean and mot_clean not in ["---", "Apenas Entrada (Sem Atribuição)"] and cidade_pacote:

        lista_cidades = carregar_cidades()

        cidade_map = encontrar_cidade_mapeada(cidade_pacote, lista_cidades) or cidade_pacote

        todos_mots_cidade = carregar_motoristas_cidade(cidade_map, "imile", cep=cep_pacote, bairro=bairro_pacote)

        if not todos_mots_cidade and cidade_map != cidade_pacote:

            todos_mots_cidade = carregar_motoristas_cidade(cidade_pacote, "imile", cep=cep_pacote, bairro=bairro_pacote)



        mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_map, "imile", cep=cep_pacote, bairro=bairro_pacote)

        if not mots_esperados and cidade_map != cidade_pacote:

            mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_pacote, "imile", cep=cep_pacote, bairro=bairro_pacote)

            

        eh_divergente = False

        msg_divergente = ""

        mot_retorno_div = ""



        if todos_mots_cidade and not mots_esperados:

            detalhe_loc = f"Bairro {bairro_pacote}" if bairro_pacote else (f"CEP {cep_pacote}" if cep_pacote else "")

            detalhe_info = f" ({detalhe_loc})" if detalhe_loc else ""

            msg_alerta = f"Divergência: Pacote de {cidade_pacote}{detalhe_info} não está coberto pelas regras permitidas para {cidade_pacote}!"

            print(f"[!] [iMile API] DIVERGÊNCIA (Atribuindo a {mot_clean})! {msg_alerta}")

            eh_divergente = True

            msg_divergente = msg_alerta

            mot_retorno_div = "Fora da Regra"



        norm_mot = remover_acentos(mot_clean.lower()).replace('-', '').replace('_', '').replace(' ', '')

        da_obj_check = resolver_motorista_imile_api(mot_clean)

        da_uname_norm = remover_acentos(da_obj_check["daName"].lower()).replace('-', '').replace('_', '').replace(' ', '') if da_obj_check else norm_mot



        if mots_esperados:

            mots_esp_norm = [remover_acentos(m.lower()).replace('-', '').replace('_', '').replace(' ', '') for m in mots_esperados]

            

            if norm_mot not in mots_esp_norm and da_uname_norm not in mots_esp_norm:

                esp_display = " / ".join(mots_esperados)

                bairro_info = f" ({bairro_pacote})" if bairro_pacote else ""

                cep_info = f" (CEP {cep_pacote})" if cep_pacote and not bairro_pacote else ""

                print(f"[!] [iMile API] DIVERGÊNCIA (Atribuindo a {mot_clean})! Pacote de {cidade_pacote}{bairro_info}{cep_info} pertence a {esp_display}, mas lote ativo é de {mot_clean}!")

                mot_retorno_div = esp_display if foi_por_regra else ""

                msg_divergente = f"Pacote de {cidade_pacote}{cep_info} pertence a {esp_display}, mas você está bipando a pilha de {mot_clean}!"

                eh_divergente = True

        elif not eh_divergente:

            # BLINDAGEM ANTI-DIVERGÊNCIA: Se a cidade do pacote não possui motorista mapeado na iMile,

            # verifica se o motorista ativo possui cidades mapeadas especificamente para ele nesta plataforma.

            cidades_mot = obter_cidades_motorista(mot_clean, "imile", da_uname_norm)

            if cidades_mot:

                cids_mot_norm = [normalizar_cidade_estrita(c) for c in cidades_mot]

                cid_teste_norm = normalizar_cidade_estrita(cidade_map or cidade_pacote)

                if cid_teste_norm not in cids_mot_norm:

                    cidades_display = " / ".join(cidades_mot)

                    cep_info = f" (CEP {cep_pacote})" if cep_pacote else ""

                    msg_alerta = f"Divergência: Pacote de {cidade_pacote}{cep_info} não pertence ao motorista {mot_clean} (Cidades vinculadas: {cidades_display})!"

                    print(f"[!] [iMile API] DIVERGÊNCIA BLINDADA (Atribuindo a {mot_clean})! {msg_alerta}")

                    eh_divergente = True

                    msg_divergente = msg_alerta

                    mot_retorno_div = cidades_display



    # 5. Atribuição ao Entregador (assignDA)

    mot_nome_final = motorista

    if mot_clean and mot_clean not in ["---", "Apenas Entrada (Sem Atribuição)"]:

        da_obj = resolver_motorista_imile_api(mot_clean)

        if not da_obj:

            return False, f"Motorista '{mot_clean}' não localizado na lista oficial da iMile", "", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote

            

        da_code = da_obj["daCode"]

        da_name = da_obj["daName"]

        mot_nome_final = da_name

        

        payload_assign = {

            "daCode": da_code,

            "scanNumber": codigo_limpo,

            "ocCode": station_code,

            "forceOperate": True,

            "fromAssign": 1,

            "daName": da_name,

            "currentStationCode": station_code,

            "currentStationName": sessao.get("stationName", "DS AVR"),

            "isRefactor": True,

            "usePreSorting": False

        }

        ok_da, msg_da, _ = executar_post_imile("/lm/express/ops/v1/biz/ofdAndReturnOfd/submit", payload_assign)

        if not ok_da:

            msg_low = msg_da.lower()

            if any(k in msg_low for k in ["success", "sucesso", "já atribuído", "já atribuido", "repetido", "duplicad", "repeat scan", "repeat"]):

                ok_da = True

            else:

                # Retentativa rápida caso o servidor da iMile tenha levado alguns milissegundos para processar a Entrada

                time.sleep(0.25)

                # Se tivermos o waybill oficial retornado pelo rastreio, tenta atribuir por ele se o código original falhar

                if waybill_pacote and waybill_pacote != codigo_limpo:

                    payload_assign["scanNumber"] = waybill_pacote

                ok_da, msg_da, _ = executar_post_imile("/lm/express/ops/v1/biz/ofdAndReturnOfd/submit", payload_assign)

                msg_low = (msg_da or "").lower()

                if ok_da or any(k in msg_low for k in ["success", "sucesso", "já atribuído", "já atribuido", "repetido", "duplicad", "repeat scan", "repeat"]):

                    ok_da = True

                else:

                    print(f"[!] [iMile API] Erro na Atribuição ({da_name}): {msg_da}")

                    return False, f"Atribuição ({da_name}): {msg_da}", da_name, cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote



    cidade_retorno = cidade_pacote if cidade_pacote else "Cidade Não Informada (Conferir)"

    if 'eh_divergente' in locals() and eh_divergente:

        return "divergente", msg_divergente, mot_retorno_div, cidade_retorno, cep_pacote, destinatario_pacote, endereco_pacote

    return True, "Pacote bipado com sucesso na iMile (API Ultra-Rápida)!", mot_nome_final, cidade_retorno, cep_pacote, destinatario_pacote, endereco_pacote



# ==============================================================================

# MOTOR DE REQUISIÇÕES DIRETAS (API ULTRA-RÁPIDA) - ANJUN EXPRESS

# ==============================================================================



cache_sessao_anjun = {

    "token": None,

    "siteId": 383,

    "siteCode": "SPRD093",

    "siteName": "SP-R-D093",

    "orgId": 383,

    "siteAddress": "R. Alferes José Ignatios, 26 - Parque Santa Elizabeth I, Avaré - SP, 18701-700",

    "siteArea": "parquesantaelizabeth",

    "siteCity": "Avaré",

    "siteLat": -23.1069575,

    "siteLng": -48.9104678,

    "siteState": "SP",

    "siteStreet": "R. Alferes José Ignatios, 26",

    "siteZipCode": "18701700",

    "timestamp": 0

}



cache_motoristas_anjun = {

    "lista": [],

    "mapa": {},

    "timestamp": 0

}



# ========================================================

# MOTOR DE BIPAGEM E GERENCIAMENTO DIRETO VIA API LOGGI (ARCO)

# ========================================================



cache_sessao_loggi = {

    "token": None,

    "exp": 0,

    "company_id": None,

    "dc_id": None,

    "routing_code": "AV3",

    "timestamp": 0

}



grupo_loggi_ativo = {

    "licensePlate": None,

    "tags": [],

    "cidade": None,

    "modo": "novo" # 'novo' ou 'existente'

}



def obter_contexto_loggi(drv=None, forcar=False):

    global cache_sessao_loggi, driver

    if not forcar and cache_sessao_loggi.get("token"):

        exp = cache_sessao_loggi.get("exp", 0)

        if (exp == 0 or time.time() < (exp - 60)) and (time.time() - cache_sessao_loggi.get("timestamp", 0) < 300):

            return cache_sessao_loggi

        

    alvo = drv if drv else driver

    if not alvo:

        porta_loggi = PORTAS_DEBUG.get("loggi", 9224)

        if is_chrome_debug_active(porta_loggi):

            try:

                conectar_chrome_existente("loggi")

                alvo = driver

            except Exception:

                pass

    if not alvo:

        return cache_sessao_loggi

        

    try:

        handles = getattr(alvo, 'window_handles', [])

        for h in handles:

            try:

                alvo.switch_to.window(h)

                if "arco.loggi.com" in (alvo.current_url or '').lower():

                    break

            except Exception:

                pass

                

        script_tok = '''

            var lastUser = '';

            for (var i = 0; i < localStorage.length; i++) {

                var k = localStorage.key(i);

                if (k.includes('LastAuthUser')) {

                    lastUser = localStorage.getItem(k);

                    break;

                }

            }

            for (var i = 0; i < localStorage.length; i++) {

                var k = localStorage.key(i);

                if (lastUser && k.includes(lastUser) && k.endsWith('.idToken')) {

                    return localStorage.getItem(k);

                }

                if (k.endsWith('.idToken')) {

                    return localStorage.getItem(k);

                }

            }

            return '';

        '''

        tok = alvo.execute_script(script_tok)

        if not tok:

            return cache_sessao_loggi

            

        import base64, json, re

        parts = tok.split('.')

        payload_raw = parts[1] + '=' * (-len(parts[1]) % 4)

        payload = json.loads(base64.urlsafe_b64decode(payload_raw).decode('utf-8'))

        exp = int(payload.get('exp', 0))

        

        # Se forçar e o token do localStorage estiver vencido, tenta dar refresh na aba para Cognito renovar

        if forcar and exp > 0 and time.time() >= exp:

            print("[*] [Loggi] Token expirado detectado no Chrome. Atualizando aba para renovar sessão...")

            try:

                alvo.refresh()

                time.sleep(2.0)

                tok_novo = alvo.execute_script(script_tok)

                if tok_novo:

                    tok = tok_novo

                    parts = tok.split('.')

                    payload_raw = parts[1] + '=' * (-len(parts[1]) % 4)

                    payload = json.loads(base64.urlsafe_b64decode(payload_raw).decode('utf-8'))

                    exp = int(payload.get('exp', 0))

            except Exception as e_rf:

                print(f"[Aviso] Falha ao recarregar aba Loggi: {e_rf}")

                

        custom_access = json.loads(payload.get('custom:access', '{}'))

        last_mile = custom_access.get('lastMile', [{}])[0]

        lm_id = last_mile.get('id', '')

        company_id, dc_id = lm_id.split(':') if ':' in lm_id else ('leve-sp-avare-3-centro_ec7b', '1378')

        

        routing_code = 'AV3'

        try:

            curr_u = (alvo.current_url or '')

            code_det = extrair_codigo_base_loggi(curr_u)

            if code_det:

                routing_code = code_det

        except Exception:

            pass

            

        cache_sessao_loggi["token"] = tok

        cache_sessao_loggi["exp"] = exp

        cache_sessao_loggi["company_id"] = company_id

        cache_sessao_loggi["dc_id"] = int(dc_id) if str(dc_id).isdigit() else 1378

        cache_sessao_loggi["routing_code"] = routing_code

        cache_sessao_loggi["timestamp"] = time.time()

        print(f"[+] Contexto Loggi atualizado: {company_id} | DC: {dc_id} | {routing_code} (Expira em: {max(0, int(exp - time.time()))}s)")

    except Exception as e:

        print(f"[Aviso] Falha ao capturar contexto Loggi via Chrome: {e}")

        

    return cache_sessao_loggi



def executar_requisicao_loggi(url, payload_bytes=None, headers=None, metodo=None, max_tentativas=2):

    """

    Executa requisição HTTP para a API da Loggi.

    Se receber 401 Unauthorized ou 403 Forbidden, força atualização do token via Chrome e tenta novamente.

    Retorna (sucesso: bool, status_code: int, dados: dict/str)

    """

    for tentativa in range(1, max_tentativas + 1):

        ctx = obter_contexto_loggi(forcar=(tentativa > 1))

        token = ctx.get("token")

        if not token:

            return False, 401, "Token de autenticação da Loggi ausente no Chrome."

            

        req_headers = {

            'accept': 'application/json, text/plain, */*',

            'appversion': 'prod-20260922.01',

            'authorization': f"Bearer {token}",

            'content-type': 'application/json;charset=UTF-8',

            'origin': 'https://arco.loggi.com',

            'referer': 'https://arco.loggi.com/',

            'service': 'arco',

            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

        }

        if headers:

            req_headers.update(headers)

            req_headers['authorization'] = f"Bearer {token}"

            

        try:

            req = urllib.request.Request(url, data=payload_bytes, headers=req_headers, method=metodo)

            with urllib.request.urlopen(req, timeout=6) as resp:

                corpo = resp.read().decode('utf-8')

                try:

                    dados = json.loads(corpo) if corpo else {}

                except Exception:

                    dados = corpo

                return True, resp.status, dados

        except urllib.error.HTTPError as e:

            corpo_erro = ""

            try:

                corpo_erro = e.read().decode('utf-8')

            except Exception:

                pass

            print(f"[!] [Loggi API] HTTP {e.code} em {url} (Tentativa {tentativa}/{max_tentativas}): {e.reason}")

            if e.code in [401, 403]:

                if tentativa < max_tentativas:

                    print("[*] [Loggi API] 401/403 detectado. Forçando renovação imediata do token...")

                    cache_sessao_loggi["token"] = None

                    obter_contexto_loggi(forcar=True)

                    time.sleep(1.0)

                    continue

                else:

                    return False, e.code, "Sessão da Loggi expirada (401). Faça login no Chrome."

            else:

                return False, e.code, corpo_erro or str(e)

        except Exception as e_geral:

            print(f"[!] [Loggi API] Oscilação de internet em {url} (Tentativa {tentativa}/{max_tentativas}): {e_geral}")

            if tentativa < max_tentativas:

                time.sleep(0.4)

                continue

            return False, 500, f"Internet lenta / oscilação na Loggi ({e_geral})"

            

    return False, 500, "Falha na comunicação com a Loggi."



_lock_grupo_loggi = threading.Lock()



def loggi_listar_grupos_api():

    ctx = obter_contexto_loggi()

    if not ctx.get("company_id") or not ctx.get("dc_id"):

        return []

    url = f"https://leve.loggi.com/api/v1/last_mile/{ctx['company_id']}:{ctx['dc_id']}/unit_load"

    payload = json.dumps({

        'citiesFilter': [],

        'page': 1,

        'itemsPerPage': 200,

        'orderBy': 'last_awaiting_resolution_promised_date_annotation.annotation.awaiting_resolution_promised_date.promised_date.promised_date',

        'view': 'base',

        'viewFilterBy': 'last_last_mile_promised_date_annotation.annotation.last_mile_promised_date.promised_date.promised_date',

        'aggregatedField': 'unit_load',

        'lastMileCompanyType': 'LEVE',

        'distribution_center_id': ctx['dc_id'],

        'last_mile_company_id': ctx['company_id'],

        'routing_code': ctx['routing_code']

    }).encode('utf-8')

    

    ok, status, data = executar_requisicao_loggi(url, payload_bytes=payload)

    if not ok or not isinstance(data, dict):

        return []

        

    grupos = []

    for g in (data.get('data') or []):

        if not isinstance(g, dict):

            continue

        plate = g.get('licensePlate', '')

        tags = g.get('packageGroupTags') or []

        station = g.get('station', '')

        qty = g.get('quantityPackages', 0)

        if plate and plate != f"{ctx['routing_code']} COL 01":

            grupos.append({

                "licensePlate": plate,

                "station": station,

                "tags": tags,

                "tag_display": ", ".join(tags) if tags else plate,

                "quantity": qty

            })

    return grupos



def obter_cidades_do_motorista(motorista, plataforma="loggi"):

    """

    Retorna a lista de cidades vinculadas ao motorista no banco de dados.

    Suporta motoristas simples ou tags compostas de grupos da Loggi (ex: 'CENTRO 1, Fernanda...').

    """

    if not motorista or str(motorista).strip() in ["", "---", "Apenas Entrada (Sem Atribuição)"]:

        return []

    

    candidatos_nomes = []

    str_mot = str(motorista).strip()

    candidatos_nomes.append(str_mot)

    if "," in str_mot:

        for parte in str_mot.split(","):

            p_limpa = parte.strip()

            if p_limpa:

                candidatos_nomes.append(p_limpa)

                p_sem_data = re.sub(r'\s*\d{1,2}[-\/]\d{1,2}.*$', '', p_limpa).strip()

                if p_sem_data and p_sem_data != p_limpa:

                    candidatos_nomes.append(p_sem_data)

    else:

        p_sem_data = re.sub(r'\s*\d{1,2}[-\/]\d{1,2}.*$', '', str_mot).strip()

        if p_sem_data and p_sem_data != str_mot:

            candidatos_nomes.append(p_sem_data)



    cidades = set()

    try:

        conn = conectar_banco()

        c = conn.cursor()

        for cand in candidatos_nomes:

            if not cand:

                continue

            c.execute("SELECT DISTINCT cidade FROM motoristas_plataforma WHERE LOWER(motorista) = LOWER(?) AND (LOWER(plataforma) = LOWER(?) OR LOWER(plataforma) = 'todas')", (cand, plataforma))

            for r in c.fetchall():

                if r[0] and r[0].strip() and r[0].strip().lower() not in ('sem cidade', 'geral', 'loggi', 'anjun', 'imile'):

                    cidades.add(r[0].strip())

            

            c.execute("SELECT DISTINCT cidade FROM motoristas_plataforma WHERE LOWER(motorista) = LOWER(?)", (cand,))

            for r in c.fetchall():

                if r[0] and r[0].strip() and r[0].strip().lower() not in ('sem cidade', 'geral', 'loggi', 'anjun', 'imile'):

                    cidades.add(r[0].strip())

            

            c.execute("SELECT DISTINCT cidade FROM motoristas WHERE LOWER(motorista) = LOWER(?)", (cand,))

            for r in c.fetchall():

                if r[0] and r[0].strip() and r[0].strip().lower() not in ('sem cidade', 'geral', 'loggi', 'anjun', 'imile'):

                    cidades.add(r[0].strip())

        conn.close()

    except Exception as e:

        print(f"[Aviso] Erro ao buscar cidades do motorista {motorista}: {e}")

    return list(cidades)



def loggi_criar_novo_grupo_api(cidade=None, motorista=None, forcar_novo=False):

    global grupo_loggi_ativo, aba_atribuicao_anjun, driver

    with _lock_grupo_loggi:

        ctx = obter_contexto_loggi()

        from datetime import datetime

        dia_mes = datetime.now().strftime("%d-%m")

        cid_limpa = str(cidade or "").strip().title()

        if cid_limpa.lower() in ["geral", "none", "null"]:

            cid_limpa = ""

            

        mot_limpo = str(motorista or "").strip().title()

        if mot_limpo.lower() in ["---", "apenas entrada (sem atribuição)", "none", "null", "geral"]:

            mot_limpo = ""



        # Regra de Palavra-chave solicitada pelo cliente:

        # 1. Se tem motorista selecionado: Palavra-chave = [Motorista] [Data] (ex: 'Joao 23-10' ou 'Marcelo 23-10')

        # 2. Se NÃO tem motorista (apenas cidade): Palavra-chave = [Cidade] [Data] (ex: 'Erechim 23-10')

        if mot_limpo:

            tag_nome = f"{mot_limpo} {dia_mes}"

            cidade_base = cid_limpa or "Geral"

        elif cid_limpa:

            tag_nome = f"{cid_limpa} {dia_mes}"

            cidade_base = cid_limpa

        else:

            tag_nome = f"Geral {dia_mes}"

            cidade_base = "Geral"



        # 0. Verifica se já está ativo na memória para a mesma chave E com a data de HOJE

        placa_mem = grupo_loggi_ativo.get("licensePlate")

        cid_mem = grupo_loggi_ativo.get("cidade")

        mot_mem = grupo_loggi_ativo.get("motorista")

        tags_mem = grupo_loggi_ativo.get("tags") or []

        

        if not forcar_novo and placa_mem:

            if mot_limpo:

                bateu_mem = (mot_limpo.lower() == str(mot_mem or "").lower()) or any(mot_limpo.lower() in str(t).lower() for t in tags_mem)

            else:

                bateu_mem = (cidades_sao_iguais(cid_limpa, cid_mem) or any(cidades_sao_iguais(cid_limpa, t) for t in tags_mem))

                

            if bateu_mem:

                tag_mem_0 = str(tags_mem[0] if tags_mem else "")

                if dia_mes in tag_mem_0 or not any(char.isdigit() for char in tag_mem_0):

                    tag_ret = tags_mem[0] if tags_mem else tag_nome

                    return placa_mem, tag_ret



        # 0.1 Consulta na API da Loggi se JÁ EXISTE um grupo aberto para este Motorista ou Cidade

        if not forcar_novo:

            try:

                grupos_abertos = loggi_listar_grupos_api()

                for g in grupos_abertos:

                    tags_list = g.get("tags", [])

                    tags_str = " ".join(tags_list)

                    tags_str_lower = tags_str.lower()

                    tem_data_hoje = dia_mes in tags_str

                    

                    if mot_limpo:

                        # Busca por motorista: ex: 'Marcelo 23-10' ou 'MARCELO'

                        bateu = (mot_limpo.lower() in tags_str_lower)

                        if bateu and (tem_data_hoje or tags_str_lower.strip() == mot_limpo.lower()):

                            placa_existente = g["licensePlate"]

                            tag_existente = tags_list[0] if tags_list else tag_nome

                            grupo_loggi_ativo["licensePlate"] = placa_existente

                            grupo_loggi_ativo["tags"] = tags_list or [tag_existente]

                            grupo_loggi_ativo["cidade"] = cidade_base

                            grupo_loggi_ativo["motorista"] = mot_limpo

                            grupo_loggi_ativo["quantity"] = g.get("quantity", 0)

                            print(f"[+] [Loggi API] Grupo existente de HOJE localizado para o Motorista '{mot_limpo}': Placa {placa_existente} ({tag_existente}). Reutilizando!")

                            return placa_existente, tag_existente

                    elif cid_limpa:

                        # Busca apenas por cidade: ex: 'Erechim 23-10' ou 'ERECHIM'

                        bateu = (

                            cidades_sao_iguais(cid_limpa, tags_str) 

                            or any(cidades_sao_iguais(cid_limpa, t) for t in tags_list)

                            or cid_limpa.lower() in tags_str_lower

                        )

                        if bateu and (tem_data_hoje or tags_str_lower.strip() == cid_limpa.lower()):

                            placa_existente = g["licensePlate"]

                            tag_existente = tags_list[0] if tags_list else tag_nome

                            grupo_loggi_ativo["licensePlate"] = placa_existente

                            grupo_loggi_ativo["tags"] = tags_list or [tag_existente]

                            grupo_loggi_ativo["cidade"] = cid_limpa

                            grupo_loggi_ativo["motorista"] = None

                            grupo_loggi_ativo["quantity"] = g.get("quantity", 0)

                            print(f"[+] [Loggi API] Grupo existente de HOJE localizado para a Cidade '{cid_limpa}': Placa {placa_existente} ({tag_existente}). Reutilizando!")

                            return placa_existente, tag_existente

            except Exception as e_chk:

                print(f"[Aviso] Falha ao consultar grupos existentes antes de criar: {e_chk}")

        

        # 1. Gera nova placa de unitLoad (somente se não existir nenhum grupo aberto)

        url_ul = 'https://leve.loggi.com/proxy/wms/api/v1/get-create-unitload'

        payload_ul = json.dumps({

            'prefixLicensePlate': ctx['routing_code'],

            'distribution_center_id': ctx['dc_id'],

            'last_mile_company_id': ctx['company_id'],

            'routing_code': ctx['routing_code']

        }).encode('utf-8')

        

        ok_ul, status_ul, data_ul = executar_requisicao_loggi(url_ul, payload_bytes=payload_ul)

        if not ok_ul or not isinstance(data_ul, dict):

            raise Exception(f"Falha ao gerar nova placa de grupo na Loggi: {data_ul}")

            

        nova_placa = (data_ul.get('unitLoad') or {}).get('license_plate')

        if not nova_placa:

            raise Exception("Placa de grupo retornada vazia pela Loggi.")

            

        # 2. Cria o grupo com a palavra-chave (Motorista Dia-Mês ou Cidade Dia-Mês)

        url_create = f"https://leve.loggi.com/api/v1/last_mile/{ctx['company_id']}:{ctx['dc_id']}/package-group/create"

        payload_create = json.dumps({

            "licensePlate": nova_placa,

            "tags": [tag_nome],

            "markSomeCircleThisUser": False,

            "distribution_center_id": ctx['dc_id'],

            "last_mile_company_id": ctx['company_id'],

            "routing_code": ctx['routing_code']

        }).encode('utf-8')

        

        ok_c, status_c, data_c = executar_requisicao_loggi(url_create, payload_bytes=payload_create)

        if not ok_c:

            raise Exception(f"Falha ao registrar novo grupo na Loggi: {data_c}")

            

        grupo_loggi_ativo["licensePlate"] = nova_placa

        grupo_loggi_ativo["tags"] = [tag_nome]

        grupo_loggi_ativo["cidade"] = cidade_base

        grupo_loggi_ativo["motorista"] = mot_limpo

        grupo_loggi_ativo["modo"] = "novo"

        grupo_loggi_ativo["quantity"] = 0

        

        # Recarrega a aba 3 (Grupos) no Chrome para exibir o novo grupo imediatamente

        try:

            if aba_atribuicao_anjun and driver:

                with _lock_selenium:

                    driver.switch_to.window(aba_atribuicao_anjun)

                    driver.execute_script("window.location.reload();")

        except Exception as e_rf:

            print(f"[Aviso] Falha ao atualizar aba 3 no Chrome: {e_rf}")

            

        print(f"[+] [Loggi API] Novo grupo criado com sucesso: Placa {nova_placa} | Palavra-chave '{tag_nome}'")

        return nova_placa, tag_nome



def resolver_pacote_avulso_loggi(codigo_procurado, ctx):

    """

    Quando um pacote foi recebido na base mas retrieve_and_validate falhou pelo código de barras,

    busca nos pacotes avulsos em AV3 COL 01 para encontrar o pacote correspondente.

    Bate por tracking_key, barcode, loggiKey, package_id ou nome do destinatário.

    """

    try:

        url = "https://leve.loggi.com/api/v2/last_mile/packages/filter_search"

        payload = {

            "citiesFilter": [],

            "page": 1,

            "itemsPerPage": 200,

            "unitLoadFilter": [f"{ctx['routing_code']} COL 01"],

            "orderBy": "last_awaiting_resolution_promised_date_annotation.annotation.awaiting_resolution_promised_date.promised_date.promised_date",

            "view": "base",

            "viewFilterBy": "last_last_mile_promised_date_annotation.annotation.last_mile_promised_date.promised_date.promised_date",

            "aggregatedField": "unit_load",

            "lastMileCompanyType": "LEVE",

            "distribution_center_id": ctx['dc_id'],

            "last_mile_company_id": ctx['company_id'],

            "routing_code": ctx['routing_code']

        }

        

        ok, status, d = executar_requisicao_loggi(url, payload_bytes=json.dumps(payload).encode('utf-8'))

        if not ok or not isinstance(d, dict):

            return None

            

        hits = (d.get("hits") or {}).get("hits") or []

        c_clean = str(codigo_procurado).strip().lower()

        

        for h in hits:

            if not isinstance(h, dict):

                continue

            src = h.get("_source") or {}

            pkg = src.get("package") or {}

            integ = src.get("package_integration_info") or {}

            dest = src.get("destination") or {}

            rec = src.get("recipient") or {}

            

            b_code = str(integ.get("barcode") or "").strip().lower()

            t_key = str(pkg.get("tracking_key") or "").strip().lower()

            l_key = str(pkg.get("loggiKey") or "").strip().lower()

            p_id = str(pkg.get("id") or "").strip()

            r_name = str(rec.get("name") or "").strip().lower()

            

            bateu = (c_clean in [b_code, t_key, l_key, p_id])

            if not bateu and len(c_clean) >= 5:

                bateu = (c_clean in t_key or c_clean in b_code or c_clean in l_key or t_key in c_clean or b_code in c_clean)

            if not bateu and len(c_clean) >= 4 and not c_clean.isdigit():

                bateu = (c_clean in r_name or r_name in c_clean)

                

            if bateu:

                barcode_real = integ.get("barcode") or pkg.get("loggiKey")

                if barcode_real and "LG" in barcode_real and not barcode_real.startswith("LG"):

                    idx_lg = barcode_real.find("LG")

                    barcode_real = barcode_real[idx_lg:]

                    

                return {

                    "package_id": str(pkg.get("id")),

                    "barcode": barcode_real,

                    "cidade": dest.get("city", ""),

                    "cep": dest.get("zip", ""),

                    "bairro": dest.get("vicinity", "") or dest.get("neighborhood", ""),

                    "destinatario": rec.get("name", ""),

                    "telefone": str(rec.get("phone") or rec.get("phoneNumber") or dest.get("phone") or "").strip(),

                    "endereco": f"{dest.get('address_st', '')}, {dest.get('address_number', '')} - {dest.get('vicinity', '')}".strip(" ,-"),

                    "empresa": (src.get("company") or {}).get("name", "Loggi"),

                    "produto": str(pkg.get("description") or pkg.get("content") or "").strip(),

                    "valor_declarado": str(pkg.get("declared_value") or pkg.get("invoice_value") or "").strip()

                }

    except Exception as e:

        print(f"[Aviso] Falha ao resolver pacote avulso Loggi: {e}")

    return None



def bipar_pacote_loggi_api(codigo_qr, cidades_selecionadas=None, motorista_lote=None, modo_triagem_direta=False):

    """

    Executa a bipagem ultra-rápida via API na Loggi em ~120-200ms:

    1. Entrada/Recebimento na Base (move-package para AV3 COL 01)

    2. Validação e extração de Cidade, Bairro, CEP e package_id

    3. Verificação de Anti-Divergência

    4. Atribuição direta ao Grupo ativo (novo ou existente) via validate-and-move-packages com re-tentativa automática

    Retorna (sucesso: bool/str, mensagem: str, motorista_atribuido: str, cidade: str, cep: str, destinatario: str, endereco: str)

    """

    global grupo_loggi_ativo

    ctx = obter_contexto_loggi()

    token = ctx.get("token")

    if not token:

        return False, "Sessão da Loggi desconectada ou token ausente.", "", "", "", "", ""

        

    codigo_limpo = str(codigo_qr).strip()

    

    # 1. Entrada / Recebimento na Base (Aba 1)

    url_move_rec = 'https://leve.loggi.com/proxy/wms/api/v1/move-package'

    payload_rec = json.dumps({

        "packageBarcode": codigo_limpo,

        "unitLoadLpn": f"{ctx['routing_code']} COL 01",

        "sortingContextLpn": f"{ctx['routing_code']} COL",

        "sideEffectParams": {"applicationName": "arco"}

    }).encode('utf-8')

    ok_rec, status_rec, data_rec = executar_requisicao_loggi(url_move_rec, payload_bytes=payload_rec)

    if not ok_rec and ("Internet lenta" in str(data_rec) or status_rec in [502, 503, 504]):

        return False, f"Servidor da Loggi não respondeu na Entrada da Base ({data_rec}). Bipe novamente!", "", "", "", "", ""

        

    # 2. Validação do Pacote e Obtenção dos Dados

    url_validate = f"https://leve.loggi.com/proxy/last-mile/v1/{ctx['company_id']}:{ctx['dc_id']}/group_packages/retrieve_and_validate_packages_by_barcode"

    def _consultar_validacao_loggi(cod_consulta):

        p_val = json.dumps({

            "barcodes": [cod_consulta],

            "arcoLocation": "IN_BASE",

            "distribution_center_id": ctx['dc_id'],

            "last_mile_company_id": ctx['company_id'],

            "routing_code": ctx['routing_code']

        }).encode('utf-8')

        ok_v, _, d_val = executar_requisicao_loggi(url_validate, payload_bytes=p_val)

        if not ok_v or not isinstance(d_val, dict):

            return False, None, d_val

        inf = d_val.get(cod_consulta)

        if not isinstance(inf, dict):

            inf = None

            for k_v, v_v in d_val.items():

                if isinstance(v_v, dict) and ('destination' in v_v or 'validationMessage' in v_v or 'integrationInfo' in v_v):

                    inf = v_v

                    break

        return True, inf, d_val



    ok_val, info, data_val = _consultar_validacao_loggi(codigo_limpo)

    if not ok_val:

        return False, f"Falha ao validar pacote na Loggi: {data_val}", "", "", "", "", ""

                

    val_msg = (info.get('validationMessage') or info.get('message') or info.get('errorMsg')) if info else None

    package_id = str((info.get('integrationInfo') or {}).get('package_id') or info.get('packageId') or '').strip() if info else ''

    barcode_oficial = str((info.get('integrationInfo') or {}).get('barcode') or info.get('barcode') or '').strip() if info else ''

    if barcode_oficial:

        codigo_limpo = barcode_oficial

    cidade_destino = ((info.get('destination') or {}).get('city', '') or ((info.get('loggiAddress') or {}).get('correiosAddress') or {}).get('cidade', '')) if info else ''

    cep_inicial = (((info.get('loggiAddress') or {}).get('correiosAddress') or {}).get('cep', '') or (info.get('destination') or {}).get('zip', '')) if info else ''

    if not cidade_destino and cep_inicial:

        cidade_destino = obter_cidade_por_cep(cep_inicial) or ''

        if cidade_destino:

            print(f"[+] [Loggi API] Cidade resolvida instantaneamente pelo CEP {cep_inicial}: {cidade_destino}")

    bairro = ""

    telefone_pacote = ""

    destinatario_real = ""

    produto_pacote = ""

    valor_pacote = ""



    # SE A LOGGI NÃO ACHOU PELO CÓDIGO BIPADO OU A ENTRADA NA BASE AINDA ESTAVA INDEXANDO:

    # Faz até 2 buscas (com breve pausa de 0.25s se necessário) nos Pacotes Avulsos e na validação!

    if val_msg or not package_id or not cidade_destino:

        print(f"[*] Código '{codigo_limpo}' aguardando indexação ou avulso ({val_msg}). Consultando base...")

        resolvido_extra = False

        for tent_av in range(2):

            if tent_av == 1:

                time.sleep(0.28)

                ok_v2, info2, _ = _consultar_validacao_loggi(codigo_limpo)

                if ok_v2 and info2:

                    v_msg2 = info2.get('validationMessage') or info2.get('message') or info2.get('errorMsg')

                    pid2 = str((info2.get('integrationInfo') or {}).get('package_id') or info2.get('packageId') or '').strip()

                    correios_addr = ((info2.get('loggiAddress') or {}).get('correiosAddress') or {})

                    dest_obj2 = info2.get('destination') or {}

                    cep2 = correios_addr.get('cep') or dest_obj2.get('zip') or ''

                    cid2 = dest_obj2.get('city', '') or correios_addr.get('cidade', '')

                    if not cid2 and cep2:

                        cid2 = obter_cidade_por_cep(cep2) or ''

                    if not v_msg2 and pid2:

                        info = info2

                        val_msg = None

                        package_id = pid2

                        cidade_destino = cid2

                        bc2 = str((info2.get('integrationInfo') or {}).get('barcode') or info2.get('barcode') or '').strip()

                        if bc2:

                            codigo_limpo = bc2

                        empresa = (info2.get('company') or {}).get('name', 'Loggi')

                        rec_obj2 = info2.get('recipient') or {}

                        bairro = correios_addr.get('bairro') or dest_obj2.get('vicinity') or dest_obj2.get('neighborhood') or ''

                        cep = cep2

                        logradouro = correios_addr.get('logradouro') or dest_obj2.get('address_st') or ''

                        numero = correios_addr.get('numero') or dest_obj2.get('address_number') or ''

                        endereco = f"{logradouro}, {numero}" if logradouro else ""

                        destinatario_real = rec_obj2.get('name') or (info2.get('loggiAddress') or {}).get('recipientName') or ''

                        telefone_pacote = str(rec_obj2.get('phone') or rec_obj2.get('phoneNumber') or dest_obj2.get('phone') or '').strip()

                        resolvido_extra = True

                        break

            dados_avulso = resolver_pacote_avulso_loggi(codigo_limpo, ctx)

            if dados_avulso:

                package_id = dados_avulso["package_id"]

                codigo_limpo = dados_avulso["barcode"] or codigo_limpo

                cep = dados_avulso["cep"]

                cidade_destino = dados_avulso["cidade"]

                if not cidade_destino and cep:

                    cidade_destino = obter_cidade_por_cep(cep) or ""

                    if cidade_destino:

                        print(f"[+] [Loggi API] Cidade do pacote avulso resolvida pelo CEP {cep}: {cidade_destino}")

                bairro = dados_avulso.get("bairro", "")

                empresa = dados_avulso["empresa"]

                destinatario_real = dados_avulso.get("destinatario", "")

                telefone_pacote = dados_avulso.get("telefone", "")

                produto_pacote = dados_avulso.get("produto", "")

                valor_pacote = dados_avulso.get("valor_declarado", "")

                endereco = dados_avulso["endereco"]

                val_msg = None

                resolvido_extra = True

                print(f"[+] [Loggi API] Pacote Avulso resolvido automaticamente via 'AV3 COL 01': {codigo_limpo} ({dados_avulso.get('destinatario')} - {cidade_destino})")

                break

        if not resolvido_extra:

            if not val_msg and package_id and info:

                # Pacote existe e foi validado, apenas veio sem cidade e sem CEP da Loggi

                empresa = (info.get('company') or {}).get('name', 'Loggi')

                loggi_addr = info.get('loggiAddress') or {}

                correios_addr = loggi_addr.get('correiosAddress') or {}

                dest_obj = info.get('destination') or {}

                rec_obj = info.get('recipient') or {}

                bairro = correios_addr.get('bairro') or dest_obj.get('vicinity') or dest_obj.get('neighborhood') or ''

                cep = correios_addr.get('cep') or dest_obj.get('zip') or ''

                logradouro = correios_addr.get('logradouro') or dest_obj.get('address_st') or ''

                numero = correios_addr.get('numero') or dest_obj.get('address_number') or ''

                endereco = f"{logradouro}, {numero}" if logradouro else ""

                destinatario_real = rec_obj.get('name') or loggi_addr.get('recipientName') or ''

                telefone_pacote = str(rec_obj.get('phone') or rec_obj.get('phoneNumber') or dest_obj.get('phone') or '').strip()

            else:

                if val_msg:

                    print(f"[!] Loggi rejeitou o código '{codigo_limpo}': {val_msg}")

                    return False, val_msg, "", "", "", "", ""

                return False, "Pacote não encontrado com o código informado.", "", "", "", "", ""

    else:

        empresa = (info.get('company') or {}).get('name', 'Loggi')

        loggi_addr = info.get('loggiAddress') or {}

        correios_addr = loggi_addr.get('correiosAddress') or {}

        dest_obj = info.get('destination') or {}

        rec_obj = info.get('recipient') or {}

        bairro = correios_addr.get('bairro') or dest_obj.get('vicinity') or dest_obj.get('neighborhood') or ''

        cep = correios_addr.get('cep') or dest_obj.get('zip') or ''

        logradouro = correios_addr.get('logradouro') or dest_obj.get('address_st') or ''

        numero = correios_addr.get('numero') or dest_obj.get('address_number') or ''

        endereco = f"{logradouro}, {numero}" if logradouro else ""

        destinatario_real = rec_obj.get('name') or loggi_addr.get('recipientName') or ''

        telefone_pacote = str(rec_obj.get('phone') or rec_obj.get('phoneNumber') or dest_obj.get('phone') or '').strip()

        pkg_det = info.get('packageDetails') or {}

        produto_pacote = str(pkg_det.get('description') or info.get('description') or info.get('content') or '').strip()

        valor_pacote = str(pkg_det.get('value') or info.get('declaredValue') or info.get('invoiceValue') or '').strip()



    registrar_detalhes_extras_pacote(

        [codigo_qr, codigo_limpo],

        bairro=bairro,

        telefone=telefone_pacote,

        negocios=empresa,

        produto=produto_pacote,

        valor_declarado=valor_pacote,

        recebedor=destinatario_real or empresa,

        cep=cep,

        endereco=endereco

    )

    

    # 3. Anti-Divergência Multi-Cidades Inteligente para Loggi

    eh_divergente = False

    msg_alerta_div = ""

    mot_esperado_div = ""

    tem_motorista_lote = bool(motorista_lote and str(motorista_lote).strip() not in ["", "---", "Apenas Entrada (Sem Atribuição)"])

    

    # Coleta todas as cidades autorizadas para o grupo/lote ativo da Loggi:

    cidades_autorizadas_loggi = set()

    todas_cidades_cadastradas = carregar_cidades() or []



    candidatos_brutos = []

    if tem_motorista_lote:

        candidatos_brutos.append(str(motorista_lote).strip())

    tags_grp = grupo_loggi_ativo.get("tags") or []

    for t in tags_grp:

        if t:

            candidatos_brutos.append(str(t).strip())

    if cidades_selecionadas:

        for cs in cidades_selecionadas:

            if cs:

                candidatos_brutos.append(str(cs).strip())

    cid_grp_base = grupo_loggi_ativo.get("cidade")

    if cid_grp_base:

        candidatos_brutos.append(str(cid_grp_base).strip())



    partes_individuais = []

    for cb in candidatos_brutos:

        if "," in cb:

            for p in cb.split(","):

                if p.strip():

                    partes_individuais.append(p.strip())

        elif cb:

            partes_individuais.append(cb)



    for parte in partes_individuais:

        if not parte or parte.lower() in ["---", "sem motorista", "apenas entrada (sem atribuição)", "geral", "loggi"]:

            continue

            

        # 1. Cidades vinculadas ao motorista/tag no banco de dados (ex: 'CENTRO 1', 'Fernanda...')

        for c_m in obter_cidades_do_motorista(parte, "loggi"):

            cidades_autorizadas_loggi.add(c_m)

            

        # 2. Remove datas (ex: 'Barao De Antonina 26-10' -> 'Barao De Antonina')

        parte_sem_data = re.sub(r'\s*\d{1,2}[-\/]\d{1,2}.*$', '', parte).strip()

        if parte_sem_data and parte_sem_data != parte:

            for c_m2 in obter_cidades_do_motorista(parte_sem_data, "loggi"):

                cidades_autorizadas_loggi.add(c_m2)

                

        # 3. Se a própria parte (ou sem data) for o nome de uma cidade cadastrada:

        candidata_cid = parte_sem_data if parte_sem_data else parte

        if candidata_cid:

            bateu_com_cadastrada = False

            for c_cad in todas_cidades_cadastradas:

                if cidades_sao_iguais(candidata_cid, c_cad):

                    norm_cad = c_cad.lower()

                    if not any(k in norm_cad for k in ["centro ", "rota ", "galpao", "base ", "hub ", "motorista"]):

                        cidades_autorizadas_loggi.add(c_cad)

                    bateu_com_cadastrada = True

                    break

            if not bateu_com_cadastrada and not obter_cidades_do_motorista(parte, "loggi"):

                norm_c = candidata_cid.lower()

                if not any(k in norm_c for k in ["centro ", "rota ", "galpao", "base ", "hub ", "motorista"]) and len(candidata_cid) > 2:

                    cidades_autorizadas_loggi.add(candidata_cid)



    if cidades_autorizadas_loggi:

        if cidade_destino:

            bateu_cidade = any(cidades_sao_iguais(cidade_destino, ca) for ca in cidades_autorizadas_loggi)

            if not bateu_cidade:

                cids_display = ", ".join(sorted(cidades_autorizadas_loggi))

                alvo_nome = motorista_lote or ", ".join(tags_grp) or "Grupo Loggi"

                msg_alerta_div = f"Divergência: Pacote é de {cidade_destino}, mas o grupo {alvo_nome} atende: {cids_display}!"

                print(f"[!] [Loggi API] DIVERGÊNCIA: {msg_alerta_div}")

                eh_divergente = True

                mot_esperado_div = cids_display

            elif tem_motorista_lote:

                if cidades_sao_iguais(str(motorista_lote), cidade_destino):

                    eh_divergente = False

                else:

                    mots_esperados, foi_por_regra, tem_alguma_regra = carregar_motoristas_cidade_detalhado(cidade_destino, "loggi", cep=cep, bairro=bairro)

                    if not mots_esperados and not foi_por_regra:

                        lista_cidades = carregar_cidades()

                        cidade_map = encontrar_cidade_mapeada(cidade_destino, lista_cidades)

                        if cidade_map and cidade_map != cidade_destino:

                            mots_esperados, foi_por_regra, tem_alguma_regra = carregar_motoristas_cidade_detalhado(cidade_map, "loggi", cep=cep, bairro=bairro)

                    if tem_alguma_regra:

                        if mots_esperados:



                            mot_sem_data = re.sub(r'\s*\d{1,2}[-\/]\d{1,2}.*$', '', str(motorista_lote)).strip()

                            norm_mot = remover_acentos(mot_sem_data.lower()).replace('-', '').replace('_', '').replace(' ', '')

                            mots_esp_norm = [remover_acentos(re.sub(r'\s*\d{1,2}[-\/]\d{1,2}.*$', '', m).lower()).replace('-', '').replace('_', '').replace(' ', '') for m in mots_esperados]

                            bateu_mot = (norm_mot in mots_esp_norm) or any(norm_mot in m or m in norm_mot for m in mots_esp_norm)

                            if not bateu_mot:

                                esp_display = " / ".join(mots_esperados)

                                bairro_info = f" ({bairro})" if bairro else ""

                                cep_info = f" (CEP {cep})" if cep and not bairro else ""

                                msg_alerta_div = f"Divergência: Pacote de {cidade_destino}{bairro_info} pertence a {esp_display}, mas você está bipando a pilha de {motorista_lote}!"

                                print(f"[!] [Loggi API] DIVERGÊNCIA DE BAIRRO/CEP: {msg_alerta_div}")

                                eh_divergente = True

                                mot_esperado_div = esp_display

                        elif foi_por_regra:

                            bairro_info = f" ({bairro})" if bairro else ""

                            cep_info = f" (CEP {cep})" if cep and not bairro else ""

                            msg_alerta_div = f"Divergência: Pacote de {cidade_destino}{bairro_info} não está coberto pelas regras permitidas para {cidade_destino}!"

                            print(f"[!] [Loggi API] DIVERGÊNCIA FORA DA REGRA: {msg_alerta_div}")

                            eh_divergente = True

                            mot_esperado_div = "Fora da Regra"

    elif modo_triagem_direta:

        if not cidade_destino:

            return "divergente", "Divergência: Pacote sem cidade de destino informada pela Loggi!", "Sem Cidade", cidade_destino, cep, empresa, endereco

        mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_destino, "loggi", cep=cep, bairro=bairro)

        if not mots_esperados:

            return "divergente", f"Divergência: Nenhum motorista/rota cadastrada para {cidade_destino}!", "Sem Rota", cidade_destino, cep, empresa, endereco



    # 4. Atribuição ao Grupo Ativo (Motorista + Data ou Cidade + Data)

    if tem_motorista_lote:

        mot_para_criar = str(motorista_lote).strip()

        cid_para_criar = str(cidade_destino or "Geral").strip()

    elif modo_triagem_direta and 'mots_esperados' in locals() and mots_esperados:

        mot_para_criar = str(mots_esperados[0]).strip()

        cid_para_criar = str(cidade_destino or "Geral").strip()

    else:

        mot_para_criar = None

        if cidades_selecionadas and len(cidades_selecionadas) > 0 and cidades_selecionadas[0]:

            cid_para_criar = str(cidades_selecionadas[0]).strip()

        elif grupo_loggi_ativo.get("modo") == "existente" and grupo_loggi_ativo.get("cidade"):

            cid_para_criar = str(grupo_loggi_ativo.get("cidade")).strip()

        else:

            cid_para_criar = str(cidade_destino or grupo_loggi_ativo.get("cidade") or "Geral").strip()



    placa_grupo = grupo_loggi_ativo.get("licensePlate")

    if placa_grupo and grupo_loggi_ativo.get("modo") != "existente":

        cid_grp_atual = grupo_loggi_ativo.get("cidade")

        mot_grp_atual = grupo_loggi_ativo.get("motorista")

        tags_grp_atual = grupo_loggi_ativo.get("tags") or []

        

        if mot_para_criar:

            bateu_ativo = (mot_para_criar.lower() == str(mot_grp_atual or "").lower()) or any(mot_para_criar.lower() in str(t).lower() for t in tags_grp_atual)

        else:

            bateu_ativo = (cidades_sao_iguais(cid_para_criar, cid_grp_atual) or any(cidades_sao_iguais(cid_para_criar, t) for t in tags_grp_atual))



        if not bateu_ativo:

            placa_grupo = None

            grupo_loggi_ativo["licensePlate"] = None

            grupo_loggi_ativo["tags"] = []

            grupo_loggi_ativo["cidade"] = None

            grupo_loggi_ativo["motorista"] = None



    if not placa_grupo:

        placa_grupo, tag_criada = loggi_criar_novo_grupo_api(cidade=cid_para_criar, motorista=mot_para_criar)

            

    # Move para o grupo com verificação real e até 3 tentativas automáticas (evita pacote ficar preso em Avulsos!)

    url_move_group = f"https://leve.loggi.com/proxy/last-mile/v1/{ctx['company_id']}:{ctx['dc_id']}/group-packages/validate-and-move-packages"

    movido_com_sucesso = False

    ultimo_erro_grp = ""



    for tent_grp in range(1, 4):

        if not package_id and tent_grp > 1:

            _, info_retry, _ = _consultar_validacao_loggi(codigo_limpo)

            if info_retry:

                package_id = str((info_retry.get('integrationInfo') or {}).get('package_id') or info_retry.get('packageId') or '').strip()

            if not package_id:

                av_retry = resolver_pacote_avulso_loggi(codigo_limpo, ctx)

                if av_retry and av_retry.get("package_id"):

                    package_id = av_retry["package_id"]

                    codigo_limpo = av_retry.get("barcode") or codigo_limpo



        payload_group = json.dumps({

            "packageIds": [package_id] if package_id else [],

            "barcodes": [codigo_limpo],

            "arcoLocation": "IN_BASE",

            "destinationUnitLoadLicensePlate": placa_grupo,

            "sideEffectParams": {"applicationName": "arco"},

            "distribution_center_id": ctx['dc_id'],

            "last_mile_company_id": ctx['company_id'],

            "routing_code": ctx['routing_code']

        }).encode('utf-8')



        ok_grp, status_grp, data_grp = executar_requisicao_loggi(url_move_group, payload_bytes=payload_group)

        erro_interno_grp = None

        if isinstance(data_grp, dict):

            erro_interno_grp = data_grp.get("validationMessage") or data_grp.get("errorMsg") or data_grp.get("message")

            if not erro_interno_grp and data_grp.get("errors"):

                erro_interno_grp = str(data_grp.get("errors"))

            if not erro_interno_grp and data_grp.get("invalidPackages"):

                erro_interno_grp = str(data_grp.get("invalidPackages"))



        if ok_grp and not erro_interno_grp:

            movido_com_sucesso = True

            print(f"[+] [Loggi API] Pacote {codigo_limpo} adicionado ao grupo {placa_grupo} com sucesso (tentativa {tent_grp})!")

            break

        else:

            ultimo_erro_grp = str(erro_interno_grp or data_grp or f"HTTP {status_grp}")

            print(f"[Aviso] [Loggi API] Tentativa {tent_grp}/3 de mover pacote {codigo_limpo} para o grupo {placa_grupo} aguardando base: {ultimo_erro_grp}")

            if tent_grp < 3:

                # Re-confirma a entrada na base e aguarda 350ms para o banco da Loggi finalizar a indexação

                executar_requisicao_loggi(url_move_rec, payload_bytes=payload_rec)

                time.sleep(0.35)



    if not movido_com_sucesso:

        print(f"[!] [Loggi API] Falha definitiva ao mover pacote {codigo_limpo} para o grupo {placa_grupo}: {ultimo_erro_grp}")

        return False, f"Pacote deu entrada na base, mas a Loggi demorou para liberar o grupo ({ultimo_erro_grp}). Bipe o pacote novamente!", "", cidade_destino, cep, empresa, endereco

        

    tag_atual = ", ".join(grupo_loggi_ativo.get("tags", [])) or placa_grupo

    cidade_retorno_loggi = cidade_destino if cidade_destino else "Cidade Não Informada (Conferir)"

    if 'eh_divergente' in locals() and eh_divergente:

        return "divergente", msg_alerta_div, mot_esperado_div, cidade_retorno_loggi, cep, empresa, endereco

    return True, "OK", tag_atual, cidade_retorno_loggi, cep, empresa, endereco



ultimo_bipe_motorista_anjun = {}

ultimo_bipe_geral_anjun = 0



def adicionar_pacote_lote_anjun(motorista, waybill):

    """Registra pacote pendente no lote do motorista no banco SQLite."""

    global ultimo_bipe_motorista_anjun, ultimo_bipe_geral_anjun

    try:

        wb_clean = str(waybill).strip()

        if 'waybills_cancelados_anjun' in globals():

            waybills_cancelados_anjun.discard(wb_clean)

        conn = conectar_banco()

        c = conn.cursor()

        c.execute("INSERT OR REPLACE INTO lote_pendente_anjun (waybill, motorista, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", (wb_clean, str(motorista).strip()))

        conn.commit()

        conn.close()

        

        mot_clean = str(motorista).strip()

        ultimo_bipe_motorista_anjun[mot_clean] = time.time()

        ultimo_bipe_geral_anjun = time.time()

    except Exception as e:

        print(f"[Aviso] Falha ao registrar pacote pendente Anjun: {e}")



def monitor_auto_finalizacao_anjun():

    """

    Monitor contínuo em segundo plano que finaliza automaticamente

    lotes abertos da Anjun após 1 hora (3600 segundos) de inatividade.

    Garante que os pacotes apareçam no aplicativo dos motoristas mesmo que o operador esqueça.

    """

    time.sleep(20)  # Aguarda inicialização do sistema e conexões

    print("[+] [Auto-Finalização Anjun] Monitor de inatividade iniciado (limite: 1 hora sem bipar).")

    

    while True:

        try:

            time.sleep(60)  # Checa a cada 60 segundos

            agora = time.time()

            

            conn = conectar_banco()

            c = conn.cursor()

            c.execute("""

                SELECT motorista, 

                       COALESCE((strftime('%s', 'now') - strftime('%s', MAX(timestamp))), 999999) AS seg_inativo,

                       count(*) AS total_pct

                FROM lote_pendente_anjun

                WHERE motorista IS NOT NULL AND TRIM(motorista) != ''

                GROUP BY motorista

            """)

            lotes_abertos = c.fetchall()

            conn.close()

            

            if not lotes_abertos:

                continue

                

            for mot, seg_inativo, total_pct in lotes_abertos:

                mot_limpo = str(mot).strip()

                if not mot_limpo or total_pct <= 0:

                    continue

                

                # Prioriza o timestamp em memória se for mais recente que o do banco

                if mot_limpo in ultimo_bipe_motorista_anjun:

                    seg_memoria = agora - ultimo_bipe_motorista_anjun[mot_limpo]

                    seg_inativo = min(seg_inativo, seg_memoria)

                    

                if seg_inativo >= 3600:

                    minutos_parado = int(seg_inativo / 60)

                    print(f"[*] [Auto-Finalização Anjun] Motorista '{mot_limpo}' com {total_pct} pacote(s) sem novos bipes há {minutos_parado} min (>= 60 min). Finalizando lote automaticamente...")

                    

                    ok_fin, qtd_fin = finalizar_lote_anjun_api(mot_limpo, reload_tab=False)

                    if ok_fin:

                        contagem = qtd_fin if qtd_fin > 0 else total_pct

                        registrar_lote_finalizado(mot_limpo, contagem, plataforma="anjun")

                        limpar_pacotes_lote_anjun(mot_limpo)

                        zerar_contagem_motorista_memoria(mot_limpo)

                        ultimo_bipe_motorista_anjun.pop(mot_limpo, None)

                        print(f"[+] [Auto-Finalização Anjun] Lote de '{mot_limpo}' finalizado com sucesso ({contagem} pacotes)! Liberado no aplicativo da Anjun.")

                    else:

                        print(f"[Aviso] [Auto-Finalização Anjun] Tentativa de finalizar lote de '{mot_limpo}' falhou temporariamente. O monitor tentará novamente no próximo minuto.")

                        

        except Exception as e_mon:

            print(f"[Aviso] Erro no ciclo do monitor de auto-finalização Anjun: {e_mon}")

            time.sleep(15)



def obter_pacotes_lote_anjun(motorista):

    """Retorna a lista de waybills pendentes no lote do motorista (busca exata e sem acentos/case/espaços)."""

    if not motorista:

        return []

    try:

        alvo_norm = remover_acentos(str(motorista).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

        conn = conectar_banco()

        c = conn.cursor()

        c.execute("SELECT waybill, motorista FROM lote_pendente_anjun")

        rows = c.fetchall()

        conn.close()

        res = []

        for wb, mot_db in rows:

            if not wb or not mot_db:

                continue

            norm_db = remover_acentos(str(mot_db).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

            if norm_db == alvo_norm or alvo_norm in norm_db or norm_db in alvo_norm:

                res.append(wb)

        return res

    except Exception as e:

        print(f"[Aviso] Falha ao obter pacotes pendentes Anjun: {e}")

        return []



def limpar_pacotes_lote_anjun(motorista):

    """Limpa os pacotes do lote pendente do motorista após finalização ou cancelamento."""

    if not motorista:

        return 0

    try:

        alvo_norm = remover_acentos(str(motorista).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

        conn = conectar_banco()

        c = conn.cursor()

        c.execute("SELECT DISTINCT motorista FROM lote_pendente_anjun")

        rows = c.fetchall()

        removidos = 0

        for (mot_db,) in rows:

            if not mot_db:

                continue

            norm_db = remover_acentos(str(mot_db).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

            if norm_db == alvo_norm or alvo_norm in norm_db or norm_db in alvo_norm:

                c.execute("DELETE FROM lote_pendente_anjun WHERE motorista = ?", (mot_db,))

                removidos += c.rowcount

        conn.commit()

        conn.close()

        return removidos

    except Exception as e:

        print(f"[Aviso] Falha ao limpar pacotes pendentes Anjun: {e}")

        return 0



def obter_motoristas_com_lote_aberto_anjun(forcar_sync=False):

    """Retorna lista de nomes de motoristas que possuem pacotes pendentes em lote_pendente_anjun."""

    try:

        try:

            sincronizar_lotes_pendentes_anjun_api(forcar=forcar_sync)

        except Exception:

            pass

        conn = conectar_banco()

        c = conn.cursor()

        c.execute("SELECT DISTINCT motorista FROM lote_pendente_anjun")

        rows = c.fetchall()

        conn.close()

        return [r[0] for r in rows if r[0]]

    except Exception as e:

        print(f"[Aviso] Falha ao consultar motoristas com lote aberto Anjun: {e}")

        return []



CONFIG_ANJUN_TOKENS = os.path.join(BASE_DIR, 'config_anjun_tokens.json')

cache_sessoes_anjun_por_conta = {}

mapa_motorista_sessao_anjun = {}

waybills_cancelados_anjun = set()

_ultimo_sync_lotes_anjun = 0

ultimo_erro_finalizacao_anjun = ""



def carregar_tokens_anjun_salvos():

    try:

        if os.path.exists(CONFIG_ANJUN_TOKENS):

            with open(CONFIG_ANJUN_TOKENS, 'r', encoding='utf-8') as f:

                return json.load(f) or {}

    except Exception:

        pass

    return {}



def _extrair_dados_jwt_anjun(token):

    if not token or not isinstance(token, str) or '.' not in token:

        return {}

    try:

        import base64

        partes = token.split('.')

        if len(partes) < 2:

            return {}

        payload_b64 = partes[1]

        pad = len(payload_b64) % 4

        if pad:

            payload_b64 += '=' * (4 - pad)

        raw = base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8')

        return json.loads(raw) or {}

    except Exception:

        return {}



def salvar_token_anjun_conta(sess_dict, conta_id=None):

    try:

        if not sess_dict or not sess_dict.get("token"):

            return

        tk = sess_dict.get("token")

        jwt_info = _extrair_dados_jwt_anjun(tk)

        uname_jwt = str(jwt_info.get("username") or sess_dict.get("username") or "").strip()

        cid_alvo = str(conta_id or sess_dict.get("conta_id") or "").strip()

        todas_contas = carregar_contas_plataformas().get("anjun", {}).get("contas", [])

        if uname_jwt:

            for c in todas_contas:

                if str(c.get("login_usuario") or "").strip().lower() == uname_jwt.lower():

                    cid_alvo = c.get("id")

                    break

        if not cid_alvo:

            cid_alvo, _ = obter_conta_ativa_plataforma("anjun")



        chave = str(sess_dict.get("siteName") or jwt_info.get("siteName") or sess_dict.get("siteId") or cid_alvo or "default").strip()

        dados = carregar_tokens_anjun_salvos()

        dados[chave] = {

            "conta_id": cid_alvo,

            "username": uname_jwt,

            "token": tk,

            "siteId": sess_dict.get("siteId") or jwt_info.get("siteId"),

            "siteCode": sess_dict.get("siteCode") or jwt_info.get("siteCode"),

            "siteName": sess_dict.get("siteName") or jwt_info.get("siteName"),

            "orgId": sess_dict.get("orgId") or jwt_info.get("orgId"),

            "timestamp": time.time()

        }

        with open(CONFIG_ANJUN_TOKENS, 'w', encoding='utf-8') as f:

            json.dump(dados, f, ensure_ascii=False, indent=2)

        cache_sessoes_anjun_por_conta[chave] = dict(dados[chave])

    except Exception as e:

        print(f"[Aviso] Falha ao salvar token Anjun por conta: {e}")



def _token_pertence_a_outra_conta_anjun(uname_jwt, cid_atual):

    if not uname_jwt:

        return False

    uname_low = str(uname_jwt).strip().lower()

    todas_contas = carregar_contas_plataformas().get("anjun", {}).get("contas", [])

    for c in todas_contas:

        c_login = str(c.get("login_usuario") or "").strip().lower()

        if c_login and c_login == uname_low and c.get("id") != cid_atual:

            return True

    return False



def obter_sessao_anjun_da_conta(conta_id=None, forcar=False):

    cid, conta_obj = obter_conta_ativa_plataforma("anjun", conta_id)

    login_esperado = str(conta_obj.get("login_usuario") or "").strip().lower()



    # Se for a conta ativa no Chrome, tenta atualizar do navegador primeiro

    if not conta_id or cid == conta_ativa or not conta_ativa:

        atualizar_sessao_anjun(forcar=forcar)



    salvos = carregar_tokens_anjun_salvos()

    # 1. Procura pelo login_usuario exato no JWT

    for v in salvos.values():

        if not isinstance(v, dict) or not v.get("token"):

            continue

        tk = v.get("token")

        jwt_info = _extrair_dados_jwt_anjun(tk)

        uname_jwt = str(jwt_info.get("username") or v.get("username") or "").strip().lower()

        if login_esperado and uname_jwt and uname_jwt == login_esperado:

            return dict(v)



    # 2. Procura pelo conta_id salvo (mesmo que o usuário tenha digitado login provisório como 'j')

    for v in salvos.values():

        if not isinstance(v, dict) or not v.get("token"):

            continue

        tk = v.get("token")

        jwt_info = _extrair_dados_jwt_anjun(tk)

        uname_jwt = str(jwt_info.get("username") or v.get("username") or "").strip().lower()

        if v.get("conta_id") and v.get("conta_id") == cid and not _token_pertence_a_outra_conta_anjun(uname_jwt, cid):

            return dict(v)



    # 3. Procura se login_esperado está contido no siteName/siteCode (ex: 'b176' em 'SP-R-D176')

    if login_esperado:

        num_login = "".join(filter(str.isdigit, login_esperado))

        for k, v in salvos.items():

            if not isinstance(v, dict) or not v.get("token"):

                continue

            sname = str(v.get("siteName") or k or "").lower()

            scode = str(v.get("siteCode") or "").lower()

            if login_esperado in sname or login_esperado in scode or (num_login and len(num_login) >= 2 and (num_login in sname or num_login in scode)):

                return dict(v)



    # 4. Fallback para a sessão ativa caso não pertença a outra conta

    if cache_sessao_anjun and cache_sessao_anjun.get("token"):

        uname_c = str(_extrair_dados_jwt_anjun(cache_sessao_anjun.get("token")).get("username") or "").strip().lower()

        if not _token_pertence_a_outra_conta_anjun(uname_c, cid):

            return dict(cache_sessao_anjun)



    return {}



def atualizar_sessao_anjun(drv=None, forcar=False):

    """

    Captura automaticamente o token de autorização JWT e dados do galpão Anjun

    a partir da janela do Chrome onde o usuário está logado, respeitando a conta_ativa.

    Nunca captura token de abas de outras plataformas (ex: iMile/Loggi).

    """

    global cache_sessao_anjun, driver

    cid, conta_obj = obter_conta_ativa_plataforma("anjun")

    login_esperado = str(conta_obj.get("login_usuario") or "").strip().lower()



    if not forcar and cache_sessao_anjun.get("token") and (time.time() - cache_sessao_anjun.get("timestamp", 0) < 120):

        uname_cache = str(_extrair_dados_jwt_anjun(cache_sessao_anjun.get("token")).get("username") or "").strip().lower()

        if (not login_esperado or not uname_cache or uname_cache == login_esperado) or not _token_pertence_a_outra_conta_anjun(uname_cache, cid):

            return cache_sessao_anjun



    alvo_driver = drv if drv else (driver if (not plataforma_ativa or 'anjun' in str(plataforma_ativa).lower()) else None)

    aba_anjun_encontrada = False



    if alvo_driver:

        try:

            if hasattr(alvo_driver, 'window_handles') and alvo_driver.window_handles:

                try:

                    curr_url = alvo_driver.current_url.lower()

                except Exception:

                    curr_url = ""

                if "anjun" in curr_url:

                    aba_anjun_encontrada = True

                else:

                    for h in alvo_driver.window_handles:

                        try:

                            alvo_driver.switch_to.window(h)

                            if "anjun" in alvo_driver.current_url.lower():

                                aba_anjun_encontrada = True

                                break

                        except Exception:

                            pass



            # SOMENTE lê localStorage se estivermos de fato em uma aba da Anjun!

            if aba_anjun_encontrada:

                user_raw = alvo_driver.execute_script("return window.localStorage.getItem('anjun-user');")

                if user_raw:

                    try:

                        u_obj = json.loads(user_raw)

                        token = u_obj.get("token")

                        if token:

                            info = u_obj.get("userInfo") or {}

                            uname_tok = str(_extrair_dados_jwt_anjun(token).get("username") or info.get("username") or "").strip().lower()

                            novo_site_id = info.get("siteId") or cache_sessao_anjun.get("siteId")

                            if cache_sessao_anjun.get("siteId") and novo_site_id and cache_sessao_anjun.get("siteId") != novo_site_id:

                                cache_motoristas_anjun["lista"] = []

                                cache_motoristas_anjun["mapa"] = {}

                                cache_motoristas_anjun["timestamp"] = 0

                            sess_capturada = {

                                "token": token,

                                "timestamp": time.time(),

                                "siteId": info.get("siteId") or cache_sessao_anjun.get("siteId"),

                                "siteCode": info.get("siteCode") or cache_sessao_anjun.get("siteCode"),

                                "siteName": info.get("siteName") or cache_sessao_anjun.get("siteName"),

                                "orgId": info.get("orgId") or cache_sessao_anjun.get("orgId"),

                                "username": uname_tok

                            }

                            salvar_token_anjun_conta(sess_capturada, conta_id=cid)

                            if (not login_esperado or not uname_tok or uname_tok == login_esperado) or not _token_pertence_a_outra_conta_anjun(uname_tok, cid):

                                cache_sessao_anjun.update(sess_capturada)

                                print(f"[+] [Anjun API] Sessão capturada do Chrome! Estação: {cache_sessao_anjun.get('siteName')} | Token: {token[:12]}...")

                                return cache_sessao_anjun

                    except Exception:

                        pass



                ls_token = alvo_driver.execute_script("return window.localStorage.getItem('token') || window.sessionStorage.getItem('token') || window.localStorage.getItem('Admin-Token');")

                if ls_token:

                    tk_clean = ls_token.replace('Bearer ', '').strip()

                    uname_tok = str(_extrair_dados_jwt_anjun(tk_clean).get("username") or "").strip().lower()

                    salvar_token_anjun_conta({"token": tk_clean}, conta_id=cid)

                    if (not login_esperado or not uname_tok or uname_tok == login_esperado) or not _token_pertence_a_outra_conta_anjun(uname_tok, cid):

                        cache_sessao_anjun["token"] = tk_clean

                        cache_sessao_anjun["timestamp"] = time.time()

                        print(f"[+] [Anjun API] Token direto capturado do Chrome: {cache_sessao_anjun['token'][:12]}...")

                        return cache_sessao_anjun

        except Exception as e:

            print(f"[Aviso] [Anjun API] Não foi possível extrair sessão do Chrome: {e}")



    # Usa o token salvo correspondente especificamente à CONTA ATIVA da Anjun

    salvos = carregar_tokens_anjun_salvos()

    if salvos:

        escolhido = None

        for k, v in salvos.items():

            if not isinstance(v, dict) or not v.get("token"):

                continue

            uname_jwt = str(_extrair_dados_jwt_anjun(v["token"]).get("username") or v.get("username") or "").strip().lower()

            if login_esperado and uname_jwt and uname_jwt == login_esperado:

                escolhido = v

                break

        if not escolhido:

            for k, v in salvos.items():

                if not isinstance(v, dict) or not v.get("token"):

                    continue

                uname_jwt = str(_extrair_dados_jwt_anjun(v["token"]).get("username") or v.get("username") or "").strip().lower()

                if v.get("conta_id") and v.get("conta_id") == cid and not _token_pertence_a_outra_conta_anjun(uname_jwt, cid):

                    escolhido = v

                    break

        if not escolhido and login_esperado:

            num_login = "".join(filter(str.isdigit, login_esperado))

            for k, v in salvos.items():

                if not isinstance(v, dict) or not v.get("token"):

                    continue

                sname = str(v.get("siteName") or k or "").lower()

                if login_esperado in sname or (num_login and len(num_login) >= 2 and num_login in sname):

                    escolhido = v

                    break

        if not escolhido and not cache_sessao_anjun.get("token"):

            escolhido = max(salvos.values(), key=lambda x: x.get("timestamp", 0))

        if escolhido and escolhido.get("token"):

            cache_sessao_anjun.update(escolhido)

            cache_sessao_anjun["timestamp"] = time.time()



    return cache_sessao_anjun



def obter_todas_sessoes_anjun_conhecidas():

    """Retorna lista de dicionários de sessão Anjun (ativa + salvas por conta)."""

    sess_principal = atualizar_sessao_anjun()

    salvos = carregar_tokens_anjun_salvos()

    for k, v in salvos.items():

        if v and v.get("token"):

            cache_sessoes_anjun_por_conta[k] = v



    lista_sess = []

    tokens_vistos = set()

    if sess_principal and sess_principal.get("token"):

        lista_sess.append(dict(sess_principal))

        tokens_vistos.add(sess_principal["token"])

    for v in cache_sessoes_anjun_por_conta.values():

        tk = v.get("token")

        if tk and tk not in tokens_vistos:

            lista_sess.append(dict(v))

            tokens_vistos.add(tk)

    return lista_sess



def executar_post_anjun(endpoint_path, payload, token_override=None):

    """

    Executa POST na API da Anjun em ~25-60ms com os headers e token de sessão.

    Retorna (sucesso: bool, mensagem: str, dados_resposta: dict)

    """

    sessao = atualizar_sessao_anjun()

    token = token_override or sessao.get("token")

    if not token and not token_override:

        sessao = atualizar_sessao_anjun(forcar=True)

        token = sessao.get("token")

    if not token:

        return False, "Sessão da Anjun não encontrada no navegador Chrome", {}



    url = f"https://newsupplier.anjunexpress.com{endpoint_path}"

    headers = {

        "accept": "application/json, text/plain, */*",

        "content-type": "application/json",

        "token": token,

        "origin": "https://newsupplier.anjunexpress.com",

        "referer": "https://newsupplier.anjunexpress.com/",

        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"

    }



    data = json.dumps(payload).encode('utf-8')

    ultimo_erro = ""

    for tentativa in range(1, 4):

        try:

            req = urllib.request.Request(url, data=data, headers=headers)

            with urllib.request.urlopen(req, timeout=8.0) as resp:

                raw = resp.read().decode('utf-8')

                res = json.loads(raw) if raw else {}

                if not isinstance(res, dict):

                    res = {}

                

                code = res.get("code")

                msg = res.get("msg") or res.get("message") or ""

                

                if code in [200, "200", 0, "0"] or (code is None and "data" in res):

                    return True, msg or "Operação realizada com sucesso", res

                elif code in [401, "401", 403, "403"] or any(k in (msg or "").lower() for k in ["sessão", "sessao", "token", "unauthorized", "login"]):

                    if not token_override:

                        cache_sessao_anjun["token"] = None

                        if tentativa == 1:

                            sessao_nova = atualizar_sessao_anjun(forcar=True)

                            tk_novo = sessao_nova.get("token")

                            if tk_novo:

                                headers["token"] = tk_novo

                                print("[*] [Anjun API] Token renovado automaticamente! Retentando requisição...")

                                continue

                    return False, f"Sessão expirada: {msg}", res

                else:

                    return False, msg or f"Erro retornado pela Anjun (code: {code})", res

        except urllib.error.HTTPError as he:

            if he.code in (401, 403) and not token_override:

                cache_sessao_anjun["token"] = None

                if tentativa == 1:

                    sessao_nova = atualizar_sessao_anjun(forcar=True)

                    tk_novo = sessao_nova.get("token")

                    if tk_novo:

                        headers["token"] = tk_novo

                        print(f"[*] [Anjun API] HTTP {he.code} recebido. Token renovado automaticamente, retentando...")

                        continue

            try:

                err_body = he.read().decode('utf-8')

                err_json = json.loads(err_body) if err_body else {}

                if not isinstance(err_json, dict):

                    err_json = {}

                msg = err_json.get("msg") or err_json.get("message") or str(he)

                return False, f"Sessão expirada ({he.code}): {msg}" if he.code in (401, 403) else msg, err_json

            except Exception:

                return False, f"Erro HTTP {he.code}: {str(he)}", {}

        except Exception as e:

            ultimo_erro = str(e)

            print(f"[!] [Anjun API] Oscilação de internet em {endpoint_path} (Tentativa {tentativa}/3): {ultimo_erro}")

            if tentativa < 3:

                time.sleep(0.4)

                continue

    return False, f"Internet lenta / oscilação na Anjun ({ultimo_erro})", {}



def extrair_registros_pagina_anjun(res):

    """Extrai a lista de registros de /admin/taskAllocation/page tanto quando data é list quanto quando é dict."""

    if not isinstance(res, dict):

        return []

    d = res.get("data")

    if isinstance(d, list):

        return d

    if isinstance(d, dict):

        return d.get("records") or d.get("list") or []

    return []



def sincronizar_lotes_pendentes_anjun_api(forcar=False):

    """

    Consulta na API da Anjun (/admin/taskAllocation/page com finalScanOperationType=3)

    todos os pacotes que estão abertos (não finalizados) na tabela de atribuição

    de todas as contas Anjun conhecidas, sincronizando-os em lote_pendente_anjun.

    """

    global _ultimo_sync_lotes_anjun, mapa_motorista_sessao_anjun

    agora = time.time()

    if not forcar and (agora - _ultimo_sync_lotes_anjun < 8.0):

        return

    _ultimo_sync_lotes_anjun = agora



    # Sincroniza exclusivamente a sessão da conta/base ativa no momento (evita puxar lotes da Base 176 em computador da Base Avaré)

    cid, conta_obj = obter_conta_ativa_plataforma("anjun")

    sess_conta = obter_sessao_anjun_da_conta(cid)

    sessoes = []

    if sess_conta and sess_conta.get("token"):

        sessoes.append(sess_conta)

    else:

        sess_principal = atualizar_sessao_anjun()

        if sess_principal and sess_principal.get("token"):

            sessoes.append(sess_principal)

    if not sessoes:

        return



    novos_pares = []

    for sess in sessoes:

        tk = sess.get("token")

        if not tk:

            continue

        ok, _, res = executar_post_anjun("/admin/taskAllocation/page", {

            "finalScanOperationType": 3,

            "pageNo": 1,

            "pageSize": 500

        }, token_override=tk)

        if not ok or not isinstance(res, dict):

            continue

        records = extrair_registros_pagina_anjun(res)

        for r in records:

            if not isinstance(r, dict):

                continue

            wb = str(r.get("waybillNumber") or "").strip()

            mot = str(r.get("dispatchUserName") or "").strip()

            uid = r.get("dispatchUserId")

            if not wb or not mot:

                continue

            if wb in waybills_cancelados_anjun:

                continue

            novos_pares.append((wb, mot))

            norm_m = remover_acentos(mot.lower())

            mapa_motorista_sessao_anjun[norm_m] = {

                "token": tk,

                "dispatchUserId": uid,

                "dispatchUserName": mot,

                "siteName": sess.get("siteName", "SP-R-D093"),

                "siteId": sess.get("siteId")

            }



    if novos_pares:

        try:

            conn = conectar_banco()

            c = conn.cursor()

            c.executemany("INSERT OR REPLACE INTO lote_pendente_anjun (waybill, motorista, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", novos_pares)

            conn.commit()

            conn.close()

        except Exception as e:

            print(f"[Aviso] Falha ao sincronizar lote_pendente_anjun da API: {e}")



def carregar_motoristas_anjun_api(forcar=False, conta_id=None):

    """

    Obtém via API oficial da Anjun (/user/pm/account/pageQuery) os entregadores

    ativos cadastrados especificamente na BASE ATIVA (conta_id), com seus respectivos id e username.

    """

    global cache_motoristas_anjun, cache_motoristas_anjun_por_conta

    cid, conta_obj = obter_conta_ativa_plataforma("anjun", conta_id)



    cache_conta = cache_motoristas_anjun_por_conta.get(cid)

    if not forcar and cache_conta and cache_conta.get("lista") and (time.time() - cache_conta.get("timestamp", 0) < 600):

        return cache_conta["lista"], cache_conta["mapa"]



    sess_conta = obter_sessao_anjun_da_conta(cid, forcar=forcar)

    token_alvo = sess_conta.get("token")



    if not token_alvo:

        if cache_conta and cache_conta.get("lista"):

            return cache_conta["lista"], cache_conta["mapa"]

        salvos_base = obter_motoristas_da_base_salvos("anjun", cid)

        if salvos_base:

            lista_fb = [{"id": idx + 1, "username": n, "realName": n, "code": ""} for idx, n in enumerate(salvos_base)]

            mapa_fb = {remover_acentos(n.lower()): obj for n, obj in zip(salvos_base, lista_fb)}

            return lista_fb, mapa_fb

        return [], {}



    url = "https://newsupplier.anjunexpress.com/user/pm/account/pageQuery"

    payload = {

        "pageNumber": 1,

        "pageSize": 200,

        "params": {

            "code": "",

            "username": "",

            "orgId": "",

            "accountState": 1,

            "userState": -1,

            "accountRole": -1

        }

    }



    records = []

    headers = {

        "accept": "application/json, text/plain, */*",

        "content-type": "application/json",

        "token": token_alvo,

        "origin": "https://newsupplier.anjunexpress.com",

        "referer": "https://newsupplier.anjunexpress.com/",

        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"

    }

    try:

        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, headers=headers)

        with urllib.request.urlopen(req, timeout=8.0) as resp:

            res = json.loads(resp.read().decode('utf-8'))

            d_obj = res.get("data") if isinstance(res, dict) else {}

            recs = (d_obj.get("records") if isinstance(d_obj, dict) else []) or []

            if isinstance(recs, list):

                records.extend(recs)

    except Exception as e:

        print(f"[Aviso] [Anjun API] Falha ao consultar motoristas da base {cid}: {e}")



    if not records:

        if cache_conta and cache_conta.get("lista"):

            return cache_conta["lista"], cache_conta["mapa"]

        salvos_base = obter_motoristas_da_base_salvos("anjun", cid)

        if salvos_base:

            lista_fb = [{"id": idx + 1, "username": n, "realName": n, "code": ""} for idx, n in enumerate(salvos_base)]

            mapa_fb = {remover_acentos(n.lower()): obj for n, obj in zip(salvos_base, lista_fb)}

            return lista_fb, mapa_fb

        return [], {}



    try:

        lista = []

        mapa = {}

        ids_vistos = set()

        for d in records:

            uname = (d.get("username") or "").strip()

            rname = (d.get("realName") or "").strip()

            uid = d.get("id")

            if not uname or not uid or uid in ids_vistos:

                continue

            ids_vistos.add(uid)

            

            obj = {

                "id": uid,

                "username": uname,

                "realName": rname or uname,

                "code": d.get("code") or ""

            }

            lista.append(obj)

            

            # Normalização para busca

            norm_u = remover_acentos(uname.lower())

            norm_r = remover_acentos(rname.lower()) if rname else norm_u

            

            mapa[norm_u] = obj

            mapa[norm_r] = obj

            

            for n in [norm_u, norm_r]:

                partes = n.split()

                if len(partes) >= 2:

                    mapa[" ".join(partes[:2])] = obj

                    mapa[partes[-1]] = obj

                    mapa[partes[0]] = obj



        cache_motoristas_anjun["lista"] = lista

        cache_motoristas_anjun["mapa"] = mapa

        cache_motoristas_anjun["timestamp"] = time.time()

        cache_motoristas_anjun_por_conta[cid] = {

            "lista": lista,

            "mapa": mapa,

            "timestamp": time.time()

        }

        salvar_motoristas_da_base("anjun", cid, [m["username"] for m in lista])

        print(f"[+] [Anjun API] {len(lista)} entregadores ativos sincronizados da base {cid} ({sess_conta.get('siteName', '')})!")

        

        # Sincroniza no banco SQLite apenas se o motorista ainda não tiver nenhuma cidade vinculada

        try:

            conn = conectar_banco()

            cursor = conn.cursor()

            for mot in lista:

                nome = mot["username"]

                cursor.execute(

                    "SELECT 1 FROM motoristas_plataforma WHERE LOWER(motorista) = LOWER(?) AND LOWER(plataforma) = 'anjun' LIMIT 1",

                    (nome,)

                )

                if cursor.fetchone():

                    continue

                cidade_cand = "Geral"

                for c_item in carregar_cidades():

                    if c_item and remover_acentos(c_item.lower()) in remover_acentos(nome.lower()):

                        cidade_cand = c_item

                        break

                cursor.execute("""

                    INSERT OR IGNORE INTO motoristas_plataforma (cidade, motorista, plataforma)

                    VALUES (?, ?, 'anjun')

                """, (cidade_cand, nome))

            conn.commit()

            conn.close()

            invalidar_cache_ram_cidades_motoristas()

            try:

                excel_path = obter_caminho_excel()

                gerar_planilha_motoristas_excel(excel_path)

                if os.path.exists(excel_path):

                    meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

                    with open(meta_mtime_file, 'w') as f_meta:

                        f_meta.write(str(os.path.getmtime(excel_path)))

            except Exception:

                pass

        except Exception:

            pass

            

        return lista, mapa

    except Exception as e:

        print(f"[Aviso] [Anjun API] Falha ao sincronizar motoristas da API ({cid}): {e}")

        return cache_motoristas_anjun.get("lista", []), cache_motoristas_anjun.get("mapa", {})



def resolver_motorista_anjun_api(mot_clean):

    """

    Localiza o objeto do entregador Anjun {id, username, realName} por aproximação inteligente.

    """

    if not mot_clean:

        return None

        

    lista, mapa = carregar_motoristas_anjun_api()

    if not lista:

        lista, mapa = carregar_motoristas_anjun_api(forcar=True)

        

    if not lista:

        return None



    try:

        anjun_map, _ = carregar_mapeamento_motoristas()

        mot_clean = anjun_map.get(mot_clean.lower(), mot_clean)

    except Exception:

        pass



    nb = remover_acentos(mot_clean.strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

    

    # 1. Match direto no mapa

    norm_direct = remover_acentos(mot_clean.strip().lower())

    if norm_direct in mapa:

        return mapa[norm_direct]



    # 2. Match exato normalizado sem espaços ou símbolos

    for d in lista:

        u_clean = remover_acentos(d["username"].lower()).replace('-', '').replace('_', '').replace(' ', '')

        r_clean = remover_acentos(d["realName"].lower()).replace('-', '').replace('_', '').replace(' ', '')

        if nb == u_clean or nb == r_clean:

            return d



    # 3. Match por substring

    for d in lista:

        u_clean = remover_acentos(d["username"].lower()).replace('-', '').replace('_', '').replace(' ', '')

        r_clean = remover_acentos(d["realName"].lower()).replace('-', '').replace('_', '').replace(' ', '')

        if nb in u_clean or u_clean in nb or nb in r_clean or r_clean in nb:

            return d



    # 4. Match por pontuação de palavras (Tokens)

    tokens = [t for t in re.split(r'[\s\-_]+', remover_acentos(mot_clean.strip().lower())) if len(t) >= 2]

    best = None

    best_score = 0

    for d in lista:

        combined = (remover_acentos(d["username"].lower()) + " " + remover_acentos(d["realName"].lower()))

        score = sum(1 for t in tokens if t in combined)

        if score > best_score:

            best_score = score

            best = d

    if best and best_score >= 1:

        return best



    # 5. Busca sob demanda direta na API iMile com keyword (para motoristas recém-adicionados ou fora do top 50)

    try:

        sessao = atualizar_sessao_imile()

        token = sessao.get("token")

        station_code = sessao.get("currentStationCode", "S210570001")

        if token and station_code:

            headers_busca = {

                "accept": "application/json, text/plain, */*",

                "authorization": f"Bearer {token}",

                "content-type": "application/json",

                "hubcode": station_code,

                "lang": "pt_BR",

                "origin": "https://ds.imile.com",

                "referer": "https://ds.imile.com/",

                "sys-name": "DS",

                "sys-portal": "DS",

                "timezone": "-3",

                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"

            }

            body_busca = json.dumps({"ocCodeList": [station_code], "isDriver": 1, "status": "ACTIVE", "keyword": mot_clean}).encode('utf-8')

            req_b = urllib.request.Request("https://ds.imile.com/hrms/user/associate/list", data=body_busca, headers=headers_busca)

            with urllib.request.urlopen(req_b, timeout=3.0) as resp_b:

                data_b = json.loads(resp_b.read().decode('utf-8'))

                for item_b in data_b.get("resultObject", []):

                    nm_b = (item_b.get("userName") or "").strip()

                    cd_b = (item_b.get("userCode") or "").strip()

                    if nm_b and cd_b:

                        obj_novo = {"daCode": cd_b, "daName": nm_b, "id": item_b.get("id")}

                        lista.append(obj_novo)

                        mapa[remover_acentos(nm_b.lower())] = obj_novo

                        cache_motoristas_imile["lista"] = lista

                        cache_motoristas_imile["mapa"] = mapa

                        cid_ativo, _ = obter_conta_ativa_plataforma("imile")

                        salvar_motoristas_da_base("imile", cid_ativo, [m["daName"] for m in lista])

                        return obj_novo

    except Exception as e_busca:

        print(f"[Aviso] [iMile API] Busca sob demanda por '{mot_clean}' falhou: {e_busca}")



    return None



def bipar_pacote_anjun_api(codigo_qr, motorista, modo_triagem_direta=False, conta_id=None):

    """

    Executa a bipagem ultra-rápida via API na Anjun Express em ~60-100ms:

    1. Entrada na Base (warehousingScan + queryList + warehousingUpload)

    2. Atribuição ao Entregador (taskAllocation)

    Retorna (sucesso: bool, mensagem: str, motorista_atribuido: str, cidade: str, cep: str, destinatario: str, endereco: str)

    """

    if conta_id and str(conta_id).strip() not in ["", "padrao"]:

        sessao = obter_sessao_anjun_da_conta(conta_id)

    else:

        sessao = atualizar_sessao_anjun()

    token = sessao.get("token")

    if not token:

        sessao = obter_sessao_anjun_da_conta(conta_id, forcar=True) if (conta_id and str(conta_id).strip() not in ["", "padrao"]) else atualizar_sessao_anjun(forcar=True)

        token = sessao.get("token")

    if not token:

        return "aguardando_login", "Sessão da Anjun ausente no navegador", "", "", "", "", ""



    codigo_limpo = str(codigo_qr).strip().upper()

    

    # 1. ENTRADA NA BASE

    payload_scan = {

        "waybillNumber": codigo_limpo,

        "lastOrderNumber": ""

    }

    ok_scan, msg_scan, res_scan = executar_post_anjun("/api/wms/console/v1/storage/dispatch/warehousingScan", payload_scan)

    

    shelves = "187"

    scan_id = None

    order_num_ql = None

    first = None

    

    if ok_scan:

        # Consulta área / scanId para confirmação

        ok_ql, _, res_ql = executar_post_anjun("/admin/scanRecord/warehousing/queryList", {"finalScanOperationType": 2})

        if ok_ql and isinstance(res_ql, dict):

            records = res_ql.get("data") or []

            if isinstance(records, list) and len(records) > 0 and isinstance(records[0], dict):

                first = records[0]

                scan_id = first.get("id")

                shelves = first.get("shelves") or shelves

                order_num_ql = first.get("orderNumber") or first.get("waybillNumber")

                

        # Finaliza a entrada com warehousingUpload

        payload_upload = {

            "source": 1,

            "waybillNumberList": [codigo_limpo],

            "scanIds": [scan_id] if scan_id else [],

            "createTaskParamList": [

                {

                    "waybillNumber": codigo_limpo,

                    "dispatchUserId": None,

                    "dispatchUserName": None,

                    "shelves": shelves

                }

            ]

        }

        ok_up, msg_up, _ = executar_post_anjun("/api/wms/console/v1/storage/dispatch/warehousingUpload", payload_upload)

        if not ok_up:

            msg_up_low = (msg_up or "").lower()

            if not any(k in msg_up_low for k in ["sucesso", "success", "já possui entrada", "ja possui entrada", "não repita", "nao repita", "já registrado", "ja registrado", "duplicad"]):

                time.sleep(0.25)

                ok_up, msg_up, _ = executar_post_anjun("/api/wms/console/v1/storage/dispatch/warehousingUpload", payload_upload)

                msg_up_low = (msg_up or "").lower()

                if not ok_up and not any(k in msg_up_low for k in ["sucesso", "success", "já possui entrada", "ja possui entrada", "não repita", "nao repita", "já registrado", "ja registrado", "duplicad"]):

                    print(f"[!] [Anjun API] Erro no warehousingUpload: {msg_up}")

                    return False, f"Entrada Anjun não confirmada pelo servidor: {msg_up}", "", "", "", "", ""

    else:

        msg_low = (msg_scan or "").lower()

        if any(k in msg_low for k in ["já possui entrada", "ja possui entrada", "possui entrada", "não repita", "nao repita", "já bipado", "ja bipado", "duplicad", "já recepcionado", "ja recepcionado", "já registrado", "ja registrado", "armazém", "armazem", "já existe", "ja existe", "já escaneado", "ja escaneado"]):

            # Já possui entrada na base, prossegue diretamente para a consulta e atribuição ao motorista!

            print(f"[*] [Anjun API] Pacote {codigo_limpo} já possui entrada na base ({msg_scan}). Prosseguindo para atribuição ao motorista...")

            pass

        elif any(k in msg_low for k in ["sessão", "sessao", "token", "401", "unauthorized"]):

            cache_sessao_anjun["token"] = None

            return "aguardando_login", f"Sessão expirada: {msg_scan}", "", "", "", "", ""

        else:

            # Erro impeditivo real da Anjun

            return False, msg_scan or "Erro na entrada Anjun", "", "", "", "", ""



    # Extrai possíveis códigos alternativos (ex: código AJ... se foi escaneado um código TT...)

    order_num_scan = None

    d_scan = {}

    if isinstance(res_scan, dict):

        d_scan_raw = res_scan.get("data")

        if isinstance(d_scan_raw, dict):

            d_scan = d_scan_raw

            order_num_scan = d_scan.get("orderNumber") or d_scan.get("waybillNumber") or d_scan.get("expressNumber")

            

    codigos_busca = list(dict.fromkeys([c for c in [codigo_limpo, order_num_ql, order_num_scan] if c]))



    # 2. DETALHES DE CIDADE, CEP, DESTINATÁRIO, BAIRRO, TELEFONE, EMPRESA, PRODUTO E VALOR

    cidade_pacote = ""

    cep_pacote = ""

    destinatario_pacote = ""

    endereco_pacote = ""

    bairro_pacote = ""

    tel_pacote = ""

    emp_pacote = ""

    prod_pacote = ""

    val_pacote = ""



    def _extrair_extras_anjun(obj):

        nonlocal bairro_pacote, tel_pacote, emp_pacote, prod_pacote, val_pacote

        if not isinstance(obj, dict):

            return

        if not bairro_pacote:

            bairro_pacote = str(obj.get("receiveArea") or obj.get("receiveNeighborhood") or obj.get("receiveDistrict") or obj.get("areaName") or "").strip()

        if not tel_pacote:

            tel_pacote = str(obj.get("receivePhone") or obj.get("receiveMobile") or obj.get("receiveTel") or obj.get("consigneePhone") or "").strip()

        if not emp_pacote:

            emp_pacote = str(obj.get("customerName") or obj.get("merchantName") or obj.get("senderName") or obj.get("clientName") or obj.get("platformName") or obj.get("channelName") or "").strip()

        if not prod_pacote:

            prod_pacote = str(obj.get("goodsName") or obj.get("itemName") or obj.get("cargoName") or obj.get("productName") or obj.get("cargoTypeDesc") or "").strip()

        if not val_pacote:

            v_cand = obj.get("totalParcelDeclaredValue") or obj.get("declaredValue") or obj.get("goodsValue") or obj.get("parcelValue")

            if v_cand is not None and str(v_cand).strip() not in ["", "0", "0.0"]:

                val_pacote = str(v_cand).strip()



    _extrair_extras_anjun(d_scan)

    _extrair_extras_anjun(first)



    # Se for código com prefixo 'TT' (TikTok) ou de parceiro, consulta imediatamente /admin/package/pageQuery

    # para obter a cidade e o waybill oficial (AJ...) antes das demais tentativas

    if codigo_limpo.upper().startswith("TT"):

        try:

            payload_pq_ini = {

                "pageNumber": 1,

                "pageSize": 50,

                "params": {

                    "type": 1,

                    "searchTimeType": 0,

                    "number": codigo_limpo,

                    "scanNumberList": [codigo_limpo]

                }

            }

            ok_pq_ini, _, res_pq_ini = executar_post_anjun("/admin/package/pageQuery", payload_pq_ini)

            if ok_pq_ini and isinstance(res_pq_ini, dict):

                d_pq_ini = res_pq_ini.get("data") if isinstance(res_pq_ini.get("data"), dict) else {}

                recs_pq_ini = d_pq_ini.get("records") or []

                if recs_pq_ini and len(recs_pq_ini) > 0 and isinstance(recs_pq_ini[0], dict):

                    p_rec_ini = recs_pq_ini[0]

                    cidade_pacote = (p_rec_ini.get("receiveCity") or p_rec_ini.get("city") or "").strip()

                    cep_pacote = cep_pacote or (p_rec_ini.get("receiveZipcode") or "").strip()

                    destinatario_pacote = destinatario_pacote or (p_rec_ini.get("receiveName") or "").strip()

                    endereco_pacote = endereco_pacote or (p_rec_ini.get("receiveAddress") or "").strip()

                    bairro_pacote = bairro_pacote or (p_rec_ini.get("receiveArea") or "").strip()

                    aj_pkg_ini = (p_rec_ini.get("packageNumber") or "").strip()

                    if aj_pkg_ini and aj_pkg_ini not in codigos_busca:

                        codigos_busca.append(aj_pkg_ini)

                        order_num_scan = aj_pkg_ini

                    _extrair_extras_anjun(p_rec_ini)

                    if cidade_pacote:

                        print(f"[+] [Anjun API] Pacote TT resolvido via /admin/package/pageQuery: Cidade='{cidade_pacote}' | AJ='{aj_pkg_ini}'")

        except Exception as e_ini:

            print(f"[Aviso] [Anjun API] Erro na consulta prioritária de TT: {e_ini}")



    # Tentativa 1: taskAllocation/printList (mais rápido e detalhado)

    if not cidade_pacote:

        try:

            ok_info, _, res_info = executar_post_anjun("/admin/taskAllocation/printList", {

                "dispatchUserName": "",

                "waybillNumberList": codigos_busca

            })

            if ok_info and isinstance(res_info, dict):

                d_info = res_info.get("data") if isinstance(res_info.get("data"), dict) else {}

                vol = d_info.get("voList") or []

                # Se acabou de dar entrada e não veio na 1ª tentativa, espera 120ms e tenta novamente

                if not vol and ok_scan:

                    time.sleep(0.12)

                    ok_info, _, res_info = executar_post_anjun("/admin/taskAllocation/printList", {

                        "dispatchUserName": "",

                        "waybillNumberList": codigos_busca

                    })

                    if ok_info and isinstance(res_info, dict):

                        d_info = res_info.get("data") if isinstance(res_info.get("data"), dict) else {}

                        vol = d_info.get("voList") or []

                if vol and len(vol) > 0 and isinstance(vol[0], dict):

                    p_item = vol[0]

                    cidade_pacote = (p_item.get("receiveCity") or "").strip()

                    cep_pacote = (p_item.get("receiveZipcode") or "").strip()

                    destinatario_pacote = (p_item.get("receiveName") or "").strip()

                    endereco_pacote = (p_item.get("receiveAddress") or "").strip()

                    _extrair_extras_anjun(p_item)

        except Exception as e_info:

            print(f"[Aviso] [Anjun API] Erro ao consultar printList: {e_info}")



    # Tentativa 2: Extrair do scanRecord/queryList caso printList não tenha retornado

    if not cidade_pacote and first:

        cidade_pacote = (first.get("receiveCity") or first.get("destination") or first.get("areaName") or "").strip()

        cep_pacote = cep_pacote or (first.get("receiveZipcode") or "").strip()

        destinatario_pacote = destinatario_pacote or (first.get("receiveName") or "").strip()

        endereco_pacote = endereco_pacote or (first.get("receiveAddress") or "").strip()



    # Tentativa 3: Se não encontrou, busca na página de alocação de tarefas (/admin/taskAllocation/page)

    if not cidade_pacote:

        for cod in codigos_busca:

            try:

                ok_page, _, res_page = executar_post_anjun("/admin/taskAllocation/page", {

                    "waybillNumber": cod,

                    "pageNo": 1,

                    "pageSize": 10

                })

                if ok_page and isinstance(res_page, dict):

                    page_list = extrair_registros_pagina_anjun(res_page)

                    if page_list and len(page_list) > 0 and isinstance(page_list[0], dict):

                        p_rec = page_list[0]

                        cidade_pacote = (p_rec.get("receiveCity") or p_rec.get("city") or "").strip()

                        cep_pacote = cep_pacote or (p_rec.get("receiveZipcode") or "").strip()

                        destinatario_pacote = destinatario_pacote or (p_rec.get("receiveName") or "").strip()

                        endereco_pacote = endereco_pacote or (p_rec.get("receiveAddress") or "").strip()

                        _extrair_extras_anjun(p_rec)

                        if cidade_pacote:

                            break

            except Exception:

                pass



    # Tentativa 3.5: Consulta geral de pacotes Anjun (/admin/package/pageQuery)

    # Essencial para qualquer pacote que não trouxe cidade nas telas de alocação

    if not cidade_pacote:

        for cod in list(codigos_busca):

            try:

                payload_pq = {

                    "pageNumber": 1,

                    "pageSize": 50,

                    "params": {

                        "type": 1,

                        "searchTimeType": 0,

                        "number": cod,

                        "scanNumberList": [cod]

                    }

                }

                ok_pq, _, res_pq = executar_post_anjun("/admin/package/pageQuery", payload_pq)

                if ok_pq and isinstance(res_pq, dict):

                    d_pq = res_pq.get("data") if isinstance(res_pq.get("data"), dict) else {}

                    recs_pq = d_pq.get("records") or []

                    if recs_pq and len(recs_pq) > 0 and isinstance(recs_pq[0], dict):

                        p_rec = recs_pq[0]

                        cidade_pacote = (p_rec.get("receiveCity") or p_rec.get("city") or "").strip()

                        cep_pacote = cep_pacote or (p_rec.get("receiveZipcode") or "").strip()

                        destinatario_pacote = destinatario_pacote or (p_rec.get("receiveName") or "").strip()

                        endereco_pacote = endereco_pacote or (p_rec.get("receiveAddress") or "").strip()

                        bairro_pacote = bairro_pacote or (p_rec.get("receiveArea") or "").strip()

                        aj_pkg = (p_rec.get("packageNumber") or "").strip()

                        if aj_pkg:

                            if aj_pkg not in codigos_busca:

                                codigos_busca.append(aj_pkg)

                            if not order_num_scan:

                                order_num_scan = aj_pkg

                        _extrair_extras_anjun(p_rec)

                        if cidade_pacote:

                            print(f"[+] [Anjun API] Cidade encontrada via /admin/package/pageQuery para {cod}: {cidade_pacote} (AJ: {aj_pkg or cod})")

                            break

            except Exception as e_pq:

                print(f"[Aviso] [Anjun API] Erro ao consultar /admin/package/pageQuery: {e_pq}")



    # Tentativa 4: Se temos o CEP mas a cidade não veio, resolve pelo CEP via ViaCEP/cache local!

    if not cidade_pacote and cep_pacote:

        try:

            cid_cep = obter_cidade_por_cep(cep_pacote)

            if cid_cep:

                cidade_pacote = cid_cep

                print(f"[+] [Anjun API] Cidade resolvida com sucesso a partir do CEP {cep_pacote}: {cidade_pacote}")

        except Exception:

            pass



    registrar_detalhes_extras_pacote(

        codigos_busca + [codigo_qr],

        bairro=bairro_pacote,

        telefone=tel_pacote,

        negocios=emp_pacote,

        produto=prod_pacote,

        valor_declarado=val_pacote,

        recebedor=destinatario_pacote,

        cep=cep_pacote,

        endereco=endereco_pacote

    )



    if cidade_pacote:

        print(f"[+] [Anjun API] Informações obtidas: Cidade: {cidade_pacote} | CEP: {cep_pacote} | Endereço: {endereco_pacote} | Destinatário: {destinatario_pacote}")



    # 3. VERIFICAÇÃO DE DIVERGÊNCIA DE CIDADE / CEP vs MOTORISTA

    mot_clean = str(motorista).strip() if motorista else ""

    if modo_triagem_direta:

        if not cidade_pacote:

            return "divergente", "Divergência: Pacote sem cidade de destino informada pelo rastreio!", "Sem Cidade", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote



        lista_cidades = carregar_cidades()

        cidade_map = encontrar_cidade_mapeada(cidade_pacote, lista_cidades) or cidade_pacote

        mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_map, "anjun", cep=cep_pacote, bairro=bairro_pacote)

        if not mots_esperados and cidade_map != cidade_pacote:

            mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_pacote, "anjun", cep=cep_pacote, bairro=bairro_pacote)



        if not mots_esperados:

            detalhe_loc = f"Bairro {bairro_pacote}" if bairro_pacote else (f"CEP {cep_pacote}" if cep_pacote else "")

            detalhe_info = f" ({detalhe_loc})" if detalhe_loc else ""

            msg_alerta = f"Divergência: Nenhum motorista cadastrado para {cidade_pacote}{detalhe_info}!"

            print(f"[!] [Anjun API] DIVERGÊNCIA MODO TRIAGEM DIRETA! {msg_alerta}")

            return "divergente", msg_alerta, "Sem Motorista", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote



        mot_clean = mots_esperados[0]

        print(f"[+] [Anjun API] MODO TRIAGEM DIRETA: {cidade_pacote} -> Atribuindo automaticamente para {mot_clean}!")

    elif mot_clean and mot_clean not in ["---", "Apenas Entrada (Sem Atribuição)"]:

        if cidade_pacote:

            lista_cidades = carregar_cidades()

            cidade_map = encontrar_cidade_mapeada(cidade_pacote, lista_cidades) or cidade_pacote

            todos_mots_cidade = carregar_motoristas_cidade(cidade_map, "anjun", cep=cep_pacote, bairro=bairro_pacote)

            if not todos_mots_cidade and cidade_map != cidade_pacote:

                todos_mots_cidade = carregar_motoristas_cidade(cidade_pacote, "anjun", cep=cep_pacote, bairro=bairro_pacote)



            mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_map, "anjun", cep=cep_pacote, bairro=bairro_pacote)

            if not mots_esperados and cidade_map != cidade_pacote:

                mots_esperados, foi_por_regra, _ = carregar_motoristas_cidade_detalhado(cidade_pacote, "anjun", cep=cep_pacote, bairro=bairro_pacote)



            if todos_mots_cidade and not mots_esperados:

                detalhe_loc = f"Bairro {bairro_pacote}" if bairro_pacote else (f"CEP {cep_pacote}" if cep_pacote else "")

                detalhe_info = f" ({detalhe_loc})" if detalhe_loc else ""

                msg_alerta = f"Divergência: Pacote de {cidade_pacote}{detalhe_info} não está coberto pelas regras permitidas para {cidade_pacote}!"

                print(f"[!] [Anjun API] DIVERGÊNCIA! {msg_alerta}")

                return "divergente", msg_alerta, "Fora da Regra", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote



            if mots_esperados:

                norm_mot = remover_acentos(mot_clean.lower()).replace('-', '').replace('_', '').replace(' ', '')

                da_obj_check = resolver_motorista_anjun_api(mot_clean)

                da_uname_norm = remover_acentos(da_obj_check["username"].lower()).replace('-', '').replace('_', '').replace(' ', '') if da_obj_check else norm_mot

                

                mots_esp_norm = [remover_acentos(m.lower()).replace('-', '').replace('_', '').replace(' ', '') for m in mots_esperados]

                

                if norm_mot not in mots_esp_norm and da_uname_norm not in mots_esp_norm:

                    # NOVA REGRA INTELIGENTE DE AUTO-ATRIBUIÇÃO PARA GRUPO ABERTO!

                    def _buscar_candidatos_abertos(forcar=False):

                        mots_com_lote = obter_motoristas_com_lote_aberto_anjun(forcar_sync=forcar)

                        encontrados = []

                        chaves_vistas = set()

                        for m_esp in mots_esperados:

                            norm_esp = remover_acentos(m_esp.lower()).replace('-', '').replace('_', '').replace(' ', '')

                            da_esp = resolver_motorista_anjun_api(m_esp)

                            da_uname_esp = remover_acentos(da_esp["username"].lower()).replace('-', '').replace('_', '').replace(' ', '') if da_esp and da_esp.get("username") else norm_esp

                            da_rname_esp = remover_acentos(da_esp["realName"].lower()).replace('-', '').replace('_', '').replace(' ', '') if da_esp and da_esp.get("realName") else norm_esp

                            chave_mot = str(da_esp.get("id") or da_uname_esp or norm_esp) if da_esp else norm_esp

                            for m_aberto in mots_com_lote:

                                norm_ab = remover_acentos(m_aberto.lower()).replace('-', '').replace('_', '').replace(' ', '')

                                if not norm_ab:

                                    continue

                                if (norm_esp == norm_ab or da_uname_esp == norm_ab or da_rname_esp == norm_ab or

                                    norm_ab in norm_esp or norm_esp in norm_ab or norm_ab in da_uname_esp or da_uname_esp in norm_ab):

                                    if chave_mot not in chaves_vistas:

                                        chaves_vistas.add(chave_mot)

                                        encontrados.append(m_esp)

                                    break

                        return encontrados



                    candidatos_abertos = _buscar_candidatos_abertos(forcar=False)

                    if not candidatos_abertos:

                        candidatos_abertos = _buscar_candidatos_abertos(forcar=True)

                    

                    bairro_info = f" ({bairro_pacote})" if bairro_pacote else ""

                    cep_info = f" (CEP {cep_pacote})" if cep_pacote and not bairro_pacote else ""

                    if len(candidatos_abertos) == 1:

                        mot_auto = candidatos_abertos[0]

                        print(f"[+] [Anjun Auto-Atribuição] Pacote de {cidade_pacote}{bairro_info}{cep_info} redirecionado automaticamente para o grupo aberto de {mot_auto}!")

                        mot_clean = mot_auto

                    else:

                        esp_display = " / ".join(mots_esperados)

                        msg_alerta = f"Pacote de {cidade_pacote}{bairro_info}{cep_info} pertence a {esp_display}, mas você está bipando o lote de {mot_clean}!"

                        print(f"[!] [Anjun API] DIVERGÊNCIA (Atribuindo a {mot_clean})! {msg_alerta}")

                        mot_retorno_div = esp_display if foi_por_regra else ""

                        msg_divergente = msg_alerta

                        eh_divergente = True

            else:

                # BLINDAGEM ANTI-DIVERGÊNCIA: Se a cidade do pacote não possui motorista mapeado na Anjun,

                # verifica se o motorista ativo possui cidades mapeadas especificamente para ele nesta plataforma.

                cidades_mot = obter_cidades_motorista(mot_clean, "anjun", da_uname_norm if 'da_uname_norm' in locals() else None)

                if cidades_mot:

                    cids_mot_norm = [normalizar_cidade_estrita(c) for c in cidades_mot]

                    cid_teste_norm = normalizar_cidade_estrita(cidade_map or cidade_pacote)

                    if cid_teste_norm not in cids_mot_norm:

                        cidades_display = " / ".join(cidades_mot)

                        cep_info = f" (CEP {cep_pacote})" if cep_pacote else ""

                        msg_alerta = f"Divergência: Pacote de {cidade_pacote}{cep_info} não pertence ao motorista {mot_clean} (Cidades vinculadas: {cidades_display})!"

                        print(f"[!] [Anjun API] DIVERGÊNCIA BLINDADA (Atribuindo a {mot_clean})! {msg_alerta}")

                        mot_retorno_div = cidades_display

                        msg_divergente = msg_alerta

                        eh_divergente = True



    # 4. ATRIBUIÇÃO AO ENTREGADOR (Aba 3)

    mot_nome_final = motorista

    if mot_clean and mot_clean not in ["---", "Apenas Entrada (Sem Atribuição)"]:

        da_obj = resolver_motorista_anjun_api(mot_clean)

        if not da_obj:

            return False, f"Motorista '{mot_clean}' não localizado na lista de DAs da Anjun", "", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote

            

        da_id = da_obj["id"]

        da_username = da_obj["username"]

        mot_nome_final = da_username

        

        wb_lote = order_num_scan or order_num_ql or codigo_limpo

        payload_assign = {

            "waybillNumber": codigo_limpo,

            "dispatchUserId": da_id,

            "dispatchUserName": da_username

        }

        ok_da, msg_da, res_da = executar_post_anjun("/api/wms/console/v1/storage/dispatch/taskAllocation", payload_assign)

        if not ok_da:

            msg_da_low = (msg_da or "").lower()

            if any(k in msg_da_low for k in ["sucesso", "success", "já atribuído", "já atribuido", "atribuído", "atribuido", "já alocado", "ja alocado", "já vinculado", "ja vinculado", "aguardando entrega", "não repita", "nao repita", "duplicad", "repetid", "já escaneado", "ja escaneado", "já bipado", "ja bipado"]):

                print(f"[*] [Anjun API] Pacote {codigo_limpo} confirmado na atribuição ({msg_da}) para {da_username}.")

                ok_da = True

            elif any(k in msg_da_low for k in ["sessão", "sessao", "token", "401", "unauthorized", "login"]):

                cache_sessao_anjun["token"] = None

                return "aguardando_login", f"Sessão expirada: {msg_da}", "", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote

            else:

                # Retentativa rápida caso o servidor da Anjun tenha levado alguns milissegundos para processar a Entrada

                time.sleep(0.25)

                payload_retry = {

                    "waybillNumber": wb_lote,

                    "dispatchUserId": da_id,

                    "dispatchUserName": da_username

                }

                ok_da, msg_da, res_da = executar_post_anjun("/api/wms/console/v1/storage/dispatch/taskAllocation", payload_retry)

                msg_da_low = (msg_da or "").lower()

                if ok_da or any(k in msg_da_low for k in ["sucesso", "success", "já atribuído", "já atribuido", "atribuído", "atribuido", "já alocado", "ja alocado", "já vinculado", "ja vinculado", "aguardando entrega", "não repita", "nao repita", "duplicad", "repetid", "já escaneado", "ja escaneado", "já bipado", "ja bipado"]):

                    ok_da = True

                else:

                    return False, f"Atribuição Anjun: {msg_da}", "", cidade_pacote, cep_pacote, destinatario_pacote, endereco_pacote

                

        # Registra pacote pendente no lote do motorista (usando o waybill oficial AJ... quando disponível)

        adicionar_pacote_lote_anjun(da_username, wb_lote)

        if wb_lote != codigo_limpo:

            try:

                conn_rm = conectar_banco()

                conn_rm.execute("DELETE FROM lote_pendente_anjun WHERE UPPER(waybill) = UPPER(?)", (codigo_limpo,))

                conn_rm.commit()

                conn_rm.close()

            except Exception:

                pass

        

    cidade_retorno_anjun = cidade_pacote if cidade_pacote else "Cidade Não Informada (Conferir)"

    if 'eh_divergente' in locals() and eh_divergente:

        return "divergente", msg_divergente, mot_retorno_div, cidade_retorno_anjun, cep_pacote, destinatario_pacote, endereco_pacote

    return True, "Pacote processado com sucesso!", mot_nome_final, cidade_retorno_anjun, cep_pacote, destinatario_pacote, endereco_pacote



def finalizar_lote_anjun_api(motorista, reload_tab=True):

    """

    Finaliza o lote acumulado de pacotes do motorista na Anjun,

    gerando um único grupo/tarefa no aplicativo do entregador.

    Chama printList -> sortByAddrList -> printListTaskNumber -> page.

    Nunca clica no botão físico da tela web (pois a tabela web mistura todos os motoristas do galpão).

    """

    global driver, aba_atribuicao_anjun, mapa_motorista_sessao_anjun, ultimo_erro_finalizacao_anjun

    ultimo_erro_finalizacao_anjun = ""

    mot_clean = str(motorista).strip() if motorista else ""

    if not mot_clean:

        return False, 0



    norm_alvo = remover_acentos(mot_clean.lower()).replace('-', '').replace('_', '').replace(' ', '')



    # 1. Consulta os lotes abertos diretamente nas sessões Anjun conhecidas para descobrir a conta exata,

    #    o dispatchUserId exato e a lista real de waybills abertos deste motorista no site!

    sessoes = obter_todas_sessoes_anjun_conhecidas()

    token_usado = None

    sess_usada = None

    da_username = None

    da_id = None

    pacotes_site = []

    alguma_sessao_ok = False



    for sess in sessoes:

        tk = sess.get("token")

        if not tk:

            continue

        ok_pg, _, res_pg = executar_post_anjun("/admin/taskAllocation/page", {

            "finalScanOperationType": 3,

            "pageNo": 1,

            "pageSize": 500

        }, token_override=tk)

        if not ok_pg or not isinstance(res_pg, dict):

            continue

        alguma_sessao_ok = True

        records = extrair_registros_pagina_anjun(res_pg)

        wbs_encontrados = []

        uname_encontrado = None

        uid_encontrado = None

        for r in records:

            if not isinstance(r, dict):

                continue

            r_mot = str(r.get("dispatchUserName") or "").strip()

            r_wb = str(r.get("waybillNumber") or "").strip()

            r_uid = r.get("dispatchUserId")

            if not r_mot or not r_wb:

                continue

            norm_r = remover_acentos(r_mot.lower()).replace('-', '').replace('_', '').replace(' ', '')

            if norm_r == norm_alvo or norm_alvo in norm_r or norm_r in norm_alvo:

                wbs_encontrados.append(r_wb)

                uname_encontrado = r_mot

                if r_uid:

                    uid_encontrado = r_uid

        if wbs_encontrados:

            token_usado = tk

            sess_usada = sess

            da_username = uname_encontrado

            da_id = uid_encontrado

            pacotes_site = list(dict.fromkeys(wbs_encontrados))

            break



    # 2. Fallback para cache/banco local se não veio da listagem page

    if not token_usado:

        info_map = mapa_motorista_sessao_anjun.get(remover_acentos(mot_clean.lower()))

        if info_map:

            token_usado = info_map.get("token")

            da_id = da_id or info_map.get("dispatchUserId")

            da_username = da_username or info_map.get("dispatchUserName")

    if not sess_usada:

        sess_usada = atualizar_sessao_anjun()

    if not token_usado and sess_usada:

        token_usado = sess_usada.get("token")



    if not da_id or not da_username:

        da_obj = resolver_motorista_anjun_api(mot_clean)

        if da_obj:

            da_username = da_username or da_obj.get("username")

            da_id = da_id or da_obj.get("id")



    da_username = da_username or mot_clean

    pacotes_banco = obter_pacotes_lote_anjun(da_username)

    if not pacotes_banco and mot_clean != da_username:

        pacotes_banco = obter_pacotes_lote_anjun(mot_clean)



    # Se a API da Anjun respondeu normalmente e já não há mais nenhum pacote em aberto no site para este motorista:

    if alguma_sessao_ok and not pacotes_site and not pacotes_banco:

        limpar_pacotes_lote_anjun(da_username)

        if mot_clean != da_username:

            limpar_pacotes_lote_anjun(mot_clean)

        zerar_contagem_motorista_memoria(da_username)

        if mot_clean != da_username:

            zerar_contagem_motorista_memoria(mot_clean)

        print(f"[+] [Anjun API] Lote de {da_username} já se encontra finalizado no site da Anjun.")

        return True, 0



    # Une os pacotes abertos no site Anjun com os pacotes registrados no banco local (garante que nenhum pacote fique de fora)

    pacotes_lote = list(dict.fromkeys((pacotes_site or []) + (pacotes_banco or [])))

    print(f"[*] [Anjun API] Finalizando lote de {da_username} (ID: {da_id}, {len(pacotes_lote)} pacotes)...")



    if not token_usado or not pacotes_lote or not da_username or not da_id:

        if not token_usado:

            ultimo_erro_finalizacao_anjun = "Sessão/conta Anjun não conectada no navegador."

        elif not da_id:

            ultimo_erro_finalizacao_anjun = f"Entregador '{da_username}' não localizado na Anjun."

        elif not pacotes_lote:

            ultimo_erro_finalizacao_anjun = "Nenhum pacote em aberto para este motorista."

        print(f"[!] [Anjun API] Dados insuficientes para finalizar lote de {da_username}: token={bool(token_usado)}, pacotes={len(pacotes_lote)}, da_id={da_id}")

        return False, 0



    sucesso_api = False

    try:

        # Etapa 1: printList filtrando exclusivamente pelos pacotes deste motorista

        ok_pl, msg_pl, res_pl = executar_post_anjun("/admin/taskAllocation/printList", {

            "dispatchUserName": da_username,

            "waybillNumberList": pacotes_lote

        }, token_override=token_usado)

        vo_list = []

        d_pl = {}

        if ok_pl and isinstance(res_pl, dict):

            d_pl = res_pl.get("data") or {}

            if isinstance(d_pl, dict):

                vo_list = d_pl.get("voList", []) or []

            elif isinstance(d_pl, list):

                vo_list = d_pl

                d_pl = {}



        # Garante que vo_list contenha apenas pacotes deste motorista / lote

        set_lote = set(str(x).strip() for x in pacotes_lote)

        if vo_list and isinstance(vo_list, list):

            vo_filtrado = [

                item for item in vo_list

                if not isinstance(item, dict) or str(item.get("waybillNumber") or "").strip() in set_lote

            ]

            if vo_filtrado:

                vo_list = vo_filtrado



        # Etapa 2: sortByAddrList

        sorted_vo = vo_list

        site_lng = (d_pl.get("siteLng") if isinstance(d_pl, dict) else None) or sess_usada.get("siteLng", -48.9104678)

        site_lat = (d_pl.get("siteLat") if isinstance(d_pl, dict) else None) or sess_usada.get("siteLat", -23.1069575)

        if vo_list and isinstance(vo_list, list):

            try:

                ok_sort, _, res_sort = executar_post_anjun("/admin/pm/address/v1/sortByAddrList", {

                    "sortLng": site_lng,

                    "sortLat": site_lat,

                    "voList": vo_list

                }, token_override=token_usado)

                if ok_sort and isinstance(res_sort, dict):

                    d_sort = res_sort.get("data")

                    if isinstance(d_sort, list):

                        sorted_vo = d_sort

                    elif isinstance(d_sort, dict) and "voList" in d_sort:

                        sorted_vo = d_sort.get("voList", [])

            except Exception:

                sorted_vo = vo_list



        # Etapa 3: printListTaskNumber (dividido em tarefas de no maximo 200 pacotes, regra oficial da Anjun)

        from datetime import datetime

        tamanho_max_tarefa = 200
        chunks_wbs = [pacotes_lote[i:i + tamanho_max_tarefa] for i in range(0, len(pacotes_lote), tamanho_max_tarefa)]
        todos_chunks_ok = True
        msg_erro_chunk = ""

        for idx_chk, chunk in enumerate(chunks_wbs, 1):
            set_chunk = set(str(x).strip() for x in chunk)
            chunk_vo = [
                item for item in (sorted_vo or [])
                if not isinstance(item, dict) or str(item.get("waybillNumber") or "").strip() in set_chunk
            ]

            payload_task = {
                "dispatchUserName": da_username,
                "waybillNumberList": chunk,
                "dispatchUserId": da_id,
                "packageCount": len(chunk),
                "siteAddress": (d_pl.get("siteAddress") if isinstance(d_pl, dict) else None) or sess_usada.get("siteAddress", "R. Alferes José Ignatios, 26 - Parque Santa Elizabeth I, Avaré - SP, 18701-700"),
                "siteArea": (d_pl.get("siteArea") if isinstance(d_pl, dict) else None) or sess_usada.get("siteArea", "parquesantaelizabeth"),
                "siteCity": (d_pl.get("siteCity") if isinstance(d_pl, dict) else None) or sess_usada.get("siteCity", "Avaré"),
                "siteLat": site_lat,
                "siteLng": site_lng,
                "siteName": (d_pl.get("siteName") if isinstance(d_pl, dict) else None) or sess_usada.get("siteName", "SP-R-D093"),
                "siteState": (d_pl.get("siteState") if isinstance(d_pl, dict) else None) or sess_usada.get("siteState", "SP"),
                "siteStreet": (d_pl.get("siteStreet") if isinstance(d_pl, dict) else None) or sess_usada.get("siteStreet", "R. Alferes José Ignatios, 26"),
                "siteZipCode": (d_pl.get("siteZipCode") if isinstance(d_pl, dict) else None) or sess_usada.get("siteZipCode", "18701700"),
                "taskCreateTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "voList": chunk_vo
            }

            ok_tn, msg_tn, _ = executar_post_anjun(
                "/api/wms/console/v1/storage/dispatch/printListTaskNumber",
                payload_task,
                token_override=token_usado
            )

            if not ok_tn:
                todos_chunks_ok = False
                msg_erro_chunk = msg_tn or f"Erro no lote {idx_chk} da Anjun"
                print(f"[!] [Anjun API] printListTaskNumber falhou no lote {idx_chk}/{len(chunks_wbs)} para {da_username}: {msg_tn}")
                break
            else:
                print(f"[+] [Anjun API] Lote {idx_chk}/{len(chunks_wbs)} ({len(chunk)} pacotes) finalizado com sucesso para {da_username}!")

        # Etapa 4: page refresh
        executar_post_anjun("/admin/taskAllocation/page", {"finalScanOperationType": 3}, token_override=token_usado)

        if todos_chunks_ok:
            sucesso_api = True
            print(f"[+] [Anjun API] Total de {len(pacotes_lote)} pacotes em {len(chunks_wbs)} tarefa(s) finalizados com sucesso via API para {da_username}!")
        else:
            ultimo_erro_finalizacao_anjun = msg_erro_chunk or "Servidor Anjun recusou a finalização do lote."
            print(f"[!] [Anjun API] Finalização parcial ou com falha para {da_username}: {msg_erro_chunk}")

    except Exception as e_fin:

        ultimo_erro_finalizacao_anjun = str(e_fin)

        print(f"[!] [Anjun API] Erro na finalização via API: {e_fin}")



    if not sucesso_api:

        return False, 0



    # Sincroniza Aba 3 no navegador Chrome apenas se a API teve sucesso

    if reload_tab:

        try:

            if driver and aba_atribuicao_anjun and aba_atribuicao_anjun in driver.window_handles:

                driver.switch_to.window(aba_atribuicao_anjun)

                if "anjun" in driver.current_url.lower():

                    fechar_popups_finalizacao_anjun(driver)

                    time.sleep(0.3)

                    driver.execute_script("window.location.reload();")

                    time.sleep(0.8)

                    fechar_popups_finalizacao_anjun(driver)

        except Exception as e_aba:

            print(f"[Aviso] Sincronização de tela Anjun: {e_aba}")



    limpar_pacotes_lote_anjun(da_username)

    if mot_clean != da_username:

        limpar_pacotes_lote_anjun(mot_clean)



    return True, len(pacotes_lote)



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

            garantir_abas_anjun(driver)

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

    if not driver:

        return jsonify({"status": "erro", "mensagem": "Navegador não está ativo."}), 400

    garantir_abas_anjun(driver)

    if not aba_atribuicao_anjun:

        return jsonify({"status": "erro", "mensagem": "Aba de atribuição não está ativa."}), 400

        

    driver_lock.acquire()

    try:

        driver.switch_to.window(aba_atribuicao_anjun)

        sucesso_bip, contagem_site, erro_msg = bipar_pacote_atribuicao_anjun(driver, codigo)

        if not sucesso_bip:

            raise Exception(erro_msg or "Falha ao enviar bipe na Aba 3.")

            

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

    """

    Fecha popups de confirmação ('Deseja finalizar atribuição?') e 'Sequência de etiqueta' na Anjun.

    Executa de forma rápida e robusta em Javascript/DOM sem timeouts lentos de 5 segundos.

    """

    if not driver:

        return

        

    for _ in range(3):

        try:

            clicou = driver.execute_script("""

                var alterou = false;

                // 1. Clica no botão Confirmar ou OK do popup de confirmação do Element-UI

                var cBtns = document.querySelectorAll('.el-message-box__btns button, .el-dialog__footer button, .el-message-box button');

                for (var i = 0; i < cBtns.length; i++) {

                    var t = (cBtns[i].innerText || cBtns[i].textContent || '').trim().toLowerCase();

                    if (t === 'confirmar' || t === 'confirm' || t === 'ok' || t === 'sim' || t === '确定') {

                        try { cBtns[i].click(); alterou = true; } catch(e){}

                    }

                }

                

                // 2. Procura botão 'Fechar' em popups de sequência de etiquetas ou diálogos

                var dBtns = document.querySelectorAll('.el-dialog__headerbtn, .el-dialog button');

                for (var j = 0; j < dBtns.length; j++) {

                    var td = (dBtns[j].innerText || dBtns[j].textContent || '').trim().toLowerCase();

                    if (td.includes('fecha') || td.includes('close') || td.includes('deixar')) {

                        try { dBtns[j].click(); alterou = true; } catch(e){}

                    }

                }

                return alterou;

            """)

            if clicou:

                time.sleep(0.3)

            else:

                time.sleep(0.15)

        except Exception:

            pass



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

                try:

                    driver.execute_script("""

                        if (document.activeElement) { document.activeElement.blur(); }

                        var poppers = document.querySelectorAll('.el-select__popper, .el-popper');

                        for (var p = 0; p < poppers.length; p++) { poppers[p].style.display = 'none'; }

                    """)

                except Exception:

                    pass

                time.sleep(0.3)

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

                try:

                    driver.execute_script("""

                        if (document.activeElement) { document.activeElement.blur(); }

                        var poppers = document.querySelectorAll('.el-select__popper, .el-popper');

                        for (var p = 0; p < poppers.length; p++) { poppers[p].style.display = 'none'; }

                    """)

                except Exception:

                    pass

                time.sleep(0.3)

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

        cidades_list = []

        try:

            cursor.execute("SELECT DISTINCT cidade FROM motoristas_plataforma WHERE LOWER(motorista) = LOWER(?)", (motorista,))

            cidades_list = [row[0] for row in cursor.fetchall() if row[0]]

            if not cidades_list:

                cursor.execute("SELECT DISTINCT cidade FROM motoristas WHERE LOWER(motorista) = LOWER(?)", (motorista,))

                cidades_list = [row[0] for row in cursor.fetchall() if row[0]]

        except Exception:

            cidades_list = []

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



def zerar_contagem_motorista_memoria(motorista):

    """Zera a contagem de pacotes na memória para o motorista informado (case/accent/space insensitive)."""

    global contagem_motoristas, motorista_atribuicao_ativa, contagem_atribuicao_ativa

    if not motorista:

        return

    alvo_norm = remover_acentos(str(motorista).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

    for k in list(contagem_motoristas.keys()):

        norm_k = remover_acentos(str(k).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

        if norm_k == alvo_norm or alvo_norm in norm_k or norm_k in alvo_norm:

            contagem_motoristas[k] = 0

    contagem_motoristas[motorista] = 0

    if motorista_atribuicao_ativa:

        norm_at = remover_acentos(str(motorista_atribuicao_ativa).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

        if norm_at == alvo_norm or alvo_norm in norm_at or norm_at in alvo_norm:

            contagem_atribuicao_ativa = 0



@app.route('/atribuicao/cancelar-lote-anjun', methods=['POST'])

@requer_licenca_ativa

def atribuicao_cancelar_lote_anjun():

    """Cancela/limpa o lote aberto de um motorista (ou de todos) na Anjun sem emitir folha no site."""

    global motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas, waybills_cancelados_anjun

    dados = request.json or {}

    todos = bool(dados.get("todos"))

    motorista = dados.get("motorista")

    

    try:

        sincronizar_lotes_pendentes_anjun_api(forcar=True)

        if todos:

            conn = conectar_banco()

            c = conn.cursor()

            c.execute("SELECT waybill FROM lote_pendente_anjun")

            wbs = [r[0] for r in c.fetchall() if r and r[0]]

            for wb in wbs:

                waybills_cancelados_anjun.add(str(wb).strip())

            total_removidos = len(wbs)

            c.execute("DELETE FROM lote_pendente_anjun")

            conn.commit()

            conn.close()

            for k in list(contagem_motoristas.keys()):

                contagem_motoristas[k] = 0

            contagem_atribuicao_ativa = 0

            print(f"[+] [Anjun] Todos os lotes abertos foram cancelados/limpos ({total_removidos} pacotes).")

            return jsonify({"status": "sucesso", "removidos": total_removidos})

            

        if not motorista:

            return jsonify({"status": "erro", "mensagem": "Motorista não informado."}), 400

            

        mot_clean = str(motorista).strip()

        wbs_mot = obter_pacotes_lote_anjun(mot_clean)

        for wb in wbs_mot:

            waybills_cancelados_anjun.add(str(wb).strip())

        removidos = limpar_pacotes_lote_anjun(mot_clean)

        try:

            da_obj = resolver_motorista_anjun_api(mot_clean)

            if da_obj and da_obj.get("username"):

                for wb in obter_pacotes_lote_anjun(da_obj["username"]):

                    waybills_cancelados_anjun.add(str(wb).strip())

                removidos += limpar_pacotes_lote_anjun(da_obj["username"])

        except Exception:

            pass

            

        zerar_contagem_motorista_memoria(mot_clean)

        print(f"[+] [Anjun] Lote aberto de '{mot_clean}' cancelado/limpo ({removidos} pacotes).")

        return jsonify({"status": "sucesso", "motorista": mot_clean, "removidos": removidos})

    except Exception as e:

        print(f"[Erro] Falha ao cancelar lote Anjun: {e}")

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/atribuicao/finalizar-todos-anjun', methods=['POST'])

@requer_licenca_ativa

def atribuicao_finalizar_todos_anjun():

    """Finaliza de uma só vez todos os lotes abertos na Anjun via API Ultra-Rápida, separando motorista por motorista."""

    global driver, aba_atribuicao_anjun, motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas

    dados = request.json or {}

    lista_extra = dados.get("motoristas") or []

    

    try:

        sincronizar_lotes_pendentes_anjun_api(forcar=True)

        motoristas_banco = obter_motoristas_com_lote_aberto_anjun()

        todos_candidatos = []

        vistos = set()

        for m in list(motoristas_banco) + list(lista_extra):

            if not m:

                continue

            m_norm = remover_acentos(str(m).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

            if m_norm and m_norm not in vistos:

                vistos.add(m_norm)

                todos_candidatos.append(str(m).strip())

                

        if not todos_candidatos:

            return jsonify({"status": "sucesso", "total_motoristas": 0, "total_pacotes": 0, "motoristas": []})

            

        print(f"[*] [Anjun API] Finalizando TODOS os lotes abertos ({len(todos_candidatos)} motoristas): {todos_candidatos}")

        total_pacotes = 0

        motoristas_finalizados = []

        motoristas_falha = []

        

        for mot in todos_candidatos:

            ok_fin, qtd_fin = finalizar_lote_anjun_api(mot, reload_tab=False)

            if ok_fin:

                contagem_lote = qtd_fin if qtd_fin > 0 else contagem_motoristas.get(mot, 0)

                registrar_lote_finalizado(mot, contagem_lote, plataforma="anjun")

                limpar_pacotes_lote_anjun(mot)

                zerar_contagem_motorista_memoria(mot)

                total_pacotes += contagem_lote

                motoristas_finalizados.append({"motorista": mot, "quantidade": contagem_lote})

            else:

                motoristas_falha.append(mot)

                

        if not motoristas_falha:

            contagem_atribuicao_ativa = 0

            

        # Recarrega a Aba 3 no Chrome apenas uma única vez ao final se estiver na Anjun

        try:

            if driver and aba_atribuicao_anjun and aba_atribuicao_anjun in driver.window_handles:

                driver.switch_to.window(aba_atribuicao_anjun)

                if "anjun" in driver.current_url.lower():

                    fechar_popups_finalizacao_anjun(driver)

                    driver.execute_script("window.location.reload();")

                    time.sleep(0.8)

                    fechar_popups_finalizacao_anjun(driver)

        except Exception as e_aba:

            print(f"[Aviso] Sincronização de tela após finalizar todos Anjun: {e_aba}")

            

        if not motoristas_finalizados and motoristas_falha:

            return jsonify({

                "status": "erro",

                "mensagem": f"Não foi possível finalizar os lotes de: {', '.join(motoristas_falha)}. Verifique se a conta Anjun está logada no Chrome.",

                "falhas": motoristas_falha

            }), 400



        print(f"[+] [Anjun API] Finalização em massa concluída: {len(motoristas_finalizados)} motoristas, {total_pacotes} pacotes!")

        return jsonify({

            "status": "sucesso",

            "total_motoristas": len(motoristas_finalizados),

            "total_pacotes": total_pacotes,

            "motoristas": motoristas_finalizados,

            "falhas": motoristas_falha

        })

    except Exception as e:

        print(f"[Erro] Falha ao finalizar todos os lotes Anjun: {e}")

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/atribuicao/finalizar', methods=['POST'])

@requer_licenca_ativa

def atribuicao_finalizar():

    global driver, aba_atribuicao_anjun, motorista_atribuicao_ativa, contagem_atribuicao_ativa, contagem_motoristas, plataforma_ativa

    

    dados = request.json or {}

    motorista = dados.get("motorista") or motorista_atribuicao_ativa

    plat_req = (dados.get("plataforma") or plataforma_ativa or "anjun").strip().lower()

    

    # Se for iMile, finaliza 100% de forma local no banco de dados e limpa o contador

    if plat_req == 'imile':

        contagem_lote = 0

        if motorista:

            contagem_lote = contagem_motoristas.get(motorista, 0)

            if contagem_lote == 0:

                contagem_lote = contagem_atribuicao_ativa

            registrar_lote_finalizado(motorista, contagem_lote, plataforma="imile")

            zerar_contagem_motorista_memoria(motorista)

        

        motorista_atribuicao_ativa = None

        contagem_atribuicao_ativa = 0

        print(f"[+] Lote iMile finalizado localmente no banco para {motorista} (Qtd: {contagem_lote}).")

        return jsonify({"status": "sucesso"})



    # Se for Loggi, realiza a finalização do lote/grupo

    if plat_req == 'loggi':

        contagem_lote = 0

        nome_lote = motorista or grupo_loggi_ativo.get("cidade") or (", ".join(grupo_loggi_ativo.get("tags", [])) if grupo_loggi_ativo.get("tags") else "Loggi")

        if nome_lote:

            contagem_lote = contagem_motoristas.get(nome_lote, 0)

            if contagem_lote == 0:

                alvo_norm = remover_acentos(str(nome_lote).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

                for k, v in contagem_motoristas.items():

                    norm_k = remover_acentos(str(k).strip().lower()).replace('-', '').replace('_', '').replace(' ', '')

                    if (norm_k == alvo_norm or alvo_norm in norm_k or norm_k in alvo_norm) and v > 0:

                        contagem_lote = v

                        break

            if contagem_lote == 0:

                contagem_lote = contagem_atribuicao_ativa

            

            apenas_se_tiver = dados.get("apenas_se_tiver_pacotes", False)

            if not apenas_se_tiver or contagem_lote > 0:

                registrar_lote_finalizado(nome_lote, contagem_lote, plataforma="loggi")

            zerar_contagem_motorista_memoria(nome_lote)

            

        # Reseta o grupo ativo da Loggi para o próximo lote

        grupo_loggi_ativo["licensePlate"] = None

        grupo_loggi_ativo["tags"] = []

        grupo_loggi_ativo["cidade"] = None

        grupo_loggi_ativo["modo"] = "novo"

        

        motorista_atribuicao_ativa = None

        contagem_atribuicao_ativa = 0

        print(f"[+] Lote Loggi finalizado com sucesso para {nome_lote} (Qtd: {contagem_lote}).")

        return jsonify({"status": "sucesso", "quantidade": contagem_lote})



    # Se for Anjun, finaliza exclusivamente via API por motorista (NUNCA clica no botão físico da tela web para não misturar motoristas!)

    if plat_req == 'anjun' or not plat_req:

        sincronizar_lotes_pendentes_anjun_api(forcar=True)

        ok_fin, qtd_fin = finalizar_lote_anjun_api(motorista)

        if ok_fin:

            contagem_lote = qtd_fin if qtd_fin > 0 else contagem_motoristas.get(motorista, 0)

            if contagem_lote == 0:

                contagem_lote = contagem_atribuicao_ativa

            if motorista:

                registrar_lote_finalizado(motorista, contagem_lote, plataforma="anjun")

                limpar_pacotes_lote_anjun(motorista)

                zerar_contagem_motorista_memoria(motorista)

            if motorista and motorista_atribuicao_ativa and remover_acentos(motorista.strip().lower()) == remover_acentos(motorista_atribuicao_ativa.strip().lower()):

                motorista_atribuicao_ativa = None

                contagem_atribuicao_ativa = 0

            print(f"[+] [Anjun API] Lote finalizado com sucesso via API para {motorista} (Qtd: {contagem_lote})!")

            return jsonify({"status": "sucesso", "quantidade": contagem_lote})

        else:

            motivo = ultimo_erro_finalizacao_anjun or "Verifique se a conta Anjun correspondente está logada."

            return jsonify({

                "status": "erro",

                "mensagem": f"Não foi possível finalizar o lote de '{motorista}' na Anjun: {motivo}"

            }), 400



    return jsonify({"status": "erro", "mensagem": "Plataforma não reconhecida."}), 400



@app.route('/salvar-cidades', methods=['POST'])

def salvar_cidades():

    dados = request.json

    cidades = dados.get("cidades")

    

    if not isinstance(cidades, list):

        return jsonify({"status": "erro", "mensagem": "Formato de cidades inválido."}), 400

        

    cidades_limpas = [

        str(c).strip() for c in cidades

        if str(c or "").strip() and str(c).strip().lower() not in ('sem cidade', 'geral', 'imile', 'anjun')

    ]

    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("DELETE FROM cidades")

        for c in cidades_limpas:

            cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (c,))

        conn.commit()

        conn.close()

        

        # Sincroniza com o arquivo JSON legado para evitar perda de dados na inicialização

        try:

            with open(CONFIG_CIDADES, 'w', encoding='utf-8') as f:

                json.dump(cidades_limpas, f, indent=4, ensure_ascii=False)

            print("[Banco] config_cidades.json sincronizado com sucesso!")

        except Exception as e_json:

            print(f"[Aviso] Falha ao gravar no config_cidades.json: {str(e_json)}")



        try:

            excel_path = obter_caminho_excel()

            gerar_planilha_motoristas_excel(excel_path)

            if os.path.exists(excel_path):

                meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

                with open(meta_mtime_file, 'w') as f_meta:

                    f_meta.write(str(os.path.getmtime(excel_path)))

        except Exception as e_xl_cid:

            print(f"[Aviso] Falha ao atualizar planilha após salvar cidades: {e_xl_cid}")

            

        invalidar_cache_ram_cidades_motoristas()

        return jsonify({

            "status": "sucesso",

            "mensagem": "Lista de cidades salva com sucesso!",

            "cidades": carregar_cidades()

        })

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

    apelido = dados.get("apelido", "").strip()

    c_id = dados.get("conta_id", "").strip()

    

    if not p_id:

        return jsonify({"status": "erro", "mensagem": "ID da plataforma é obrigatório."}), 400

        

    todas_contas = carregar_contas_plataformas()

    if p_id not in todas_contas:

        todas_contas[p_id] = {"conta_ativa": "conta_1", "contas": []}

        

    contas_list = todas_contas[p_id].get("contas", [])

    alvo = None

    if c_id:

        for c in contas_list:

            if c.get("id") == c_id:

                alvo = c

                break

    if not alvo and contas_list:

        alvo = contas_list[0]

        

    if alvo:

        alvo["login_usuario"] = usuario

        alvo["login_senha"] = senha

        if apelido:

            alvo["apelido"] = apelido

    else:

        novo_id = f"conta_{int(time.time())}"

        contas_list.append({

            "id": novo_id,

            "apelido": apelido or (usuario or "Conta Principal"),

            "login_usuario": usuario,

            "login_senha": senha

        })

        todas_contas[p_id]["conta_ativa"] = novo_id

        

    todas_contas[p_id]["contas"] = contas_list

    salvar_contas_plataformas(todas_contas)

    return jsonify({"status": "sucesso", "mensagem": "Credenciais salvas com sucesso!", "dados": todas_contas})



@app.route('/plataformas/contas', methods=['GET'])

def rota_obter_contas_plataformas():

    try:

        contas_dict = carregar_contas_plataformas()

        return jsonify({

            "status": "sucesso",

            "dados": contas_dict,

            "plataforma_ativa": plataforma_ativa,

            "conta_ativa": conta_ativa

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/plataformas/salvar-conta', methods=['POST'])

def rota_salvar_conta_plataforma():

    try:

        dados = request.json or {}

        p_id = str(dados.get("plataforma") or "").strip().lower()

        c_id = str(dados.get("id") or "").strip()

        apelido = str(dados.get("apelido") or "").strip()

        usuario = str(dados.get("login_usuario") or "").strip()

        senha = str(dados.get("login_senha") or "").strip()

        ativar_agora = bool(dados.get("ativar_agora", False))

        

        if not p_id:

            return jsonify({"status": "erro", "mensagem": "Plataforma não informada."}), 400

            

        todas_contas = carregar_contas_plataformas()

        if p_id not in todas_contas:

            todas_contas[p_id] = {"conta_ativa": "", "contas": []}

            

        contas_list = todas_contas[p_id].get("contas", [])

        conta_encontrada = None

        if c_id:

            for c in contas_list:

                if c.get("id") == c_id:

                    conta_encontrada = c

                    break

                    

        if conta_encontrada:

            conta_encontrada["apelido"] = apelido or (usuario or conta_encontrada.get("apelido") or "Conta")

            conta_encontrada["login_usuario"] = usuario

            conta_encontrada["login_senha"] = senha

            c_id_final = conta_encontrada["id"]

        else:

            c_id_final = f"conta_{int(time.time())}"

            nova_conta = {

                "id": c_id_final,

                "apelido": apelido or (usuario or f"Conta {len(contas_list)+1}"),

                "login_usuario": usuario,

                "login_senha": senha

            }

            contas_list.append(nova_conta)

            

        if ativar_agora or not todas_contas[p_id].get("conta_ativa"):

            todas_contas[p_id]["conta_ativa"] = c_id_final

            

        todas_contas[p_id]["contas"] = contas_list

        salvar_contas_plataformas(todas_contas)

        

        if ativar_agora and plataforma_ativa == p_id:

            try:

                inicializar_selenium(p_id, c_id_final)

            except Exception as e_init:

                print(f"[Aviso] Falha ao alternar navegador para nova conta: {e_init}")

                

        return jsonify({

            "status": "sucesso", 

            "mensagem": "Conta salva com sucesso!", 

            "dados": todas_contas,

            "conta_id": c_id_final

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/plataformas/excluir-conta', methods=['POST'])

def rota_excluir_conta_plataforma():

    try:

        dados = request.json or {}

        p_id = str(dados.get("plataforma") or "").strip().lower()

        c_id = str(dados.get("id") or "").strip()

        

        if not p_id or not c_id:

            return jsonify({"status": "erro", "mensagem": "Plataforma e ID da conta são obrigatórios."}), 400

            

        todas_contas = carregar_contas_plataformas()

        if p_id not in todas_contas:

            return jsonify({"status": "erro", "mensagem": "Plataforma não encontrada."}), 404

            

        contas_list = todas_contas[p_id].get("contas", [])

        if len(contas_list) <= 1:

            return jsonify({"status": "erro", "mensagem": "Você não pode excluir a única conta cadastrada. Adicione outra antes de excluir esta."}), 400

            

        contas_filtradas = [c for c in contas_list if c.get("id") != c_id]

        todas_contas[p_id]["contas"] = contas_filtradas

        

        if todas_contas[p_id].get("conta_ativa") == c_id:

            todas_contas[p_id]["conta_ativa"] = contas_filtradas[0]["id"]

            

        salvar_contas_plataformas(todas_contas)

        return jsonify({

            "status": "sucesso", 

            "mensagem": "Conta excluída com sucesso!", 

            "dados": todas_contas

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/plataformas/selecionar-conta', methods=['POST'])

def rota_selecionar_conta_plataforma():

    try:

        dados = request.json or {}

        p_id = str(dados.get("plataforma") or "").strip().lower()

        c_id = str(dados.get("conta_id") or "").strip()

        

        if not p_id or not c_id:

            return jsonify({"status": "erro", "mensagem": "Plataforma e conta são obrigatórios."}), 400



        lic = validar_licenca()

        liberadas = [str(p).strip().lower() for p in (lic.get("plataformas_liberadas") or ["anjun", "imile", "loggi", "magalog"])]

        if p_id not in liberadas:

            return jsonify({"status": "erro", "mensagem": f"A empresa '{p_id.upper()}' não está liberada na licença contratada para esta máquina."}), 403

            

        todas_contas = carregar_contas_plataformas()

        if p_id in todas_contas:

            todas_contas[p_id]["conta_ativa"] = c_id

            salvar_contas_plataformas(todas_contas)

            

        inicializar_selenium(p_id, c_id)

        salvar_sessao_ativa(p_id, motorista_atribuicao_ativa, contagem_atribuicao_ativa, c_id)

        if p_id == 'anjun':

            fechar_avisos_todas_abas_anjun(driver)

            

        return jsonify({

            "status": "sucesso", 

            "mensagem": f"Conta ativada com sucesso para {p_id}!",

            "plataforma_ativa": p_id,

            "conta_ativa": c_id

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/deletar-plataforma', methods=['POST'])

def deletar_plataforma():

    dados = request.json

    p_id = dados.get("id", "").strip().lower()

    

    plataformas = carregar_plataformas()

    if p_id in plataformas:

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

    conta_id = dados.get("conta_id", "").strip() or None



    lic = validar_licenca()

    liberadas = [str(p).strip().lower() for p in (lic.get("plataformas_liberadas") or ["anjun", "imile", "loggi", "magalog"])]

    if p_id not in liberadas:

        return jsonify({"status": "erro", "mensagem": f"A empresa '{p_id.upper()}' não está liberada na licença contratada para esta máquina."}), 403

    

    try:

        inicializar_selenium(p_id, conta_id)

        salvar_sessao_ativa(p_id, motorista_atribuicao_ativa, contagem_atribuicao_ativa, conta_ativa)

        if p_id == 'anjun':

            fechar_avisos_todas_abas_anjun(driver)

        return jsonify({

            "status": "sucesso", 

            "mensagem": f"Browser inicializado para a plataforma {p_id}.",

            "plataforma_ativa": p_id,

            "conta_ativa": conta_ativa

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/salvar-motoristas', methods=['POST'])

def salvar_motoristas():

    dados = request.json or {}

    motoristas = dados.get("motoristas")

    plat_id = (dados.get("plataforma") or plataforma_ativa or "anjun").strip().lower()

    acao = (dados.get("acao") or "").strip().lower()



    def _eh_cidade_valida(c_str):

        return bool(c_str and str(c_str).strip().lower() not in ('sem cidade', 'geral', 'imile', 'anjun', ''))



    try:

        conn = conectar_banco()

        cursor = conn.cursor()



        # Limpa eventuais registros inválidos de "Sem Cidade" ou "Geral" no banco

        cursor.execute("DELETE FROM motoristas_plataforma WHERE LOWER(cidade) IN ('sem cidade', 'geral', 'imile', 'anjun', '')")

        cursor.execute("DELETE FROM motoristas WHERE LOWER(cidade) IN ('sem cidade', 'geral', 'imile', 'anjun', '')")



        cid_ativa, _ = obter_conta_ativa_plataforma(plat_id, dados.get("conta_id"))

        _, nomes_base_oficiais, nomes_outras_bases = obter_nomes_oficiais_base_ativa(plat_id, cid_ativa, forcar=False)



        if acao in ('adicionar', 'editar', 'deletar'):

            cid_alvo = (dados.get("cidade") or "").strip()

            mot_alvo = (dados.get("motorista") or "").strip()

            faixa_cep_alvo = normalizar_faixa_cep(dados.get("faixa_cep") or "")

            bairros_alvo = (dados.get("bairros") or "").strip()

            cid_antiga = (dados.get("cidade_antiga") or "").strip()

            mot_antigo = (dados.get("motorista_antigo") or "").strip()



            if acao == 'deletar':

                if cid_alvo and mot_alvo:

                    cursor.execute(

                        "DELETE FROM motoristas_plataforma WHERE LOWER(plataforma) = LOWER(?) AND LOWER(cidade) = LOWER(?) AND LOWER(motorista) = LOWER(?)",

                        (plat_id, cid_alvo, mot_alvo)

                    )

                    if plat_id == 'anjun':

                        cursor.execute(

                            "DELETE FROM motoristas WHERE LOWER(cidade) = LOWER(?) AND LOWER(motorista) = LOWER(?)",

                            (cid_alvo, mot_alvo)

                        )

            else:

                if acao == 'editar' and cid_antiga and mot_antigo:

                    cursor.execute(

                        "DELETE FROM motoristas_plataforma WHERE LOWER(plataforma) = LOWER(?) AND LOWER(cidade) = LOWER(?) AND LOWER(motorista) = LOWER(?)",

                        (plat_id, cid_antiga, mot_antigo)

                    )

                    if plat_id == 'anjun':

                        cursor.execute(

                            "DELETE FROM motoristas WHERE LOWER(cidade) = LOWER(?) AND LOWER(motorista) = LOWER(?)",

                            (cid_antiga, mot_antigo)

                        )

                if _eh_cidade_valida(cid_alvo) and mot_alvo:

                    cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid_alvo,))

                    cursor.execute(

                        "INSERT OR REPLACE INTO motoristas_plataforma (cidade, plataforma, motorista, faixa_cep, bairros) VALUES (?, ?, ?, ?, ?)",

                        (cid_alvo, plat_id, mot_alvo, faixa_cep_alvo, bairros_alvo)

                    )

                    if plat_id == 'anjun':

                        cursor.execute(

                            "INSERT OR IGNORE INTO motoristas (cidade, motorista) VALUES (?, ?)",

                            (cid_alvo, mot_alvo)

                        )

                    # Garante que o motorista pertença à base ativa

                    if plat_id in ('anjun', 'imile') and cid_ativa:

                        atuais_base = list(nomes_base_oficiais or [])

                        set_norm = {_normalizar_nome_base_comp(x) for x in atuais_base if x}

                        mn = _normalizar_nome_base_comp(mot_alvo)

                        if mn and mn not in set_norm:

                            atuais_base.append(mot_alvo)

                        if atuais_base:

                            salvar_motoristas_da_base(plat_id, cid_ativa, atuais_base)

        else:

            lista_mapeamentos = []

            if isinstance(motoristas, list):

                for item in motoristas:

                    if isinstance(item, dict):

                        c = (item.get("cidade") or "").strip()

                        m = (item.get("motorista") or "").strip()

                        f_cep = normalizar_faixa_cep(item.get("faixa_cep") or "")

                        b_val = (item.get("bairros") or "").strip()

                        if _eh_cidade_valida(c) and m:

                            lista_mapeamentos.append((c, m, f_cep, b_val))

            elif isinstance(motoristas, dict):

                for c, m in motoristas.items():

                    c_clean = str(c).strip()

                    if not _eh_cidade_valida(c_clean):

                        continue

                    if isinstance(m, list):

                        for sub_m in m:

                            sub_m_clean = str(sub_m).strip()

                            if sub_m_clean:

                                lista_mapeamentos.append((c_clean, sub_m_clean, ""))

                    else:

                        m_clean = str(m).strip()

                        if m_clean:

                            lista_mapeamentos.append((c_clean, m_clean, ""))

            else:

                conn.close()

                return jsonify({"status": "erro", "mensagem": "Formato de motoristas inválido."}), 400



            # Preserva mapeamentos que pertencem a outras bases (e preserva faixa_cep existente se não veio no payload)

            cursor.execute("SELECT cidade, motorista, COALESCE(faixa_cep, ''), COALESCE(bairros, '') FROM motoristas_plataforma WHERE LOWER(plataforma) = LOWER(?)", (plat_id,))

            existentes = cursor.fetchall()

            preservados_outras_bases = []

            cep_existente_map = {(c_ex.strip().lower(), m_ex.strip().lower()): ((f_ex or "").strip(), (b_ex or "").strip()) for c_ex, m_ex, f_ex, b_ex in existentes if c_ex and m_ex}

            if plat_id in ('anjun', 'imile') and (nomes_base_oficiais or nomes_outras_bases):

                for c_ex, m_ex, f_ex, b_ex in existentes:

                    if _eh_cidade_valida(c_ex) and m_ex and not motorista_pertence_a_base_ativa(m_ex, nomes_base_oficiais, nomes_outras_bases, plat_id):

                        preservados_outras_bases.append((c_ex, m_ex, (f_ex or "").strip(), (b_ex or "").strip()))



            lista_mapeamentos_final = []

            for item_m in lista_mapeamentos:

                cid_i = item_m[0]

                mot_i = item_m[1]

                f_cep_i = item_m[2] if len(item_m) > 2 else ""

                b_val_i = item_m[3] if len(item_m) > 3 else ""

                if not f_cep_i or not b_val_i:

                    f_old, b_old = cep_existente_map.get((cid_i.strip().lower(), mot_i.strip().lower()), ("", ""))

                    if not f_cep_i: f_cep_i = f_old

                    if not b_val_i: b_val_i = b_old

                lista_mapeamentos_final.append((cid_i, mot_i, f_cep_i, b_val_i))



            todos_para_salvar = lista_mapeamentos_final + preservados_outras_bases



            cursor.execute("DELETE FROM motoristas_plataforma WHERE LOWER(plataforma) = LOWER(?)", (plat_id,))

            for item_save in todos_para_salvar:

                cid = item_save[0]

                mot = item_save[1]

                f_cep = item_save[2] if len(item_save) > 2 else ""

                b_val = item_save[3] if len(item_save) > 3 else ""

                if _eh_cidade_valida(cid):

                    cursor.execute("INSERT OR IGNORE INTO cidades (cidade) VALUES (?)", (cid,))

                cursor.execute("INSERT OR REPLACE INTO motoristas_plataforma (cidade, plataforma, motorista, faixa_cep, bairros) VALUES (?, ?, ?, ?, ?)", (cid, plat_id, mot, f_cep, b_val))



            if plat_id == 'anjun':

                cursor.execute("DELETE FROM motoristas")

                for cid, mot, _ in todos_para_salvar:

                    cursor.execute("INSERT OR IGNORE INTO motoristas (cidade, motorista) VALUES (?, ?)", (cid, mot))



            if plat_id in ('anjun', 'imile') and cid_ativa and lista_mapeamentos_final:

                atuais_base = list(nomes_base_oficiais or [])

                set_norm = {_normalizar_nome_base_comp(x) for x in atuais_base if x}

                for _, mot_item, _ in lista_mapeamentos_final:

                    mn = _normalizar_nome_base_comp(mot_item)

                    if mn and mn not in set_norm:

                        set_norm.add(mn)

                        atuais_base.append(mot_item)

                if atuais_base:

                    salvar_motoristas_da_base(plat_id, cid_ativa, atuais_base)



        conn.commit()

        conn.close()

        

        # Sincroniza com o arquivo JSON no novo formato multi-plataforma com suporte a múltiplos motoristas e faixa_cep

        try:

            conn_json = conectar_banco()

            cursor_json = conn_json.cursor()

            cursor_json.execute("""

                SELECT cidade, plataforma, motorista, COALESCE(faixa_cep, ''), COALESCE(bairros, '')

                FROM motoristas_plataforma

                WHERE LOWER(cidade) NOT IN ('sem cidade', 'geral', 'imile', 'anjun', '')

                ORDER BY plataforma, cidade, motorista

            """)

            rows_json = cursor_json.fetchall()

            conn_json.close()

            

            mapeamento_completo = {}

            for r_json in rows_json:

                cid = r_json[0]

                plat = r_json[1]

                mot = r_json[2]

                f_cep = (r_json[3] or "").strip() if len(r_json) > 3 else ""

                b_val = (r_json[4] or "").strip() if len(r_json) > 4 else ""

                if plat not in mapeamento_completo:

                    mapeamento_completo[plat] = []

                item_json = {"cidade": cid, "motorista": mot}

                if f_cep:

                    item_json["faixa_cep"] = f_cep

                if b_val:

                    item_json["bairros"] = b_val

                mapeamento_completo[plat].append(item_json)

                

            with open(CONFIG_MOTORISTAS, 'w', encoding='utf-8') as f:

                json.dump(mapeamento_completo, f, indent=4, ensure_ascii=False)

            print("[Banco] config_motoristas.json sincronizado com sucesso!")

        except Exception as e_json:

            print(f"[Aviso] Falha ao gravar no config_motoristas.json: {str(e_json)}")



        # Atualiza a planilha Excel e o .excel_sync_meta para não sobrescrever alterações feitas na interface

        try:

            excel_path = obter_caminho_excel()

            gerar_planilha_motoristas_excel(excel_path)

            if os.path.exists(excel_path):

                meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

                with open(meta_mtime_file, 'w') as f_meta:

                    f_meta.write(str(os.path.getmtime(excel_path)))

        except Exception as e_xl:

            print(f"[Aviso] Falha ao atualizar planilha após salvar motorista: {e_xl}")

            

        invalidar_cache_ram_cidades_motoristas()

        return jsonify({

            "status": "sucesso",

            "mensagem": f"Mapeamento de motoristas para a plataforma '{plat_id}' salvo com sucesso!",

            "motoristas": carregar_motoristas(plat_id, conta_id=cid_ativa),

            "cidades": carregar_cidades()

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/motoristas/status-excel', methods=['GET'])

def rota_status_motoristas_excel():

    try:

        excel_path = obter_caminho_excel()

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



@app.route('/motoristas/lista-sistema', methods=['GET'])

def rota_motoristas_lista_sistema():

    try:

        conn = conectar_banco()

        cursor = conn.cursor()

        cursor.execute("SELECT cidade, motorista, plataforma FROM motoristas_plataforma WHERE cidade NOT IN ('iMile', 'Anjun')")

        rows = cursor.fetchall()

        conn.close()

        

        map_cidades = {}

        for cid, mot, plat in rows:

            chave = ((plat or '').lower(), mot.strip().lower())

            if chave not in map_cidades:

                map_cidades[chave] = []

            map_cidades[chave].append(cid)



        # iMile

        todos_imile = []

        try:

            fn_im = globals().get('carregar_motoristas_imile_api')

            if fn_im:

                lista_im, _ = fn_im()

                todos_imile = [m.get("daName", "").strip() for m in lista_im if m.get("daName")]

        except Exception:

            pass



        # Anjun

        todos_anjun = []

        try:

            fn_an = globals().get('carregar_motoristas_anjun_api')

            if fn_an:

                lista_an, _ = fn_an()

                todos_anjun = [m.get("username", "").strip() for m in lista_an if m.get("username")]

        except Exception:

            pass



        # Complementa com Motoristas.xlsx

        path_xlsx = os.path.join(BASE_DIR, "Motoristas.xlsx")

        if os.path.exists(path_xlsx):

            try:

                import openpyxl

                wb_ref = openpyxl.load_workbook(path_xlsx, data_only=True)

                ws_ref = wb_ref.active

                for r in list(ws_ref.iter_rows(values_only=True))[1:]:

                    if r and len(r) > 0 and r[0] and str(r[0]).strip() and str(r[0]).strip() not in todos_imile:

                        todos_imile.append(str(r[0]).strip())

                    if r and len(r) > 2 and r[2] and str(r[2]).strip() and str(r[2]).strip() not in todos_anjun:

                        todos_anjun.append(str(r[2]).strip())

                wb_ref.close()

            except Exception:

                pass



        todos_imile = sorted(list(set(todos_imile)), key=lambda s: s.lower())

        todos_anjun = sorted(list(set(todos_anjun)), key=lambda s: s.lower())



        resp_imile = []

        for mot in todos_imile:

            cidades = map_cidades.get(('imile', mot.lower()), [])

            resp_imile.append({

                "motorista": mot,

                "cidades": cidades,

                "tem_cidade": len(cidades) > 0

            })



        resp_anjun = []

        for mot in todos_anjun:

            cidades = map_cidades.get(('anjun', mot.lower()), [])

            resp_anjun.append({

                "motorista": mot,

                "cidades": cidades,

                "tem_cidade": len(cidades) > 0

            })



        return jsonify({

            "status": "sucesso",

            "imile": resp_imile,

            "anjun": resp_anjun,

            "total_imile": len(resp_imile),

            "total_anjun": len(resp_anjun)

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500





@app.route('/motoristas/sincronizar-excel', methods=['POST'])

def rota_sincronizar_motoristas_excel():

    try:

        excel_path = obter_caminho_excel()

        ok, c_qtd, m_qtd, msg = sincronizar_motoristas_excel(excel_path)

        if ok:

            try:

                mtime = os.path.getmtime(excel_path)

                meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

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

            

        excel_path = obter_caminho_excel()

        file.save(excel_path)

        

        ok, c_qtd, m_qtd, msg = sincronizar_motoristas_excel(excel_path)

        if ok:

            try:

                mtime = os.path.getmtime(excel_path)

                meta_mtime_file = os.path.join(BASE_DIR, '.excel_sync_meta')

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



@app.route('/motoristas/abrir-excel', methods=['POST'])

def rota_abrir_motoristas_excel():

    try:

        excel_path = obter_caminho_excel()

        if not os.path.exists(excel_path):

            gerar_planilha_motoristas_excel(excel_path)

            

        os.startfile(excel_path)

        return jsonify({"status": "sucesso", "mensagem": "Planilha Excel aberta no computador."})

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": f"Erro ao abrir planilha: {str(e)}"}), 500



@app.route('/motoristas/abrir-pasta-excel', methods=['POST'])

def rota_abrir_pasta_motoristas_excel():

    try:

        excel_path = obter_caminho_excel()

        if not os.path.exists(excel_path):

            gerar_planilha_motoristas_excel(excel_path)

        pasta = os.path.dirname(os.path.abspath(excel_path))

        if os.name == 'nt' and os.path.exists(excel_path):

            import subprocess

            subprocess.Popen(f'explorer /select,"{os.path.abspath(excel_path)}"', env=obter_env_limpo_pyinstaller())

        else:

            os.startfile(pasta)

        return jsonify({"status": "sucesso", "mensagem": "Pasta da planilha aberta no Windows Explorer."})

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": f"Erro ao abrir pasta: {str(e)}"}), 500



@app.route('/imile/motoristas/sincronizar', methods=['GET', 'POST'])

def sincronizar_motoristas_imile_route():

    try:

        lista, _ = carregar_motoristas_imile_api(forcar=True)

        return jsonify({

            "status": "sucesso",

            "total": len(lista),

            "motoristas": lista,

            "mensagem": f"{len(lista)} entregadores sincronizados com sucesso direto da iMile!"

        }), 200

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/anjun/motoristas/sincronizar', methods=['GET', 'POST'])

def sincronizar_motoristas_anjun_route():

    try:

        lista, _ = carregar_motoristas_anjun_api(forcar=True)

        return jsonify({

            "status": "sucesso",

            "total": len(lista),

            "motoristas": lista,

            "mensagem": f"{len(lista)} entregadores sincronizados com sucesso direto da Anjun!"

        }), 200

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/loggi/grupos', methods=['GET'])

def loggi_grupos_route():

    try:

        grupos = loggi_listar_grupos_api()

        return jsonify({

            "status": "sucesso",

            "grupos": grupos,

            "grupo_ativo": grupo_loggi_ativo

        }), 200

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/loggi/grupo-ativo', methods=['GET'])

def loggi_grupo_ativo_route():

    return jsonify({

        "status": "sucesso",

        "grupo_ativo": grupo_loggi_ativo

    }), 200



@app.route('/loggi/definir-grupo', methods=['POST'])

def loggi_definir_grupo_route():

    global grupo_loggi_ativo

    dados = request.get_json(silent=True) or {}

    modo = dados.get("modo", "novo")

    grupo_loggi_ativo["modo"] = modo

    if modo == "existente":

        if dados.get("licensePlate"):

            grupo_loggi_ativo["licensePlate"] = dados.get("licensePlate")

        if dados.get("tags") is not None:

            grupo_loggi_ativo["tags"] = dados.get("tags", [])

        if dados.get("cidade"):

            grupo_loggi_ativo["cidade"] = dados.get("cidade")

        if dados.get("cidades"):

            grupo_loggi_ativo["cidades_autorizadas"] = dados.get("cidades")

    else:

        forcar_reset = dados.get("reset", False)

        nova_cidade = dados.get("cidade_principal") or dados.get("cidade")

        cid_atual = grupo_loggi_ativo.get("cidade")

        mudou_cidade = bool(nova_cidade and cid_atual and not cidades_sao_iguais(nova_cidade, cid_atual))

        if forcar_reset or mudou_cidade or not nova_cidade:

            grupo_loggi_ativo["licensePlate"] = None

            grupo_loggi_ativo["tags"] = []

            grupo_loggi_ativo["cidade"] = nova_cidade

            grupo_loggi_ativo["quantity"] = 0

            if nova_cidade:

                from datetime import datetime

                dia_mes = datetime.now().strftime("%d-%m")

                try:

                    grupos_abertos = loggi_listar_grupos_api()

                    for g in grupos_abertos:

                        tags_list = g.get("tags", [])

                        tags_str = " ".join(tags_list)

                        if (any(cidades_sao_iguais(nova_cidade, t) for t in tags_list) or cidades_sao_iguais(nova_cidade, tags_str)) and dia_mes in tags_str:

                            grupo_loggi_ativo["licensePlate"] = g["licensePlate"]

                            grupo_loggi_ativo["tags"] = tags_list

                            grupo_loggi_ativo["cidade"] = nova_cidade

                            grupo_loggi_ativo["quantity"] = g.get("quantity", 0)

                            print(f"[+] [Loggi API] Cidade '{nova_cidade}' vinculada ao grupo existente de HOJE: {g['licensePlate']} ({tags_str}) com {g.get('quantity', 0)} pacotes")

                            break

                except Exception as e_lk:

                    print(f"[Aviso] Falha ao consultar grupo de hoje para {nova_cidade}: {e_lk}")

        else:

            if not grupo_loggi_ativo.get("licensePlate"):

                grupo_loggi_ativo["cidade"] = nova_cidade

                if nova_cidade:

                    from datetime import datetime

                    dia_mes = datetime.now().strftime("%d-%m")

                    try:

                        grupos_abertos = loggi_listar_grupos_api()

                        for g in grupos_abertos:

                            tags_list = g.get("tags", [])

                            tags_str = " ".join(tags_list)

                            if (any(cidades_sao_iguais(nova_cidade, t) for t in tags_list) or cidades_sao_iguais(nova_cidade, tags_str)) and dia_mes in tags_str:

                                grupo_loggi_ativo["licensePlate"] = g["licensePlate"]

                                grupo_loggi_ativo["tags"] = tags_list

                                grupo_loggi_ativo["cidade"] = nova_cidade

                                grupo_loggi_ativo["quantity"] = g.get("quantity", 0)

                                print(f"[+] [Loggi API] Cidade '{nova_cidade}' vinculada ao grupo existente de HOJE: {g['licensePlate']} ({tags_str}) com {g.get('quantity', 0)} pacotes")

                                break

                    except Exception:

                        pass

    print(f"[+] [Loggi API] Grupo ativo atualizado: Modo '{modo}' | Placa: {grupo_loggi_ativo.get('licensePlate')} | Tags: {grupo_loggi_ativo.get('tags')} | Cidade Base: {grupo_loggi_ativo.get('cidade')}")

    return jsonify({"status": "sucesso", "grupo_ativo": grupo_loggi_ativo}), 200



@app.route('/loggi/criar-grupo', methods=['POST'])

def loggi_criar_grupo_route():

    dados = request.get_json(silent=True) or {}

    cidade = dados.get("cidade", "Geral")

    motorista = dados.get("motorista")

    forcar = dados.get("forcar", True)

    try:

        nova_placa, tag_nome = loggi_criar_novo_grupo_api(cidade, motorista=motorista, forcar_novo=forcar)

        return jsonify({

            "status": "sucesso",

            "licensePlate": nova_placa,

            "tag": tag_nome,

            "grupo_ativo": grupo_loggi_ativo

        }), 200

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500





@app.route('/reiniciar-sistema', methods=['POST'])

def rota_reiniciar_sistema():

    print("\n" + "=" * 60)

    print(" [*] COMANDO DE REINICIALIZAÇÃO DO SERVIDOR (CMD) RECEBIDO DO PAINEL!")

    print("=" * 60)



    # 1. Salva a sessão ativa antes de reiniciar (plataforma, motorista, contagem e conta_id)

    dados = request.get_json(silent=True) or {}

    plat_req = dados.get("plataforma") or plataforma_ativa

    mot_req = dados.get("motorista") or motorista_atribuicao_ativa

    cont_req = dados.get("contagem", contagem_atribuicao_ativa)

    conta_req = dados.get("conta_id") or conta_ativa

    salvar_sessao_ativa(plat_req, mot_req, cont_req, conta_req)



    def executar_reinicio():

        time.sleep(0.6)  # Aguarda envio da resposta HTTP ao navegador

        

        # 2. Desconecta o Selenium em memória SEM FECHAR O CHROME!

        # O Chrome permanece aberto no Windows, intacto com todas as abas e logins!

        print("[*] Desconectando sessão local do Selenium (Chrome permanece aberto)...")

        desconectar_selenium()



        # 3. Mata apenas processos residuais de chromedriver (a ponte), NÃO o chrome.exe

        try:

            import subprocess

            subprocess.run("taskkill /f /im chromedriver.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        except Exception:

            pass



        # 4. Se o script estiver rodando dentro do loop do start_server.bat, sai com código 42

        if os.environ.get("GS_LOOP_ACTIVE") == "1":

            print("[*] Reiniciando via loop do CMD (código 42)...")

            os._exit(42)

        else:

            print("[*] Loop do CMD não detectado. Re-spawnando processo Python com ambiente limpo...")

            try:

                import subprocess, sys

                env_limpo = obter_env_limpo_pyinstaller()

                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if os.name == 'nt' else 0

                if getattr(sys, 'frozen', False):

                    cmd_str = f'cmd /c "ping 127.0.0.1 -n 3 > nul && \"{sys.executable}\""'

                    subprocess.Popen(cmd_str, cwd=BASE_DIR, env=env_limpo, shell=True, creationflags=flags, close_fds=True)

                else:

                    script_path = os.path.abspath(__file__)

                    py_exe = sys.executable

                    if not py_exe or not os.path.isfile(py_exe):

                        py_exe = os.path.join(os.path.dirname(script_path), "venv", "Scripts", "python.exe")

                    cmd_str = f'cmd /c "ping 127.0.0.1 -n 3 > nul && \"{py_exe}\" \"{script_path}\""'

                    subprocess.Popen(cmd_str, cwd=BASE_DIR, env=env_limpo, shell=True, creationflags=flags, close_fds=True)

            except Exception as e_respawn:

                print(f"[Aviso] Erro ao re-spawnar Python: {e_respawn}")

            os._exit(0)



    import threading

    threading.Thread(target=executar_reinicio, daemon=True).start()

    return jsonify({"status": "sucesso", "mensagem": "Servidor reiniciando (o Chrome permanecerá aberto)..."})



@app.route('/focar-chrome', methods=['POST', 'GET'])

def rota_focar_chrome():

    try:

        dados = request.get_json(silent=True) or {}

        plat = (dados.get("plataforma") or plataforma_ativa or "").strip().lower()

        cid = (dados.get("conta_id") or conta_ativa or "").strip() or None



        if plat:

            _, porta, cid_resolvido, _ = obter_perfil_e_porta_conta(plat, cid)

            if not is_chrome_debug_active(porta) or not chrome_tem_janela_visivel_na_tela(porta):

                inicializar_selenium(plat, cid_resolvido)

                salvar_sessao_ativa(plat, motorista_atribuicao_ativa, contagem_atribuicao_ativa, cid_resolvido)

                return jsonify({"status": "sucesso", "mensagem": "Chrome iniciado e focado com sucesso!"})

            else:

                if not driver or plataforma_ativa != plat or (cid_resolvido and conta_ativa != cid_resolvido):

                    conectar_chrome_existente(plat, cid_resolvido)

                try:

                    driver.maximize_window()

                    driver.execute_cdp_cmd("Page.bringToFront", {})

                except Exception:

                    pass

                forcar_janela_chrome_visivel(porta, plat_alvo=plat)

                return jsonify({"status": "sucesso", "mensagem": "Chrome focado com sucesso!"})



        if driver:

            try:

                driver.maximize_window()

                driver.execute_cdp_cmd("Page.bringToFront", {})

            except Exception:

                pass

        forcar_janela_chrome_visivel()

        return jsonify({"status": "sucesso", "mensagem": "Chrome focado com sucesso!"})

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/bip', methods=['POST'])

@requer_licenca_ativa

def processar_bip():

    global driver, aba_recebimento, aba_descarregamento, aba_atribuicao, aba_atribuicao_anjun, plataforma_ativa, motorista_atribuicao_ativa, contagem_atribuicao_ativa, alertas_gerencia, modo_consulta, contagem_motoristas, ultimo_motorista_bipado, primeiro_bip_validado, total_bipes_processados

    

    tempo_inicio = time.time()

    dados = request.json

    codigo_qr = dados.get("codigo", "").strip()

    p_id = dados.get("plataforma", "").strip().lower()

    c_id = str(dados.get("conta_id") or dados.get("conta") or "").strip()

    motorista_lote = dados.get("motorista")

    cidades_selecionadas = dados.get("cidades_selecionadas") or []

    if not isinstance(cidades_selecionadas, list):

        cidades_selecionadas = [cidades_selecionadas]

    cidades_selecionadas = [str(c).strip() for c in cidades_selecionadas if str(c).strip()]

    if not cidades_selecionadas and motorista_lote:

        cidades_selecionadas = [motorista_lote.strip()]

    if not motorista_lote and cidades_selecionadas:

        motorista_lote = cidades_selecionadas[0]

    # Validação de licença para coletores móveis
    if dados.get("origem") == "coletor":
        device_id_bip = str(dados.get("device_id") or "").strip()
        ok_coletor, motivo_coletor = verificar_autorizacao_coletor(device_id_bip, request.remote_addr)
        if not ok_coletor:
            return jsonify({
                "status": "erro",
                "codigo": "COLETOR_NAO_AUTORIZADO",
                "mensagem": motivo_coletor
            }), 403

    pacote_solto = bool(dados.get("pacote_solto", False))

    triagem_direta = bool(dados.get("triagem_direta", False))

    if triagem_direta:

        tem_motorista = True

    

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

            WHERE UPPER(codigo) = UPPER(?) AND status = 'OK' AND timestamp >= ?

            ORDER BY timestamp DESC LIMIT 1

        ''', (codigo_qr, limite_data))

        res_dup = cursor_dup.fetchone()



        if not res_dup and ('anjun' in p_id or 'anjun' in str(plataforma_ativa or '').lower()):

            try:

                cursor_dup.execute('''

                    SELECT motorista FROM lote_pendente_anjun

                    WHERE UPPER(waybill) = UPPER(?) LIMIT 1

                ''', (codigo_qr,))

                row_lote = cursor_dup.fetchone()

                if row_lote:

                    res_dup = (datetime.datetime.now().isoformat(), row_lote[0], "Anjun")

            except Exception:

                pass



        conn_dup.close()



        if not res_dup and codigo_qr.upper() in bipes_ok_sessao:

            res_dup = bipes_ok_sessao[codigo_qr.upper()]

        

        if res_dup:

            timestamp_raw, mot_dup, cid_dup = res_dup

            try:

                dt_obj = datetime.datetime.fromisoformat(timestamp_raw)

                dt_str = dt_obj.strftime("%d/%m/%Y %H:%M:%S")

            except Exception:

                dt_str = timestamp_raw

                

            print(f"[!] PACOTE DUPLICADO DETECTADO: {codigo_qr} (Bipado em {dt_str} para {mot_dup}).")

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

        if codigo_qr.upper() in bipes_ok_sessao:

            ts_m, mot_m, cid_m = bipes_ok_sessao[codigo_qr.upper()]

            pacote_duplicado = True

            motorista_anterior = mot_m

            cidade_duplicada = cid_m

            timestamp_anterior = ts_m

        

    if pacote_duplicado:

        print(f"[!] PACOTE DUPLICADO ({p_id}): {codigo_qr} (Bipado anteriormente para {motorista_anterior} em {timestamp_anterior}). Executando fluxo completo no site (Entrada + Atribuição)...")

            

    driver_lock.acquire()

    try:

        # Se o navegador não estiver aberto para esta plataforma, verifica confirmação de motorista

        confirmado_reabertura = dados.get("confirmado_reabertura", False)

        tem_motorista = bool(motorista_lote and str(motorista_lote).strip() not in ["", "---", "Apenas Entrada (Sem Atribuição)"])

        if not is_driver_ativo() or plataforma_ativa != p_id:

            porta_p = PORTAS_DEBUG.get(p_id, 9222)

            chrome_ja_aberto = is_chrome_debug_active(porta_p)



            if not chrome_ja_aberto and (p_id in ['anjun', 'imile', 'loggi']) and tem_motorista and not confirmado_reabertura and (p_id == plataforma_ativa) and (str(dados.get("origem") or "").lower() != "coletor"):

                print(f"[!] Chrome fechado detectado com motorista/destino ({motorista_lote}) para {p_id}. Solicitando confirmação do operador...")

                return jsonify({

                    "status": "chrome_fechado",

                    "mensagem": "O navegador Chrome está fechado. Confirme se o motorista está correto para continuar.",

                    "motorista": motorista_lote,

                    "plataforma": p_id

                }), 200



            try:

                if chrome_ja_aberto and chrome_tem_janela_visivel_na_tela(porta_p):

                    conectar_chrome_existente(p_id, c_id or None)

                else:

                    inicializar_selenium(p_id, c_id or None)

                plataforma_ativa = p_id

            except Exception as e:

                if True:

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

            # --- MOTOR DE BIPAGEM DIRETA VIA API LOGGI (SUB-150MS) ---

            print("[*] [Loggi] Disparando bipagem direta via API Ultra-Rápida...")

            sucesso_api, msg_api, mot_final, cid_api, cep_api, rec_api, end_api = bipar_pacote_loggi_api(

                codigo_qr, cidades_selecionadas, motorista_lote, modo_triagem_direta=triagem_direta

            )

            

            if sucesso_api is True or (sucesso_api and sucesso_api != "divergente"):

                cidade_detectada = cid_api if cid_api else "Loggi"

                motorista = mot_final if mot_final else (motorista_lote or grupo_loggi_ativo.get("cidade") or "Loggi")

                recebedor = rec_api if rec_api else "---"

                cep = cep_api if cep_api else ""

                endereco = end_api if end_api else ""

                

                # Incrementa contagem local sempre no grupo ativo principal

                chave_cont = motorista if motorista else (motorista_lote or grupo_loggi_ativo.get("cidade") or cidade_detectada)

                contagem_motoristas[chave_cont] = contagem_motoristas.get(chave_cont, 0) + 1

                

                if pacote_duplicado:

                    if motorista_anterior:

                        for k_m in list(contagem_motoristas.keys()):

                            if k_m.strip().lower() == str(motorista_anterior).strip().lower():

                                contagem_motoristas[k_m] = max(0, contagem_motoristas[k_m] - 1)

                                break

                    try:

                        conn_up = conectar_banco()

                        cursor_up = conn_up.cursor()

                        cursor_up.execute('''

                            UPDATE historico 

                            SET status = 'REATRIBUIDO' 

                            WHERE UPPER(codigo) = UPPER(?) AND status = 'OK' AND timestamp >= ?

                        ''', (codigo_qr, limite_data))

                        conn_up.commit()

                        conn_up.close()

                    except Exception:

                        pass

                

                contagem_atribuicao_ativa = contagem_motoristas.get(chave_cont, 0)

                if not pacote_duplicado:
                    salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista, "OK", recebedor=recebedor, cep=cep, endereco=endereco)

                

                total_bipes_processados += 1

                if total_bipes_processados % 100 == 0:

                    otimizar_memoria()

                    

                tempo_total = time.time() - tempo_inicio

                print(f"[+] [Loggi API] PACOTE PROCESSADO COM SUCESSO EM {tempo_total:.2f}s ({motorista} | {cidade_detectada} | CEP: {cep})!")

                

                return jsonify({

                    "status": "sucesso",

                    "cidade": cidade_detectada,

                    "motorista": motorista,

                    "triagem_direta": triagem_direta,

                    "recebedor": recebedor,

                    "cep": cep,

                    "endereco": endereco,

                    "contagem": contagem_atribuicao_ativa,

                    "contagem_site": None,

                    "duplicado": pacote_duplicado,

                    "motorista_anterior": motorista_anterior,

                    "timestamp_anterior": timestamp_anterior,

                    "mesmo_motorista": bool(motorista_lote and motorista_anterior and motorista_lote.strip().lower() == motorista_anterior.strip().lower())

                })

            elif sucesso_api == "divergente":

                cidade_detectada = cid_api if cid_api else "Loggi"

                motorista_esperado_display = mot_final

                recebedor = rec_api if rec_api else "---"

                cep = cep_api if cep_api else ""

                endereco = end_api if end_api else ""

                

                # Incrementa contagem local sempre no grupo ativo principal (pois o pacote foi atribuído com sucesso)

                chave_cont = motorista_lote or grupo_loggi_ativo.get("cidade") or cidade_detectada

                contagem_motoristas[chave_cont] = contagem_motoristas.get(chave_cont, 0) + 1

                contagem_atribuicao_ativa = contagem_motoristas.get(chave_cont, 0)

                

                try:

                    conn_div = conectar_banco()

                    cursor_div = conn_div.cursor()

                    cursor_div.execute("""

                        INSERT OR REPLACE INTO divergencias_pendentes (codigo, motorista_lote, motorista_esperado, status)

                        VALUES (?, ?, ?, 'pendente')

                    """, (codigo_qr, chave_cont, motorista_esperado_display))

                    conn_div.commit()

                    conn_div.close()

                except Exception:

                    pass

                

                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista_esperado_display, "DIVERGENTE", recebedor=recebedor, cep=cep, endereco=endereco)

                

                total_bipes_processados += 1

                return jsonify({

                    "status": "divergente",

                    "mensagem": msg_api,

                    "cidade": cidade_detectada,

                    "recebedor": recebedor,

                    "motorista_esperado": motorista_esperado_display,

                    "motorista": chave_cont,

                    "atribuido": True,

                    "contagem": contagem_atribuicao_ativa

                })

            else:

                msg_low = (msg_api or "").lower()

                eh_falha_rede = any(k in msg_low for k in ["internet lenta", "oscilação", "oscilacao", "timeout", "timed out", "urlopen error", "connection reset", "falha na comunicação", "network error"])

                eh_falha_sessao = any(k in msg_low for k in ["sessão", "token", "desconectada", "401"])



                if eh_falha_rede:

                    print(f"[!] [Loggi API] Queda de internet detectada: '{msg_api}'. Travando processo para evitar bipes no escuro.")

                    return jsonify({

                        "status": "erro_rede",

                        "plataforma": "loggi",

                        "mensagem": "Falha na conexão de internet com a Loggi. Verifique a internet e bipe novamente."

                    }), 400



                if eh_falha_sessao:

                    return jsonify({

                        "status": "aguardando_login",

                        "plataforma": "loggi",

                        "mensagem": "Sessão da Loggi desconectada ou expirada. Verifique o login no Chrome."

                    }), 400

                else:

                    salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {msg_api}")

                    return jsonify({

                        "status": "erro",

                        "mensagem": f"Alerta Loggi: {msg_api}"

                    }), 400

            

        elif (p_id == 'imile' or 'imile' in config['recebimento_url'].lower()):

            # --- MOTOR DE BIPAGEM DIRETA VIA API IMILE (SUB-100MS) ---

            print(f"[*] [iMile] Disparando bipagem direta via API Ultra-Rápida (Base: {c_id or 'Padrão'})...")

            sucesso_api, msg_api, mot_final, cid_api, cep_api, rec_api, end_api = bipar_pacote_imile_api(codigo_qr, motorista_lote, pacote_solto, modo_triagem_direta=triagem_direta, conta_id=c_id)

            

            if sucesso_api is True:

                cidade_detectada = cid_api if cid_api else "iMile"

                motorista = mot_final if mot_final else motorista_lote

                recebedor = rec_api if rec_api else "---"

                cep = cep_api if cep_api else ""

                endereco = end_api if end_api else ""

                

                # Incrementa contagem local

                if motorista_lote:

                    contagem_motoristas[motorista_lote] = contagem_motoristas.get(motorista_lote, 0) + 1

                elif motorista:

                    contagem_motoristas[motorista] = contagem_motoristas.get(motorista, 0) + 1

                

                # Se for duplicado, só anula a atribuição anterior se o motorista mudou (evita perder contagem ao bipar para o mesmo motorista)

                if pacote_duplicado:

                    eh_mesmo_mot = bool(motorista and motorista_anterior and str(motorista).strip().lower() == str(motorista_anterior).strip().lower())

                    if not eh_mesmo_mot:

                        if motorista_anterior:

                            for k_m in list(contagem_motoristas.keys()):

                                if k_m.strip().lower() == str(motorista_anterior).strip().lower():

                                    contagem_motoristas[k_m] = max(0, contagem_motoristas[k_m] - 1)

                                    break

                        try:

                            conn_up = conectar_banco()

                            cursor_up = conn_up.cursor()

                            cursor_up.execute('''

                                UPDATE historico 

                                SET status = 'REATRIBUIDO' 

                                WHERE UPPER(codigo) = UPPER(?) AND status = 'OK' AND timestamp >= ?

                            ''', (codigo_qr, limite_data))

                            conn_up.commit()

                            conn_up.close()

                        except Exception:

                            pass

                

                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) if motorista_lote else 0

                if not pacote_duplicado:
                    salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista, "OK", recebedor=recebedor, cep=cep, endereco=endereco)

                

                total_bipes_processados += 1

                if total_bipes_processados % 100 == 0:

                    otimizar_memoria()

                    

                tempo_total = time.time() - tempo_inicio

                print(f"[+] [iMile API] PACOTE PROCESSADO COM SUCESSO EM {tempo_total:.2f}s ({motorista} | {cidade_detectada} | CEP: {cep})!")

                

                return jsonify({

                    "status": "sucesso",

                    "cidade": cidade_detectada,

                    "motorista": motorista or motorista_lote,

                    "triagem_direta": triagem_direta,

                    "recebedor": recebedor,

                    "cep": cep,

                    "endereco": endereco,

                    "contagem": contagem_atribuicao_ativa,

                    "contagem_site": None,

                    "duplicado": pacote_duplicado,

                    "motorista_anterior": motorista_anterior,

                    "timestamp_anterior": timestamp_anterior,

                    "mesmo_motorista": bool(motorista_lote and motorista_anterior and motorista_lote.strip().lower() == motorista_anterior.strip().lower())

                })

            elif sucesso_api == "aguardando_login":

                return jsonify({

                    "status": "aguardando_login",

                    "plataforma": "imile",

                    "mensagem": msg_api or "Sessão da iMile desconectada. Faça o login no Chrome para continuar."

                })

            elif sucesso_api == "divergente":

                cidade_detectada = cid_api if cid_api else "iMile"

                motorista_esperado_display = mot_final

                recebedor = rec_api if rec_api else "---"

                cep = cep_api if cep_api else ""

                endereco = end_api if end_api else ""

                

                # Incrementa contagem local do motorista ativo (pois o pacote foi atribuído com sucesso a ele)

                if motorista_lote:

                    contagem_motoristas[motorista_lote] = contagem_motoristas.get(motorista_lote, 0) + 1

                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) if motorista_lote else 0



                try:

                    conn_div = conectar_banco()

                    cursor_div = conn_div.cursor()

                    cursor_div.execute("""

                        INSERT OR REPLACE INTO divergencias_pendentes (codigo, motorista_lote, motorista_esperado, status)

                        VALUES (?, ?, ?, 'pendente')

                    """, (codigo_qr, motorista_lote, motorista_esperado_display))

                    conn_div.commit()

                    conn_div.close()

                except Exception:

                    pass

                

                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista_esperado_display, "DIVERGENTE", recebedor=recebedor, cep=cep, endereco=endereco)

                

                total_bipes_processados += 1

                return jsonify({

                    "status": "divergente",

                    "mensagem": msg_api,

                    "cidade": cidade_detectada,

                    "recebedor": recebedor,

                    "motorista_esperado": motorista_esperado_display,

                    "motorista": motorista_lote,

                    "atribuido": True,

                    "contagem": contagem_atribuicao_ativa

                })

            else:

                # Verifica se foi um erro impeditivo / regra de negócio retornado pela iMile

                msg_low = (msg_api or "").lower()

                eh_falha_rede = any(k in msg_low for k in ["internet lenta", "oscilação", "oscilacao", "timeout", "timed out", "urlopen error", "connection reset", "falha na comunicação", "network error"])

                eh_falha_sessao = any(k in msg_low for k in ["sessão", "sessao", "token", "ausente no navegador", "conexão com a imile", "http 50", "401", "unauthorized"])



                if eh_falha_rede:

                    print(f"[!] [iMile API] Queda de internet detectada: '{msg_api}'. Travando processo para evitar bipes no escuro.")

                    return jsonify({

                        "status": "erro_rede",

                        "plataforma": "imile",

                        "mensagem": "Falha na conexão de internet com a iMile. Verifique a internet e bipe novamente."

                    }), 400



                if eh_falha_sessao:

                    cache_sessao_imile["token"] = None

                    try:

                        if driver and "login" in (driver.current_url or "").lower():

                            return jsonify({

                                "status": "aguardando_login",

                                "plataforma": "imile",

                                "mensagem": "Sessão da iMile desconectada. Faça o login no Chrome para continuar."

                            })

                        sess_im = atualizar_sessao_imile(forcar=True)

                        if not sess_im.get("token"):

                            return jsonify({

                                "status": "aguardando_login",

                                "plataforma": "imile",

                                "mensagem": "Sessão da iMile desconectada. Faça o login no Chrome para continuar."

                            })

                    except Exception:

                        pass

                    return jsonify({

                        "status": "aguardando_login",

                        "plataforma": "imile",

                        "mensagem": "Sessão da iMile expirada ou desconectada. Faça login no Chrome."

                    })



                # Erro de negócio real retornado pela iMile (ex: pacote não existe, retenção, estação errada, etc.)

                print(f"[!] [iMile API] Alerta impeditivo retornado pela iMile: '{msg_api}'")

                salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {msg_api}")

                return jsonify({

                    "status": "erro",

                    "mensagem": f"Alerta iMile: {msg_api}"

                }), 400



            garantir_abas_imile(driver)



            def bipar_descarregamento_imile():

                global aba_descarregamento

                garantir_abas_imile(driver)

                if not aba_descarregamento:

                    print("[Aviso] Aba de Descarregamento (dsOffloadingScan) iMile não encontrada.")

                    return

                print("[*] Mudando para a Aba 2 (Descarregamento - dsOffloadingScan) iMile...")

                mudar_aba_acelerado(driver, aba_descarregamento, delay=0.15)

                fechar_modais_imile(driver)

                

                # Localiza o input diretamente com tolerância a renderização

                campo_desc = obter_input_imile_html(driver, timeout=2.0)

                if not campo_desc:

                    # Se o input ainda não estiver ativo, procura e clica em 'Começar Leitura'

                    try:

                        driver.execute_script("""

                            var btns = document.querySelectorAll("button, .ImileButton, .MuiButton-root, [role='button'], .ant-btn");

                            for (var i = 0; i < btns.length; i++) {

                                var t = (btns[i].innerText || btns[i].textContent || '').trim().toLowerCase();

                                if (t.includes('começar leitura') || t.includes('comecar leitura') || t.includes('start scan') || t.includes('iniciar leitura')) {

                                    btns[i].click();

                                    break;

                                }

                            }

                        """)

                        time.sleep(0.2)

                        campo_desc = obter_input_imile_html(driver, timeout=1.5)

                    except Exception:

                        pass



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

                mudar_aba_acelerado(driver, aba_recebimento, delay=0.15)

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

        elif (p_id == 'anjun' or 'anjun' in config.get('recebimento_url', '').lower() or 'anjun' in str(plataforma_ativa or '').lower()):

            # --- MOTOR DE BIPAGEM DIRETA VIA API ANJUN EXPRESS (SUB-100MS) ---

            print(f"[*] [Anjun] Disparando bipagem direta via API Ultra-Rápida (Base: {c_id or 'Padrão'})...")

            sucesso_api, msg_api, mot_final, cid_api, cep_api, rec_api, end_api = bipar_pacote_anjun_api(codigo_qr, motorista_lote, modo_triagem_direta=triagem_direta, conta_id=c_id)

            

            if sucesso_api is True:

                cidade_detectada = cid_api if cid_api else "Anjun"

                motorista = mot_final if mot_final else motorista_lote

                recebedor = rec_api if rec_api else "---"

                cep = cep_api if cep_api else ""

                endereco = end_api if end_api else ""

                

                # Incrementa contagem local do motorista que realmente recebeu o pacote

                if motorista:

                    contagem_motoristas[motorista] = contagem_motoristas.get(motorista, 0) + 1

                    

                eh_auto_atribuido = bool(motorista_lote and motorista and remover_acentos(motorista.strip().lower()) != remover_acentos(motorista_lote.strip().lower()))

                

                # Se for duplicado, só anula a atribuição anterior se o motorista mudou (evita perder contagem ao bipar para o mesmo motorista)

                if pacote_duplicado:

                    eh_mesmo_mot = bool(motorista and motorista_anterior and str(motorista).strip().lower() == str(motorista_anterior).strip().lower())

                    if not eh_mesmo_mot:

                        if motorista_anterior:

                            for k_m in list(contagem_motoristas.keys()):

                                if k_m.strip().lower() == str(motorista_anterior).strip().lower():

                                    contagem_motoristas[k_m] = max(0, contagem_motoristas[k_m] - 1)

                                    break

                        try:

                            conn_up = conectar_banco()

                            cursor_up = conn_up.cursor()

                            cursor_up.execute('''

                                UPDATE historico 

                                SET status = 'REATRIBUIDO' 

                                WHERE UPPER(codigo) = UPPER(?) AND status = 'OK' AND timestamp >= ?

                            ''', (codigo_qr, limite_data))

                            conn_up.commit()

                            conn_up.close()

                        except Exception:

                            pass

                

                if motorista_lote:

                    if not eh_auto_atribuido and motorista:

                        contagem_atribuicao_ativa = contagem_motoristas.get(motorista, contagem_motoristas.get(motorista_lote, 0))

                    else:

                        contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0)

                else:

                    contagem_atribuicao_ativa = 0

                

                if not pacote_duplicado:
                    salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista, "OK", recebedor=recebedor, cep=cep, endereco=endereco)

                

                total_bipes_processados += 1

                if total_bipes_processados % 100 == 0:

                    otimizar_memoria()

                    

                tempo_total = time.time() - tempo_inicio

                if eh_auto_atribuido:

                    print(f"[+] [Anjun API] AUTO-ATRIBUÍDO: {cidade_detectada} ➔ Grupo aberto de {motorista} em {tempo_total:.2f}s (Tela estava em: {motorista_lote})!")

                else:

                    print(f"[+] [Anjun API] PACOTE PROCESSADO COM SUCESSO EM {tempo_total:.2f}s ({motorista} | {cidade_detectada} | CEP: {cep})!")

                

                # Se o motorista atingir 200 pacotes, finaliza automaticamente o lote APENAS se a API confirmar

                lote_atingiu_200 = False

                if motorista and contagem_motoristas.get(motorista, 0) >= 200:

                    print(f"[!] Limite de 200 pacotes atingido para {motorista}. Finalizando lote Anjun automaticamente...")

                    try:

                        ok_fin_200, qtd_fin_200 = finalizar_lote_anjun_api(motorista)

                        if ok_fin_200:

                            registrar_lote_finalizado(motorista, qtd_fin_200 or 200, plataforma="anjun")

                            contagem_motoristas[motorista] = 0

                            if motorista == motorista_lote:

                                contagem_atribuicao_ativa = 0

                            lote_atingiu_200 = True

                        else:

                            print(f"[!] Aviso: Servidor da Anjun não confirmou o auto-fechamento de 200 pacotes para {motorista}. Mantendo lote aberto para nova tentativa.")

                    except Exception as e_200:

                        print(f"[!] Erro ao auto-finalizar lote Anjun de 200: {e_200}")

                

                if lote_atingiu_200:

                    return jsonify({

                        "status": "finalizado_limite",

                        "cidade": cidade_detectada,

                        "motorista": motorista,

                        "motorista_tela": motorista_lote,

                        "auto_atribuido": eh_auto_atribuido,

                        "recebedor": recebedor,

                        "cep": cep,

                        "endereco": endereco,

                        "contagem": contagem_atribuicao_ativa,

                        "contagem_motorista": 0,

                        "contagem_site": 0,

                        "duplicado": pacote_duplicado,

                        "motorista_anterior": motorista_anterior,

                        "timestamp_anterior": timestamp_anterior,

                        "mesmo_motorista": bool(motorista and motorista_anterior and motorista.strip().lower() == motorista_anterior.strip().lower())

                    })

                

                qtd_lote_site = len(obter_pacotes_lote_anjun(motorista)) if motorista else None

                return jsonify({

                    "status": "sucesso",

                    "cidade": cidade_detectada,

                    "motorista": motorista,

                    "motorista_tela": motorista_lote,

                    "auto_atribuido": eh_auto_atribuido,

                    "recebedor": recebedor,

                    "cep": cep,

                    "endereco": endereco,

                    "contagem": contagem_atribuicao_ativa,

                    "contagem_motorista": contagem_motoristas.get(motorista, 0) if motorista else 0,

                    "contagem_site": qtd_lote_site,

                    "duplicado": pacote_duplicado,

                    "motorista_anterior": motorista_anterior,

                    "timestamp_anterior": timestamp_anterior,

                    "mesmo_motorista": bool(motorista and motorista_anterior and motorista.strip().lower() == motorista_anterior.strip().lower())

                })

            elif sucesso_api == "aguardando_login":

                return jsonify({

                    "status": "aguardando_login",

                    "plataforma": "anjun",

                    "mensagem": msg_api or "Sessão da Anjun desconectada ou 'Não sou robô' solicitado."

                })

            elif sucesso_api == "duplicado":

                cidade_detectada = cid_api if cid_api else (cidade_duplicada or "Anjun")

                mot_dup_exibir = motorista_anterior or mot_final or motorista_lote or "Anjun"

                ts_dup_exibir = timestamp_anterior or datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, mot_dup_exibir, "DUPLICADO")

                return jsonify({

                    "status": "duplicado",

                    "mensagem": msg_api or f"Pacote já bipado para {mot_dup_exibir}",

                    "motorista": mot_dup_exibir,

                    "cidade": cidade_detectada,

                    "timestamp": ts_dup_exibir

                }), 400

            elif sucesso_api == "divergente":

                cidade_detectada = cid_api if cid_api else "Anjun"

                motorista_esperado_display = mot_final

                recebedor = rec_api if rec_api else "---"

                cep = cep_api if cep_api else ""

                endereco = end_api if end_api else ""

                

                # Incrementa contagem local do motorista ativo (pois o pacote foi atribuído com sucesso a ele)

                if motorista_lote:

                    contagem_motoristas[motorista_lote] = contagem_motoristas.get(motorista_lote, 0) + 1

                contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) if motorista_lote else 0



                try:

                    conn_div = conectar_banco()

                    cursor_div = conn_div.cursor()

                    cursor_div.execute("""

                        INSERT OR REPLACE INTO divergencias_pendentes (codigo, motorista_lote, motorista_esperado, status)

                        VALUES (?, ?, ?, 'pendente')

                    """, (codigo_qr, motorista_lote, motorista_esperado_display))

                    conn_div.commit()

                    conn_div.close()

                except Exception:

                    pass

                

                salvar_entrada_historico(codigo_qr, p_id, cidade_detectada, motorista_esperado_display, "DIVERGENTE", recebedor=recebedor, cep=cep, endereco=endereco)

                

                total_bipes_processados += 1

                return jsonify({

                    "status": "divergente",

                    "mensagem": msg_api,

                    "cidade": cidade_detectada,

                    "recebedor": recebedor,

                    "motorista_esperado": motorista_esperado_display,

                    "motorista": motorista_lote,

                    "atribuido": True,

                    "contagem": contagem_atribuicao_ativa

                })

            else:

                msg_low = (msg_api or "").lower()

                eh_falha_rede = any(k in msg_low for k in ["internet lenta", "oscilação", "oscilacao", "timeout", "timed out", "urlopen error", "connection reset", "falha na comunicação", "network error"])

                eh_falha_sessao = any(k in msg_low for k in ["sessão", "sessao", "token", "ausente no navegador", "conexão com a anjun", "conexão com anjun", "http 50", "401", "unauthorized"])



                if eh_falha_rede:

                    print(f"[!] [Anjun API] Queda de internet detectada: '{msg_api}'. Travando processo para evitar bipes no escuro.")

                    return jsonify({

                        "status": "erro_rede",

                        "plataforma": "anjun",

                        "mensagem": "Falha na conexão de internet com a Anjun. Verifique a internet e bipe novamente."

                    }), 400



                if eh_falha_sessao:

                    cache_sessao_anjun["token"] = None

                    try:

                        if driver and "login" in (driver.current_url or "").lower():

                            return jsonify({

                                "status": "aguardando_login",

                                "plataforma": "anjun",

                                "mensagem": "Sessão desconectada. Faça o login ou 'Não sou robô' no Chrome."

                            })

                        sess_aj = atualizar_sessao_anjun(forcar=True)

                        if not sess_aj.get("token"):

                            return jsonify({

                                "status": "aguardando_login",

                                "plataforma": "anjun",

                                "mensagem": "Sessão desconectada. Faça o login ou 'Não sou robô' no Chrome."

                            })

                    except Exception:

                        pass

                    return jsonify({

                        "status": "aguardando_login",

                        "plataforma": "anjun",

                        "mensagem": "Sessão da Anjun expirada ou desconectada. Faça login no Chrome."

                    })



                # Erro de negócio real retornado pela Anjun (ex: pacote não existe, bloqueio, etc.)

                print(f"[!] [Anjun API] Alerta impeditivo retornado pela Anjun: '{msg_api}'")

                salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {msg_api}")

                return jsonify({

                    "status": "erro",

                    "mensagem": f"Alerta Anjun: {msg_api}"

                }), 400

        else:

            is_anjun = ("anjun" in p_id or "anjun" in config.get('recebimento_url', '').lower())

            if is_anjun and driver:

                try:

                    if "login" in driver.current_url.lower():

                        return jsonify({

                            "status": "aguardando_login",

                            "plataforma": "anjun",

                            "mensagem": "Sessão desconectada. Faça o login ou 'Não sou robô' no Chrome."

                        })

                except Exception:

                    pass

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

                

                def clicar_botao_enviar_anjun(drv):

                    sucesso_click = False

                    try:

                        res_js = drv.execute_script("""

                            var btns = document.querySelectorAll("button, .el-button, [role='button']");

                            for (var i = 0; i < btns.length; i++) {

                                var b = btns[i];

                                if (b && (b.offsetWidth > 0 || b.offsetHeight > 0 || b.offsetParent !== null)) {

                                    var t = (b.innerText || b.textContent || '').trim().toLowerCase();

                                    if (t === 'enviar' || t.includes('enviar') || b.classList.contains('el-button--primary')) {

                                        try { b.focus(); } catch(e){}

                                        try { b.click(); } catch(e){}

                                        b.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));

                                        b.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));

                                        b.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

                                        return true;

                                    }

                                }

                            }

                            return false;

                        """)

                        if res_js:

                            sucesso_click = True

                    except Exception:

                        pass

                    

                    try:

                        xpath_cands = [

                            "//button[contains(., 'Enviar') or contains(span, 'Enviar')]",

                            "//button[contains(@class, 'el-button--primary') and not(contains(., 'Consulta'))]",

                            "//div[contains(@class, 'netEntryScanning') or contains(@class, 'operatingCenter')]//button[contains(@class, 'el-button--primary')]"

                        ]

                        for xp in xpath_cands:

                            try:

                                elems = drv.find_elements(By.XPATH, xp)

                                for el in elems:

                                    if el.is_displayed():

                                        drv.execute_script("arguments[0].click();", el)

                                        try:

                                            el.click()

                                        except Exception:

                                            pass

                                        try:

                                            webdriver.ActionChains(drv).move_to_element(el).click().perform()

                                        except Exception:

                                            pass

                                        sucesso_click = True

                                        break

                                if sucesso_click:

                                    break

                            except Exception:

                                continue

                    except Exception:

                        pass

                    return sucesso_click



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

                                    if (msgLow.includes("já escaneado") || msgLow.includes("já bipado") || msgLow.includes("já recepcionado") || msgLow.includes("duplicad") || msgLow.includes("sendo processado") || msgLow.includes("processado") || msgLow.includes("já existe") || msgLow.includes("já recebido") || msgLow.includes("já conferido")) {

                                        return { tipo: "duplicado", texto: msg };

                                    }

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

                        if (err.tipo === "duplicado") return { status: "alerta_duplicado", texto: err.texto };

                        if (err.tipo === "erro_fatal") return { status: "alerta_erro", texto: err.texto };

                    }

                    

                    // 2. DETECÇÃO ROBUSTA SE HÁ PACOTE NA TABELA:

                    var pacoteNaTabela = false;

                    

                    // A) Contador 'Já bipado:' maior que zero (ex: 'Já bipado: 1')

                    var bodyTxt = document.body.innerText || document.body.textContent || '';

                    var matchBip = bodyTxt.match(/J[áa]\\s*bipado:\\s*([1-9]\\d*)/i);

                    if (matchBip && parseInt(matchBip[1], 10) > 0) {

                        pacoteNaTabela = true;

                    }

                    

                    // B) Paginação 'Total 1' ou mais

                    if (!pacoteNaTabela) {

                        var matchTotal = bodyTxt.match(/Total\\s+([1-9]\\d*)/i);

                        if (matchTotal && parseInt(matchTotal[1], 10) > 0) {

                            pacoteNaTabela = true;

                        }

                    }

                    

                    // C) Linhas da tabela com conteúdo visível

                    if (!pacoteNaTabela) {

                        var rows = document.querySelectorAll(".el-table__body tr, table tbody tr, .el-table__row");

                        for (var r = 0; r < rows.length; r++) {

                            var row = rows[r];

                            if (row && (row.offsetWidth > 0 || row.offsetHeight > 0 || row.offsetParent !== null)) {

                                var rTxt = (row.innerText || row.textContent || '').trim().toLowerCase();

                                if (rTxt && !rTxt.includes("sem dados") && !rTxt.includes("nenhum") && !rTxt.includes("no data") && rTxt.length > 5) {

                                    pacoteNaTabela = true;

                                    break;

                                }

                            }

                        }

                    }

                    

                    // D) Busca pelo código direto ou classe firstOrder

                    if (!pacoteNaTabela && cleanQr) {

                        var cleanNums = cleanQr.replace(/[^a-z0-9]/g, '');

                        var allCells = document.querySelectorAll(".el-table__body td, table tbody td, .firstOrder");

                        for (var c = 0; c < allCells.length; c++) {

                            var cellTxt = (allCells[c].innerText || allCells[c].textContent || '').trim().toLowerCase();

                            if (cellTxt && (cellTxt.includes(cleanQr) || cleanQr.includes(cellTxt) || (cleanNums.length >= 6 && cellTxt.includes(cleanNums)))) {

                                pacoteNaTabela = true;

                                break;

                            }

                        }

                    }

                    

                    if (pacoteNaTabela) {

                        return { status: "pacote_na_tabela" };

                    }

                    

                    return { status: "aguardando_tabela" };

                """

                

                while time.time() - inicio_wait < 10.0:

                    try:

                        res = driver.execute_script(script_anjun_aba1, codigo_qr)

                        if res:

                            st = res.get("status")

                            if st == "pacote_na_tabela":

                                enviado_com_sucesso = True

                                print(f"[+] [Anjun] Pacote {codigo_qr} confirmado na tabela inferior! Clicando no botão 'Enviar'...")

                                clicar_botao_enviar_anjun(driver)

                                break

                            elif st == "alerta_erro":

                                alerta_texto = res.get("texto")

                                break

                            elif st == "alerta_duplicado":

                                print(f"[*] [Anjun] Aviso de pacote já escaneado: '{res.get('texto')}'. Prosseguindo para Aba 3...")

                                enviado_com_sucesso = True

                                pacote_ja_recepcionado_aba1 = True

                                break

                    except Exception:

                        pass

                        

                    # Se passou 1.5s e ainda não apareceu na tabela, re-dispara Enter no campo de bipe

                    if not re_disparado and (time.time() - inicio_wait > 1.5):

                        re_disparado = True

                        print(f"[*] [Anjun] Pacote ainda não apareceu na tabela após 1.5s. Re-disparando Enter no input...")

                        try:

                            if campo_rec:

                                campo_rec.send_keys(Keys.ENTER)

                        except Exception:

                            pass

                            

                    time.sleep(0.08)

                

                # Se o timeout estourou mas não houve alerta, tenta clique final no Enviar por garantia

                if not enviado_com_sucesso and not alerta_texto:

                    print("[*] [Anjun] Forçando clique no botão 'Enviar' por garantia...")

                    clicar_botao_enviar_anjun(driver)

                

                if alerta_texto and not pacote_duplicado:

                    alerta_low = alerta_texto.lower()

                    if any(k in alerta_low for k in ["sendo processado", "processado", "já escaneado", "já bipado", "já recepcionado", "duplicad", "já existe", "já recebido"]):

                        print(f"[*] [Anjun] Aviso de pacote já em processamento/recepcionado na Aba 1: '{alerta_texto}'. Prosseguindo para Aba 3...")

                        enviado_com_sucesso = True

                        pacote_ja_recepcionado_aba1 = True

                    else:

                        print(f"[!] [Anjun] Alerta impeditivo na Aba 1: '{alerta_texto}'. Cancelando processo.")

                        salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"FALHA: {alerta_texto}")

                        return jsonify({

                            "status": "erro",

                            "mensagem": f"Alerta da Anjun: {alerta_texto}"

                        }), 400

                    

                # SINCRONIZAÇÃO ROBUSTA PÓS-ENVIO NA ABA 1:

                # O site da Anjun pode ser lento. Enquanto o loading estiver ativo, o robô FICA ESPERANDO

                # e NÃO passa para atribuir em hipótese alguma.

                # Só passa quando o pacote sumir da tabela inferior e o site exibir 'Sem dados' ou 'Já bipado: 0'.

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

                                        if (msgLow.includes("já escaneado") || msgLow.includes("já bipado") || msgLow.includes("já recepcionado") || msgLow.includes("duplicad") || msgLow.includes("sendo processado") || msgLow.includes("processado") || msgLow.includes("já existe") || msgLow.includes("já recebido") || msgLow.includes("já conferido")) {

                                            return { tipo: "duplicado", texto: msg };

                                        }

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



                        // 3. Verifica se AINDA há pacote na tabela inferior

                        var temPacote = false;

                        var bodyText = document.body.innerText || document.body.textContent || '';

                        

                        var matchBip = bodyText.match(/J[áa]\\s*bipado:\\s*(\\d+)/i);

                        if (matchBip) {

                            if (parseInt(matchBip[1], 10) === 0) {

                                temPacote = false;

                            } else {

                                temPacote = true;

                            }

                        } else {

                            var matchTot = bodyText.match(/Total\\s+(\\d+)/i);

                            if (matchTot && parseInt(matchTot[1], 10) === 0) {

                                temPacote = false;

                            } else if (matchTot && parseInt(matchTot[1], 10) > 0) {

                                temPacote = true;

                            } else {

                                var rows = document.querySelectorAll(".el-table__body tr, table tbody tr, .el-table__row");

                                for (var r = 0; r < rows.length; r++) {

                                    var row = rows[r];

                                    if (row && (row.offsetWidth > 0 || row.offsetHeight > 0 || row.offsetParent !== null)) {

                                        var rTxt = (row.innerText || row.textContent || '').trim().toLowerCase();

                                        if (rTxt && !rTxt.includes("sem dados") && !rTxt.includes("nenhum") && rTxt.length > 5) {

                                            temPacote = true;

                                            break;

                                        }

                                    }

                                }

                            }

                        }



                        // Se estiver em loading, aguarda!

                        if (loadingAtivo) {

                            return { status: "carregando", temPacote: temPacote };

                        }



                        // Se não há mais pacote na tabela e loading acabou: SUCESSO!

                        if (!temPacote) {

                            return { status: "confirmado_limpo" };

                        }



                        // Se ainda há pacote na tabela e não está em loading: precisa re-clicar Enviar!

                        return { status: "na_tabela_aguardando", alertaGateway: (alerta && alerta.tipo === "timeout_gateway") };

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

                                    pass

                                elif st_env == "na_tabela_aguardando":

                                    # Se parou o loading mas o pacote ainda está na tabela, re-clica em Enviar a cada 1.8s!

                                    if time.time() - ultimo_re_clique >= 1.8:

                                        ultimo_re_clique = time.time()

                                        motivo = "após 网关超时" if res_env.get("alertaGateway") else "sem loading ativo"

                                        print(f"[*] [Anjun] Pacote {codigo_qr} ainda na tabela ({motivo}). Re-clicando no botão 'Enviar'...")

                                        clicar_botao_enviar_anjun(driver)

                        except Exception:

                            pass

                        time.sleep(0.08)



                        

                    if alerta_pos_envio and not pacote_duplicado:

                        alerta_low = alerta_pos_envio.lower()

                        if any(k in alerta_low for k in ["sendo processado", "processado", "já escaneado", "já bipado", "já recepcionado", "duplicad", "já existe", "já recebido"]):

                            print(f"[*] [Anjun] Aviso pós-envio de pacote em processamento/recepcionado: '{alerta_pos_envio}'. Prosseguindo para Aba 3...")

                            confirmado_limpo = True

                        else:

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

                        if verificar_tela_login_loggi(driver):

                            tentar_clicar_login_google_loggi(driver)

                            return jsonify({

                                "status": "aguardando_login",

                                "plataforma": "loggi",

                                "mensagem": "Sessão da Loggi desconectada. Clique em 'Entrar com o Google' no Chrome."

                            })

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

            mots_cidade = carregar_motoristas_cidade(cidade_detectada, p_id, cep=cep)

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

                        

                if not pacote_duplicado:
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

                    todos_mots_cidade = carregar_motoristas_cidade(cidade_detectada, p_id)

                    motoristas_esperados = carregar_motoristas_cidade(cidade_detectada, p_id, cep=cep)

                    if todos_mots_cidade and not motoristas_esperados:

                        houve_divergencia = True

                        motorista_esperado_display = f"Fora da Faixa de CEP ({cidade_detectada})"

                    elif motoristas_esperados:

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

                    if verificar_tela_login_loggi(driver):

                        tentar_clicar_login_google_loggi(driver)

                        return jsonify({

                            "status": "aguardando_login",

                            "plataforma": "loggi",

                            "mensagem": "Sessão da Loggi desconectada. Clique em 'Entrar com o Google' no Chrome."

                        })

                    

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

                                    if cidades_sao_iguais(cid, texto_chk):

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



                                        // 1. PRIORIDADE MÁXIMA: se qualquer parágrafo do card for exatamente uma das cidades permitidas, retorna imediatamente!

                                        for (let p of ps) {

                                            if (p === pParent) continue;

                                            const txt = (p.innerText || p.textContent || "").trim();

                                            const txtL = txt.toLowerCase();

                                            for (let c of permitidas) {

                                                if (c && txtL === c) {

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



                            // Fallback: se não achou pelo código exato no em, procura se alguma cidade permitida aparece exatamente em parágrafo da gaveta

                            for (let c of permitidas) {

                                if (!c) continue;

                                const allPs = drawer.querySelectorAll("p");

                                for (let p of allPs) {

                                    const txt = (p.innerText || p.textContent || "").trim();

                                    if (txt.toLowerCase() === c) return txt;

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

                                                    if (c && txtL === c) {

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

                                        if (txt.toLowerCase() === c) return txt;

                                    }

                                }

                                return null;

                            """, codigo_qr, cidades_selecionadas)

                        except Exception:

                            pass



                    # Validação de Divergência de Cidade na Aba 3 da Loggi

                    if cidade_gaveta_extraida:

                        print(f"[+] [Loggi Aba 3] Cidade detectada no card da gaveta: '{cidade_gaveta_extraida}'")

                        cidades_permitidas_lista = cidades_selecionadas if cidades_selecionadas else ([motorista_lote] if motorista_lote else [])

                        cidade_bateu = any(cidades_sao_iguais(cidade_gaveta_extraida, c_perm) for c_perm in cidades_permitidas_lista)



                        if cidades_permitidas_lista and not cidade_bateu:

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

                        

                if not pacote_duplicado:
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

                # 1. Garante que as 3 abas da Anjun estejam ativas e mapeadas

                garantir_abas_anjun(driver)

                

                if not motorista_lote or motorista_lote in ["---", "Apenas Entrada (Sem Atribuição)"]:

                    print("[*] [Anjun] Modo apenas entrada (sem atribuição a motorista). Concluindo bip.")

                    contagem_atribuicao_ativa = 0

                else:

                    if not aba_atribuicao_anjun:

                        raise Exception("Aba 3 de Atribuição da Anjun (TaskAssignment) não pôde ser aberta ou mapeada.")

                    

                    print(f"[*] Acessando aba 3 para atribuir o pacote {codigo_qr} ao motorista {motorista_lote}...")

                    mudar_aba_acelerado(driver, aba_atribuicao_anjun, delay=0.1)

                    fechar_possiveis_lembretes(driver)

                    

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

                        

                    # VERIFICAÇÃO AUTOMÁTICA DE DRIVER EM ABA 3 (Só altera quando o motorista mudar)

                    global motorista_atribuicao_ativa

                    mot_atual = str(motorista_atribuicao_ativa or '').strip().lower()

                    mot_desejado = str(motorista_lote or '').strip().lower()

                    

                    # Checa se o motorista mudou no sistema

                    precisa_selecionar = (mot_atual != mot_desejado)

                    

                    # Se localmente já é o mesmo motorista, apenas confere se o site não foi resetado

                    if not precisa_selecionar:

                        try:

                            site_sem_motorista = driver.execute_script("""

                                var sel = document.querySelector('.el-select__wrapper, .el-select');

                                if (!sel) return true;

                                var txt = (sel.innerText || sel.textContent || '').trim().toLowerCase();

                                return (!txt || txt.includes('selecion') || txt.includes('favor'));

                            """)

                            if site_sem_motorista:

                                precisa_selecionar = True

                        except Exception:

                            pass

                            

                    if precisa_selecionar:

                        print(f"[*] Selecionando motorista na Aba 3! De '{motorista_atribuicao_ativa}' para '{motorista_lote}'...")

                        try:

                            selecionar_motorista_anjun(driver, motorista_lote)

                            motorista_atribuicao_ativa = motorista_lote

                            print(f"[+] Motorista alterado com sucesso na Aba 3 para: {motorista_atribuicao_ativa}")

                        except Exception as e_sel:

                            print(f"[Erro] Falha ao selecionar motorista na Aba 3: {str(e_sel)}")

                            raise Exception(f"Falha ao alterar o motorista no site para '{motorista_lote}': {str(e_sel)}")

                    else:

                        print(f"[*] [Anjun] Motorista '{motorista_lote}' já ativo na Aba 3. Bipando pacote direto!")

                    

                    # Bipa o pacote na Aba 3 de forma ultra-robusta e captura contagem real do site

                    sucesso_bip_aba3, contagem_site_lida, erro_bip_aba3 = bipar_pacote_atribuicao_anjun(driver, codigo_qr)

                    if not sucesso_bip_aba3:

                        raise Exception(erro_bip_aba3 or "Falha ao enviar bipe na Aba 3 da Anjun.")

                    

                    adicionar_pacote_lote_anjun(motorista_lote, codigo_qr)



                    if contagem_site_lida is not None:

                        contagem_atribuicao_ativa = contagem_site_lida

                        contagem_motoristas[motorista_lote] = contagem_site_lida

                        contagem_site = contagem_site_lida

                        print(f"[+] Lote Anjun atribuído (confirmado pelo site): {contagem_atribuicao_ativa}/200")

                    else:

                        contagem_atribuicao_ativa = contagem_motoristas.get(motorista_lote, 0) + 1

                        contagem_motoristas[motorista_lote] = contagem_atribuicao_ativa

                        print(f"[+] Lote Anjun atribuído (contagem local): {contagem_atribuicao_ativa}/200")

                    time.sleep(0.4)

                    

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

                                

                        if not pacote_duplicado:
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

                    mudar_aba_acelerado(driver, aba_atribuicao_anjun, delay=0.15)

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

                            try:

                                webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()

                            except Exception:

                                pass

                            time.sleep(0.3)

                        except Exception as e_da:

                            print(f"[Erro] Falha ao selecionar motorista iMile: {str(e_da)}")

                            raise Exception(f"Falha ao alterar o motorista no site para '{motorista_lote}': {str(e_da)}")

                    

                    # Bipa o pacote na Aba Atribuição iMile (instantâneo, sem esperas de conferência)

                    try:

                        fechar_modais_imile(driver)

                        campo_pacote = obter_input_imile_html(driver, timeout=2.0)

                        if not campo_pacote:

                            try:

                                campo_pacote = driver.find_element(By.XPATH, config.get('atribuicao_bip_xpath', "//*[@id='scanNumber']//input"))

                            except Exception:

                                pass



                        if campo_pacote:

                            sucesso_bip = enviar_bipe_imile_html(driver, campo_pacote, codigo_qr)

                            if sucesso_bip:

                                print(f"[+] Pacote {codigo_qr} bipeado na Aba Atribuição iMile com sucesso!")

                            else:

                                print(f"[Aviso] Falha ao confirmar envio na Aba Atribuição iMile.")

                            

                            # Confirma modal de reatribuição se for pacote duplicado

                            if pacote_duplicado:

                                time.sleep(0.3)

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



        if not pacote_duplicado:
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

        porta_p = PORTAS_DEBUG.get(p_id, 9222)

        if is_chrome_debug_active(porta_p):

            print(f"\n[!] Desconexão momentânea do WebDriver detectada (suspensão/hibernação do PC). Reconectando ao Chrome na porta {porta_p}...")

            try:

                conectar_chrome_existente(p_id)

                salvar_entrada_historico(codigo_qr, p_id, "---", "---", "AVISO: Reconexão pós-suspensão realizada", recebedor, telefone, email, tempo_criacao, status_pacote)

                return jsonify({"status": "erro", "mensagem": "Navegador Chrome reconectado após suspensão do computador. Por favor, bipe o pacote novamente."}), 400

            except Exception as e_recon:

                print(f"[Aviso] Falha ao reconectar ao Chrome existente ({e_recon}). Prosseguindo com tratamento padrão...")



        if is_driver_ativo():

            print(f"\n[Aviso WebDriver] Erro na interação com a página (Chrome permanece aberto): {str(wde)}")

            salvar_entrada_historico(codigo_qr, p_id, "---", "---", f"AVISO: {str(wde)[:100]}", recebedor, telefone, email, tempo_criacao, status_pacote)

            return jsonify({"status": "erro", "mensagem": f"Aviso na página: {str(wde)}"}), 400

            

        print(f"\n[Erro] Conexão com o Chrome realmente perdida ou fechada: {str(wde)}")

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



def restaurar_sessao_inicial():

    global plataforma_ativa, motorista_atribuicao_ativa, conta_ativa, contagem_atribuicao_ativa, conta_ativa

    try:

        sessao = carregar_sessao_ativa()

        p_id = sessao.get("plataforma")

        mot = sessao.get("motorista")

        cont = sessao.get("contagem", 0)

        c_id = sessao.get("conta_id")

        

        if p_id:

            if not c_id:

                try:

                    creds = carregar_credenciais_locais()

                    c_id = creds.get(p_id, {}).get("conta_ativa")

                except Exception:

                    c_id = None

            _, porta, cid_final, _ = obter_perfil_e_porta_conta(p_id, c_id)

            conta_ativa = cid_final

            if is_chrome_debug_active(porta):

                print(f"[*] Sessão anterior detectada ({p_id} / {cid_final}). Reconectando ao Chrome na porta {porta}...")

                conectar_chrome_existente(p_id, cid_final)

                plataforma_ativa = p_id

                motorista_atribuicao_ativa = mot

                contagem_atribuicao_ativa = cont

                if mot and cont:

                    contagem_motoristas[mot] = cont

                print(f"[+] Sessão restaurada com sucesso: Plataforma={p_id}, Conta={cid_final}, Motorista={mot}, Contagem={cont}")

            else:

                print(f"[*] Sessão anterior encontrada ({p_id} / {cid_final}), aguardando ativação do Chrome na porta {porta}.")

                plataforma_ativa = p_id

                motorista_atribuicao_ativa = mot

                contagem_atribuicao_ativa = cont

                if mot and cont:

                    contagem_motoristas[mot] = cont

    except Exception as e:

        print(f"[Aviso] Falha ao restaurar sessão inicial: {e}")



def _loop_heartbeat_periodico():

    while True:

        try:

            validar_licenca(forcar_rede=True)

        except Exception:

            pass

        time.sleep(60)



def _tarefas_boot_background():

    try:

        obter_hwid()

    except Exception:

        pass

    try:

        sincronizar_excel_na_inicializacao()

    except Exception:

        pass

    restaurar_sessao_inicial()

    threading.Thread(target=_loop_heartbeat_periodico, daemon=True).start()

    threading.Thread(target=monitor_auto_finalizacao_anjun, daemon=True).start()



# ==============================================================================

# MÓDULO COLETOR MOBILE (TURBOSCAN COLETOR ANDROID / PDA WI-FI)

# ==============================================================================



def obter_ip_rede_local():

    import socket

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



def gerar_qr_code_base64(texto):

    try:

        import qrcode

        import qrcode.image.svg

        import io, base64

        factory = qrcode.image.svg.SvgPathImage

        img = qrcode.make(texto, image_factory=factory)

        buf = io.BytesIO()

        img.save(buf)

        svg_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return "data:image/svg+xml;base64," + svg_b64

    except Exception as e:

        print(f"[!] Erro ao gerar QR Code SVG: {e}")

        try:

            import qrcode

            import io, base64

            qr = qrcode.QRCode(box_size=6, border=2)

            qr.add_data(texto)

            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()

            img.save(buf, format="PNG")

            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')

        except Exception as e2:

            print(f"[!] Erro no fallback QR Code: {e2}")

            return ""



def obter_limite_coletores_licenca():
    try:
        lic = validar_licenca()
        if lic and lic.get("valido"):
            plano = str(lic.get("plano") or "").lower()
            dias = lic.get("dias_restantes") or 0
            if "vital" in plano or dias > 1000:
                return 999
            return int(lic.get("max_coletores") or 10)
    except Exception:
        pass
    return 10

def verificar_autorizacao_coletor(device_id, ip=None, nome_dispositivo=None):
    if not device_id:
        return False, "Identificador do aparelho não informado."

    max_c = obter_limite_coletores_licenca()
    if max_c <= 0:
        return False, "Licença do sistema inativa ou sem permissão para coletores móveis."

    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT status, nome_dispositivo FROM coletores_autorizados WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()

        if row:
            st = row[0]
            if st == 'BLOQUEADO':
                conn.close()
                return False, "Este aparelho foi bloqueado pelo administrador no computador."
            cursor.execute('''
                UPDATE coletores_autorizados 
                SET ultimo_acesso = CURRENT_TIMESTAMP,
                    ip = COALESCE(?, ip),
                    nome_dispositivo = CASE WHEN ? IS NOT NULL AND ? != '' THEN ? ELSE nome_dispositivo END
                WHERE device_id = ?
            ''', (ip, nome_dispositivo, nome_dispositivo, nome_dispositivo, device_id))
            conn.commit()
            conn.close()
            return True, "Autorizado"
        else:
            cursor.execute("SELECT COUNT(*) FROM coletores_autorizados WHERE status = 'AUTORIZADO'")
            total_ativos = cursor.fetchone()[0]

            if total_ativos >= max_c:
                conn.close()
                return False, f"Limite de {max_c} coletor(es) atingido para esta licença. Libere uma vaga no TurboScan do computador ou contate o suporte."

            nome_final = nome_dispositivo if (nome_dispositivo and nome_dispositivo.strip()) else f"Coletor {total_ativos + 1}"
            cursor.execute('''
                INSERT INTO coletores_autorizados (device_id, nome_dispositivo, ip, status)
                VALUES (?, ?, ?, 'AUTORIZADO')
            ''', (device_id, nome_final, ip))
            conn.commit()
            conn.close()
            return True, "Autorizado"
    except Exception as e:
        return False, f"Erro ao verificar autorização do aparelho: {str(e)}"

@app.route('/api/coletor/autenticar', methods=['POST'])
def rota_coletor_autenticar():
    try:
        dados = request.get_json(force=True) or {}
        device_id = str(dados.get("device_id") or "").strip()
        nome_dispositivo = str(dados.get("nome_dispositivo") or "").strip()
        ip = request.remote_addr

        ok, motivo = verificar_autorizacao_coletor(device_id, ip, nome_dispositivo)
        max_c = obter_limite_coletores_licenca()

        conn = conectar_banco()
        c = conn.cursor()
        c.execute("SELECT count(*) FROM coletores_autorizados WHERE status = 'AUTORIZADO'")
        total_ativos = c.fetchone()[0]
        conn.close()

        if ok:
            return jsonify({
                "status": "sucesso",
                "autorizado": True,
                "max_coletores": max_c,
                "total_ativos": total_ativos,
                "device_id": device_id
            })
        else:
            return jsonify({
                "status": "erro",
                "autorizado": False,
                "codigo": "LIMITE_EXCEDIDO" if "Limite" in motivo else "BLOQUEADO",
                "motivo": motivo,
                "max_coletores": max_c,
                "total_ativos": total_ativos,
                "device_id": device_id
            }), 403
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/coletor/dispositivos', methods=['GET'])
def rota_coletor_dispositivos():
    try:
        max_c = obter_limite_coletores_licenca()
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT device_id, nome_dispositivo, ip, primeiro_acesso, ultimo_acesso, status 
            FROM coletores_autorizados 
            ORDER BY ultimo_acesso DESC
        ''')
        rows = cursor.fetchall()
        conn.close()

        lista = []
        for r in rows:
            lista.append({
                "device_id": r[0],
                "nome_dispositivo": r[1] or "Coletor",
                "ip": r[2] or "---",
                "primeiro_acesso": r[3] or "",
                "ultimo_acesso": r[4] or "",
                "status": r[5] or "AUTORIZADO"
            })

        total_ativos = len([d for d in lista if d["status"] == "AUTORIZADO"])
        return jsonify({
            "status": "sucesso",
            "max_coletores": max_c,
            "total_ativos": total_ativos,
            "vagas_restantes": max(0, max_c - total_ativos),
            "dispositivos": lista
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/coletor/dispositivos/remover', methods=['POST'])
def rota_coletor_remover_dispositivo():
    try:
        dados = request.get_json(force=True) or {}
        device_id = str(dados.get("device_id") or "").strip()
        if not device_id:
            return jsonify({"status": "erro", "mensagem": "device_id obrigatório"}), 400

        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM coletores_autorizados WHERE device_id = ?", (device_id,))
        conn.commit()
        conn.close()
        print(f"[+] [Coletor] Dispositivo {device_id} removido pelo administrador. Vaga liberada!")
        return jsonify({"status": "sucesso", "mensagem": "Aparelho desconectado e vaga liberada com sucesso!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/coletor')

def rota_coletor_mobile():

    caminho = os.path.join(BASE_DIR, 'coletor.html')

    if os.path.exists(caminho):

        with open(caminho, 'r', encoding='utf-8') as f:

            headers = {

                'Content-Type': 'text/html; charset=utf-8',

                'Cache-Control': 'no-cache, no-store, must-revalidate',

                'Pragma': 'no-cache',

                'Expires': '0'

            }

            return f.read(), 200, headers

    return "Arquivo coletor.html não encontrado no servidor.", 404



@app.route('/api/coletor/info', methods=['GET'])

def rota_coletor_info():

    ip = obter_ip_rede_local()

    porta = 5055

    url = f"http://{ip}:{porta}/coletor"

    qr = gerar_qr_code_base64(url)

    return jsonify({

        "status": "sucesso",

        "ip": ip,

        "porta": porta,

        "url": url,

        "qrcode": qr

    })



_cache_grupos_loggi_coletor = {"ts": 0, "grupos": []}



@app.route('/api/coletor/status', methods=['GET'])

def rota_coletor_status():

    global plataforma_ativa, motorista_atribuicao_ativa, conta_ativa, contagem_motoristas

    try:
        device_id_chk = str(request.args.get("device_id") or "").strip()
        if device_id_chk:
            ok_dev, mot_dev = verificar_autorizacao_coletor(device_id_chk, request.remote_addr)
            if not ok_dev:
                return jsonify({
                    "status": "erro",
                    "codigo": "COLETOR_BLOQUEADO",
                    "mensagem": mot_dev,
                    "max_coletores": obter_limite_coletores_licenca()
                }), 403

        plat_req = str(request.args.get("plataforma") or "").strip().lower()

        conta_req = str(request.args.get("conta") or "").strip()



        todas_contas = carregar_contas_plataformas()

        plat = plat_req if plat_req in ['anjun', 'imile', 'loggi'] else (plataforma_ativa or "anjun").lower()



        info_plat = todas_contas.get(plat, {})

        contas_plat = info_plat.get("contas", [])



        # Identifica a conta/base alvo

        cid = conta_req

        if not cid or cid == "padrao":

            cid = info_plat.get("conta_ativa") or (contas_plat[0]["id"] if contas_plat else "padrao")



        mots = []

        try:

            conn = conectar_banco()

            cursor = conn.cursor()

            if plat == 'loggi':

                cursor.execute(

                    "SELECT DISTINCT motorista FROM motoristas_plataforma WHERE motorista NOT IN ('Sem Motorista', 'Geral', '---', '') ORDER BY motorista ASC"

                )

            else:

                cursor.execute(

                    "SELECT DISTINCT motorista FROM motoristas_plataforma WHERE LOWER(plataforma) = LOWER(?) AND motorista NOT IN ('Sem Motorista', 'Geral', '---', '') ORDER BY motorista ASC",

                    (plat,)

                )

            mots = [r[0] for r in cursor.fetchall() if r[0]]

            conn.close()

        except Exception:

            pass



        if not mots:

            try:

                mots_salvos = obter_motoristas_da_base_salvos(plat, cid)

                if mots_salvos:

                    mots = mots_salvos

            except Exception:

                pass



        # Monta a lista completa de contas/bases disponíveis para a tela do coletor

        opcoes_contas = []

        for p_key in ['anjun', 'imile', 'loggi']:

            p_info = todas_contas.get(p_key, {})

            c_list = p_info.get("contas", [])

            c_ativa_p = p_info.get("conta_ativa") or (c_list[0]["id"] if c_list else "padrao")



            p_icon = "🚚" if p_key == "anjun" else ("📦" if p_key == "imile" else "⚡")

            p_nome_base = "Anjun Express" if p_key == "anjun" else ("iMile Delivery" if p_key == "imile" else "Loggi")



            if not c_list:

                opcoes_contas.append({

                    "plataforma": p_key,

                    "conta_id": "padrao",

                    "nome": p_nome_base,

                    "apelido": "Principal",

                    "icone": p_icon,

                    "selecionada": bool(p_key == plat and cid in ["padrao", "", c_ativa_p])

                })

            else:

                for c in c_list:

                    c_apelido = c.get("apelido") or c.get("login_usuario") or c.get("id")

                    nome_completo = f"{p_nome_base} ({c_apelido})"

                    opcoes_contas.append({

                        "plataforma": p_key,

                        "conta_id": c.get("id"),

                        "nome": nome_completo,

                        "apelido": c_apelido,

                        "icone": p_icon,

                        "selecionada": bool(p_key == plat and c.get("id") == cid)

                    })



        contagem_mot = contagem_motoristas.get(motorista_atribuicao_ativa, 0) if motorista_atribuicao_ativa else 0

        total_hoje = sum(contagem_motoristas.values()) if contagem_motoristas else 0



        # Carrega grupos da Loggi com cache de 10s para garantir resposta instantânea e estável ao coletor

        grupos_loggi_coletor = []

        if plat == 'loggi':

            agora = time.time()

            if agora - _cache_grupos_loggi_coletor["ts"] < 10.0 and _cache_grupos_loggi_coletor["grupos"]:

                grupos_loggi_coletor = _cache_grupos_loggi_coletor["grupos"]

            else:

                try:

                    grupos_buscados = loggi_listar_grupos_api() or []

                    _cache_grupos_loggi_coletor["ts"] = agora

                    _cache_grupos_loggi_coletor["grupos"] = grupos_buscados

                    grupos_loggi_coletor = grupos_buscados

                except Exception:

                    grupos_loggi_coletor = _cache_grupos_loggi_coletor.get("grupos", [])



        cidades_base = []

        try:

            cidades_base = carregar_cidades() or []

        except Exception:

            pass



        return jsonify({

            "status": "sucesso",

            "plataforma": plat,

            "conta_id": cid,

            "opcoes_contas": opcoes_contas,

            "motorista_ativo": motorista_atribuicao_ativa or "",

            "contagem": contagem_mot,

            "motoristas": sorted(list(set(mots))),

            "cidades": cidades_base,

            "grupos_loggi": grupos_loggi_coletor,

            "contagem_total_hoje": total_hoje,

            "grupo_loggi_ativo": (grupo_loggi_ativo if plat == "loggi" else None)

        })

    except Exception as e:

        return jsonify({"status": "erro", "mensagem": str(e)}), 500



@app.route('/api/coletor/trocar-plataforma', methods=['POST'])

def rota_coletor_trocar_plataforma():

    global plataforma_ativa, motorista_atribuicao_ativa, conta_ativa

    dados = request.get_json(force=True) or {}

    nova_plat = str(dados.get("plataforma") or "").strip().lower()

    nova_conta = str(dados.get("conta_id") or dados.get("conta") or "").strip() or None

    if nova_plat in ['anjun', 'imile', 'loggi']:

        global _init_seq_id

        _init_seq_id += 1

        plataforma_ativa = nova_plat

        motorista_atribuicao_ativa = None

        if nova_conta:

            conta_ativa = nova_conta

        print(f"[Coletor Mobile] Plataforma alterada para: {nova_plat.upper()} (Conta: {nova_conta or 'padrao'})")



        def _abrir_chrome_coletor_bg(p, c):

            try:

                time.sleep(0.1)

                with driver_lock:

                    _, porta, cid_resolvido, _ = obter_perfil_e_porta_conta(p, c)

                    if not is_chrome_debug_active(porta) or not chrome_tem_janela_visivel_na_tela(porta):

                        print(f"[Coletor Mobile] Abrindo Chrome para {p.upper()} (porta {porta})...")

                        inicializar_selenium(p, cid_resolvido)

                    else:

                        if not driver or plataforma_ativa != p or (cid_resolvido and conta_ativa != cid_resolvido):

                            conectar_chrome_existente(p, cid_resolvido)

                        forcar_janela_chrome_visivel(porta)

                    salvar_sessao_ativa(p, None, 0, cid_resolvido)

                    if p == 'anjun':

                        try:

                            fechar_avisos_todas_abas_anjun(driver)

                        except Exception:

                            pass

                    print(f"[Coletor Mobile] Chrome para {p.upper()} pronto e focado no computador central!")

            except Exception as e_ch:

                print(f"[Coletor Mobile] Aviso ao focar/iniciar Chrome para {p}: {e_ch}")



        import threading

        threading.Thread(target=_abrir_chrome_coletor_bg, args=(nova_plat, nova_conta), daemon=True).start()

        return jsonify({"status": "sucesso", "plataforma": nova_plat, "conta_id": nova_conta})

    return jsonify({"status": "erro", "mensagem": "Plataforma inválida"}), 400



@app.route('/api/coletor/trocar-motorista', methods=['POST'])

def rota_coletor_trocar_motorista():

    global motorista_atribuicao_ativa

    dados = request.get_json(force=True) or {}

    novo_mot = str(dados.get("motorista") or "").strip()

    motorista_atribuicao_ativa = novo_mot if novo_mot not in ["", "---", "Sem Motorista"] else None

    print(f"[Coletor Mobile] Motorista ativo alterado para: {motorista_atribuicao_ativa or 'Nenhum'}")

    return jsonify({"status": "sucesso", "motorista": motorista_atribuicao_ativa or ""})





if __name__ == '__main__':

    # Inicializa o banco de dados SQLite e realiza migração dos JSONs legados

    inicializar_db()

    

    # Mantém a inicialização das configurações de plataformas

    carregar_plataformas()

    

    # Executa sincronização do Excel, aquecimento de HWID e restauração de sessão em background para liberar a porta 5055 imediatamente

    threading.Thread(target=_tarefas_boot_background, daemon=True).start()

    

    print("=" * 60)

    print(" SERVIDOR MULTI-PLATAFORMA DA TRIAGEM LOGÍSTICA INICIADO")

    print(" Porta: 5055 | CORS Habilitado")

    print("=" * 60)

    app.run(host='0.0.0.0', port=5055, threaded=True)



