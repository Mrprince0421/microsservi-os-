# loja/gateway/app/main.py
from http import HTTPStatus
from typing import Annotated, List
import json

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, Header
from fastapi.security import OAuth2PasswordBearer
import httpx
import jwt  # Para simular a decodificação do token
from pydantic import BaseModel, Field


USER_SERVICE_URL = "http://3.137.142.190:8000"
PRODUCT_SERVICE_URL = "http://3.20.238.211:8001"
SALES_SERVICE_URL = "http://3.133.90.240:8002"

# A SECRET_KEY DEVE SER A MESMA USADA NO USER-SERVICE para decodificação local
# Em um cenário ideal, o gateway buscaria uma chave pública, mas para simplificação:
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

# Esquema de autenticação para extrair o token do cabeçalho
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/token')



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

class Token(BaseModel): # <-- GARANTA QUE ESTA CLASSE ESTÁ PRESENTE
    access_token: str
    token_type: str

class UserPublic(BaseModel):
    id: int
    username: str
    email: str


def get_current_user_id(token: str = Depends(oauth2_scheme)):
    """
    Decodifica e valida o JWT localmente para obter o ID do usuário.
    """
    credentials_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail='Could not validate credentials - Invalid Token',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        # Tenta decodificar o token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get('sub')  # Assume que o 'sub' é o ID

        if not user_id:
            raise credentials_exception

        # Tenta converter o ID para int
        try:
            user_id_int = int(user_id)
        except ValueError:
            # Se a conversão falhar (ex: 'sub' é 'string' ou 'abc')
            raise credentials_exception

        return {"id": user_id_int, "token": token}

    except jwt.PyJWTError:
        # Se a decodificação falhar (chave incorreta, expirado, etc.)
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


@app.get("/api/users/me", response_model=UserPublic, tags=["users"])
async def read_users_me(
        current_user: T_CurrentUser,
        request: Request  # Injete o objeto Request original
):
    """Obtém os dados do usuário autenticado (User-service)."""

    # CORREÇÃO: Passar o objeto 'request' completo.
    # O path será extraído de request.url.path dentro de proxy_request.
    return await proxy_request(
        request,  # Passa o Request original completo
        USER_SERVICE_URL,
        current_user
    )


@app.post("/auth/token", response_model=Token, tags=["auth"])
async def login_for_access_token(request: Request):
    """
    Encaminha a requisição de token diretamente para o User-Service.
    Esta rota NÃO USA T_CurrentUser, pois ela é a própria autenticação.
    """

    # URL completa do endpoint de token no User-service
    full_url = f"{USER_SERVICE_URL}/auth/token"

    # 1. Obter o form-data do cliente original
    form_data = await request.form()

    # 2. CORREÇÃO CRÍTICA: Converter o objeto FormData para um dicionário
    # padrão (str: str) para que o httpx possa serializar corretamente
    # como 'application/x-www-form-urlencoded'.
    form_data_dict = {k: str(v) for k, v in form_data.items()}

    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            # O httpx irá definir o Content-Type correto (application/x-www-form-urlencoded)
            # e serializar o dicionário 'data' para o corpo da requisição.
            response = await client.post(
                url=full_url,
                data=form_data_dict,  # <-- Usando o dicionário corrigido
                # OBS: O parâmetro 'headers' com Content-Type explícito foi removido.
            )

            # Propaga o erro (ex: 401 Unauthorized) ou o sucesso
            if response.status_code != HTTPStatus.OK:
                detail = "Authentication failed in User-Service"
                try:
                    detail = response.json().get("detail", detail)
                except:
                    pass

                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail
                )

            # Retorna o token gerado pelo User-service
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type="application/json"
            )

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=f"User-Service unavailable: {USER_SERVICE_URL} - {e}"
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