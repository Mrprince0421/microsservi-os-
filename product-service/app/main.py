# loja/product-service/app/main.py
from http import HTTPStatus
from typing import Annotated, List

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Header # NOVO: Importa Header
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import DB, models, schemas

app = FastAPI(
    title='Microserviço de Produtos',
    description='API para gerenciar o catálogo de produtos.',
    version='1.0.0'
)

T_Session = Annotated[Session, Depends(DB.get_session)]

# --- INTEGRAÇÃO COM GATEWAY (AUTENTICAÇÃO SIMPLIFICADA) ---
def get_current_user_from_header(x_user_id: Annotated[int, Header(convert_underscores=True)]):
    """
    Extrai o ID do usuário do cabeçalho X-User-ID, confiando no API Gateway.
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='X-User-ID header missing. Must be called through API Gateway.',
        )
    return {"id": x_user_id}

T_CurrentUser = Annotated[dict, Depends(get_current_user_from_header)]
# --------------------------------------------------------------------------

router = APIRouter(prefix='/products', tags=['products'])

# ... (Rotas create_product, read_products, get_product_by_id, update_product, delete_product) ...

@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=schemas.ProductPublic
)
def create_product(
        product: schemas.ProductSchema, session: T_Session, current_user: T_CurrentUser
):
    db_product = models.Product(
        user_id=current_user["id"], # Usa o ID extraído do cabeçalho
        name=product.name,
        description=product.description,
        price=product.price,
        QT=product.QT
    )
    session.add(db_product)
    session.commit()
    session.refresh(db_product)

    return db_product


@router.get('/', response_model=schemas.ProductListResponse)
def read_products(
        session: T_Session,
        current_user: T_CurrentUser,
        skip: int = 0,
        limit: int = 100,
        name: str | None = Query(None),
        product_id: int | None = Query(None)
):
    query = select(models.Product).where(models.Product.user_id == current_user["id"])
    if name:
        query = query.where(models.Product.name.contains(name))
    if product_id:
        query = query.where(models.Product.id == product_id)

    total_count = session.scalar(select(func.count()).select_from(query.subquery()))
    products = session.scalars(query.offset(skip).limit(limit)).all()

    if not products and total_count == 0:
        return schemas.ProductListResponse(products=[], total_count=0)

    return schemas.ProductListResponse(products=products, total_count=total_count)


@router.get('/{product_id}', response_model=schemas.ProductPublic)
def get_product_by_id(
    product_id: int, session: T_Session, current_user: T_CurrentUser
):
    db_product = session.scalar(
        select(models.Product).where(
            models.Product.id == product_id,
            models.Product.user_id == current_user["id"]
        )
    )
    if not db_product:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Product not found',
        )
    return db_product


@router.put('/{product_id}', response_model=schemas.ProductPublic)
def update_product(
        product_id: int,
        product: schemas.ProductUpdateSchema,
        session: T_Session,
        current_user: T_CurrentUser
):
    db_product = session.scalar(
        select(models.Product).where(
            models.Product.id == product_id,
            models.Product.user_id == current_user["id"]
        )
    )
    if not db_product:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Product not found',
        )

    for key, value in product.model_dump(exclude_unset=True).items():
        setattr(db_product, key, value)

    session.commit()
    session.refresh(db_product)

    return db_product


@router.delete(
    '/{product_id}',
    status_code=HTTPStatus.NO_CONTENT,
)
def delete_product(
        product_id: int, session: T_Session, current_user: T_CurrentUser
):
    db_product = session.scalar(
        select(models.Product).where(
            models.Product.id == product_id,
            models.Product.user_id == current_user["id"]
        )
    )
    if not db_product:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Product not found',
        )

    session.delete(db_product)
    session.commit()
    return None

app.include_router(router)
# Remova ou corrija as rotas antigas de read_products e create_product se elas existirem fora do router
# ...