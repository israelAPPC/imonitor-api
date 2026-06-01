import os
import random
import string
import stripe
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, Response
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session

import models
from database import engine, get_db
from pydantic import BaseModel

# Cria as tabelas do banco de dados (SQLite local)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="iMonitor License API")

# --- Configurações do Stripe ---
# IMPORTANTE: Essas chaves virão do painel do Stripe depois.
# Para agora, estamos usando variáveis de ambiente simuladas.
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_simulacao123")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_simulacao123")

def gerar_chave():
    """Gera uma chave aleatória no formato XXXX-XXXX-XXXX"""
    parts = [''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(3)]
    return f"IMONITOR-{'-'.join(parts)}"

def enviar_email_licenca(email_destino: str, chave: str, dias: int):
    """Envia a chave de licença para o e-mail do cliente via Gmail."""
    remetente = "imonitordfe@gmail.com"
    
    # Credenciais do Brevo
    smtp_login = "ac7d8b001@smtp-brevo.com"
    smtp_senha = "xsmtpsib-8047c857994e7fb77d9b39fe1801e642f1b637f485135ffed64c0cc307235117-wDAmhWlxKZUWjGrR"
    
    if email_destino == "cliente@desconhecido.com":
        return
        
    assunto = "Sua Licença do iMonitor Chegou! 🎉"
    
    plano_nome = "Mensal"
    if dias == 365: plano_nome = "Anual"
    elif dias == 180: plano_nome = "Semestral"
    elif dias == 90: plano_nome = "Trimestral"
    
    corpo = f"""Olá!

Obrigado por adquirir o iMonitor. Sua assinatura do Plano {plano_nome} foi confirmada com sucesso!

Aqui está a sua Chave de Licença ({dias} dias):
{chave}

COMO ATIVAR:
1. Abra o aplicativo iMonitor no seu computador.
2. Na tela de bloqueio, insira o seu CNPJ.
3. Cole a chave de licença acima e clique em "Ativar Licença".

Qualquer dúvida, estamos à disposição.
Equipe iMonitor
"""
    
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = email_destino
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
    
    try:
        # Usando o servidor do Brevo na porta 2525 para ignorar o Firewall do Render
        server = smtplib.SMTP('smtp-relay.brevo.com', 2525)
        server.starttls()
        server.login(smtp_login, smtp_senha)
        server.send_message(msg)
        server.quit()
        
        print(f"[E-MAIL] Licença enviada com sucesso para {email_destino}")
    except Exception as e:
        print(f"[ERRO E-MAIL] {e}")

class VerifyRequest(BaseModel):
    license_key: str
    cnpj: str

class TrialRequest(BaseModel):
    cnpj: str

@app.get("/")
def read_root():
    return {"status": "ok", "message": "iMonitor API is running"}

