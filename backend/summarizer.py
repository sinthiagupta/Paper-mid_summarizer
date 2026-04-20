from database import mongo_db
import os
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

# RESTORED: Using the original stable model string
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest", 
    google_api_key=os.getenv("GEMINI_API_KEY")
)

def generate_paper_briefing(paper_id: str):
    """
    Generates a briefing with a specific structure: 
    # Paper Title 
    Authors, Date, and Place 
    Detailed sections.
    """
    all_sections = list(mongo_db.sections.find({"paper_id": paper_id}).sort("index", 1))
    if not all_sections:
        return "No content found to summarize."

    context = ""
    for s in all_sections:
        name = s.get("section_name", "Section")
        context += f"\n\n### {name}\n{s['content']}\n\n"
        
    # --- CRITICAL FIX: Bypass Token Limits (TPM) by truncating massive files ---
    # 80,000 characters is ~20,000 tokens, well below the 1 million limit, ensuring successful generation
    if len(context) > 80000:
        context = context[:80000] + "\n\n... [REMAINDER TRUNCATED TO FIT API LIMITS] ..."

    
    sys_prompt = """You are an Academic Research Assistant. Summarize this paper following this EXACT structure:
    
    1. # [MAIN PAPER TITLE]
    2. [AUTHORS, DATE, AND CONFERENCE/PLACE] (Summarize this from the Metadata section)
    3. ## Executive Summary (High-level overview)
    4. ## Technical Breakdown (Summarize every section and sub-section provided in the context)
    
    CRITICAL RULES:
    - Preserve all Markdown Tables (|---|).
    - Maintain the hierarchy of headers (## for main, ### for sub-sections).
    - Output ONLY pure Markdown.
    """
    
    user_prompt = f"PAPER CONTENT:\n{context}\n\nGenerate the structured summary now:"
    
    # --- AUTO-RETRY LOOP (3 attempts) ---
    for attempt in range(3):
        try:
            print(f"[BRAIN] Summarizing: {paper_id} (Attempt {attempt + 1})")
            response = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
            
            # Safely extract text — newer Gemini models can return a list of content parts
            raw = response.content
            if isinstance(raw, list):
                final_text = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw
                )
                return final_text
            else:
                return str(raw)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print(f"⚠️ [QUOTA WINDOW] API limit hit. Waiting 65s for reset so we don't lose the summary...")
                time.sleep(65)
            elif "503" in error_str or "UNAVAILABLE" in error_str:
                print(f"⚠️ [HIGH DEMAND 503] Server overloaded. Retrying in 10s...")
                time.sleep(10)
            else:
                print(f"❌ [ERROR] {e}")
                # If primary model fails again with 404, fallback to flash-latest automatically
                if "404" in error_str:
                    print("🔄 [FALLBACK] Trying 'gemini-flash-latest'...")
                    fallback_llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=os.getenv("GEMINI_API_KEY"))
                    try:
                        resp = fallback_llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
                        raw_fb = resp.content
                        if isinstance(raw_fb, list):
                            return " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw_fb)
                        else:
                            return str(raw_fb)
                    except Exception as fallback_e:
                        print(f"❌ [FALLBACK ERROR] {fallback_e}")
                        return f"Summary failed on fallback: {fallback_e}"
                return f"Summary failed: {e}"
                
    return "AI Quota depleted. Please wait a few minutes."
