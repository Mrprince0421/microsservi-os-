# loja/gateway/app/main.py
from http import HTTPStatus
from typing import Annotated, List
import json

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer
import httpx
import jwt  # Para simular a decodificação do token
from pydantic import BaseModel, Field

# --- CONFIGURAÇÃO DE MICROSSERVIÇOS (MOCK DE ENV) ---
# Em produção, estas URLs seriam obtidas de um sistema de orquestração (Kubernetes, Docker-compose)
USER_SERVICE_URL = "http://3.80.87.236"
PRODUCT_SERVICE_URL = "http://44.203.15.210"
SALES_SERVICE_URL = "http://44.201.13.247"

# A SECRET_KEY DEVE SER A MESMA USADA NO USER-SERVICE para decodificação local
# Em um cenário ideal, o gateway buscaria uma chave pública, mas para simplificação:
SECRET_KEY = "sua-chave-secreta"  # Substitua pela chave real do seu User-service
ALGORITHM = "HS256"

# Esquema de autenticação para extrair o token do cabeçalho
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/token')


# --- MOCK DE SCHEMAS (para evitar dependência de arquivos) ---
# Usar Pydantic models minimiza a necessidade de dependências externas
class ProductSchema(BaseModel):
    name: str = Field(..., max_length=50)
    description: str | None = Field(None, max_length=150)
    price: float = Field(..., gt=0)
    QT: int = Field(..., ge=0)


class ProductUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    QT: int | None = None


class ProductPublic(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    price: float
    QT: int

    class Config:
        from_attributes = True


class SaleItemSchema(BaseModel):
    product_id: int
    QT: int


class SaleSchema(BaseModel):
    items: List[SaleItemSchema]


class SalePublic(BaseModel):
    id: int
    user_id: int
    total_price: float


# --- DEPENDÊNCIA PARA OBTER O USUÁRIO (AUTENTICAÇÃO) ---
def get_current_user_id(token: str = Depends(oauth2_scheme)):
    """
    Decodifica e valida o JWT localmente para obter o ID do usuário.
    Levanta HTTPException se o token for inválido ou expirado.
    """
    credentials_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail='Could not validate credentials - Invalid Token',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        # Tenta decodificar o token com a mesma chave e algoritmo do User-service
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get('sub')  # Assume que o 'sub' é o user_id

        if not user_id:
            raise credentials_exception

        return {"id": int(user_id), "token": token}

    except jwt.PyJWTError:
        raise credentials_exception


T_CurrentUser = Annotated[dict, Depends(get_current_user_id)]

# --- API GATEWAY APP ---
app = FastAPI(
    title='API Gateway da Loja',
    description='Ponto de entrada unificado para todos os microsserviços.',
    version='1.0.0'
)


# --- FUNÇÃO DE ROTEAMENTO GENÉRICA ---
async def proxy_request(
        request: Request,
        target_url: str,
        current_user: T_CurrentUser,
        # Inclui o body para POST/PUT/PATCH
        body: dict | None = None
):
    """
    Roteia a requisição para o serviço de destino, injetando o User ID
    e o token nos cabeçalhos e/ou corpo da requisição.
    """

    # Prepara a URL de destino (ignora o prefixo do gateway, ex: /products)
    path = request.url.path.replace("/api", "")
    full_url = f"{target_url}{path}"

    # Headers obrigatórios para autenticação e formato
    headers = {
        "Authorization": f"Bearer {current_user['token']}",
        "X-User-ID": str(current_user["id"]),  # Injeta o ID do usuário para o serviço alvo
        "Content-Type": "application/json"
    }

    # Tratamento especial para o método GET (não tem body)
    if request.method in ["GET", "DELETE"]:
        request_data = None
        # Para GET, anexa os parâmetros de query (ex: /products?name=a)
        if request.method == "GET" and request.query_params:
            full_url += f"?{str(request.query_params)}"

    else:
        # Para POST, PUT, PATCH, usa o body fornecido
        request_data = json.dumps(body)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Envia a requisição para o microsserviço
            response = await client.request(
                method=request.method,
                url=full_url,
                headers=headers,
                data=request_data
            )

            # Retorna a resposta do microsserviço
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.headers.get("content-type", "application/json")
            )

    except httpx.HTTPStatusError as e:
        # Propaga exceções HTTP de volta (NotFound, BadRequest, etc.)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.json().get("detail", "Internal Service Error")
        )
    except httpx.RequestError as e:
        # Lidar com erros de conexão (serviço indisponível)
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: {target_url}"
        )


