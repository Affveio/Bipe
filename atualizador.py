# -*- coding: utf-8 -*-
"""
Módulo de Auto-Atualização pela Nuvem (GitHub)
Galpão Monitored - Sistema de Triagem Logística
Repositório Oficial: https://github.com/Affveio/Bipe
"""

import os
import sys
import json
import urllib.request
import urllib.error
import shutil
import datetime
import time

# Configurações do Repositório na Nuvem
GITHUB_USER = "Affveio"
GITHUB_REPO = "Bipe"
GITHUB_BRANCH = "main"

# URL base dos arquivos brutos (raw) no GitHub
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"
VERSAO_REMOTA_URL = f"{RAW_BASE_URL}/versao.json"

# Diretório base do sistema
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSAO_LOCAL_FILE = os.path.join(BASE_DIR, "versao.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups_atualizacao")

# Arquivos e pastas protegidos que NUNCA devem ser sobrescritos por atualização
ARQUIVOS_PROTEGIDOS = {
    "license.key",
    ".sys_meta.dat",
    "historico.db",
    "triagem.db",
    "config_plataformas.json",
    "config_cidades.json",
    "config_motoristas.json",
    "credenciais_locais.json",
    "gerar_licenca.py"  # Nunca sobrescrever ou baixar ferramenta do desenvolvedor
}


def obter_versao_local():
    """Lê as informações da versão instalada localmente."""
    if os.path.exists(VERSAO_LOCAL_FILE):
        try:
            with open(VERSAO_LOCAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Aviso] Erro ao ler versao.json local: {e}")
    
    # Fallback caso versao.json ainda não exista
    return {
        "versao": "2.0.0",
        "data": "2026-09-13",
        "titulo": "Versão Inicial",
        "descricao": "Galpão Monitored 2.0"
    }


def _comparar_versoes(v_atual, v_nova):
    """
    Compara duas strings de versão no formato semântico (ex: '2.0.0' vs '2.1.0').
    Retorna True se v_nova for estritamente superior a v_atual.
    """
    try:
        partes_atual = [int(p) for p in v_atual.strip().split(".") if p.isdigit()]
        partes_nova = [int(p) for p in v_nova.strip().split(".") if p.isdigit()]
        
        # Iguala o tamanho das listas
        max_len = max(len(partes_atual), len(partes_nova))
        partes_atual += [0] * (max_len - len(partes_atual))
        partes_nova += [0] * (max_len - len(partes_nova))
        
        return partes_nova > partes_atual
    except Exception:
        return v_nova.strip() != v_atual.strip()


