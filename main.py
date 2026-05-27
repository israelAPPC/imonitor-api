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
                
        # Define limite e dias de validade com base no valor pago
        dias = 30
        limite = 5
        
        # Planos de 15 empresas
        if valor_pago in [5990, 11990, 24990, 49990]:
            limite = 15
            
        # Dias de validade
        if valor_pago in [39990, 49990]:
            dias = 365
        elif valor_pago in [19990, 24990]:
            dias = 180
        elif valor_pago in [9990, 11990]:
            dias = 90
        elif valor_pago in [3990, 5990]:
            dias = 30
            
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
            limite_empresas=limite
        )
        db.add(db_license)
        db.commit()
        db.refresh(db_license)
        
        # Disparar e-mail para o cliente
        try:
            enviar_email_licenca(email_cliente, nova_chave, dias)
        except Exception as e:
            print(f"Erro ao disparar e-mail: {e}")
            
        print(f"[SUCESSO] Nova licenca gerada: {nova_chave} para {email_cliente}")

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
