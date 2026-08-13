"""User bootstrap and login endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.user import LoginRequest, SeedUsersRequest, SeedUsersResponse, UserResponse
from app.services.user_service import UserService

router = APIRouter()


@router.post("/login", response_model=UserResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = UserService(db).authenticate(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return user


@router.post("/seed", response_model=SeedUsersResponse, status_code=201)
def seed_users(data: SeedUsersRequest, db: Session = Depends(get_db)):
    """Create the five initial accounts; permanently disabled once any user exists."""
    try:
        users = UserService(db).seed_initial_users(data.users)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"message": f"{len(users)} initial users created", "users": users}
