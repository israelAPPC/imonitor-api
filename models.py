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
    payment_status = Column(String, default="Pendente") # Pago, Pendente, etc.
    parceiro = Column(String, nullable=True) # Quem vendeu a licença (se for parceria)
    comissao_percentual = Column(Integer, default=0) # % de comissão a repassar

class TrialCompany(Base):
    __tablename__ = "trial_companies"

    id = Column(Integer, primary_key=True, index=True)
    cnpj = Column(String, unique=True, index=True)
    data_registro = Column(DateTime, default=datetime.utcnow)
