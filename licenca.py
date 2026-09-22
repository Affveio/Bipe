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

# Caminho do arquivo de licença local
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LICENSE_FILE = os.path.join(BASE_DIR, "license.key")
STATE_FILE = os.path.join(BASE_DIR, ".sys_meta.dat")


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
    # 1. Tenta WMIC
    try:
        out = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=3
        )
        lines = [l.strip() for l in out.splitlines() if l.strip() and "UUID" not in l.upper()]
        if lines and lines[0]:
            return lines[0]
    except Exception:
        pass

    # 2. Tenta PowerShell CIM como alternativa
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"]
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=4
        ).strip()
        if out:
            return out
    except Exception:
        pass

    return "NO_MBOARD_UUID"


def _get_processor_id():
    """Obtém o ID do processador."""
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance -ClassName Win32_Processor).ProcessorId"]
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            timeout=4
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return "NO_CPU_ID"


_CACHED_HWID = None

def obter_hwid():
    """
    Gera o Hardware ID (HWID) único e imutável para a máquina atual.
    Retorna no formato: GS-XXXX-XXXX-XXXX com cache ultra-rápido.
    """
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    hwid_cache_file = os.path.join(BASE_DIR, ".hwid_cache.dat")
    if os.path.exists(hwid_cache_file):
        try:
            with open(hwid_cache_file, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val.startswith("GS-") and len(val) == 17:
                    _CACHED_HWID = val
                    return _CACHED_HWID
        except Exception:
            pass

    guid = _get_machine_guid()
    uuid = _get_motherboard_uuid()
    cpu = _get_processor_id()

    raw_signature = f"{guid}::{uuid}::{cpu}"
    digest = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest().upper()
    _CACHED_HWID = f"GS-{digest[:4]}-{digest[4:8]}-{digest[8:12]}"

    try:
        with open(hwid_cache_file, "w", encoding="utf-8") as f:
            f.write(_CACHED_HWID)
    except Exception:
        pass

    return _CACHED_HWID


def gerar_chave_licenca(hwid, dias_validade=30, cliente="Cliente Autorizado", tipo="mensal"):
    """
    Gera uma chave criptográfica assinada para um determinado HWID.
    (Utilizado pelo administrador/dono para enviar ao cliente).
    """
    hoje = datetime.date.today()
    expiracao = hoje + datetime.timedelta(days=int(dias_validade))

    payload = {
        "hwid": hwid.strip().upper(),
        "cliente": cliente.strip(),
        "tipo": tipo,
        "emissao": hoje.strftime("%Y-%m-%d"),
        "expiracao": expiracao.strftime("%Y-%m-%d"),
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


def validar_licenca(chave_string=None):
    """
    Valida a licença atual (do arquivo ou string informada).
    Retorna dicionário com status detalhado:
    {
        "valido": bool,
        "motivo": str,
        "cliente": str,
        "dias_restantes": int,
        "expiracao": str,
        "hwid_maquina": str,
        "hwid_licenca": str
    }
    """
    hwid_local = obter_hwid()

    # Se não foi passada chave em string, lê do arquivo de licença local
    if not chave_string:
        if not os.path.exists(LICENSE_FILE):
            return {
                "valido": False,
                "motivo": "Nenhuma licença encontrada. Ativação necessária.",
                "codigo": "SEM_LICENCA",
                "hwid_maquina": hwid_local
            }
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                chave_string = f.read().strip()
        except Exception as e:
            return {
                "valido": False,
                "motivo": f"Erro ao ler arquivo de licença: {e}",
                "codigo": "ERRO_LEITURA",
                "hwid_maquina": hwid_local
            }

    chave_string = chave_string.strip()
    if not chave_string.startswith("GSKEY-") or "." not in chave_string:
        return {
            "valido": False,
            "motivo": "Formato de chave de licença inválido!",
            "codigo": "FORMATO_INVALIDO",
            "hwid_maquina": hwid_local
        }

    try:
        sem_prefixo = chave_string[6:]  # remove GSKEY-
        payload_b64, assinatura_fornecida = sem_prefixo.split(".", 1)

        # 1. Verifica integridade e autenticidade da assinatura
        assinatura_esperada = hmac.new(MASTER_SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(assinatura_fornecida, assinatura_esperada):
            return {
                "valido": False,
                "motivo": "Chave de licença inválida ou falsificada!",
                "codigo": "CHAVE_FALSIFICADA",
                "hwid_maquina": hwid_local
            }

        # 2. Decodifica o conteúdo
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)

        hwid_licenca = payload.get("hwid", "").upper()
        cliente = payload.get("cliente", "Desconhecido")
        expiracao_str = payload.get("expiracao", "")

        # 3. Verifica se a licença pertence a ESTA máquina (ou se é chave mestra coringa '*')
        if hwid_licenca != "*" and hwid_licenca != hwid_local:
            return {
                "valido": False,
                "motivo": f"Esta licença foi gerada para outra máquina ({hwid_licenca}). O ID desta máquina é {hwid_local}.",
                "codigo": "MAQUINA_INCORRETA",
                "hwid_maquina": hwid_local,
                "hwid_licenca": hwid_licenca,
                "cliente": cliente
            }

        # 4. Verifica data de expiração
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
            "hwid_maquina": hwid_local
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
    """
    chave_string = chave_string.strip()
    resultado = validar_licenca(chave_string)
    if not resultado["valido"]:
        return False, resultado["motivo"]

    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(chave_string)
        return True, "Licença instalada e ativada com sucesso!"
    except Exception as e:
        return False, f"Falha ao salvar licença: {str(e)}"