@app.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Recebe as notificações de pagamento do Stripe."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        # Quando tiver a chave real, descomente a linha abaixo e remova o mock:
        # event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        
        # Simulação para testes locais (aceita qualquer JSON como sucesso)
        import json
        event = json.loads(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Verifica se o evento é de um checkout completado (pagamento aprovado)
    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        
        email_cliente = session.get("customer_details", {}).get("email", "cliente@desconhecido.com")
        valor_pago = session.get("amount_total", 0) # Valor em centavos (ex: 39990 = R$ 399,90)
        
        stripe_customer_id = session.get("customer", None)
        stripe_subscription_id = session.get("subscription", None)
        
        # Extrair dados de contato / custom fields do Stripe
        nome_empresa = session.get("customer_details", {}).get("name", "")
        telefone = session.get("customer_details", {}).get("phone", "")
        cnpj_stripe = ""
        
        for field in session.get("custom_fields", []):
            label = field.get("label", {}).get("custom", "").lower()
            val = field.get("text", {}).get("value", "")
            if "cnpj" in label:
                cnpj_stripe = ''.join(filter(str.isdigit, val))
            elif "nome" in label or "empresa" in label:
                nome_empresa = val
            elif "telefone" in label or "celular" in label:
                telefone = val
                
        # Define limite e dias de validade
        dias = 30
        limite = 1
        
        # Mapeamento automático pelo valor pago (mensal)
        if valor_pago == 2990:
            limite = 1
        elif valor_pago == 3990:
            limite = 3
        elif valor_pago == 5990:
            limite = 5
        elif valor_pago >= 9990:
            limite = 10
            extras = valor_pago - 9990
            if extras > 0:
                limite += (extras // 590) # +1 CNPJ a cada R$ 5,90 extras
                
        # Leitura dos Metadados do Stripe (Conforme sua configuração no Dashboard)
        try:
            session_id = session.get("id")
            if session_id and stripe.api_key and "simulacao" not in stripe.api_key:
                line_items = stripe.checkout.Session.list_line_items(session_id)
                if line_items and line_items.data:
                    price_obj = stripe.Price.retrieve(line_items.data[0].price.id)
                    meta_limite = price_obj.metadata.get("limite_empresas")
                    if meta_limite:
                        base_limite = int(meta_limite)
                        quantidade = line_items.data[0].quantity or 1
                        # Se for um preço com quantidade configurada para extras:
                        if base_limite == 10 and quantidade > 1:
                            limite = base_limite + (quantidade - 1)
                        else:
                            limite = base_limite
        except Exception as e:
            print(f"Aviso: Não foi possível buscar metadata do Stripe, usando cálculo por valor: {e}")
            
        # Verifica se é um Upgrade através do client_reference_id
        client_ref = session.get("client_reference_id")
        is_upgrade = False
        db_license = None
        
        if client_ref and client_ref.startswith("IMONITOR-"):
            db_license = db.query(models.License).filter(models.License.license_key == client_ref).first()
            
        if db_license:
            is_upgrade = True
            nova_chave = db_license.license_key
            
            # Lógica de limite: Se for um "Adicional" (valor baixo), soma. Se for plano (29,90+), substitui/pega o maior.
            if valor_pago < 2990 and limite == 1:
                db_license.limite_empresas += 1
            else:
                db_license.limite_empresas = max(db_license.limite_empresas, limite)
                
            # Cancela a assinatura antiga no Stripe para não ter cobrança dupla
            old_sub = db_license.stripe_subscription_id
            if old_sub and old_sub != stripe_subscription_id:
                try:
                    if stripe.api_key and "simulacao" not in stripe.api_key:
                        stripe.Subscription.delete(old_sub)
                except Exception as e:
                    print(f"Erro cancelando sub antiga: {e}")
                    
            db_license.stripe_subscription_id = stripe_subscription_id
            if db_license.data_expiracao:
                db_license.data_expiracao = db_license.data_expiracao + timedelta(days=dias)
            db.commit()
            db.refresh(db_license)
            print(f"[UPGRADE] Licença {nova_chave} atualizada com sucesso.")
        else:
            # Idempotency check: verifica se a assinatura já foi processada
            if stripe_subscription_id:
                existente = db.query(models.License).filter(models.License.stripe_subscription_id == stripe_subscription_id).first()
                if existente:
                    print(f"Assinatura {stripe_subscription_id} já processada na licença {existente.license_key}.")
                    return Response(status_code=200)

            # Gera uma nova chave
            nova_chave = gerar_chave()
            
            # Salva no banco de dados
            db_license = models.License(
                license_key=nova_chave,
                email_cliente=email_cliente,
                dias_validade=dias,
                cnpj=cnpj_stripe if cnpj_stripe else None,
                nome_empresa=nome_empresa if nome_empresa else None,
                telefone=telefone if telefone else None,
                limite_empresas=limite,
                parceiro="Venda Online",
                comissao_percentual=0,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id
            )
            db.add(db_license)
            db.commit()
            db.refresh(db_license)
            print(f"[SUCESSO] Nova licenca gerada: {nova_chave} para {email_cliente}")
        
        # Gera o primeiro pagamento
        # Para simular a taxa do Stripe: 3.99% + 0.39 fixo (exemplo)
        # Ex: 39.90 -> 3990. Taxa: (3990 * 0.0399) + 39 = 159 + 39 = 198 (R$ 1,98)
        taxa = int(valor_pago * 0.0399) + 39
        liq = valor_pago - taxa
        
        agora = datetime.utcnow()
        mes_ref = f"{agora.month:02d}/{agora.year}"
        
        db_payment = models.Payment(
            license_id=db_license.id,
            data_pagamento=agora,
            mes_referencia=mes_ref,
            valor_bruto=valor_pago,
            taxa_gateway=taxa,
            valor_liquido=liq,
            metodo="Stripe Upgrade" if is_upgrade else "Stripe",
            status="Pago"
        )
        db.add(db_payment)
        db.commit()
        
        # Disparar e-mail para o cliente (só para novas licenças)
        if not is_upgrade:
            try:
                enviar_email_licenca(email_cliente, nova_chave, dias)
            except Exception as e:
                print(f"Erro ao disparar e-mail: {e}")

    elif event.get("type") == "invoice.payment_succeeded":
        invoice = event.get("data", {}).get("object", {})
        
        # O pagamento de uma fatura de assinatura
        sub_id = invoice.get("subscription", None)
        cust_id = invoice.get("customer", None)
        valor_pago = invoice.get("amount_paid", 0)
        
        # O Stripe cobra as faturas iniciais E recorrentes aqui.
        # Para evitar duplicar o primeiro pagamento (que já vem no checkout session), o Stripe indica
        # billing_reason = "subscription_create" na primeira e "subscription_cycle" nas seguintes.
        if invoice.get("billing_reason") == "subscription_cycle" and sub_id:
            # Busca a licença correspondente no banco
            db_license = db.query(models.License).filter(models.License.stripe_subscription_id == sub_id).first()
            if db_license:
                # Estender a expiração
                if db_license.data_expiracao:
                    db_license.data_expiracao = db_license.data_expiracao + timedelta(days=db_license.dias_validade)
                else:
                    db_license.data_expiracao = datetime.utcnow() + timedelta(days=db_license.dias_validade)
                
                # Criar pagamento
                taxa = int(valor_pago * 0.0399) + 39
                liq = valor_pago - taxa
                agora = datetime.utcnow()
                mes_ref = f"{agora.month:02d}/{agora.year}"
                
                db_payment = models.Payment(
                    license_id=db_license.id,
                    data_pagamento=agora,
                    mes_referencia=mes_ref,
                    valor_bruto=valor_pago,
                    taxa_gateway=taxa,
                    valor_liquido=liq,
                    metodo="Stripe Recorrente",
                    status="Pago"
                )
                db.add(db_payment)
                db.commit()
                print(f"[RENOVAÇÃO] Licença {db_license.license_key} renovada para {mes_ref}.")

    return Response(status_code=200)

@app.post("/verify")
def verify_license(req: VerifyRequest, db: Session = Depends(get_db)):
    """Endpoint chamado pelo iMonitor Desktop para validar a chave."""
    # Remove máscaras do CNPJ
    cnpj_limpo = ''.join(filter(str.isdigit, req.cnpj))
    chave_limpa = req.license_key.strip().upper()
    
    db_license = db.query(models.License).filter(models.License.license_key == chave_limpa).first()
    
    if not db_license:
        raise HTTPException(status_code=404, detail="Licença não encontrada.")
    
    if not db_license.is_active:
        raise HTTPException(status_code=403, detail="Esta licença foi revogada.")

    # Se a licença ainda não tem CNPJ vinculado (Primeira Ativação)
    if not db_license.cnpj:
        db_license.cnpj = cnpj_limpo
        # Calcula a data de expiração a partir do momento da primeira ativação
        db_license.data_expiracao = datetime.utcnow() + timedelta(days=db_license.dias_validade)
        db.commit()
        db.refresh(db_license)
    
    # Se já tem CNPJ vinculado, verifica se é o mesmo
    elif db_license.cnpj != cnpj_limpo:
        raise HTTPException(status_code=403, detail="Esta licença já está vinculada a outro CNPJ.")

    # Verifica se já expirou
    if datetime.utcnow() > db_license.data_expiracao:
        raise HTTPException(status_code=403, detail="A licença expirou.")
        
    return {
        "status": "success",
        "license_key": db_license.license_key,
        "valid_until": db_license.data_expiracao.strftime("%Y-%m-%d"),
        "cnpj": db_license.cnpj,
        "limite_empresas": db_license.limite_empresas
    }

@app.post("/register_trial")
def register_trial(req: TrialRequest, db: Session = Depends(get_db)):
    """Endpoint para registrar que um CNPJ usou o trial."""
    cnpj_limpo = ''.join(filter(str.isdigit, req.cnpj))
    
    if not cnpj_limpo:
        raise HTTPException(status_code=400, detail="CNPJ inválido.")
        
    db_trial = db.query(models.TrialCompany).filter(models.TrialCompany.cnpj == cnpj_limpo).first()
    
    if db_trial:
        raise HTTPException(status_code=403, detail="Este CNPJ já utilizou o período de testes.")
        
    # Se não existe, cria
    novo_trial = models.TrialCompany(cnpj=cnpj_limpo)
    db.add(novo_trial)
    db.commit()
    
    return {"status": "success", "message": "CNPJ registrado para período de teste."}
