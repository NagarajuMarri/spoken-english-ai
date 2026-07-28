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
from backend.app.core.operations import enforce_rate_limit, privacy_key

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, request: Request, session: Session = Depends(get_db)):
    enforce_rate_limit(request, "registration", privacy_key(request.client.host if request.client else "unknown"))
    return AuthService(session, request).register(data)


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, request: Request, session: Session = Depends(get_db)):
    from backend.app.core.security import normalize_email, privacy_minimised_network_key
    enforce_rate_limit(request, "login_email", privacy_key(normalize_email(str(data.email))))
    enforce_rate_limit(request, "login_network", privacy_minimised_network_key(request))
    return AuthService(session, request).login(data)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, request: Request, session: Session = Depends(get_db)):
    enforce_rate_limit(request, "refresh", privacy_key(request.client.host if request.client else "unknown"))
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
