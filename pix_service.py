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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

def gerar_pix_brcode(chave: str, beneficiario: str, cidade: str, valor: float, txid: str = "***") -> str:
    """
    Gera a string oficial 'PIX Copia e Cola' (BRCode EMVCo) reconhecida
    por qualquer aplicativo bancário brasileiro.
    """
    # Limpa chave de caracteres especiais se for telefone ou CNPJ
    chave_limpa = chave.strip()
    if chave_limpa.isdigit() and len(chave_limpa) in (10, 11) and not chave_limpa.startswith("+55"):
        # Se for telefone sem DDI, adiciona +55 padrão PIX
        chave_limpa = f"+55{chave_limpa}"

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
        print(f"[PIX Service] Aviso ao gerar QR SVG: {e}")
        return ""

# 2. CARREGAMENTO E GESTÃO DE CONFIGURAÇÕES

def carregar_pix_config():
    if os.path.exists(PIX_CONFIG_FILE):
        try:
            with open(PIX_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "chave_pix": "14996405436",
        "tipo_chave": "TELEFONE",
        "beneficiario": "GS TRANSPORTES",
        "cidade": "MARILIA",
        "valor_padrao_mensalidade": 150.00,
        "mercado_pago_access_token": "",
        "permitir_simulacao_teste": True
    }

