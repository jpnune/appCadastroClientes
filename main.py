# Para rodar este backend:
# 1. Instale as bibliotecas: pip install "fastapi[all]" uvicorn vercel-kv vercel-blob python-multipart
# 2. No terminal, execute: uvicorn main:app --reload

import os
from typing import List, Dict, Optional
import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from vercel_kv import KV
import vercel_blob

# --- Configuração do App FastAPI ---
app = FastAPI(
    title="API de Controle de Fiado com Banco de Dados e Ficheiros",
    description="Backend para gerenciar clientes e transações usando Vercel KV e Vercel Blob.",
    version="3.0.0"
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Conexão com os Serviços Vercel ---
kv_client = KV()
DB_KEY = "fiado_app_data_v2"

# --- Modelos de Dados (Pydantic) ---
class Customer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    cpf: Optional[str] = None
    phone: str
    dob: Optional[str] = None
    address: Optional[str] = None
    limit: float = 0.0
    pictureUrl: Optional[str] = None

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
def calculate_balance(customer_id: str, transactions: List[Transaction]) -> float:
    balance = 0.0
    for t in transactions:
        if t.customerId == customer_id:
            balance += t.purchase - t.payment
    return balance

# --- Endpoints da API ---

@app.get("/api/data", response_model=AppData, summary="Obter todos os dados")
def get_all_data():
    data = kv_client.get(DB_KEY)
    if not data:
        return {"customers": [], "transactions": []}
    return data

@app.post("/api/customers", response_model=Customer, status_code=201, summary="Adicionar novo cliente")
def create_customer(customer: Customer):
    data = kv_client.get(DB_KEY) or {"customers": [], "transactions": []}
    customer.pictureUrl = None # Garante que a foto é nula ao criar
    data["customers"].append(customer.dict())
    kv_client.set(DB_KEY, data)
    return customer

@app.put("/api/customers/{customer_id}", response_model=Customer, summary="Atualizar um cliente")
def update_customer(customer_id: str, customer_data: CustomerUpdate):
    data = kv_client.get(DB_KEY) or {"customers": [], "transactions": []}
    customer_index = next((i for i, c in enumerate(data["customers"]) if c["id"] == customer_id), -1)

    if customer_index == -1:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    update_data = customer_data.dict(exclude_unset=True)
    data["customers"][customer_index].update(update_data)
    
    kv_client.set(DB_KEY, data)
    return data["customers"][customer_index]

@app.post("/api/customers/{customer_id}/upload-picture", response_model=Customer, summary="Upload da foto do cliente")
async def upload_customer_picture(customer_id: str, file: UploadFile = File(...)):
    data = kv_client.get(DB_KEY) or {"customers": [], "transactions": []}
    customer_index = next((i for i, c in enumerate(data["customers"]) if c["id"] == customer_id), -1)

    if customer_index == -1:
        raise HTTPException(status_code=404, detail="Cliente não encontrado para associar a foto.")

    try:
        blob_result = vercel_blob.put(f"customers/{customer_id}/{file.filename}", file.file.read(), {'access': 'public'})
        picture_url = blob_result['url']
        data["customers"][customer_index]['pictureUrl'] = picture_url
        kv_client.set(DB_KEY, data)
        return data["customers"][customer_index]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no upload do ficheiro: {str(e)}")

@app.post("/api/transactions", response_model=Transaction, status_code=201, summary="Adicionar novo lançamento")
def create_transaction(transaction: Transaction):
    data = kv_client.get(DB_KEY) or {"customers": [], "transactions": []}
    
    customers_obj = [Customer(**c) for c in data.get("customers", [])]
    transactions_obj = [Transaction(**t) for t in data.get("transactions", [])]

    customer = next((c for c in customers_obj if c.id == transaction.customerId), None)
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    if transaction.purchase > 0:
        current_balance = calculate_balance(transaction.customerId, transactions_obj)
        if (current_balance + transaction.purchase) > customer.limit:
            raise HTTPException(status_code=400, detail=f"Limite de crédito excedido para {customer.name}!")
    
    data["transactions"].append(transaction.dict())
    kv_client.set(DB_KEY, data)
    return transaction

@app.delete("/api/customers/{customer_id}", status_code=204, summary="Excluir um cliente")
def delete_customer(customer_id: str):
    data = kv_client.get(DB_KEY) or {"customers": [], "transactions": []}
    if not any(c["id"] == customer_id for c in data["customers"]):
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    data["customers"] = [c for c in data["customers"] if c["id"] != customer_id]
    data["transactions"] = [t for t in data["transactions"] if t["customerId"] != customer_id]
    
    kv_client.set(DB_KEY, data)
    return {}

@app.delete("/api/transactions/{transaction_id}", status_code=204, summary="Excluir um lançamento")
def delete_transaction(transaction_id: str):
    data = kv_client.get(DB_KEY) or {"customers": [], "transactions": []}
    initial_len = len(data["transactions"])
    data["transactions"] = [t for t in data["transactions"] if t["id"] != transaction_id]
    
    if len(data["transactions"]) == initial_len:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")
        
    kv_client.set(DB_KEY, data)
    return {}
