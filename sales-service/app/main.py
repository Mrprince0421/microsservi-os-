# loja/sales-service/app/main.py
from http import HTTPStatus
from typing import Annotated
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Header  # NOVO: Importa Header
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from datetime import date
import httpx

from . import DB, models, schemas

# URL de outro serviço (A URL interna correta para o Product-service)
PRODUCT_SERVICE_URL = "http://127.0.0.1:8001"

app = FastAPI(
    title='Microserviço de Vendas',
    description='API para gerenciar vendas e relatórios de contabilidade.',
    version='1.0.0'
)

T_Session = Annotated[Session, Depends(DB.get_session)]


# --------------------------------------------------------------------------
# AUTENTICAÇÃO COM GATEWAY
# --------------------------------------------------------------------------
def get_current_user_from_header(
        x_user_id: Annotated[int, Header(convert_underscores=True)],
        authorization: Annotated[str, Header()]  # Captura o token para chamadas internas
):
    """
    Extrai o ID do usuário do cabeçalho X-User-ID, confiando no API Gateway.
    Também captura o token para chamadas internas.
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='X-User-ID header missing. Must be called through API Gateway.',
        )
    # authorization é uma string "Bearer <token>", então pegamos a segunda parte
    token = authorization.split(" ")[1] if authorization and " " in authorization else authorization

    return {"id": x_user_id, "token": token}


T_CurrentUser = Annotated[dict, Depends(get_current_user_from_header)]


# --------------------------------------------------------------------------
# COMUNICAÇÃO ENTRE SERVIÇOS (PRODUCT-SERVICE)
# --------------------------------------------------------------------------

async def get_product_from_service(product_id: int, user_id: int, token: str):
    """Busca um produto no Product-service e retorna os dados."""

    async with httpx.AsyncClient(timeout=5) as client:
        url = f'{PRODUCT_SERVICE_URL}/products/{product_id}'

        # Headers: Passa o token e o ID do usuário para o Product-service validar a posse
        headers = {
            "Authorization": f"Bearer {token}",
            "X-User-ID": str(user_id)
        }

        response = await client.get(url, headers=headers)

        if response.status_code == HTTPStatus.OK:
            return response.json()
        elif response.status_code == HTTPStatus.NOT_FOUND:
            return None
        else:
            response.raise_for_status()


async def update_product_stock_in_service(product_id: int, new_quantity: int, user_id: int, token: str):
    """Atualiza o estoque (QT) de um produto no Product-service."""

    async with httpx.AsyncClient(timeout=5) as client:
        url = f'{PRODUCT_SERVICE_URL}/products/{product_id}'
        headers = {
            "Authorization": f"Bearer {token}",
            "X-User-ID": str(user_id),
            "Content-Type": "application/json"
        }
        data = {"QT": new_quantity}

        response = await client.put(url, json=data, headers=headers)

        if response.status_code == HTTPStatus.OK:
            return response.json()
        else:
            response.raise_for_status()


# --------------------------------------------------------------------------

router = APIRouter(prefix='/sales', tags=['sales'])


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=schemas.SalePublic
)
async def create_sale(
        sale: schemas.SaleSchema,
        session: T_Session,
        current_user: T_CurrentUser
):
    total_price = 0
    sale_items_to_create = []

    user_id = current_user['id']
    user_token = current_user['token']

    for item in sale.items:
        # Comunicação com o serviço de produtos para obter dados
        product = await get_product_from_service(item.product_id, user_id, user_token)

        if not product:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=f'Produto com ID {item.product_id} não encontrado no serviço de produtos.'
            )
        if product['QT'] < item.QT:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f'Produto {product["name"]} não tem estoque suficiente.'
            )

        # Comunicação com o serviço de produtos para atualizar o estoque
        new_quantity = product['QT'] - item.QT
        await update_product_stock_in_service(product['id'], new_quantity, user_id, user_token)

        sale_items_to_create.append(models.SaleItem(
            sale_id=0,
            product_id=product['id'],
            QT=item.QT,
            product_price=product['price']
        ))
        total_price += product['price'] * item.QT

    # Cria a venda no banco de dados do serviço de vendas
    db_sale = models.Sale(
        user_id=user_id,
        total_price=total_price
    )
    session.add(db_sale)
    session.commit()
    session.refresh(db_sale)

    # Associa os itens à venda recém-criada
    for sale_item in sale_items_to_create:
        sale_item.sale_id = db_sale.id
        session.add(sale_item)

    session.commit()
    session.refresh(db_sale)

    return db_sale


# Outras rotas de relatórios (daily_report, report_by_period, etc.) podem ser adicionadas aqui
# ...

app.include_router(router)