# --- ROTAS DE AUTENTICAÇÃO (User-Service) ---
# Essas rotas não são roteadas; elas são tratadas localmente ou diretamente para o User-service.
# A rota /auth/token PRECISA SER CHAMADA DIRETAMENTE NO USER-SERVICE para gerar o token.
# O Gateway não precisa rotear /auth/token se ele só usa o token gerado.

# Exemplo de rota de usuário (roteada)
@app.get("/api/users/me", tags=["users"], response_model=dict)
async def read_users_me(current_user: T_CurrentUser):
    """Obtém os dados do usuário autenticado (User-service)."""
    # Roteia a requisição GET, o User-service vai usar o X-User-ID para buscar o usuário
    return await proxy_request(
        Request(scope={'type': 'http', 'method': 'GET', 'path': '/users/me', 'query_string': b''}),
        USER_SERVICE_URL,
        current_user
    )


# --- ROTAS DE PRODUTOS (Product-Service) ---
# Todas as rotas de produto devem passar pelo Gateway

@app.post("/api/products/", status_code=HTTPStatus.CREATED, response_model=ProductPublic, tags=["products"])
async def create_product(product: ProductSchema, current_user: T_CurrentUser, request: Request):
    """Cria um novo produto (Product-service)."""
    return await proxy_request(request, PRODUCT_SERVICE_URL, current_user, product.model_dump())


@app.get("/api/products/", response_model=List[ProductPublic], tags=["products"])
async def list_products(current_user: T_CurrentUser, request: Request):
    """Lista os produtos do usuário autenticado (Product-service)."""
    # A função proxy_request irá anexar os query parameters automaticamente
    return await proxy_request(request, PRODUCT_SERVICE_URL, current_user)


@app.get("/api/products/{product_id}", response_model=ProductPublic, tags=["products"])
async def get_product(product_id: int, current_user: T_CurrentUser, request: Request):
    """Obtém um produto por ID (Product-service)."""
    return await proxy_request(request, PRODUCT_SERVICE_URL, current_user)


@app.put("/api/products/{product_id}", response_model=ProductPublic, tags=["products"])
async def update_product(
        product_id: int,
        product: ProductUpdateSchema,
        current_user: T_CurrentUser,
        request: Request
):
    """Atualiza um produto (Product-service)."""
    return await proxy_request(request, PRODUCT_SERVICE_URL, current_user, product.model_dump(exclude_unset=True))


@app.delete("/api/products/{product_id}", status_code=HTTPStatus.NO_CONTENT, tags=["products"])
async def delete_product(product_id: int, current_user: T_CurrentUser, request: Request):
    """Deleta um produto (Product-service)."""
    return await proxy_request(request, PRODUCT_SERVICE_URL, current_user)


# --- ROTAS DE VENDAS (Sales-Service) ---
# A rota de vendas é complexa pois envolve comunicação com o Product-service,
# mas o Gateway apenas a roteia.

@app.post("/api/sales/", status_code=HTTPStatus.CREATED, response_model=SalePublic, tags=["sales"])
async def create_sale(sale: SaleSchema, current_user: T_CurrentUser, request: Request):
    """Cria uma nova venda (Sales-service)."""
    # O Sales-service lida com a comunicação com o Product-service para dar baixa no estoque.
    return await proxy_request(request, SALES_SERVICE_URL, current_user, sale.model_dump())

# Você pode adicionar rotas de relatórios de venda aqui, roteando para o Sales-Service
# ...