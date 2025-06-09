# Para rodar este backend:
# 1. Instale as bibliotecas necessárias: pip install "fastapi[all]" uvicorn
# 2. No terminal, execute o comando: uvicorn main:app --reload

import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Configuração do App FastAPI ---
app = FastAPI(
    title="API de Controle de Fiado",
    description="Backend para gerenciar clientes e transações de uma loja.",
    version="1.1.0"
)

# --- CORS (Cross-Origin Resource Sharing) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuração do "Banco de Dados" (Arquivo JSON) ---
DB_FILE = Path("database.json")

def load_db() -> Dict[str, List[Dict]]:
    """Carrega os dados do arquivo JSON. Se não existir, cria um novo."""
    if not DB_FILE.exists():
        return {"customers": [], "transactions": []}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data: Dict[str, List[Dict]]):
    """Salva os dados no arquivo JSON."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Modelos de Dados (Pydantic) ---
class Customer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    cpf: Optional[str] = None
    phone: str
    dob: Optional[str] = None
    address: Optional[str] = None
    limit: float = 0.0

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    cpf: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    limit: Optional[float] = None

class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customerId: str
    date: str
    description: str
    purchase: float = 0.0
    payment: float = 0.0

class AppData(BaseModel):
    customers: List[Customer]
    transactions: List[Transaction]

# --- Lógica de Negócio ---
def calculate_balance(customer_id: str, transactions: List[Dict]) -> float:
    """Calcula o saldo devedor de um cliente específico."""
    balance = 0.0
    for t in transactions:
        if t['customerId'] == customer_id:
            balance += t.get('purchase', 0) - t.get('payment', 0)
    return balance

# --- Endpoints da API ---

@app.get("/api/data", response_model=AppData, summary="Obter todos os dados")
def get_all_data():
    """Retorna todos os clientes e transações do banco de dados."""
    db = load_db()
    return db

@app.post("/api/customers", response_model=Customer, status_code=201, summary="Adicionar um novo cliente")
def create_customer(customer: Customer):
    """Cria um novo cliente e o salva no banco de dados."""
    db = load_db()
    customer.id = str(uuid.uuid4())
    db["customers"].append(customer.dict())
    save_db(db)
    return customer

@app.put("/api/customers/{customer_id}", response_model=Customer, summary="Atualizar um cliente")
def update_customer(customer_id: str, customer_data: CustomerUpdate):
    """Atualiza os dados de um cliente existente."""
    db = load_db()
    
    customer_index = -1
    for i, c in enumerate(db["customers"]):
        if c["id"] == customer_id:
            customer_index = i
            break

    if customer_index == -1:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    # Atualiza os dados do cliente com os novos dados
    update_data = customer_data.dict(exclude_unset=True)
    db["customers"][customer_index].update(update_data)
    
    save_db(db)
    return db["customers"][customer_index]

@app.post("/api/transactions", response_model=Transaction, status_code=201, summary="Adicionar um novo lançamento")
def create_transaction(transaction: Transaction):
    """Cria um novo lançamento, verificando o limite de crédito."""
    db = load_db()
    customer = next((c for c in db["customers"] if c["id"] == transaction.customerId), None)
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    if transaction.purchase > 0:
        current_balance = calculate_balance(transaction.customerId, db["transactions"])
        if (current_balance + transaction.purchase) > customer["limit"]:
            raise HTTPException(status_code=400, detail=f"Limite de crédito excedido para {customer['name']}!")
    
    transaction.id = str(uuid.uuid4())
    db["transactions"].append(transaction.dict())
    save_db(db)
    return transaction

@app.delete("/api/customers/{customer_id}", status_code=204, summary="Excluir um cliente")
def delete_customer(customer_id: str):
    """Exclui um cliente e todos os seus lançamentos associados."""
    db = load_db()
    if not any(c for c in db["customers"] if c["id"] == customer_id):
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    db["customers"] = [c for c in db["customers"] if c["id"] != customer_id]
    db["transactions"] = [t for t in db["transactions"] if t["customerId"] != customer_id]
    
    save_db(db)
    return {}

@app.delete("/api/transactions/{transaction_id}", status_code=204, summary="Excluir um lançamento")
def delete_transaction(transaction_id: str):
    """Exclui um lançamento específico."""
    db = load_db()
    initial_len = len(db["transactions"])
    db["transactions"] = [t for t in db["transactions"] if t["id"] != transaction_id]
    
    if len(db["transactions"]) == initial_len:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")
        
    save_db(db)
    return {}
