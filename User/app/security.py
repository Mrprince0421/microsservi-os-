from .settings import Settings
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated # NOVO: Import adicionado
from fastapi import Depends, HTTPException, Header # Import Header adicionado
from fastapi.security import OAuth2PasswordBearer
from jwt import DecodeError, decode, encode, ExpiredSignatureError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from .DB import get_session
from .models import User

settings = Settings()
pwd_context = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/token')

def get_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({'exp': expire})
    return encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

# FUNÇÃO ORIGINAL: Utilizada pela rota de login (/auth/token)
def get_current_user(
    session: Session = Depends(get_session),
    token: str = Depends(oauth2_scheme),
):
    credentials_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        subject_username = payload.get('sub')
        if not subject_username:
            raise credentials_exception
    except (DecodeError, ExpiredSignatureError):
        raise credentials_exception

    user = session.scalar(select(User).where(User.username == subject_username))
    if not user:
        raise credentials_exception
    return user


def get_current_user_from_gateway(
    x_user_id: Annotated[int, Header(convert_underscores=True)],
    session: Session = Depends(get_session),
):
    """
    Função de dependência para ser usada nas rotas protegidas do User-service.
    Confia que o API Gateway já validou o token e injetou o ID do usuário.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Missing X-User-ID header. Request must pass through API Gateway.',
        )

    # Busca o usuário pelo ID no banco de dados
    user = session.scalar(select(User).where(User.id == x_user_id))

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='User not found.',
        )
    return user

# NOVO: Alias de tipo para ser usado nas rotas protegidas
T_CurrentUser = Annotated[User, Depends(get_current_user_from_gateway)]