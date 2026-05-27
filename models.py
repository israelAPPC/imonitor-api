from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from database import Base

class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String, unique=True, index=True)
    cnpj = Column(String, index=True, nullable=True) # Ficará em branco até a primeira ativação
    nome_empresa = Column(String, nullable=True) # Recebido do Stripe
    telefone = Column(String, nullable=True) # Recebido do Stripe
    email_cliente = Column(String, index=True) # E-mail do pagador
    data_criacao = Column(DateTime, default=datetime.utcnow)
    data_expiracao = Column(DateTime, nullable=True) # Será calculada na primeira ativação ou já na geração
    is_active = Column(Boolean, default=True)
    dias_validade = Column(Integer, default=30) # Quantos dias vale essa licença
    limite_empresas = Column(Integer, default=5) # Quantidade máxima de empresas permitida
    
    # Parcerias
    parceiro = Column(String, nullable=True) # Quem vendeu a licença
    comissao_percentual = Column(Integer, default=0) # % de comissão a repassar
    
    # Integração Stripe (Assinatura)
    stripe_customer_id = Column(String, nullable=True, index=True)
    stripe_subscription_id = Column(String, nullable=True, index=True)

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    license_id = Column(Integer, index=True) # Ligação com a licença
    data_pagamento = Column(DateTime, default=datetime.utcnow)
    mes_referencia = Column(String) # Ex: "08/2026"
    valor_bruto = Column(Integer) # Em centavos
    taxa_gateway = Column(Integer) # Em centavos
    valor_liquido = Column(Integer) # Em centavos
    metodo = Column(String) # "Stripe", "Pix Manual"
    status = Column(String, default="Pago") # "Pago", "Pendente"

class SysConfig(Base):
    __tablename__ = "sys_config"
    
    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String, unique=True)
    valor = Column(String)

class TrialCompany(Base):
    __tablename__ = "trial_companies"

    id = Column(Integer, primary_key=True, index=True)
    cnpj = Column(String, unique=True, index=True)
    data_registro = Column(DateTime, default=datetime.utcnow)
