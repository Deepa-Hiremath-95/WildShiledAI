import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(tags=["auth"])

# In-memory sliding-window failed login rate limiter (Item 15)
_FAILED_LOGINS = defaultdict(list)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 60



@router.post("/auth/register")
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Item 1: Public registration cannot create administrator accounts
    role_str = user_in.role.value if hasattr(user_in.role, "value") else str(user_in.role)
    if role_str.lower() == "admin":
        raise HTTPException(
            status_code=403,
            detail="Public registration cannot create administrator accounts",
        )

    user = models.User(
        username=user_in.username,
        hashed_password=auth.hash_password(user_in.password),
        role=models.UserRole.OPERATOR,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/auth/token", response_model=schemas.Token)
@router.post("/auth/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    client_ip = request.client.host if (request and request.client) else "unknown"
    rate_key = f"{client_ip}:{form_data.username}"
    now_ts = time.time()

    # Purge attempts older than the lockout window
    _FAILED_LOGINS[rate_key] = [t for t in _FAILED_LOGINS[rate_key] if now_ts - t < LOCKOUT_WINDOW_SECONDS]
    if len(_FAILED_LOGINS[rate_key]) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please try again after 60 seconds.",
        )

    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        _FAILED_LOGINS[rate_key].append(now_ts)
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    # Reset failed attempts on successful authentication
    _FAILED_LOGINS.pop(rate_key, None)

    user.last_login_at = datetime.utcnow()
    db.commit()

    token = auth.create_access_token({"sub": user.username, "role": user.role.value if hasattr(user.role, 'value') else str(user.role)})
    return schemas.Token(access_token=token)


@router.get("/users/me", response_model=schemas.UserProfileOut)
def get_current_user_profile(current_user: models.User = Depends(auth.get_current_user)):
    return schemas.UserProfileOut.model_validate(current_user)


@router.put("/users/me", response_model=schemas.UserProfileOut)
@router.patch("/users/me", response_model=schemas.UserProfileOut)
def update_current_user_profile(
    profile_in: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if profile_in.full_name is not None:
        current_user.full_name = profile_in.full_name
    if profile_in.email is not None:
        current_user.email = profile_in.email
    if profile_in.location is not None:
        current_user.location = profile_in.location
    if profile_in.role is not None:
        current_role_val = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
        if profile_in.role.lower() != current_role_val.lower():
            raise HTTPException(
                status_code=403,
                detail="Privilege escalation forbidden: users cannot modify their own role",
            )
    db.commit()
    db.refresh(current_user)
    return schemas.UserProfileOut.model_validate(current_user)


@router.get("/security/settings", response_model=schemas.SecuritySettingsOut)
def get_security_settings(
    current_user: models.User = Depends(auth.get_current_user),
):
    last_login_str = current_user.last_login_at.isoformat() if current_user.last_login_at else "Just now"
    return schemas.SecuritySettingsOut(
        two_factor_enabled=bool(current_user.two_factor_enabled),
        authorized_devices_count=1,
        last_login=last_login_str,
        events=[
            {"title": "Recent login", "detail": "Successful authentication via command center", "time": last_login_str},
            {"title": "Device verification", "detail": "Active authenticated browser session", "time": "Approved"},
            {"title": "Role verification", "detail": f"Access granted under {current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)} privilege", "time": "Verified"},
        ],
    )


@router.post("/security/toggle-2fa")
def toggle_two_factor(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    current_user.two_factor_enabled = not bool(current_user.two_factor_enabled)
    db.commit()
    db.refresh(current_user)
    return {
        "two_factor_enabled": current_user.two_factor_enabled,
        "status": "enabled" if current_user.two_factor_enabled else "disabled",
    }