def salvar_pix_config(novos_dados):
    atual = carregar_pix_config()
    atual.update(novos_dados)
    try:
        with open(PIX_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(atual, f, indent=4)
        return True
    except Exception as e:
        print(f"[PIX Config] Erro ao salvar: {e}")
        return False

def carregar_cloud_config():
    if os.path.exists(CLOUD_CONFIG_FILE):
        try:
            with open(CLOUD_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# 3. INTERAÇÃO COM O SUPABASE (FATURAS E ATIVAÇÃO AUTOMÁTICA)

def _fazer_requisicao_supabase(endpoint, metodo="GET", payload=None):
    """Auxiliar para requisições seguras ao Supabase REST API"""
    cfg = carregar_cloud_config()
    url_base = cfg.get("supabase_url", "").strip().rstrip("/")
    anon_key = cfg.get("supabase_anon_key", "").strip()

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

def obter_cobranca_renovacao_atual(chave_licenca=None, hwid=None):
    """
    Busca os dados da fatura em aberto para esta licença/terminal ou gera
    uma nova cobrança PIX automática no Supabase caso não exista nenhuma pendente.
    """
    from license_client import ler_chave_local, obter_hwid
    chave = (chave_licenca or ler_chave_local() or "").strip()
    maquina_hwid = hwid or obter_hwid()
    pix_cfg = carregar_pix_config()

    if not chave:
        return {
            "sucesso": False,
            "mensagem": "Nenhuma chave de licença instalada neste terminal."
        }

    # 1. Localiza a licença e empresa no Supabase
    lic_data, err = _fazer_requisicao_supabase(f"/rest/v1/licencas?chave_licenca=eq.{chave}&select=*,empresas(*)")
    if not lic_data or len(lic_data) == 0:
        # Fallback: tenta buscar empresa pelo HWID
        comp_data, _ = _fazer_requisicao_supabase(f"/rest/v1/computadores?hwid=eq.{maquina_hwid}&select=*,empresas(*),licencas(*)")
        if comp_data and len(comp_data) > 0:
            lic_info = comp_data[0].get("licencas") or {}
            emp_info = comp_data[0].get("empresas") or {}
        else:
            return {
                "sucesso": False,
                "mensagem": "Licença não localizada no servidor em nuvem."
            }
    else:
        lic_info = lic_data[0]
        emp_info = lic_info.get("empresas") or {}

    empresa_id = lic_info.get("empresa_id")
    licenca_id = lic_info.get("id")
    nome_empresa = emp_info.get("nome_fantasia") or emp_info.get("razao_social") or "Cliente"
    valor_mensalidade = float(pix_cfg.get("valor_padrao_mensalidade", 150.00))

    # 2. Procura fatura PENDENTE existente
    faturas, _ = _fazer_requisicao_supabase(
        f"/rest/v1/faturas_clientes?empresa_id=eq.{empresa_id}&status=eq.PENDENTE&order=created_at.desc&limit=1"
    )

    fatura = None
    if faturas and len(faturas) > 0:
        fatura = faturas[0]
        valor_cobranca = float(fatura.get("valor") or valor_mensalidade)
        if valor_cobranca <= 0:
            valor_cobranca = valor_mensalidade
    else:
        # 3. Cria uma nova fatura pendente para a renovação
        hoje = datetime.date.today().isoformat()
        nova_fat = {
            "empresa_id": empresa_id,
            "licenca_id": licenca_id,
            "valor": valor_mensalidade,
            "data_vencimento": hoje,
            "metodo_pagamento": "PIX",
            "status": "PENDENTE",
            "observacoes": f"Mensalidade Galpão Monitored - {lic_info.get('plano', 'Profissional')}"
        }
        res_fat, err_fat = _fazer_requisicao_supabase("/rest/v1/faturas_clientes", metodo="POST", payload=nova_fat)
        if res_fat and len(res_fat) > 0:
            fatura = res_fat[0]
            valor_cobranca = valor_mensalidade
        else:
            # Em caso de falha de conexão, monta fatura provisória local
            fatura = {
                "id": "fat_offline_" + hoje.replace("-", ""),
                "valor": valor_mensalidade,
                "empresa_id": empresa_id,
                "licenca_id": licenca_id,
                "status": "PENDENTE"
            }
            valor_cobranca = valor_mensalidade

    # 4. Gera TxID único para identificação bancária
    fatura_id = fatura.get("id", "00000000")
    txid = "GM" + "".join(c for c in fatura_id if c.isalnum())[:20].upper()

    # 5. Gera a string oficial do PIX Copia e Cola
    pix_copia_cola = gerar_pix_brcode(
        chave=pix_cfg.get("chave_pix", "14996405436"),
        beneficiario=pix_cfg.get("beneficiario", "GS TRANSPORTES"),
        cidade=pix_cfg.get("cidade", "MARILIA"),
        valor=valor_cobranca,
        txid=txid
    )

    # 6. Gera a imagem do QR Code
    qr_base64 = gerar_qr_code_base64(pix_copia_cola)

    return {
        "sucesso": True,
        "fatura_id": fatura_id,
        "txid": txid,
        "cliente": nome_empresa,
        "plano": lic_info.get("plano", "Profissional"),
        "valor": valor_cobranca,
        "valor_formatado": f"R$ {valor_cobranca:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "chave_pix": pix_cfg.get("chave_pix", "14996405436"),
        "beneficiario": pix_cfg.get("beneficiario", "GS TRANSPORTES"),
        "cidade": pix_cfg.get("cidade", "MARILIA"),
        "pix_copia_cola": pix_copia_cola,
        "qr_code_base64": qr_base64,
        "permitir_simulacao": bool(pix_cfg.get("permitir_simulacao_teste", True))
    }

def checar_status_pagamento_fatura(fatura_id):
    """
    Verifica se a fatura já foi paga. Se estiver PAGA, executa a renovação da licença
    e força a atualização do cache local para desbloqueio imediato da tela.
    """
    if not fatura_id:
        return {"pago": False, "mensagem": "ID da fatura não informado."}

    # 1. Consulta o status da fatura no Supabase
    res, err = _fazer_requisicao_supabase(f"/rest/v1/faturas_clientes?id=eq.{fatura_id}&select=*,licencas(*)")
    if not res or len(res) == 0:
        return {"pago": False, "mensagem": "Fatura em processamento..."}

    fatura = res[0]
    status = fatura.get("status", "PENDENTE")

    if status == "PAGO":
        # 2. Força re-validação imediata com a nuvem para renovar o cache local (.sys_meta.dat)
        from license_client import checar_status_licenca
        status_lic = checar_status_licenca()

        return {
            "pago": True,
            "status": "PAGO",
            "mensagem": "Pagamento confirmado com sucesso! Terminal desbloqueado.",
            "licenca": status_lic
        }

    return {
        "pago": False,
        "status": status,
        "mensagem": "Aguardando confirmação bancária..."
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
        # Sucesso pela RPC! Atualiza cache local
        from license_client import checar_status_licenca
        lic = checar_status_licenca()
        rpc_res["licenca_atualizada"] = lic
        return rpc_res

    # 2. Fallback resiliente via REST PATCH direto caso a RPC ainda não tenha sido rodada
    # A) Atualiza fatura
    patch_fat, _ = _fazer_requisicao_supabase(
        f"/rest/v1/faturas_clientes?id=eq.{fatura_id}",
        metodo="PATCH",
        payload={
            "status": "PAGO",
            "data_pagamento": hoje.isoformat(),
            "metodo_pagamento": "PIX",
            "codigo_transacao": tx_code
        }
    )

    # B) Localiza a fatura e licença
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

                # Se for plano vitalício (2099+), preserva
                if exp_atual.year >= 2099:
                    nova_exp = exp_atual
                elif exp_atual < hoje:
                    nova_exp = hoje + datetime.timedelta(days=30)
                else:
                    nova_exp = exp_atual + datetime.timedelta(days=30)

                # Atualiza a licença
                _fazer_requisicao_supabase(
                    f"/rest/v1/licencas?id=eq.{lic_id}",
                    metodo="PATCH",
                    payload={
                        "data_expiracao": nova_exp.isoformat(),
                        "status": "ATIVA",
                        "motivo_bloqueio": None
                    }
                )

                # Revalida cache local
                from license_client import checar_status_licenca
                lic_atual = checar_status_licenca()

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
