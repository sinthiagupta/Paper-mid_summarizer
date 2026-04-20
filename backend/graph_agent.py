import os
from typing import Annotated, TypedDict, List, Union
from dotenv import load_dotenv

# LangGraph & Chain imports
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

# Import our tools from the retriever.py we just made!
from retriever import vector_search_tool, structured_table_tool

load_dotenv()

# --- 1. Define the Agent State ---
class AgentState(TypedDict):
    """The 'Memory' of our agent during a single chat."""
    question: str
    user_id: str
    paper_id: str
    chat_history: List[dict]
    retrieved_context: List[dict]
    tables: List[str]
    final_answer: str

# --- 2. Initialize the LLM (Gemini) ---
# Optimized for Free Tier Stability:
# - gemini-1.5-flash: Fastest & highest free quota
# - max_retries: Automatically waits and tries again if you hit the '15 per minute' limit
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest", 
    google_api_key=os.getenv("GEMINI_API_KEY"),
    max_retries=5,
    timeout=60
)

def router_node(state: AgentState):
    """
    Decides how to handle the question. 
    In a real app, the LLM decides, but here we enforce a logic flow.
    """
    print("[BRAIN] Node: Router (Analyzing intent...)")
    return state

def retrieval_node(state: AgentState):
    """Calls our specialized Qdrant and MongoDB tools."""
    print(f"[FIND] Node: Retrieval (Target Paper: {state.get('paper_id')}, User: {state.get('user_id')})")
    
    # 1. Semantic Search (Now scoped to specific user AND paper!)
    chunks = vector_search_tool(
        state["question"], 
        user_id=state.get("user_id"), 
        paper_id=state.get("paper_id")
    )
    
    # 2. Advanced Table Detection
    found_tables = []
    
    # If the user mentioned 'table' or 'chart', we pull ALL tables from this paper
    q_lower = state["question"].lower()
    if "table" in q_lower or "data" in q_lower:
        print("[TABLE] Question mentions tables - performing Global Table Scan...")
        from retriever import get_all_tables_tool
        tables = get_all_tables_tool(state.get("paper_id"))
        found_tables.extend(tables)
    else:
        # Fallback to older logic: only check tables in the found chunks
        for chunk in chunks:
            t = structured_table_tool(chunk["section_id"])
            if t:
                found_tables.extend(t)
            
    return {"retrieved_context": chunks, "tables": found_tables}

def synthesis_node(state: AgentState):
    """Uses Gemini to write the final expert response."""
    print("[WRITE] Node: Synthesis (Writing final response via Gemini...)")
    
    # 1. Format Context & Tables
    context_text = "\n\n".join([f"[{c['section_name']}]: {c['text']}" for c in state["retrieved_context"]])
    table_text = "\n\n".join(state["tables"])
    
    # 2. Format Chat Memory (Short & Concise to save tokens/quota)
    history_block = ""
    if state["chat_history"]:
        history_block = "\nCONVERSATION MEMORY (Last 5 turns):\n"
        for msg in state["chat_history"][-5:]: # Only use last 5!
            role = "Q" if msg["role"] == "user" else "A"
            history_block += f"{role}: {msg['content']}\n"

    prompt = f"""
    You are 'PaperMind AI', an expert research assistant. 
    Use the following paper context and memory to answer the user's question accurately.
    
    {history_block}
    
    PAPER CONTEXT:
    {context_text}
    
    TABLES FOUND:
    {table_text}
    
    CURRENT USER QUESTION: 
    {state["question"]}
    
    INSTRUCTIONS:
    - Refer back to your previous answers (Memory) if the user asks follow-up questions.
    - If a table is provided, use the data from it.
    - Be technical and professional.
    """
    
    response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=state["question"])])
    
    # Safely extract text — newer Gemini models can return a list of content parts
    raw = response.content
    if isinstance(raw, list):
        final_text = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    else:
        final_text = str(raw)
    
    return {"final_answer": final_text}

# --- 4. Build the Graph Workflow ---
workflow = StateGraph(AgentState)

# Add our nodes
workflow.add_node("router", router_node)
workflow.add_node("retrieve", retrieval_node)
workflow.add_node("generate", synthesis_node)

# Connect the nodes (The flow of logic)
workflow.set_entry_point("router")
workflow.add_edge("router", "retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

# Compile the agent!
app = workflow.compile()

def ask_paper_agent(question: str, paper_id: str, user_id: str):
    """Entry point for the FastAPI server with a robust 'Free Tier' retry loop."""
    import time
    import random
    from mongodb_history import get_chat_history
    
    # FETCH LAST 5 MESSAGES (Memory)
    history = get_chat_history(user_id, paper_id, limit=5)
    
    inputs = {
        "question": question,
        "paper_id": paper_id,
        "user_id": user_id,
        "chat_history": history
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            result = app.invoke(inputs)
            return result["final_answer"]
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "resource_exhausted" in err_str:
                wait_time = (attempt + 1) * 5 + random.uniform(0, 3)
                print(f"[QUOTA] Free Tier Limit Reached. Waiting {wait_time:.1f}s and retrying (Attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                # If it's a real error (not just a quota limit), raise it
                raise e
    
    # Final fallback if all retries fail
    raise Exception("I'm sorry, Google's Free Tier is extremely busy right now. Please wait 1 minute and try again.")

# --- TEST THE AGENT ---
if __name__ == "__main__":
    # Change this to any question you want to ask your PDF!
    user_input = "What are the main findings of the study and what does Table 1 show?"
    
    print(f"\n[START] STARTING AGENTIC SESSION: '{user_input}'\n")
    
    answer = ask_paper_agent(user_input)
    
    print("\n" + "="*50)
    print("📚 FINAL PAPERMIND RESPONSE:")
    print("="*50)
    print(answer)
    print("="*50)
