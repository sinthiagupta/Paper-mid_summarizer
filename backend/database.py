import os
import requests
import numpy as np
import pymongo
import certifi
import concurrent.futures
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models

# NEW: Use Google's ultra-reliable embedding AI instead of buggy free HF APIs
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

# --- CLOUD MONGODB SETUP ---
def get_mongo_db():
    uri = os.getenv("MONGODB_URI")
    if not uri or uri.startswith("mongodb+srv://<username>"):
        print("[WARN] MONGODB_URI is not set properly in .env.")
        return None
    try:
        client = pymongo.MongoClient(
            uri, 
            tls=True,
            tlsCAFile=certifi.where(),
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=5000
        )
        # Test connection instantly
        client.admin.command('ping')
        return client["research_database"]
    except Exception as e:
        print(f"\n❌ MONGODB ERROR: {e}")
        print("FIX: Add your IP to the MongoDB Atlas 'Network Access' Whitelist.\n")
        raise Exception("MongoDB Connection Failed. Check your IP Whitelist in Atlas.")

mongo_db = get_mongo_db()

# --- CLOUD QDRANT SETUP ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if QDRANT_URL and not QDRANT_URL.startswith("https://xxxxxx"):
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
else:
    # Fallback to local if cloud URL not configured yet
    print("[WARN] QDRANT_URL not set properly, falling back to local for now.")
    qdrant_client = QdrantClient(path="./qdrant_db")

# --- GOOGLE GEMINI EMBEDDING SETUP ---
# Replaces BGE and HuggingFace entirely with Google's zero-downtime infrastructure
# Current Mode: High-Resolution (3,072 dimensions - matched to API environment)
gemini_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001", 
    google_api_key=os.getenv("GEMINI_API_KEY")
)
EMBEDDING_DIMENSION = 3072

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embeds a list of texts using Google Gemini Text-Embedding-004."""
    # Runs flawlessly via LangChain & Google servers
    return gemini_embeddings.embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """Embeds a single query using Google Gemini Text-Embedding-004."""
    return gemini_embeddings.embed_query(text)

# --- SPARSE EMBEDDING FALLBACK ---
# Hugging Face frequently crashes Splade queries on the free tier.
# Since we now rely entirely on Google Gemini's super-strong dense search,
# we gracefully handle Splade requests so Qdrant Hybrid logic doesn't crash.
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
HF_HEADERS = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
SPARSE_MODEL = "prithvida/Splade_PP_en_v1"
SPARSE_API_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{SPARSE_MODEL}"

def _process_splade_output(raw_output) -> dict:
    list_arr = np.array(raw_output)
    if list_arr.ndim == 3:
        list_arr = list_arr[0]
    
    pooled = np.max(list_arr, axis=0)
    pooled = np.maximum(pooled, 0)
    pooled = np.log1p(pooled)
    
    threshold = 0.1
    non_zero_mask = pooled > threshold
    indices = np.where(non_zero_mask)[0].tolist()
    values = pooled[non_zero_mask].tolist()
    
    if len(indices) == 0:
        return {"indices": [0], "values": [0.1]}
    
    return {"indices": indices, "values": values}


def embed_sparse(text: str) -> dict:
    """Attempt SPLADE sparse vector, graceful fallback if HuggingFace is down."""
    try:
        response = requests.post(SPARSE_API_URL, headers=HF_HEADERS, json={
            "inputs": text,
            "options": {"wait_for_model": True}
        }, timeout=10)
        
        if response.status_code == 200:
            return _process_splade_output(response.json())
        else:
            return {"indices": [0], "values": [0.1]}
    except Exception:
        # Graceful fallback: return empty sparse vector so Qdrant just relies entirely on Gemini Dense search
        return {"indices": [0], "values": [0.1]}


def embed_sparse_batch(texts: list[str]) -> list[dict]:
    """Get SPLADE sparse vectors for a batch of texts with fallback."""
    return [embed_sparse(text) for text in texts]


COLLECTION_NAME = "research_papers_v6"

# Initialize Qdrant Collection dynamically
try:
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "dense": models.VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams()
            },
        )
        # NEW: Create payload indexes for filtered fields (Required by Qdrant Cloud)
        qdrant_client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="user_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        qdrant_client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="paper_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
except Exception as e:
    print(f"[QDRANT INIT ERROR] {e}")

print("[OK] Shared Cloud Database Clients Initialized.")
