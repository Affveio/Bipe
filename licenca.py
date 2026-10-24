# -*- coding: utf-8 -*-
"""
Módulo de Proteção de Hardware e Licenciamento
Galpão Monitored - Sistema de Triagem Logística
"""

import os
import sys
import json
import base64
import hmac
import hashlib
import subprocess
import datetime

# Chave mestra interna usada para assinar digitalmente as licenças.
# Nenhuma chave gerada por terceiros será aceita sem esta assinatura.
MASTER_SECRET_KEY = b"GS_LOGISTICA_PROT_2026_MASTER_SECRET_9874#!"

def get_base_dir():
    raw_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    try:
        test_file = os.path.join(raw_dir, ".write_test_lic.tmp")
        with open(test_file, "w") as f:
            f.write("1")
        os.remove(test_file)
        return raw_dir
    except Exception:
        appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        fallback_dir = os.path.join(appdata, "TurboScan", "core-engine")
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir

BASE_DIR = get_base_dir()
LICENSE_FILE = os.path.join(BASE_DIR, "license.key")
STATE_FILE = os.path.join(BASE_DIR, ".sys_meta.dat")


def obter_versao_instalada():
    """Lê a versão dinâmica a partir do versao.json local ou package.json."""
    candidates = [
        os.path.join(BASE_DIR, "versao.json"),
        os.path.join(os.getcwd(), "versao.json"),
        os.path.join(os.getcwd(), "core-engine", "versao.json"),
        os.path.abspath(os.path.join(BASE_DIR, "..", "versao.json"))
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    v = str(dados.get("versao") or "").strip()
                    if v:
                        return v
            except Exception:
                pass
    return "2.4.2"


def _get_machine_guid():
    """Lê o GUID exclusivo do Windows do registro."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            return winreg.QueryValueEx(key, "MachineGuid")[0].strip()
    except Exception:
        return "NO_GUID"


def _get_motherboard_uuid():
    """Obtém o UUID da placa-mãe do Windows via WMIC ou PowerShell CIM."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    # 1. Tenta WMIC
    try:
        out = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            creationflags=flags,
            timeout=2
        )
        lines = [l.strip() for l in out.splitlines() if l.strip() and "UUID" not in l.upper()]
        if lines and lines[0]:
            return lines[0]
    except Exception:
        pass

    # 2. Tenta PowerShell CIM como alternativa
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"]
        out = subprocess.check_output(
            cmd,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            creationflags=flags,
            timeout=3
        ).strip()
        if out:
            return out
    except Exception:
        pass

    return "NO_MBOARD_UUID"


