# -*- coding: utf-8 -*-
"""
Módulo de Cobrança e Renovação Automática via PIX - Galpão Monitored
Geração de BRCode padrão Banco Central (EMVCo), consulta e liquidação de faturas.
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.error
import base64
import io

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
PIX_CONFIG_FILE = os.path.join(BASE_DIR, "pix_config.json")
CLOUD_CONFIG_FILE = os.path.join(BASE_DIR, "cloud_config.json")

# 1. FUNÇÕES CRIPTOGRÁFICAS E DE FORMATAÇÃO PADRÃO BANCO CENTRAL (EMVCo)

def crc16_ccitt(data: str) -> str:
    """Calcula o CRC-16 CCITT (polinômio 0x1021, valor inicial 0xFFFF)"""
    poly = 0x1021
    crc = 0xFFFF
    for byte in data.encode('utf-8'):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def format_tlv(tag: str, value: str) -> str:
    """Formata campo Tag-Length-Value com tamanho em bytes UTF-8"""
    encoded = value.encode('utf-8')
    return f"{tag}{len(encoded):02d}{value}"

def gerar_pix_brcode(chave: str, beneficiario: str, cidade: str, valor: float, txid: str = "***", tipo_chave: str = None) -> str:
    """
    Gera a string oficial 'PIX Copia e Cola' (BRCode EMVCo) reconhecida
    por qualquer aplicativo bancário brasileiro.
    """
    chave_limpa = chave.strip()
    tipo_up = (tipo_chave or "").strip().upper()

    if tipo_up == "CPF":
        # CPF são estritamente os 11 dígitos numéricos (sem +55)
        chave_limpa = "".join(c for c in chave_limpa if c.isdigit())[:11]
    elif tipo_up == "CNPJ":
        chave_limpa = "".join(c for c in chave_limpa if c.isdigit())[:14]
    elif tipo_up == "TELEFONE":
        so_digitos = "".join(c for c in chave_limpa if c.isdigit())
        if not chave_limpa.startswith("+55"):
            chave_limpa = f"+55{so_digitos}"
    elif tipo_up == "EMAIL":
        chave_limpa = chave_limpa.lower()
    else:
        # Fallback de autodetecção quando tipo não for especificado
        so_num = "".join(c for c in chave_limpa if c.isdigit())
        if "@" in chave_limpa:
            chave_limpa = chave_limpa.lower()
        elif len(so_num) == 14:
            chave_limpa = so_num
        elif len(so_num) == 11 and chave_limpa.startswith("+55"):
            chave_limpa = chave_limpa
        elif len(so_num) == 11:
            # Padrão para 11 dígitos sem +55: CPF
            chave_limpa = so_num

    # Limitações de tamanho do padrão BCB
    nome_beneficiario = (beneficiario or "GALPAO MONITORED").strip()[:25].upper()
    cidade_beneficiario = (cidade or "SAO PAULO").strip()[:15].upper()
    
    # TxID sanitizado (apenas letras e números, max 25 chars)
    txid_limpo = "".join(c for c in (txid or "***") if c.isalnum())[:25]
    if not txid_limpo:
        txid_limpo = "***"

    # Merchant Account Information (Tag 26)
    mai = format_tlv("00", "br.gov.bcb.pix") + format_tlv("01", chave_limpa)

    # Montagem de todos os campos EMVCo
    payload = (
        format_tlv("00", "01") +                          # Payload Format Indicator
        format_tlv("26", mai) +                           # Merchant Account Info
        format_tlv("52", "0000") +                        # Merchant Category Code
        format_tlv("53", "986") +                         # Currency (BRL)
        format_tlv("54", f"{float(valor):.2f}") +         # Transaction Amount
        format_tlv("58", "BR") +                          # Country Code
        format_tlv("59", nome_beneficiario) +             # Merchant Name
        format_tlv("60", cidade_beneficiario) +           # Merchant City
        format_tlv("62", format_tlv("05", txid_limpo)) +  # Additional Data (TxID)
        "6304"                                            # CRC16 Placeholder
    )

    crc = crc16_ccitt(payload)
    return payload + crc

def gerar_qr_code_base64(conteudo: str) -> str:
    """
    Gera a imagem do QR Code em formato Base64 Data URI (SVG).
    Totalmente vetorial, ultra nítido e sem dependência do Pillow.
    """
    try:
        import qrcode
        import qrcode.image.svg
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
            image_factory=qrcode.image.svg.SvgImage
        )
        qr.add_data(conteudo)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0b0f19", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/svg+xml;base64,{b64}"
    except Exception as e:
        print(f"[PIX Service] Aviso ao gerar QR SVG local: {e}. Usando fallback online.")
        import urllib.parse
        return f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&margin=2&data={urllib.parse.quote(conteudo)}"

# 2. CARREGAMENTO E GESTÃO DE CONFIGURAÇÕES (COM SINCRONIZAÇÃO EM NUVEM SUPABASE)

DEFAULT_SUPABASE_URL = "https://bgrwwbyjltcghuhoflht.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_0aq-oGnqS0BZoabeGbMlWA_oy-SlJ1l"
MATRIZ_EMPRESA_ID = "a0000000-0000-0000-0000-000000000001"
_CACHE_PIX_NUVEM = {"ts": 0, "dados": None}

def carregar_cloud_config():
    if os.path.exists(CLOUD_CONFIG_FILE):
        try:
            with open(CLOUD_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("supabase_url") and cfg.get("supabase_anon_key"):
                    return cfg
        except Exception:
            pass
    return {
        "supabase_url": DEFAULT_SUPABASE_URL,
        "supabase_anon_key": DEFAULT_SUPABASE_ANON_KEY
    }

def _fazer_requisicao_supabase(endpoint, metodo="GET", payload=None):
    """Auxiliar para requisições seguras ao Supabase REST API"""
    cfg = carregar_cloud_config()
    url_base = cfg.get("supabase_url", DEFAULT_SUPABASE_URL).strip().rstrip("/")
    anon_key = cfg.get("supabase_anon_key", DEFAULT_SUPABASE_ANON_KEY).strip()

    if not url_base or not anon_key:
        return None, "Supabase não configurado"

    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    url = f"{url_base}{endpoint}"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=metodo)

    try:
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            body = resp.read().decode("utf-8")
            return (json.loads(body) if body else {}), None
    except urllib.error.HTTPError as he:
        try:
            err = json.loads(he.read().decode("utf-8"))
            return None, err.get("message", f"HTTP {he.code}")
        except Exception:
            return None, f"HTTP {he.code}"
    except Exception as e:
        return None, str(e)

def carregar_pix_config(forcar_nuvem=False):
    import time
    config = {
        "provedor": "ASAAS",  # "ASAAS" ou "ESTATICO"
        "asaas_api_key": "",
        "asaas_ambiente": "PRODUCAO",  # "PRODUCAO" ou "SANDBOX"
        "cpf_cnpj_padrao_cliente": "36971699807",
        "chave_pix": "Chave Aleatória (QR Code)",
        "tipo_chave": "EVP",
        "beneficiario": "FERNANDO GOMEZ",
        "cidade": "BRASIL",
        "valor_padrao_mensalidade": 150.00,
        "mercado_pago_access_token": "",
        "permitir_simulacao_teste": True
    }
    if os.path.exists(PIX_CONFIG_FILE):
        try:
            with open(PIX_CONFIG_FILE, "r", encoding="utf-8") as f:
                local_cfg = json.load(f)
                if isinstance(local_cfg, dict):
                    config.update(local_cfg)
        except Exception:
            pass

    # Sincroniza configurações PIX/Asaas salvas na Central Admin (Supabase)
    agora = time.time()
    if forcar_nuvem or (agora - _CACHE_PIX_NUVEM["ts"] > 45):
        try:
            res, err = _fazer_requisicao_supabase(f"/rest/v1/empresas?id=eq.{MATRIZ_EMPRESA_ID}&select=configuracoes")
            if res and isinstance(res, list) and len(res) > 0:
                cfg_emp = res[0].get("configuracoes") or {}
                pix_nuvem = cfg_emp.get("pix_asaas")
                if isinstance(pix_nuvem, dict):
                    _CACHE_PIX_NUVEM["dados"] = pix_nuvem
                    _CACHE_PIX_NUVEM["ts"] = agora
        except Exception:
            pass

    if isinstance(_CACHE_PIX_NUVEM["dados"], dict):
        for k, v in _CACHE_PIX_NUVEM["dados"].items():
            if v is not None and v != "":
                config[k] = v

    return config

def salvar_pix_config(novos_dados):
    atual = carregar_pix_config()
    atual.update(novos_dados)
    try:
        with open(PIX_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(atual, f, indent=4)
    except Exception as e:
        print(f"[PIX Config] Erro ao salvar local: {e}")

    # Também salva no Supabase (Galpão Matriz) para sincronizar com todos os terminais
    try:
        res, _ = _fazer_requisicao_supabase(f"/rest/v1/empresas?id=eq.{MATRIZ_EMPRESA_ID}&select=configuracoes")
        cfg_emp = (res[0].get("configuracoes") or {}) if (res and isinstance(res, list) and len(res) > 0) else {}
        cfg_emp["pix_asaas"] = {
            "provedor": atual.get("provedor", "ASAAS"),
            "asaas_api_key": atual.get("asaas_api_key", ""),
            "asaas_ambiente": atual.get("asaas_ambiente", "PRODUCAO"),
            "cpf_cnpj_padrao_cliente": atual.get("cpf_cnpj_padrao_cliente", "36971699807"),
            "chave_pix": atual.get("chave_pix", "Chave Aleatória (QR Code)"),
            "tipo_chave": atual.get("tipo_chave", "EVP"),
            "beneficiario": atual.get("beneficiario", "FERNANDO GOMEZ"),
            "cidade": atual.get("cidade", "BRASIL"),
            "valor_padrao_mensalidade": float(atual.get("valor_padrao_mensalidade", 150.00))
        }
        _fazer_requisicao_supabase(
            f"/rest/v1/empresas?id=eq.{MATRIZ_EMPRESA_ID}",
            metodo="PATCH",
            payload={"configuracoes": cfg_emp}
        )
        _CACHE_PIX_NUVEM["dados"] = cfg_emp["pix_asaas"]
    except Exception as e_cloud:
        print(f"[PIX Config] Aviso ao sincronizar com nuvem: {e_cloud}")

    return True

# 3. INTEGRAÇÃO OFICIAL ASAAS API v3 (PIX DINÂMICO + BAIXA AUTOMÁTICA)

def _fazer_requisicao_asaas(endpoint, metodo="GET", payload=None, pix_cfg=None):
    cfg = pix_cfg or carregar_pix_config()
    api_key = str(cfg.get("asaas_api_key") or "").strip()
    if api_key.startswith("aact_"):
        api_key = "$" + api_key
    if not api_key:
        return None, "Chave de API do Asaas não configurada."

    ambiente = str(cfg.get("asaas_ambiente") or "PRODUCAO").strip().upper()
    if "_hmlg_" in api_key.lower():
        ambiente = "SANDBOX"
    base_url = "https://sandbox.asaas.com/api/v3" if ambiente == "SANDBOX" else "https://api.asaas.com/v3"

    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    url = f"{base_url}{endpoint}"
    headers = {
        "access_token": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "TurboScanPro/2.3.0"
    }

    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=metodo)

    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            body = resp.read().decode("utf-8")
            return (json.loads(body) if body else {}), None
    except urllib.error.HTTPError as he:
        try:
            err_json = json.loads(he.read().decode("utf-8"))
            errors = err_json.get("errors")
            if isinstance(errors, list) and len(errors) > 0:
                msg = errors[0].get("description") or f"HTTP {he.code}"
            else:
                msg = err_json.get("message") or f"HTTP {he.code}"
            return None, msg
        except Exception:
            return None, f"HTTP {he.code}"
    except Exception as e:
        return None, str(e)

def _obter_ou_criar_cliente_asaas(emp_info, pix_cfg):
    nome = (emp_info.get("nome_fantasia") or emp_info.get("razao_social") or "Cliente TurboScan").strip()
    doc_raw = "".join(c for c in str(emp_info.get("cnpj") or "") if c.isdigit())
    if len(doc_raw) not in (11, 14) or doc_raw in ("00000000000000", "00000000000", "0"):
        doc_raw = "".join(c for c in str(pix_cfg.get("cpf_cnpj_padrao_cliente") or "36971699807") if c.isdigit())
        if len(doc_raw) not in (11, 14) or doc_raw in ("0", "00000000000"):
            doc_raw = "36971699807"

    for candidato_doc in [doc_raw, "36971699807"]:
        # 1. Busca cliente existente pelo CPF/CNPJ no Asaas
        res_busca, err_busca = _fazer_requisicao_asaas(f"/customers?cpfCnpj={candidato_doc}&limit=1", metodo="GET", pix_cfg=pix_cfg)
        if res_busca and isinstance(res_busca.get("data"), list) and len(res_busca["data"]) > 0:
            return res_busca["data"][0].get("id"), None

        # 2. Cria novo cliente no Asaas
        novo_cli = {
            "name": nome,
            "cpfCnpj": candidato_doc,
            "notificationDisabled": True
        }
        res_cria, err_cria = _fazer_requisicao_asaas("/customers", metodo="POST", payload=novo_cli, pix_cfg=pix_cfg)
        if res_cria and res_cria.get("id"):
            return res_cria.get("id"), None

    return None, (err_cria or err_busca or "Não foi possível criar cliente no Asaas")

def _obter_ou_criar_cobranca_asaas(fatura, emp_info, valor_cobranca, pix_cfg):
    """
    Cria ou reaproveita uma cobrança PIX dinâmica no Asaas para a fatura atual.
    Retorna (qr_base64, pix_copia_cola, asaas_payment_id, erro).
    """
    fatura_id = str(fatura.get("id") or "")
    cod_tx = str(fatura.get("codigo_transacao") or "").strip()
    asaas_pay_id = None

    if cod_tx.startswith("ASAAS:"):
        asaas_pay_id = cod_tx.split("ASAAS:", 1)[1].strip()
    elif cod_tx.startswith("pay_"):
        asaas_pay_id = cod_tx

    # Se já existe um pagamento Asaas vinculado à fatura, verifica se ainda é válido
    if asaas_pay_id:
        pay_info, _ = _fazer_requisicao_asaas(f"/payments/{asaas_pay_id}", metodo="GET", pix_cfg=pix_cfg)
        if pay_info and not pay_info.get("deleted"):
            status_asaas = str(pay_info.get("status") or "").upper()
            valor_asaas = float(pay_info.get("value") or 0)
            if status_asaas in ("PENDING", "OVERDUE") and abs(valor_asaas - float(valor_cobranca)) < 0.05:
                qr_res, qr_err = _fazer_requisicao_asaas(f"/payments/{asaas_pay_id}/pixQrCode", metodo="GET", pix_cfg=pix_cfg)
                if qr_res and qr_res.get("payload"):
                    img_b64 = qr_res.get("encodedImage", "")
                    if img_b64 and not img_b64.startswith("data:image"):
                        img_b64 = f"data:image/png;base64,{img_b64}"
                    return img_b64, qr_res.get("payload"), asaas_pay_id, None

    # Cria ou localiza o cliente no Asaas
    customer_id, err_cli = _obter_ou_criar_cliente_asaas(emp_info, pix_cfg)
    if not customer_id:
        return None, None, None, err_cli

    hoje = datetime.date.today().isoformat()
    nome_empresa = emp_info.get("nome_fantasia") or emp_info.get("razao_social") or "Cliente"
    payload_cobranca = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": round(float(valor_cobranca), 2),
        "dueDate": hoje,
        "description": f"Licenca TurboScan Pro - {nome_empresa}",
        "externalReference": fatura_id
    }

    pay_criado, err_pay = _fazer_requisicao_asaas("/payments", metodo="POST", payload=payload_cobranca, pix_cfg=pix_cfg)
    if not pay_criado or not pay_criado.get("id"):
        return None, None, None, (err_pay or "Erro ao criar cobrança PIX no Asaas")

    asaas_pay_id = pay_criado.get("id")

    # Obtém o QR Code e Copia e Cola oficial do Asaas
    qr_res, qr_err = _fazer_requisicao_asaas(f"/payments/{asaas_pay_id}/pixQrCode", metodo="GET", pix_cfg=pix_cfg)
    if not qr_res or not qr_res.get("payload"):
        return None, None, asaas_pay_id, (qr_err or "Erro ao obter QR Code PIX do Asaas")

    pix_copia_cola = qr_res.get("payload")
    img_b64 = qr_res.get("encodedImage", "")
    if img_b64 and not img_b64.startswith("data:image"):
        img_b64 = f"data:image/png;base64,{img_b64}"

    # Salva o ID do pagamento Asaas e o payload na fatura do Supabase
    if fatura_id and not fatura_id.startswith("fat_offline_"):
        _fazer_requisicao_supabase(
            f"/rest/v1/faturas_clientes?id=eq.{fatura_id}",
            metodo="PATCH",
            payload={
                "codigo_transacao": f"ASAAS:{asaas_pay_id}",
                "comprovante_url": pix_copia_cola
            }
        )

    return img_b64, pix_copia_cola, asaas_pay_id, None

# 4. INTERAÇÃO COM O SUPABASE (FATURAS E ATIVAÇÃO AUTOMÁTICA)

def _ler_chave_licenca_instalada():
    from licenca import LICENSE_FILE as LIC_MAIN
    candidates = [
        LIC_MAIN,
        os.path.join(os.path.expanduser("~"), ".turboscan_license.key"),
        os.path.join(BASE_DIR, "license.key"),
        os.path.join(os.getcwd(), "license.key"),
        os.path.join(os.getcwd(), "core-engine", "license.key")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                    if val:
                        return val
            except Exception:
                pass
    return ""

def obter_cobranca_renovacao_atual(chave_licenca=None, hwid=None):
    """
    Busca os dados da fatura em aberto para esta licença/terminal ou gera
    uma nova cobrança PIX automática (via Asaas se configurado, ou BRCode estático) no Supabase.
    """
    import socket
    import urllib.parse
    from licenca import obter_hwid
    chave = (chave_licenca or _ler_chave_licenca_instalada() or "").strip()
    maquina_hwid = hwid or obter_hwid()
    pix_cfg = carregar_pix_config(forcar_nuvem=True)

    # 1. Localiza a licença e empresa no Supabase (por chave, pelo HWID/nome do computador ou última licença ativa/expirada)
    lic_data = None
    if chave:
        lic_data, _ = _fazer_requisicao_supabase(f"/rest/v1/licencas?chave_licenca=eq.{urllib.parse.quote(chave)}&select=*,empresas(*)")

    if not lic_data or len(lic_data) == 0:
        comp_data, _ = _fazer_requisicao_supabase(f"/rest/v1/computadores?hwid=eq.{urllib.parse.quote(maquina_hwid)}&order=created_at.desc&limit=1&select=*,empresas(*),licencas(*)")
        if not comp_data or len(comp_data) == 0:
            nome_host = (socket.gethostname() or "").strip()
            if nome_host:
                comp_data, _ = _fazer_requisicao_supabase(f"/rest/v1/computadores?nome_computador=eq.{urllib.parse.quote(nome_host)}&order=created_at.desc&limit=1&select=*,empresas(*),licencas(*)")
        if comp_data and len(comp_data) > 0 and comp_data[0].get("licencas"):
            lic_info = comp_data[0].get("licencas") or {}
            emp_info = comp_data[0].get("empresas") or {}
        else:
            lic_fallback, _ = _fazer_requisicao_supabase("/rest/v1/licencas?order=updated_at.desc&limit=1&select=*,empresas(*)")
            if lic_fallback and len(lic_fallback) > 0:
                lic_info = lic_fallback[0]
                emp_info = lic_info.get("empresas") or {}
            else:
                lic_info = {"id": None, "empresa_id": MATRIZ_EMPRESA_ID, "plano": "Profissional", "observacoes": ""}
                emp_info = {"id": MATRIZ_EMPRESA_ID, "nome_fantasia": "Cliente TurboScan", "configuracoes": {}}
    else:
        lic_info = lic_data[0]
        emp_info = lic_info.get("empresas") or {}

    empresa_id = lic_info.get("empresa_id")
    licenca_id = lic_info.get("id")
    nome_empresa = emp_info.get("nome_fantasia") or emp_info.get("razao_social") or "Cliente"
    valor_mensalidade = float(pix_cfg.get("valor_padrao_mensalidade", 150.00))
    valor_cadastrado_cliente = None

    # Verifica se há valor específico cadastrado na empresa (Gerenciamento de Clientes)
    emp_cfg = emp_info.get("configuracoes") if isinstance(emp_info.get("configuracoes"), dict) else {}
    if emp_cfg.get("valor_mensalidade"):
        try:
            v_emp = float(str(emp_cfg.get("valor_mensalidade")).replace(",", "."))
            if v_emp > 0:
                valor_cadastrado_cliente = v_emp
                valor_mensalidade = v_emp
        except Exception:
            pass

    # Verifica se há tag [VALOR:X.XX] específica na licença emitida no Painel Admin
    import re
    obs_lic = str(lic_info.get("observacoes") or "")
    m_val = re.search(r"\[VALOR:([0-9.,]+)\]", obs_lic, re.IGNORECASE)
    if m_val:
        try:
            v_lic = float(m_val.group(1).replace(",", "."))
            if v_lic > 0:
                valor_cadastrado_cliente = v_lic
                valor_mensalidade = v_lic
        except Exception:
            pass

    # 2. Procura fatura PENDENTE existente (prioriza a fatura mais recente criada no Admin)
    faturas, _ = _fazer_requisicao_supabase(
        f"/rest/v1/faturas_clientes?empresa_id=eq.{empresa_id}&status=eq.PENDENTE&order=created_at.desc&limit=1"
    )

    fatura = None
    if faturas and len(faturas) > 0:
        fatura = faturas[0]
        valor_cobranca = float(fatura.get("valor") or valor_mensalidade)
        if valor_cobranca <= 0:
            valor_cobranca = valor_mensalidade
        # Se o admin cadastrou/alterou o valor da licença ou do cliente no Painel Admin, garante que a fatura PENDENTE use esse valor exato
        if valor_cadastrado_cliente and valor_cadastrado_cliente > 0 and abs(valor_cobranca - valor_cadastrado_cliente) > 0.01:
            valor_cobranca = valor_cadastrado_cliente
            fatura["valor"] = valor_cobranca
            fatura["codigo_transacao"] = None
            fatura["comprovante_url"] = None
            if fatura.get("id"):
                _fazer_requisicao_supabase(
                    f"/rest/v1/faturas_clientes?id=eq.{fatura.get('id')}",
                    metodo="PATCH",
                    payload={"valor": valor_cobranca, "codigo_transacao": None, "comprovante_url": None}
                )
    else:
        # 3. Cria uma nova fatura pendente para a renovação com o valor exato cadastrado no Admin
        hoje = datetime.date.today().isoformat()
        nova_fat = {
            "empresa_id": empresa_id,
            "licenca_id": licenca_id,
            "valor": valor_mensalidade,
            "data_vencimento": hoje,
            "metodo_pagamento": "PIX",
            "status": "PENDENTE",
            "observacoes": f"Mensalidade TurboScan Pro - {lic_info.get('plano', 'Profissional')}"
        }
        res_fat, err_fat = _fazer_requisicao_supabase("/rest/v1/faturas_clientes", metodo="POST", payload=nova_fat)
        if res_fat and len(res_fat) > 0:
            fatura = res_fat[0]
            valor_cobranca = valor_mensalidade
        else:
            fatura = {
                "id": "fat_offline_" + hoje.replace("-", ""),
                "valor": valor_mensalidade,
                "empresa_id": empresa_id,
                "licenca_id": licenca_id,
                "status": "PENDENTE"
            }
            valor_cobranca = valor_mensalidade

    fatura_id = fatura.get("id", "00000000")
    txid = "GM" + "".join(c for c in str(fatura_id) if c.isalnum())[:20].upper()

    # 4. Verifica se o Asaas está ativo e configurado
    asaas_key = str(pix_cfg.get("asaas_api_key") or "").strip()
    provedor = str(pix_cfg.get("provedor") or "ASAAS").upper()
    qr_base64 = None
    pix_copia_cola = None
    aviso_asaas = None

    if asaas_key and provedor == "ASAAS":
        qr_asaas, payload_asaas, asaas_id, err_asaas = _obter_ou_criar_cobranca_asaas(fatura, emp_info, valor_cobranca, pix_cfg)
        if payload_asaas:
            pix_copia_cola = payload_asaas
            qr_base64 = qr_asaas or gerar_qr_code_base64(pix_copia_cola)
            txid = asaas_id or txid
        else:
            aviso_asaas = err_asaas
            print(f"[Asaas PIX] Aviso ao gerar cobrança dinâmica ({err_asaas}). Usando fallback BRCode.")

    # 5. Fallback para BRCode Estático caso Asaas ainda não tenha chave configurada
    if not pix_copia_cola:
        pix_copia_cola = gerar_pix_brcode(
            chave=pix_cfg.get("chave_pix", "36971699807"),
            beneficiario=pix_cfg.get("beneficiario", "FERNANDO GOMEZ"),
            cidade=pix_cfg.get("cidade", "BRASIL"),
            valor=valor_cobranca,
            txid=txid,
            tipo_chave=pix_cfg.get("tipo_chave", "CPF")
        )
        qr_base64 = gerar_qr_code_base64(pix_copia_cola)

    return {
        "sucesso": True,
        "fatura_id": fatura_id,
        "txid": txid,
        "provedor_ativo": "ASAAS" if (asaas_key and not aviso_asaas) else "ESTATICO",
        "aviso_provedor": aviso_asaas,
        "cliente": nome_empresa,
        "plano": lic_info.get("plano", "Profissional"),
        "valor": valor_cobranca,
        "valor_formatado": f"R$ {valor_cobranca:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "chave_pix": "Chave Aleatória (QR Code)",
        "beneficiario": pix_cfg.get("beneficiario", "FERNANDO GOMEZ"),
        "cidade": pix_cfg.get("cidade", "BRASIL"),
        "pix_copia_cola": pix_copia_cola,
        "qr_code_base64": qr_base64,
        "permitir_simulacao": bool(pix_cfg.get("permitir_simulacao_teste", True))
    }

def checar_status_pagamento_fatura(fatura_id):
    """
    Verifica se a fatura já foi paga (no Supabase ou diretamente na API do Asaas).
    Se estiver PAGA, executa a renovação automática de +30 dias da licença e
    desbloqueia o terminal na hora!
    """
    if not fatura_id:
        return {"pago": False, "mensagem": "ID da fatura não informado."}

    # 1. Consulta o status da fatura no Supabase
    res, err = _fazer_requisicao_supabase(f"/rest/v1/faturas_clientes?id=eq.{fatura_id}&select=*,licencas(*)")
    if not res or len(res) == 0:
        return {"pago": False, "mensagem": "Fatura em processamento..."}

    fatura = res[0]
    status = str(fatura.get("status") or "PENDENTE").upper()

    # 2. Se ainda estiver PENDENTE no Supabase, consulta em tempo real a API do Asaas!
    if status != "PAGO":
        pix_cfg = carregar_pix_config()
        asaas_key = str(pix_cfg.get("asaas_api_key") or "").strip()
        if asaas_key:
            cod_tx = str(fatura.get("codigo_transacao") or "").strip()
            asaas_pay_id = None
            if cod_tx.startswith("ASAAS:"):
                asaas_pay_id = cod_tx.split("ASAAS:", 1)[1].strip()
            elif cod_tx.startswith("pay_"):
                asaas_pay_id = cod_tx

            # 1. Verifica primeiro o paymentId associado diretamente
            pago_confirmado = False
            pago_pay_id = None

            if asaas_pay_id:
                pay_info, _ = _fazer_requisicao_asaas(f"/payments/{asaas_pay_id}", metodo="GET", pix_cfg=pix_cfg)
                if pay_info and str(pay_info.get("status") or "").upper() in ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"):
                    pago_confirmado = True
                    pago_pay_id = asaas_pay_id

            # 2. Se o ID gravado não constar como pago, busca todas as cobranças com a mesma externalReference (caso tenha gerado mais de uma tentativa)
            if not pago_confirmado and fatura_id:
                busca_ext, _ = _fazer_requisicao_asaas(f"/payments?externalReference={fatura_id}&limit=10", metodo="GET", pix_cfg=pix_cfg)
                if busca_ext and isinstance(busca_ext.get("data"), list):
                    for p in busca_ext["data"]:
                        if str(p.get("status") or "").upper() in ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"):
                            pago_confirmado = True
                            pago_pay_id = p.get("id")
                            break

            # 3. Fallback inteligente: busca se houve algum pagamento recente com o mesmo valor da fatura hoje
            if not pago_confirmado:
                busca_rec, _ = _fazer_requisicao_asaas("/payments?status=RECEIVED&limit=5", metodo="GET", pix_cfg=pix_cfg)
                if busca_rec and isinstance(busca_rec.get("data"), list):
                    val_esperado = float(fatura.get("valor") or 0)
                    for p in busca_rec["data"]:
                        val_p = float(p.get("value") or 0)
                        ref_p = str(p.get("externalReference") or "")
                        if ref_p == str(fatura_id) or (val_esperado > 0 and abs(val_p - val_esperado) < 0.05):
                            pago_confirmado = True
                            pago_pay_id = p.get("id")
                            break

            if pago_confirmado and pago_pay_id:
                # Pagamento confirmado no Asaas! Liquida a fatura e renova +30 dias no Supabase!
                confirmar_pagamento_e_renovar(fatura_id, codigo_transacao=f"ASAAS:{pago_pay_id}")
                status = "PAGO"

    if status == "PAGO":
        try:
            from licenca import _CACHE_VALIDACAO_NUVEM, validar_licenca
            _CACHE_VALIDACAO_NUVEM["timestamp"] = 0
            _CACHE_VALIDACAO_NUVEM["resultado"] = None
            status_lic = validar_licenca(forcar_rede=True)
        except Exception:
            from license_client import checar_status_licenca
            status_lic = checar_status_licenca(forcar=True)

        return {
            "pago": True,
            "status": "PAGO",
            "mensagem": "Pagamento confirmado com sucesso! Licença renovada e terminal desbloqueado.",
            "licenca": status_lic
        }

    return {
        "pago": False,
        "status": status,
        "mensagem": "Aguardando confirmação bancária do PIX..."
    }

def confirmar_pagamento_e_renovar(fatura_id, codigo_transacao=None):
    """
    Executa a confirmação de pagamento e a extensão automática de +30 dias na licença.
    Funciona via RPC ou direto via REST PATCH com resiliência total.
    """
    if not fatura_id:
        return {"sucesso": False, "mensagem": "Fatura ID ausente."}

    hoje = datetime.date.today()
    tx_code = codigo_transacao or f"PIX-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    # 1. Tenta acionar a RPC no Supabase
    rpc_res, rpc_err = _fazer_requisicao_supabase(
        "/rest/v1/rpc/confirmar_pagamento_e_renovar",
        metodo="POST",
        payload={"p_fatura_id": fatura_id, "p_codigo_transacao": tx_code}
    )

    if rpc_res and isinstance(rpc_res, dict) and rpc_res.get("sucesso"):
        try:
            from licenca import _CACHE_VALIDACAO_NUVEM, validar_licenca
            _CACHE_VALIDACAO_NUVEM["timestamp"] = 0
            _CACHE_VALIDACAO_NUVEM["resultado"] = None
            lic = validar_licenca(forcar_rede=True)
        except Exception:
            from license_client import checar_status_licenca
            lic = checar_status_licenca(forcar=True)
        rpc_res["licenca_atualizada"] = lic
        return rpc_res

    # 2. Fallback resiliente via REST PATCH direto
    _fazer_requisicao_supabase(
        f"/rest/v1/faturas_clientes?id=eq.{fatura_id}",
        metodo="PATCH",
        payload={
            "status": "PAGO",
            "data_pagamento": hoje.isoformat(),
            "metodo_pagamento": "PIX",
            "codigo_transacao": tx_code
        }
    )

    fats, _ = _fazer_requisicao_supabase(f"/rest/v1/faturas_clientes?id=eq.{fatura_id}&select=*")
    if fats and len(fats) > 0:
        fat = fats[0]
        empresa_id = fat.get("empresa_id")
        lic_id = fat.get("licenca_id")

        if not lic_id and empresa_id:
            lics, _ = _fazer_requisicao_supabase(f"/rest/v1/licencas?empresa_id=eq.{empresa_id}&order=created_at.desc&limit=1")
            if lics and len(lics) > 0:
                lic_id = lics[0].get("id")

        if lic_id:
            lics_info, _ = _fazer_requisicao_supabase(f"/rest/v1/licencas?id=eq.{lic_id}&select=*")
            if lics_info and len(lics_info) > 0:
                lic_rec = lics_info[0]
                exp_atual_str = lic_rec.get("data_expiracao", hoje.isoformat())
                try:
                    exp_atual = datetime.date.fromisoformat(exp_atual_str)
                except Exception:
                    exp_atual = hoje

                if exp_atual.year >= 2099:
                    nova_exp = exp_atual
                elif exp_atual < hoje:
                    nova_exp = hoje + datetime.timedelta(days=30)
                else:
                    nova_exp = exp_atual + datetime.timedelta(days=30)

                _fazer_requisicao_supabase(
                    f"/rest/v1/licencas?id=eq.{lic_id}",
                    metodo="PATCH",
                    payload={
                        "data_expiracao": nova_exp.isoformat(),
                        "status": "ATIVA",
                        "motivo_bloqueio": None
                    }
                )

                try:
                    from licenca import _CACHE_VALIDACAO_NUVEM, validar_licenca
                    _CACHE_VALIDACAO_NUVEM["timestamp"] = 0
                    _CACHE_VALIDACAO_NUVEM["resultado"] = None
                    lic_atual = validar_licenca(forcar_rede=True)
                except Exception:
                    from license_client import checar_status_licenca
                    lic_atual = checar_status_licenca(forcar=True)

                return {
                    "sucesso": True,
                    "codigo": "RENOVADO_COM_SUCESSO",
                    "mensagem": f"Pagamento PIX confirmado! Licença renovada até {nova_exp.strftime('%d/%m/%Y')}.",
                    "fatura_id": fatura_id,
                    "nova_expiracao": nova_exp.strftime("%d/%m/%Y"),
                    "licenca_atualizada": lic_atual
                }

    return {
        "sucesso": True,
        "mensagem": "Fatura marcada como PAGA com sucesso.",
        "fatura_id": fatura_id
    }
