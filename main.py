import os
import random
import string
import stripe
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, Response
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

class VerifyRequest(BaseModel):
    license_key: str
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
        
        # Gera uma nova chave
        nova_chave = gerar_chave()
        
        # Salva no banco de dados (Licença de 30 dias por padrão)
        db_license = models.License(
            license_key=nova_chave,
            email_cliente=email_cliente,
            dias_validade=30 # Pode ser lido dos metadados do produto no Stripe
        )
        db.add(db_license)
        db.commit()
        db.refresh(db_license)
        
        # AQUI entraria o código para disparar o e-mail pro cliente com a 'nova_chave'
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
        "cnpj": db_license.cnpj
    }