def _get_processor_id():
    """Obtém o ID do processador."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    try:
        out = subprocess.check_output(
            "wmic cpu get processorid",
            shell=True,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            creationflags=flags,
            timeout=2
        )
        lines = [l.strip() for l in out.splitlines() if l.strip() and "PROCESSORID" not in l.upper()]
        if lines and lines[0]:
            return lines[0]
    except Exception:
        pass
    try:
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", "(Get-CimInstance -ClassName Win32_Processor).ProcessorId"]
        out = subprocess.check_output(
            cmd,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            creationflags=flags,
            timeout=3
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return "NO_CPU_ID"


import threading
_CACHED_HWID = None
_HWID_LOCK = threading.Lock()
_ULTIMA_BUSCA_NUVEM_SEM_CHAVE = 0.0

def obter_hwid():
    """
    Gera o Hardware ID (HWID) único e imutável para a máquina atual.
    Retorna no formato: GS-XXXX-XXXX-XXXX com cache ultra-rápido vinculado ao hostname da máquina.
    """
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    with _HWID_LOCK:
        if _CACHED_HWID:
            return _CACHED_HWID

        import socket
        host_atual = (socket.gethostname() or "PC").strip().upper()
        cache_paths = [
            os.path.join(os.path.expanduser("~"), ".turboscan_hwid.dat"),
            os.path.join(BASE_DIR, ".hwid_cache.dat")
        ]
        for cp in cache_paths:
            if os.path.exists(cp):
                try:
                    with open(cp, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                        if "::" in val:
                            saved_host, saved_hwid = val.split("::", 1)
                            if saved_host == host_atual and saved_hwid.startswith("GS-") and len(saved_hwid) == 17:
                                _CACHED_HWID = saved_hwid
                                return _CACHED_HWID
                except Exception:
                    pass

        guid = _get_machine_guid()
        uuid = _get_motherboard_uuid()
        cpu = _get_processor_id()

        raw_signature = f"{guid}::{uuid}::{cpu}"
        digest = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest().upper()
        _CACHED_HWID = f"GS-{digest[:4]}-{digest[4:8]}-{digest[8:12]}"

        for cp in cache_paths:
            try:
                with open(cp, "w", encoding="utf-8") as f:
                    f.write(f"{host_atual}::{_CACHED_HWID}")
            except Exception:
                pass

        return _CACHED_HWID


PLATAFORMAS_TODAS = ["anjun", "imile", "loggi"]
PLATAFORMAS_LOCAL_FILE = os.path.join(BASE_DIR, "plataformas_licenca.json")


def normalizar_lista_plataformas(raw):
    """Normaliza uma lista ou string de plataformas para IDs válidos (anjun, imile, loggi, magalog)."""
    if not raw:
        return []
    if isinstance(raw, str):
        itens = [x.strip().lower() for x in raw.replace(";", ",").split(",") if x.strip()]
    elif isinstance(raw, (list, tuple, set)):
        itens = [str(x).strip().lower() for x in raw if str(x).strip()]
    else:
        return []

    resultado = []
    for item in itens:
        p = item
        if "anjun" in p:
            p = "anjun"
        elif "imile" in p or "mile" in p:
            p = "imile"
        elif "loggi" in p or "arco" in p:
            p = "loggi"
        elif "maga" in p:
            p = "magalog"
        if p in PLATAFORMAS_TODAS and p not in resultado:
            resultado.append(p)
    return resultado


def obter_override_plataformas_local():
    """Lê configuração local de plataformas liberadas (se existir)."""
    if os.path.exists(PLATAFORMAS_LOCAL_FILE):
        try:
            with open(PLATAFORMAS_LOCAL_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
                plats = normalizar_lista_plataformas(dados.get("plataformas_liberadas"))
                if plats:
                    return plats
        except Exception:
            pass
    return None


def salvar_override_plataformas_local(plataformas):
    """Salva localmente a lista de plataformas liberadas nesta máquina e limpa cache."""
    plats = normalizar_lista_plataformas(plataformas)
    if not plats:
        return False, "Selecione pelo menos uma empresa/plataforma para liberar."
    try:
        with open(PLATAFORMAS_LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump({"plataformas_liberadas": plats, "atualizado_em": datetime.datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)
        _CACHE_VALIDACAO_NUVEM["timestamp"] = 0
        return True, plats
    except Exception as e:
        return False, str(e)


def _extrair_plataformas_licenca(lic_dict, permitir_override_local=True, priorizar_override_local=False):
    """
    Extrai as plataformas liberadas de um registro do Supabase (coluna observacoes com [PLATS:...])
    ou do payload de uma chave GSKEY. Se não especificado, usa override local ou libera todas por padrão.
    """
    import re
    if permitir_override_local and priorizar_override_local:
        local_plats = obter_override_plataformas_local()
        if local_plats:
            return local_plats

    if isinstance(lic_dict, dict):
        # 1. Tag [PLATS:anjun,imile,...] dentro de observacoes ou plano (Supabase)
        obs = str(lic_dict.get("observacoes") or "") + " " + str(lic_dict.get("plano") or "")
        match = re.search(r"\[PLATS:([^\]]+)\]", obs, re.IGNORECASE)
        if match:
            plats = normalizar_lista_plataformas(match.group(1))
            if plats:
                return plats

        # 2. Campo explícito no dicionário/payload
        for campo in ("plataformas_liberadas", "plataformas", "empresas_liberadas"):
            if campo in lic_dict and lic_dict[campo]:
                plats = normalizar_lista_plataformas(lic_dict[campo])
                if plats:
                    return plats

    # 3. Override local salvo na máquina
    if permitir_override_local:
        local_plats = obter_override_plataformas_local()
        if local_plats:
            return local_plats

    # 4. Padrão (retrocompatibilidade: Anjun, iMile, Loggi e Magalog)
    return list(PLATAFORMAS_TODAS)


def gerar_chave_licenca(hwid, dias_validade=30, cliente="Cliente Autorizado", tipo="mensal", plataformas=None):
    """
    Gera uma chave criptográfica assinada para um determinado HWID.
    (Utilizado pelo administrador/dono para enviar ao cliente).
    """
    hoje = datetime.date.today()
    expiracao = hoje + datetime.timedelta(days=int(dias_validade))
    plats = normalizar_lista_plataformas(plataformas) or list(PLATAFORMAS_TODAS)

    payload = {
        "hwid": hwid.strip().upper(),
        "cliente": cliente.strip(),
        "tipo": tipo,
        "emissao": hoje.strftime("%Y-%m-%d"),
        "expiracao": expiracao.strftime("%Y-%m-%d"),
        "plataformas": plats,
    }

    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8")

    # Gera assinatura HMAC-SHA256
    assinatura = hmac.new(MASTER_SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    # Formato final da chave
    return f"GSKEY-{payload_b64}.{assinatura[:32]}"


def _verificar_adulteracao_relogio(hoje):
    """Protege contra o usuário voltar o relógio do Windows para tentar burlar a validade."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ultimo = datetime.datetime.fromisoformat(data.get("ultimo_uso", ""))
                if hoje < ultimo.date():
                    return False  # Relógio foi retrocedido!
        # Atualiza último uso
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ultimo_uso": datetime.datetime.now().isoformat()}, f)
    except Exception:
        pass
    return True


