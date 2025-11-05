from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import users, auth

app = FastAPI(
    title='Microserviço de Usuários e Autenticação',
    description='API para gerenciar usuários e autenticação.',
    version='1.0.0'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(auth.router)

@app.get("/")
def read_root():
    return {"message": "Bem-vindo ao serviço de Usuários e Autenticação"}