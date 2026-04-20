import shutil
import os
from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

# Import our specialized backend logic
from ingestion import ingest_paper
from graph_agent import ask_paper_agent
from mongodb_history import save_chat_message, get_chat_history, list_all_papers, clear_chat_history
from database import mongo_db
from auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    decode_access_token, 
    verify_google_token
)
from database import initialize_qdrant

app = FastAPI(title="PaperMind API")

@app.on_event("startup")
async def startup_event():
    # Run heavy DB initialization in the background after the port is bound
    # This prevents Render from timing out during "Port Scanning"
    import threading
    threading.Thread(target=initialize_qdrant, daemon=True).start()


# Setup CORS (Allows Frontend to talk to Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def force_cors_middleware(request, call_next):
    # Handle preflight OPTIONS requests directly
    if request.method == "OPTIONS":
        from fastapi import Response
        response = Response()
    else:
        response = await call_next(request)
    
    # Inject CORS headers manually to every response
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "false"
    
    return response

@app.get("/")
def read_root():
    return {"message": "PaperMind AI Backend is LIVE", "docs": "/docs"}

@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow()}


# --- 1. CONFIG & STATIC FILES ---
# Create folder if missing and mount it so images can be viewed in browser
os.makedirs("extracted_images", exist_ok=True)
app.mount("/extracted_images", StaticFiles(directory="extracted_images"), name="extracted_images")

# --- 2. AUTHENTICATION DEPENDENCIES ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Verifies the JWT token and returns the current user email."""
    email = decode_access_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return email

# --- 3. MODELS ---
class UserSignup(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None

class QueryRequest(BaseModel):
    question: str
    paper_id: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    token: str

# --- 4. DATA ASSETS ENDPOINT (For Graphs & Tables) ---
@app.get("/papers/{paper_id}/assets")
def get_paper_assets(paper_id: str, current_user: str = Depends(get_current_user)):
    """Returns all images and tables associated with a paper."""
    images = list(mongo_db.images.find({"paper_id": paper_id, "user_id": current_user}))
    tables = list(mongo_db.tables.find({"paper_id": paper_id, "user_id": current_user}))
    
    return {
        "images": [os.path.basename(img["image_path"]) for img in images],
        "tables": [t["markdown_content"] for t in tables]
    }

# --- 5. AUTHENTICATION ROUTES ---

@app.post("/auth/signup")
async def signup(user: UserSignup):
    if mongo_db.users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    mongo_db.users.insert_one({
        "email": user.email,
        "password": hashed_password,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "created_at": datetime.utcnow()
    })
    return {"message": "User created successfully"}

@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db_user = mongo_db.users.find_one({"email": form_data.username})
    if not db_user or not db_user.get("password") or not verify_password(form_data.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/google")
async def google_auth(request: GoogleLoginRequest):
    idinfo = verify_google_token(request.token)
    if not idinfo:
        raise HTTPException(status_code=401, detail="Invalid Google Token")
    
    email = idinfo['email']
    db_user = mongo_db.users.find_one({"email": email})
    if not db_user:
        mongo_db.users.insert_one({
            "email": email,
            "first_name": idinfo.get('given_name', ""),
            "last_name": idinfo.get('family_name', ""),
            "auth_method": "GOOGLE",
            "created_at": datetime.utcnow()
        })
    
    access_token = create_access_token(data={"sub": email})
    return {"access_token": access_token, "token_type": "bearer"}

# --- 6. PAPER & HISTORY ROUTES ---

@app.get("/papers")
def get_papers(current_user: str = Depends(get_current_user)):
    return list_all_papers(current_user)

@app.post("/papers/{paper_id}/select")
def select_paper(paper_id: str, current_user: str = Depends(get_current_user)):
    from mongodb_history import set_active_paper
    set_active_paper(current_user, paper_id)
    return {"status": "success"}

@app.get("/history/{paper_id}")
def get_history(paper_id: str, current_user: str = Depends(get_current_user)):
    return get_chat_history(current_user, paper_id)

@app.delete("/history/{paper_id}")
def delete_history(paper_id: str, current_user: str = Depends(get_current_user)):
    """Clears all chat messages for the current user and the given paper."""
    deleted_count = clear_chat_history(current_user, paper_id)
    return {"status": "cleared", "deleted": deleted_count}

@app.get("/papers/{paper_id}/summary")
def get_paper_summary(paper_id: str, current_user: str = Depends(get_current_user)):
    paper = mongo_db.papers.find_one({"paper_id": paper_id, "user_id": current_user})
    if not paper: raise HTTPException(status_code=404, detail="Not found")
    return {
        "summary": paper.get("auto_summary", "Processing..."),
        "is_ready": paper.get("status") == "ready"
    }

@app.delete("/papers/{paper_id}")
def delete_paper(paper_id: str, current_user: str = Depends(get_current_user)):
    """Permanently removes a paper and ALL its associated data for the current user."""
    # Verify the paper belongs to this user
    paper = mongo_db.papers.find_one({"paper_id": paper_id, "user_id": current_user})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found or access denied")

    # 1. Wipe all MongoDB collections for this paper
    mongo_db.papers.delete_one({"paper_id": paper_id, "user_id": current_user})
    mongo_db.chat_history.delete_many({"paper_id": paper_id, "user_id": current_user})
    mongo_db.sections.delete_many({"paper_id": paper_id, "user_id": current_user})
    mongo_db.tables.delete_many({"paper_id": paper_id, "user_id": current_user})
    mongo_db.images.delete_many({"paper_id": paper_id, "user_id": current_user})

    # 2. Wipe Qdrant vectors for this paper
    try:
        from database import qdrant_client, COLLECTION_NAME
        from qdrant_client.http import models as qmodels
        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(key="paper_id", match=qmodels.MatchValue(value=paper_id)),
                        qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=current_user)),
                    ]
                )
            )
        )
    except Exception as e:
        print(f"[WARN] Could not delete Qdrant vectors: {e}")

    # 3. Clear active paper pointer if it was this paper
    mongo_db.users.update_one(
        {"email": current_user, "active_paper_id": paper_id},
        {"$unset": {"active_paper_id": ""}}
    )

    return {"status": "deleted", "paper_id": paper_id}


# --- 7. CORE PROCESSING ROUTES ---

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    try:
        os.makedirs("./uploads", exist_ok=True)
        file_path = f"./uploads/{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        paper_id = str(uuid.uuid4())
        # Run heavy ingestion in a threadpool to keep the server responsive
        result = await run_in_threadpool(ingest_paper, file_path, user_id=current_user, existing_paper_id=paper_id)
        
        from mongodb_history import set_active_paper
        set_active_paper(current_user, paper_id)
        
        return {
            "paper_id": paper_id,
            "summary": result.get("summary"),
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_with_paper(request: QueryRequest, current_user: str = Depends(get_current_user)):
    try:
        from mongodb_history import get_active_paper
        paper_id = request.paper_id or get_active_paper(current_user)
        if not paper_id: raise HTTPException(status_code=400, detail="No paper selected")
            
        save_chat_message(current_user, paper_id, "user", request.question)
        answer = ask_paper_agent(request.question, paper_id, current_user)
        # Guarantee the answer is always a plain string — never an object
        answer_str = answer if isinstance(answer, str) else str(answer)
        save_chat_message(current_user, paper_id, "assistant", answer_str)
        
        return {"answer": answer_str, "paper_id": paper_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Use Render's PORT or fallback to 8000 for local dev
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
