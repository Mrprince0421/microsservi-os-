from http import HTTPStatus
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import DB, schemas, models, security

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/token', response_model=schemas.Token)
def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        session: Session = Depends(DB.get_session),
):
    user = session.scalar(
        select(models.User).where(models.User.username == form_data.username)
    )

    if not user or not security.verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Incorrect username or password',
        )

    # CORREÇÃO CRÍTICA: Usar o ID (convertido para string) em vez do username.
    # O Gateway espera um valor numérico para criar o cabeçalho X-User-ID.
    access_token = security.create_access_token(data={'sub': str(user.id)})

    return {'access_token': access_token, 'token_type': 'bearer'}


# A rota refresh_access_token também deve usar user.id
@router.post('/refresh_token', response_model=schemas.Token)
def refresh_access_token(
        user: models.User = Depends(security.get_current_user)
):
    # CORREÇÃO: Usar o ID do usuário para o novo token
    new_access_token = security.create_access_token(data={'sub': str(user.id)})
    return {'access_token': new_access_token, 'token_type': 'bearer'}