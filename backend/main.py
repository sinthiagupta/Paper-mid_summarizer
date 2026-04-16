import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from starlette.concurrency import run_in_threadpool
from datetime import datetime

# Import our backend logic
from ingestion import ingest_paper
from graph_agent import ask_paper_agent
from mongodb_history import save_chat_message, get_chat_history, list_all_papers
from database import mongo_db
from auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    decode_access_token, 
    verify_google_token
)

app = FastAPI(title="PaperMind API")

# Setup Auth Security
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Verifies the JWT token and returns the current user email."""
    email = decode_access_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return email

# Setup CORS for React (Port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # More permissive for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserSignup(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    token: str # The ID token from Google Frontend

class QueryRequest(BaseModel):
    question: str
    paper_id: Optional[str] = None # Now optional! System uses last active paper if empty.

@app.get("/")
def home():
    return {"message": "Welcome to PaperMind API"}

# --- AUTHENTICATION ROUTES ---

@app.post("/auth/signup")
async def signup(user: UserSignup):
    """Creates a new user account with full profile details and logs the event."""
    if mongo_db.users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = {
        "email": user.email,
        "password": hashed_password,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "created_at": datetime.utcnow()
    }
    mongo_db.users.insert_one(new_user)
    
    # Log Auth History
    mongo_db.auth_logs.insert_one({
        "email": user.email,
        "action": "SIGNUP",
        "timestamp": datetime.utcnow(),
        "method": "CREDENTIALS"
    })
    
    return {"message": "User created successfully"}

@app.post("/auth/google")
async def google_auth(request: GoogleLoginRequest):
    """Verifies Google token, creates/finds user, and logs the event."""
    idinfo = verify_google_token(request.token)
    if not idinfo:
        raise HTTPException(status_code=401, detail="Invalid Google Token")
    
    email = idinfo['email']
    first_name = idinfo.get('given_name', "")
    last_name = idinfo.get('family_name', "")
    
    # Find or Create User
    db_user = mongo_db.users.find_one({"email": email})
    if not db_user:
        mongo_db.users.insert_one({
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "auth_method": "GOOGLE",
            "created_at": datetime.utcnow()
        })
        print(f"[NEW] New User created via Google: {email}")

    # Log Auth History
    mongo_db.auth_logs.insert_one({
        "email": email,
        "action": "LOGIN",
        "timestamp": datetime.utcnow(),
        "method": "GOOGLE"
    })
    
    access_token = create_access_token(data={"sub": email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Logs in and records history. (Supports Swagger Authorize button)"""
    # Swagger sends 'username', which we use as 'email'
    db_user = mongo_db.users.find_one({"email": form_data.username})
    
    if not db_user or not db_user.get("password") or not verify_password(form_data.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Log Auth History
    mongo_db.auth_logs.insert_one({
        "email": form_data.username,
        "action": "LOGIN",
        "timestamp": datetime.utcnow(),
        "method": "CREDENTIALS"
    })
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/papers")
def get_papers(current_user: str = Depends(get_current_user)):
    """Returns a list of all papers ONLY for the logged-in user."""
    try:
        return list_all_papers(current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/papers/{paper_id}/select")
def select_paper(paper_id: str, current_user: str = Depends(get_current_user)):
    """Manually switches the active research context to a specific paper."""
    from mongodb_history import set_active_paper
    paper = mongo_db.papers.find_one({"paper_id": paper_id, "user_id": current_user})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found or unauthorized")
    
    set_active_paper(current_user, paper_id)
    return {"status": "success", "message": f"Active context switched to paper: {paper_id}"}

@app.get("/history/{paper_id}")
def get_history(paper_id: str, current_user: str = Depends(get_current_user)):
    """Retrieves chat history for a specific paper and user."""
    try:
        return get_chat_history(current_user, paper_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/papers/{paper_id}/summary")
def get_paper_summary(paper_id: str, current_user: str = Depends(get_current_user)):
    """Returns the summary status and content if ready."""
    paper = mongo_db.papers.find_one({"paper_id": paper_id, "user_id": current_user})
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    status = paper.get("status", "processing")
    summary = paper.get("auto_summary")
    
    return {
        "paper_id": paper_id,
        "status": status,
        "summary": summary if status == "ready" else "Summary is being generated in the background. Please check back in a moment.",
        "is_ready": status == "ready"
    }

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    """Handles PDF upload and returns EVERYTHING (Summary + ID) in one go."""
    try:
        os.makedirs("./uploads", exist_ok=True)
        file_path = f"./uploads/{file.filename}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        import uuid
        paper_id = str(uuid.uuid4())
        print(f"[START] Processing Paper: {file.filename} (ID: {paper_id})...")
        
        # 1. Block and wait for Ingestion + Summary
        from ingestion import ingest_paper
        result = await run_in_threadpool(ingest_paper, file_path, user_id=current_user, existing_paper_id=paper_id)
        
        # 2. Automatically set as active
        from mongodb_history import set_active_paper
        set_active_paper(current_user, paper_id)
        
        return {
            "status": "success",
            "paper_id": paper_id,
            "summary": result.get("summary"),
            "message": "Paper ingested and summarized successfully. You can chat now!"
        }
    except Exception as e:
        print(f"[ERROR] Upload Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_with_paper(request: QueryRequest, current_user: str = Depends(get_current_user)):
    """Passes user question to the Agent and saves context automatically."""
    try:
        # Determine the target paper ID (Request ID or Fallback to Active Session)
        from mongodb_history import get_active_paper
        paper_id = request.paper_id or get_active_paper(current_user)
        
        if not paper_id:
            raise HTTPException(
                status_code=400, 
                detail="No paper context found. Please upload a paper or select one first."
            )
            
        # 1. Save user message
        save_chat_message(current_user, paper_id, "user", request.question)
        
        # 2. Get Agent response (Now with User + Paper Isolation!)
        print(f"[USER] User {current_user} Question (Paper {paper_id}): {request.question}")
        answer = ask_paper_agent(request.question, paper_id, current_user)
        
        # 3. Save assistant response
        save_chat_message(current_user, paper_id, "assistant", str(answer))
        
        return {"answer": answer, "paper_id": paper_id} # Return ID so frontend knows which paper was used
    except Exception as e:
        print(f"[ERROR] Chat Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