_CACHE_VALIDACAO_NUVEM = {
    "chave": None,
    "timestamp": 0,
    "resultado": None
}

SUPABASE_DEFAULT_URL = "https://bgrwwbyjltcghuhoflht.supabase.co"
SUPABASE_DEFAULT_KEY = "sb_publishable_0aq-oGnqS0BZoabeGbMlWA_oy-SlJ1l"


def _obter_config_supabase():
    cloud_cfg_path = os.path.join(BASE_DIR, "cloud_config.json")
    if os.path.exists(cloud_cfg_path):
        try:
            with open(cloud_cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return (
                    cfg.get("supabase_url", SUPABASE_DEFAULT_URL).strip().rstrip("/"),
                    cfg.get("supabase_anon_key", SUPABASE_DEFAULT_KEY).strip()
                )
        except Exception:
            pass
    return SUPABASE_DEFAULT_URL, SUPABASE_DEFAULT_KEY


def _validar_chave_gm_supabase(chave_gm, hwid_local, forcar_rede=False):
    """
    Valida uma chave no formato GM-XXXX-XXXX-XXXX gerada no Painel Admin (Supabase),
    verificando status ATIVA, data de vencimento, limite de computadores (HWID)
    e quais empresas/transportadoras (Anjun, iMile, Loggi, Magalog) foram contratadas.
    """
    import time
    import urllib.request
    import urllib.parse
    import socket

    agora_ts = time.time()
    if (
        not forcar_rede
        and _CACHE_VALIDACAO_NUVEM["chave"] == chave_gm
        and _CACHE_VALIDACAO_NUVEM["resultado"] is not None
        and (agora_ts - _CACHE_VALIDACAO_NUVEM["timestamp"] < 15)
    ):
        return _CACHE_VALIDACAO_NUVEM["resultado"]

    url_base, anon_key = _obter_config_supabase()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    try:
        chave_enc = urllib.parse.quote(chave_gm)
        url_lic = f"{url_base}/rest/v1/licencas?chave_licenca=eq.{chave_enc}&select=*,empresas(nome_fantasia)"
        req = urllib.request.Request(url_lic, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            lics = json.loads(resp.read().decode("utf-8"))

        if not lics or not isinstance(lics, list):
            res = {
                "valido": False,
                "motivo": "Chave de licença não encontrada! Verifique se digitou corretamente.",
                "codigo": "CHAVE_NAO_ENCONTRADA",
                "hwid_maquina": hwid_local
            }
            return res

        lic = lics[0]
        lic_id = lic.get("id")
        emp_id = lic.get("empresa_id")
        emp_obj = lic.get("empresas") or {}
        cliente_nome = emp_obj.get("nome_fantasia") if isinstance(emp_obj, dict) else "Cliente Autorizado"
        cliente_nome = cliente_nome or "Cliente Autorizado"
        status_lic = (lic.get("status") or "ATIVA").upper()
        expiracao_str = (lic.get("data_expiracao") or "2099-12-31")[:10]
        max_pcs = int(lic.get("max_computadores") or 1)
        plataformas_liberadas = _extrair_plataformas_licenca(lic, permitir_override_local=True)

        if status_lic == "BLOQUEADA" or status_lic == "CANCELADA":
            res = {
                "valido": False,
                "motivo": "Esta licença foi bloqueada pela administração. Entre em contato com o suporte.",
                "codigo": "BLOQUEADA",
                "cliente": cliente_nome,
                "hwid_maquina": hwid_local
            }
            _CACHE_VALIDACAO_NUVEM.update({"chave": chave_gm, "timestamp": agora_ts, "resultado": res})
            return res

        # Verifica e registra o computador (HWID) na tabela computadores mesmo se expirada (para vincular o terminal ao PIX)
        if lic_id:
            try:
                url_pcs = f"{url_base}/rest/v1/computadores?licenca_id=eq.{urllib.parse.quote(str(lic_id))}&select=*"
                req_pcs = urllib.request.Request(url_pcs, headers=headers, method="GET")
                with urllib.request.urlopen(req_pcs, timeout=4.0) as resp_pcs:
                    pcs = json.loads(resp_pcs.read().decode("utf-8")) or []

                nome_host = (socket.gethostname() or "TERMINAL-PC").strip()
                pc_atual = next((p for p in pcs if (p.get("hwid") or "").upper() == hwid_local.upper()), None)
                if not pc_atual and nome_host:
                    pc_atual = next((p for p in pcs if (p.get("nome_computador") or "").strip().upper() == nome_host.upper()), None)
                    if pc_atual and pc_atual.get("id"):
                        try:
                            upd_payload = json.dumps({
                                "hwid": hwid_local,
                                "versao_instalada": obter_versao_instalada(),
                                "ultimo_heartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            }).encode("utf-8")
                            req_upd = urllib.request.Request(
                                f"{url_base}/rest/v1/computadores?id=eq.{pc_atual.get('id')}",
                                data=upd_payload,
                                headers=headers,
                                method="PATCH"
                            )
                            urllib.request.urlopen(req_upd, timeout=3.0).close()
                        except Exception:
                            pass

                if pc_atual:
                    if (pc_atual.get("status") or "").upper() == "BLOQUEADO":
                        res = {
                            "valido": False,
                            "motivo": f"Este computador ({hwid_local}) foi bloqueado pelo administrador.",
                            "codigo": "TERMINAL_BLOQUEADO",
                            "cliente": cliente_nome,
                            "hwid_maquina": hwid_local,
                            "chave_licenca": chave_gm,
                            "licenca_id": lic_id
                        }
                        _CACHE_VALIDACAO_NUVEM.update({"chave": chave_gm, "timestamp": agora_ts, "resultado": res})
                        return res
                    elif pc_atual.get("id"):
                        global _ULTIMO_HEARTBEAT_ENVIADO
                        if agora_ts - globals().get("_ULTIMO_HEARTBEAT_ENVIADO", 0.0) > 45.0:
                            _ULTIMO_HEARTBEAT_ENVIADO = agora_ts
                            pc_id_hb = pc_atual.get("id")
                            def _patch_hb():
                                try:
                                    hb_payload = json.dumps({
                                        "status": "ONLINE",
                                        "versao_instalada": obter_versao_instalada(),
                                        "ultimo_heartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                    }).encode("utf-8")
                                    req_hb = urllib.request.Request(
                                        f"{url_base}/rest/v1/computadores?id=eq.{pc_id_hb}",
                                        data=hb_payload,
                                        headers=headers,
                                        method="PATCH"
                                    )
                                    urllib.request.urlopen(req_hb, timeout=3.0).close()
                                except Exception:
                                    pass
                            threading.Thread(target=_patch_hb, daemon=True).start()
                else:
                    plano_lic = (lic.get("plano") or "").lower()
                    eh_ilimitado = (max_pcs >= 999) or ("vital" in plano_lic) or (expiracao_str >= "2090-01-01")
                    if not eh_ilimitado and len(pcs) >= max_pcs:
                        res = {
                            "valido": False,
                            "motivo": f"Limite de computadores atingido para esta chave ({len(pcs)}/{max_pcs} em uso)!",
                            "codigo": "LIMITE_PCS",
                            "cliente": cliente_nome,
                            "hwid_maquina": hwid_local
                        }
                        return res
                    # Registra automaticamente o novo computador na licença
                    novo_pc_payload = json.dumps({
                        "empresa_id": emp_id,
                        "licenca_id": lic_id,
                        "nome_computador": nome_host,
                        "hwid": hwid_local,
                        "versao_instalada": obter_versao_instalada(),
                        "status": "ONLINE",
                        "ultimo_heartbeat": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }).encode("utf-8")
                    req_ins = urllib.request.Request(
                        f"{url_base}/rest/v1/computadores",
                        data=novo_pc_payload,
                        headers=headers,
                        method="POST"
                    )
                    urllib.request.urlopen(req_ins, timeout=4.0).close()
            except Exception:
                pass

        hoje = datetime.date.today()
        expiracao_date = datetime.datetime.strptime(expiracao_str, "%Y-%m-%d").date()
        dias_restantes = (expiracao_date - hoje).days

        if dias_restantes < 0:
            res = {
                "valido": False,
                "motivo": f"Período de acesso expirado em {expiracao_date.strftime('%d/%m/%Y')}! Realize a renovação para continuar.",
                "codigo": "EXPIRADA",
                "dias_restantes": 0,
                "expiracao": expiracao_date.strftime("%d/%m/%Y"),
                "cliente": cliente_nome,
                "hwid_maquina": hwid_local,
                "chave_licenca": chave_gm,
                "licenca_id": lic_id
            }
            _CACHE_VALIDACAO_NUVEM.update({"chave": chave_gm, "timestamp": agora_ts, "resultado": res})
            return res

        res = {
            "valido": True,
            "motivo": "Licença ativa e regular.",
            "codigo": "OK",
            "cliente": cliente_nome,
            "dias_restantes": dias_restantes,
            "expiracao": expiracao_date.strftime("%d/%m/%Y"),
            "expiracao_iso": expiracao_str,
            "hwid_maquina": hwid_local,
            "chave_licenca": chave_gm,
            "licenca_id": lic_id,
            "plataformas_liberadas": plataformas_liberadas
        }
        _CACHE_VALIDACAO_NUVEM.update({"chave": chave_gm, "timestamp": agora_ts, "resultado": res})
        return res

    except Exception as e_net:
        # Se já tinha validado antes na sessão e a internet oscilou, mantém o último estado válido
        if _CACHE_VALIDACAO_NUVEM["chave"] == chave_gm and _CACHE_VALIDACAO_NUVEM["resultado"]:
            return _CACHE_VALIDACAO_NUVEM["resultado"]
        return {
            "valido": False,
            "motivo": f"Não foi possível validar a chave na nuvem ({str(e_net)}). Verifique sua conexão.",
            "codigo": "ERRO_REDE",
            "hwid_maquina": hwid_local
        }


def validar_licenca(chave_string=None, forcar_rede=False):
    """
    Valida a licença atual (do arquivo ou string informada).
    Aceita tanto chaves GM-XXXX-XXXX-XXXX (Painel Admin Nuvem) quanto GSKEY-... (Assinatura Local).
    """
    hwid_local = obter_hwid()

    # Se não foi passada chave em string, lê do arquivo de licença local
    if not chave_string:
        candidates = [
            LICENSE_FILE,
            os.path.join(os.path.expanduser("~"), ".turboscan_license.key"),
            os.path.join(os.getcwd(), "license.key"),
            os.path.join(os.getcwd(), "core-engine", "license.key"),
            os.path.join(BASE_DIR, "license.key")
        ]
        for c in candidates:
            if os.path.exists(c):
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        chave_string = f.read().strip()
                        if chave_string:
                            break
                except Exception:
                    pass

        # Se não encontrou license.key no disco, tenta recuperar automaticamente pelo HWID ou nome_computador na nuvem
        global _ULTIMA_BUSCA_NUVEM_SEM_CHAVE
        import time as _time_lic
        agora_busca = _time_lic.time()
        if not chave_string and (forcar_rede or (agora_busca - _ULTIMA_BUSCA_NUVEM_SEM_CHAVE > 45.0)):
            _ULTIMA_BUSCA_NUVEM_SEM_CHAVE = agora_busca
            try:
                import urllib.request
                import urllib.parse
                import socket
                url_base, anon_key = _obter_config_supabase()
                headers = {
                    "apikey": anon_key,
                    "Authorization": f"Bearer {anon_key}",
                    "Accept": "application/json"
                }
                url_pc = f"{url_base}/rest/v1/computadores?hwid=eq.{urllib.parse.quote(hwid_local)}&order=created_at.desc&limit=1&select=*,licencas(chave_licenca)"
                req_pc = urllib.request.Request(url_pc, headers=headers, method="GET")
                with urllib.request.urlopen(req_pc, timeout=2.5) as resp_pc:
                    pcs_found = json.loads(resp_pc.read().decode("utf-8")) or []
                if not pcs_found:
                    nome_host = (socket.gethostname() or "").strip()
                    if nome_host:
                        url_host = f"{url_base}/rest/v1/computadores?nome_computador=eq.{urllib.parse.quote(nome_host)}&order=created_at.desc&limit=1&select=*,licencas(chave_licenca)"
                        req_host = urllib.request.Request(url_host, headers=headers, method="GET")
                        with urllib.request.urlopen(req_host, timeout=2.5) as resp_host:
                            pcs_found = json.loads(resp_host.read().decode("utf-8")) or []
                if pcs_found and isinstance(pcs_found, list):
                    lic_rel = pcs_found[0].get("licencas") or {}
                    chave_rec = (lic_rel.get("chave_licenca") or "").strip()
                    if chave_rec:
                        chave_string = chave_rec
                        for path_save in [LICENSE_FILE, os.path.join(os.path.expanduser("~"), ".turboscan_license.key")]:
                            try:
                                with open(path_save, "w", encoding="utf-8") as f_rec:
                                    f_rec.write(chave_string)
                            except Exception:
                                pass
            except Exception:
                pass

        if not chave_string:
            return {
                "valido": False,
                "motivo": "Sistema aguardando ativação. Insira sua chave de licença para liberar o terminal.",
                "codigo": "SEM_LICENCA",
                "hwid_maquina": hwid_local
            }

    chave_string = chave_string.strip()

    # 1. Suporte às chaves GM-XXXX-XXXX-XXXX geradas no Painel Admin (Central de Gestão Administrativa)
    if chave_string.upper().startswith("GM-"):
        return _validar_chave_gm_supabase(chave_string.upper(), hwid_local, forcar_rede=forcar_rede)

    # 2. Suporte às chaves criptográficas locais GSKEY-...
    if not chave_string.startswith("GSKEY-") or "." not in chave_string:
        return {
            "valido": False,
            "motivo": "Formato de chave de licença inválido! Use uma chave GM-XXXX-XXXX-XXXX.",
            "codigo": "FORMATO_INVALIDO",
            "hwid_maquina": hwid_local
        }

    try:
        chave_limpa = str(chave_string).strip()
        sem_prefixo = chave_limpa[6:]  # remove GSKEY-
        payload_b64, assinatura_fornecida = sem_prefixo.split(".", 1)
        assinatura_fornecida = assinatura_fornecida.strip()

        assinatura_esperada = hmac.new(MASTER_SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(assinatura_fornecida, assinatura_esperada):
            return {
                "valido": False,
                "motivo": "Chave de licença inválida ou falsificada!",
                "codigo": "CHAVE_FALSIFICADA",
                "hwid_maquina": hwid_local
            }

        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)

        hwid_licenca = payload.get("hwid", "").upper()
        cliente = payload.get("cliente", "Desconhecido")
        expiracao_str = payload.get("expiracao", "")
        plataformas_liberadas = _extrair_plataformas_licenca(payload, permitir_override_local=True, priorizar_override_local=True)

        if hwid_licenca != "*" and hwid_licenca != hwid_local:
            return {
                "valido": False,
                "motivo": f"Esta licença foi gerada para outra máquina ({hwid_licenca}). O ID desta máquina é {hwid_local}.",
                "codigo": "MAQUINA_INCORRETA",
                "hwid_maquina": hwid_local,
                "hwid_licenca": hwid_licenca,
                "cliente": cliente
            }

        hoje = datetime.date.today()
        if not _verificar_adulteracao_relogio(hoje):
            return {
                "valido": False,
                "motivo": "Alteração no relógio do sistema detectada! Acerte a data e hora do Windows.",
                "codigo": "RELOGIO_ADULTERADO",
                "hwid_maquina": hwid_local
            }

        expiracao_date = datetime.datetime.strptime(expiracao_str, "%Y-%m-%d").date()
        dias_restantes = (expiracao_date - hoje).days

        if dias_restantes < 0:
            return {
                "valido": False,
                "motivo": f"Licença expirada em {expiracao_date.strftime('%d/%m/%Y')}! Renove sua mensalidade.",
                "codigo": "EXPIRADA",
                "dias_restantes": 0,
                "expiracao": expiracao_str,
                "cliente": cliente,
                "hwid_maquina": hwid_local
            }

        return {
            "valido": True,
            "motivo": "Licença ativa e regular.",
            "codigo": "OK",
            "cliente": cliente,
            "dias_restantes": dias_restantes,
            "expiracao": expiracao_date.strftime("%d/%m/%Y"),
            "expiracao_iso": expiracao_str,
            "hwid_maquina": hwid_local,
            "plataformas_liberadas": plataformas_liberadas
        }

    except Exception as e:
        return {
            "valido": False,
            "motivo": f"Erro ao processar licença: {str(e)}",
            "codigo": "ERRO_INTERNO",
            "hwid_maquina": hwid_local
        }


def salvar_licenca(chave_string):
    """
    Grava a chave de licença no arquivo local se for válida para esta máquina.
    Mesmo se a chave estiver EXPIRADA (ex: teste de bloqueio), grava no arquivo para vincular a cobrança PIX.
    """
    chave_string = chave_string.strip()
    if chave_string.upper().startswith("GM-"):
        chave_string = chave_string.upper()
    if os.path.exists(PLATAFORMAS_LOCAL_FILE):
        try:
            os.remove(PLATAFORMAS_LOCAL_FILE)
        except Exception:
            pass
    resultado = validar_licenca(chave_string, forcar_rede=True)
    if not resultado["valido"]:
        if resultado.get("codigo") == "EXPIRADA":
            for path_save in [LICENSE_FILE, os.path.join(os.path.expanduser("~"), ".turboscan_license.key")]:
                try:
                    with open(path_save, "w", encoding="utf-8") as f:
                        f.write(chave_string)
                except Exception:
                    pass
        return False, resultado["motivo"]

    try:
        for path_save in [LICENSE_FILE, os.path.join(os.path.expanduser("~"), ".turboscan_license.key")]:
            try:
                with open(path_save, "w", encoding="utf-8") as f:
                    f.write(chave_string)
            except Exception:
                pass
        return True, "Licença instalada e ativada com sucesso!"
    except Exception as e:
        return False, f"Falha ao salvar licença: {str(e)}"

