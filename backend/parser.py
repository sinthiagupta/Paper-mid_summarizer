import os
import re
from llama_parse import LlamaParse
from dotenv import load_dotenv

load_dotenv()

def extract_markdown_tables(text: str) -> list[str]:
    """Finds and extracts any Markdown tables inside a text block."""
    lines = text.splitlines()
    tables = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if ('|' in line and '--' in line and re.match(r'^[ \t]*\|?[-:\s|]+[-:\s|]*$', line)):
            if i > 0 and '|' in lines[i-1]:
                start_index = i - 1
                end_index = i
                j = i + 1
                while j < len(lines) and '|' in lines[j]:
                    end_index = j
                    j += 1
                table_text = '\n'.join(lines[start_index:end_index+1])
                tables.append(table_text)
                i = end_index
        i += 1
    return tables

def parse_pdf_to_sections(file_path: str) -> list[dict]:
    """
    Parses a PDF using LlamaParse and returns sections based on Markdown headers (#).
    This version is optimized for stability and text accuracy.
    """
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
        result_type="markdown",
        verbose=True
    )
    
    documents = parser.load_data(file_path)
    full_markdown = "\n".join([doc.text for doc in documents])
    
    # Precise splitting based ONLY on standard Markdown headers: #, ##, ###
    lines = full_markdown.split('\n')
    sections = []
    current_section_name = "0. Metadata & Title"
    current_content = []
    
    for line in lines:
        header_match = re.match(r'^(#{1,6})\s+(.*)', line.strip())
        
        if header_match:
            # Save previous section
            text = "\n".join(current_content).strip()
            if text or current_section_name != "0. Metadata & Title":
                sections.append({
                    "section_name": current_section_name,
                    "content": text or "(Section Heading Only)",
                    "tables_found": extract_markdown_tables(text) if text else []
                })
            current_section_name = f"{header_match.group(1)} {header_match.group(2).strip()}"
            current_content = []
        else:
            current_content.append(line)
            
    # Save the final section
    text = "\n".join(current_content).strip()
    if text:
        sections.append({
            "section_name": current_section_name,
            "content": text,
            "tables_found": extract_markdown_tables(text)
        })
        
    print(f"✅ Extracted {len(sections)} sections and sub-sections.")
    return sections
