from fastapi import Cookie, Depends, HTTPException
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

serializer = URLSafeSerializer(settings.secret_key, salt="atlas-session")


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def get_current_user(session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = serializer.loads(session)
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    user = db.get(User, payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
