# loja/User/app/routers/users.py
from typing import Annotated
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, DB
from ..security import get_password, T_CurrentUser  # T_CurrentUser é a nova dependência

# Alias para dependências
T_Session = Annotated[Session, Depends(DB.get_session)]

router = APIRouter(prefix='/users', tags=['users'])


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=schemas.UserPublic
)
def create_user(user: schemas.UserCreate, session: T_Session):
    """Cria um novo usuário no sistema (rota de registro)."""
    # ... (Lógica de verificação de username e email) ...
    db_user_username = session.scalar(
        select(models.User).where(models.User.username == user.username)
    )
    if db_user_username:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Username already registered',
        )

    db_user_email = session.scalar(
        select(models.User).where(models.User.email == user.email)
    )
    if db_user_email:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Email already registered',
        )

    db_user = models.User(
        username=user.username,
        password=get_password(user.password),
        email=user.email,
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    return db_user


@router.get('/me', response_model=schemas.UserPublic)
def read_users_me(
        current_user: T_CurrentUser,  # AGORA USA O ID INJETADO PELO GATEWAY
):
    """
    Retorna os dados do usuário autenticado.
    """
    return current_user