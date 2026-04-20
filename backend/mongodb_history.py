import os
import pymongo
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- DB Setup ---
from database import mongo_db as db

def save_chat_message(user_id: str, paper_id: str, role: str, content: str):
    """
    Saves a message to the history for a specific user and paper.
    role: 'user' or 'assistant'
    """
    chat_entry = {
        "user_id": user_id,
        "paper_id": paper_id,
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    }
    db.chat_history.insert_one(chat_entry)
    print(f"[SAVE] Saved {role} message for User {user_id} on paper {paper_id}")

def get_chat_history(user_id: str, paper_id: str, limit: int = 20):
    """
    Retrieves the last N messages for a specific user and paper.
    """
    history = list(db.chat_history.find(
        {"user_id": user_id, "paper_id": paper_id}
    ).sort("timestamp", 1).limit(limit)) # Sort by time ascending
    
    # Format for the LLM
    formatted_history = []
    for entry in history:
        formatted_history.append({
            "role": entry["role"],
            "content": entry["content"]
        })
    return formatted_history

def list_all_papers(user_id: str):
    """
    Returns a list of all uploaded papers for a specific user.
    """
    papers = list(db.papers.find({"user_id": user_id}, {"_id": 0})) # Hide Mongo ID
    return papers

def set_active_paper(user_id: str, paper_id: str):
    """
    Updates the user profile to set the current 'active' paper context.
    """
    db.users.update_one(
        {"email": user_id},
        {"$set": {"active_paper_id": paper_id, "last_active_at": datetime.now()}},
        upsert=True
    )
    print(f"[CONTEXT] User {user_id} now active on paper {paper_id}")

def clear_chat_history(user_id: str, paper_id: str) -> int:
    """
    Deletes all chat messages for a specific user and paper.
    Returns the number of messages deleted.
    """
    result = db.chat_history.delete_many({"user_id": user_id, "paper_id": paper_id})
    print(f"[CLEAR] Deleted {result.deleted_count} messages for User {user_id} on paper {paper_id}")
    return result.deleted_count

def get_active_paper(user_id: str) -> str:
    """
    Retrieves the last active paper ID for a user.
    """
    user = db.users.find_one({"email": user_id}, {"active_paper_id": 1})
    if user and "active_paper_id" in user:
        return user["active_paper_id"]
    return None

if __name__ == "__main__":
    # Test
    test_id = "test_paper_123"
    save_chat_message(test_id, "user", "What is the result?")
    save_chat_message(test_id, "assistant", "The result is 42.")
    print(get_chat_history(test_id))
