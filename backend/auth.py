import os
import hashlib
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests

load_dotenv()

# --- CONFIGURATION ---
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-default-key-change-me")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 14400))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

# --- PASSWORD LOGIC ---

def _pre_hash(password: str) -> bytes:
    """Hashes the password to a 64-char string and returns it as bytes."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_pre_hash(plain_password), hashed_password.encode("utf-8"))
    except Exception as e:
        print(f"❌ Verification Error: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Hashes a password with a fresh salt using bcrypt."""
    print(f"🔒 Hashing password (length: {len(password)})")
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_pre_hash(password), salt)
    return hashed.decode("utf-8")

# --- JWT TOKEN LOGIC ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Creates a JWT Token (Access Pass)."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str):
    """Decodes a token to extract the user email."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub") if payload else None
    except JWTError:
        return None

def verify_google_token(token: str):
    """Verifies a Google ID Token."""
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        return idinfo
    except Exception as e:
        print(f"❌ Google Verification Error: {e}")
        return None
