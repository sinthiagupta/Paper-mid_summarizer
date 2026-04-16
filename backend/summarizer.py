from database import mongo_db
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

# Setup Gemini using the modern Langchain package (which fixes the versioning bug)
# --- 2. Initialize the LLM (Gemini) ---
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest", 
    google_api_key=os.getenv("GEMINI_API_KEY")
)

def generate_paper_briefing(paper_id: str):
    """
    Generates a high-accuracy researcher's briefing by prioritizing 
    key sections (Abstract, Introduction, Conclusion).
    """
    # 1. Fetch ALL sections, sorted correctly by their order in the paper
    all_sections = list(mongo_db.sections.find({"paper_id": paper_id}).sort("index", 1))
    if not all_sections:
        return "No content found to summarize."

    # 2. Prepare the FULL context for the LLM
    context = ""
    for s in all_sections:
        raw_name = s.get("section_name", "Text Segment")
        clean_name = raw_name.replace("Section: [", "").replace("[", "").replace("]", "").replace(" > ", " - ")
        context += f"\n\n### {clean_name}\n{s['content']}\n\n"
    
    sys_prompt = """You are an Expert Research Scientist. Your task is to provide an exhaustive, high-accuracy summary of every single part of this research paper.
    CRITICAL INSTRUCTIONS: 
    1. You MUST go through EVERY single heading provided in the text sequentially (from Abstract, all the way to the end, including References or Footnotes). 
    2. Do NOT skip any content. If a section exists, summarize it.
    3. You MUST perfectly preserve and display any raw Markdown Data Tables (|---|) exactly as they appear in the text. 
    4. Provide a detailed description of any Graphs, Images, Figures, or Charts mentioned.
    5. Include the exact dates, authors, and every single bibliographic reference mentioned in the text.
    6. Maintain the original numbered section headings EXACTLY as provided."""
    
    user_prompt = f"PAPER CONTEXT:\n{context}\n\nPlease provide a highly accurate summary now:"
    
    try:
        print(f"[BRAIN] Generating High-Accuracy Briefing for Paper: {paper_id}")
        response = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)])
        return response.content
    except Exception as e:
        print(f"[ERROR] Summarizer real error: {e}")
        return "Briefing generation failed due to technical error."