def verificar_atualizacao():
    """
    Consulta o GitHub para checar se existe uma versão mais recente disponível.
    Retorna dicionário com os detalhes da checagem.
    """
    info_local = obter_versao_local()
    v_atual = info_local.get("versao", "2.0.0")

    try:
        # Consulta versao.json com timeout rápido (3.5 segundos) para não travar o painel
        req = urllib.request.Request(
            f"{VERSAO_REMOTA_URL}?_={int(time.time())}",
            headers={"User-Agent": "Galpao-Monitored-Updater/2.0"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as response:
            if response.status != 200:
                return {
                    "sucesso": False,
                    "mensagem": f"Servidor retornou código {response.status}",
                    "versao_atual": v_atual
                }
            
            conteudo = response.read().decode("utf-8")
            info_remota = json.loads(conteudo)

        v_nova = info_remota.get("versao", "2.0.0")
        tem_atualizacao = _comparar_versoes(v_atual, v_nova)

        return {
            "sucesso": True,
            "tem_atualizacao": tem_atualizacao,
            "versao_atual": v_atual,
            "versao_nova": v_nova,
            "data_lancamento": info_remota.get("data", ""),
            "titulo": info_remota.get("titulo", "Atualização Disponível"),
            "descricao": info_remota.get("descricao", "Melhorias de desempenho e correções gerais."),
            "arquivos": info_remota.get("arquivos", []),
            "url_repo": f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}"
        }

    except urllib.error.URLError as e:
        return {
            "sucesso": False,
            "tem_atualizacao": False,
            "versao_atual": v_atual,
            "mensagem": f"Sem conexão com o servidor de atualizações ({e.reason})"
        }
    except Exception as e:
        return {
            "sucesso": False,
            "tem_atualizacao": False,
            "versao_atual": v_atual,
            "mensagem": f"Falha ao verificar atualizações: {str(e)}"
        }


def aplicar_atualizacao(lista_arquivos=None):
    """
    Baixa os arquivos atualizados da nuvem (GitHub) e substitui os locais de forma segura.
    Garante backup prévio e NUNCA sobrescreve dados locais do cliente.
    """
    # 1. Verifica se há versão remota disponível
    check = verificar_atualizacao()
    if not check.get("sucesso"):
        return False, check.get("mensagem", "Erro ao conectar à nuvem.")

    if not check.get("tem_atualizacao") and not lista_arquivos:
        return True, f"O sistema já está na versão mais recente ({check.get('versao_atual')})."

    arquivos_para_baixar = lista_arquivos or check.get("arquivos", [])
    if not arquivos_para_baixar:
        # Arquivos padrão essenciais do sistema
        arquivos_para_baixar = ["app.py", "app.js", "index.html", "style.css", "licenca.py"]

    # 2. Cria pasta de backup com data e hora
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_backup_atual = os.path.join(BACKUP_DIR, f"backup_{timestamp}")
    try:
        os.makedirs(pasta_backup_atual, exist_ok=True)
    except Exception as e:
        print(f"[Aviso] Não foi possível criar pasta de backup: {e}")

    arquivos_atualizados = []
    erros = []

    print(f"[*] Iniciando atualização para versão {check.get('versao_nova')}...")

    # 3. Baixa e substitui cada arquivo
    for nome_arq in arquivos_para_baixar:
        nome_arq_limpo = os.path.basename(nome_arq.strip())
        
        # Proteção rígida contra sobrescrita de arquivos protegidos
        if nome_arq_limpo.lower() in {p.lower() for p in ARQUIVOS_PROTEGIDOS}:
            print(f"[*] Arquivo protegido ignorado por segurança: {nome_arq_limpo}")
            continue

        url_arquivo = f"{RAW_BASE_URL}/{nome_arq_limpo}?_={int(time.time())}"
        caminho_local = os.path.join(BASE_DIR, nome_arq_limpo)
        caminho_backup = os.path.join(pasta_backup_atual, nome_arq_limpo)

        try:
            req = urllib.request.Request(
                url_arquivo,
                headers={"User-Agent": "Galpao-Monitored-Updater/2.0"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status != 200:
                    erros.append(f"HTTP {resp.status} para {nome_arq_limpo}")
                    continue
                conteudo = resp.read()

            # Validação: se arquivo estiver vazio, não aplica
            if not conteudo or len(conteudo) < 10:
                erros.append(f"Conteúdo vazio recebido para {nome_arq_limpo}")
                continue

            # Faz backup do arquivo antigo caso ele já exista
            if os.path.exists(caminho_local):
                try:
                    shutil.copy2(caminho_local, caminho_backup)
                except Exception:
                    pass

            # Grava o novo arquivo
            with open(caminho_local, "wb") as f_out:
                f_out.write(conteudo)

            # Se for arquivo do frontend do Electron, sincroniza também na pasta app/src/renderer
            if nome_arq_limpo in ["app.js", "index.html", "style.css", "dashboard.html", "dashboard.js", "dashboard.css"]:
                renderer_dir = os.path.abspath(os.path.join(BASE_DIR, "..", "app", "src", "renderer"))
                if os.path.exists(renderer_dir):
                    renderer_file = os.path.join(renderer_dir, nome_arq_limpo)
                    try:
                        with open(renderer_file, "wb") as f_rend:
                            f_rend.write(conteudo)
                        print(f"[+] Atualizado também em app/src/renderer: {nome_arq_limpo}")
                    except Exception as e_rend:
                        print(f"[Aviso] Falha ao atualizar app/src/renderer/{nome_arq_limpo}: {e_rend}")

            arquivos_atualizados.append(nome_arq_limpo)
            print(f"[+] Atualizado: {nome_arq_limpo} ({len(conteudo)} bytes)")

        except Exception as e:
            erros.append(f"Erro em {nome_arq_limpo}: {str(e)}")
            print(f"[Erro] Falha ao atualizar {nome_arq_limpo}: {e}")

    if not arquivos_atualizados:
        return False, f"Nenhum arquivo pôde ser atualizado. Erros: {'; '.join(erros)}"

    # 4. Atualiza o versao.json local com a nova versão
    try:
        dados_nova_versao = {
            "versao": check.get("versao_nova"),
            "data": check.get("data_lancamento") or datetime.date.today().strftime("%Y-%m-%d"),
            "titulo": check.get("titulo"),
            "descricao": check.get("descricao"),
            "arquivos": arquivos_para_baixar,
            "ultima_atualizacao": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }
        with open(VERSAO_LOCAL_FILE, "w", encoding="utf-8") as f_ver:
            json.dump(dados_nova_versao, f_ver, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Aviso] Falha ao atualizar versao.json local: {e}")

    msg_sucesso = f"Sistema atualizado com sucesso para a versão {check.get('versao_nova')}! ({len(arquivos_atualizados)} arquivos atualizados)"
    if erros:
        msg_sucesso += f" Avisos: {'; '.join(erros)}"

    return True, msg_sucesso


if __name__ == "__main__":
    print("=" * 60)
    print("   VERIFICADOR DE ATUALIZAÇÕES - GALPÃO MONITORED")
    print("=" * 60)
    res = verificar_atualizacao()
    print(f"Versão Local:  {res.get('versao_atual')}")
    if res.get("sucesso"):
        print(f"Versão Nuvem:  {res.get('versao_nova')}")
        print(f"Atualização?:  {'SIM' if res.get('tem_atualizacao') else 'NÃO (Sistema Atualizado)'}")
        if res.get("tem_atualizacao"):
            print(f"Descrição:     {res.get('descricao')}")
            resp = input("\nDeseja aplicar a atualização agora? (S/N): ").strip().upper()
            if resp in ["S", "SIM"]:
                ok, msg = aplicar_atualizacao()
                print(f"[Resultado] {msg}")
    else:
        print(f"[Aviso] {res.get('mensagem')}")
