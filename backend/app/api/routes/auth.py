from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.security import Principal, current_principal
from backend.app.db.session import get_db
from backend.app.schemas.auth import (
    AccountRead,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
)
from backend.app.services.auth import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, request: Request, session: Session = Depends(get_db)):
    return AuthService(session, request).register(data)


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, request: Request, session: Session = Depends(get_db)):
    return AuthService(session, request).login(data)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, request: Request, session: Session = Depends(get_db)):
    return AuthService(session, request).refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    data: LogoutRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    AuthService(session, request).logout(data.refresh_token, principal.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    AuthService(session, request).logout_all(principal.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AccountRead)
def me(principal: Principal = Depends(current_principal)):
    return AuthService.account_payload(principal.user, principal.learner)
