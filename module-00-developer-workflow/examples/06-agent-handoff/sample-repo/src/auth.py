import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Session:
    token: str
    user_id: int
    created_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class AuthService:
    """
    Autenticación con username/password.
    Pendiente: agregar soporte OAuth2 (ver handoff demo).
    """

    SESSION_DURATION_HOURS = 24

    def __init__(self, db):
        self.db = db
        self._sessions: dict[str, Session] = {}

    def login(self, username: str, password: str) -> dict:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        user = self.db.find_user(username, hashed)
        if not user:
            raise ValueError("Credenciales inválidas")

        token = secrets.token_urlsafe(32)
        session = Session(
            token=token,
            user_id=user.id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=self.SESSION_DURATION_HOURS)
        )
        self._sessions[token] = session
        return {"user_id": user.id, "token": token, "expires_at": session.expires_at.isoformat()}

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def validate_token(self, token: str) -> int | None:
        """Retorna user_id si el token es válido, None si no."""
        session = self._sessions.get(token)
        if not session or session.is_expired:
            return None
        return session.user_id
