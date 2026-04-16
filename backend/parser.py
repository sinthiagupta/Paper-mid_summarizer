import os
import re
import fitz  # PyMuPDF
from llama_parse import LlamaParse
from dotenv import load_dotenv

load_dotenv()

def extract_markdown_tables(text: str) -> list[str]:
    """
    Finds and extracts any Markdown tables inside a text block.
    """
    # Regex pattern to match standard markdown tables starting with '|'
    table_pattern = re.compile(r'(\|.*\|[\r\n]+\|[-:| ]+\|[\r\n]+(?:\|.*\|[\r\n]*)+)')
    tables = table_pattern.findall(text)
    return tables

def extract_images_from_pdf(file_path: str) -> list[str]:
    """
    Scans the PDF and extracts all pictures, graphs, and charts
    saving them to an 'extracted_images' folder.
    Returns a list of the saved image file paths.
    """
    image_paths = []
    
    # Create the folder if it doesn't exist
    output_folder = "extracted_images"
    os.makedirs(output_folder, exist_ok=True)
    
    # Open the PDF
    pdf_document = fitz.open(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    
    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        
        # Grab all images on this specific page
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Save it: extracted_images/sample_page_1_img_0.png
            image_filename = f"{output_folder}/{base_name}_page_{page_num+1}_img_{img_index}.{image_ext}"
            
            with open(image_filename, "wb") as f:
                f.write(image_bytes)
                
            image_paths.append(image_filename)
            
    return image_paths

def parse_pdf_to_sections(file_path: str) -> list[dict]:
    """
    Parses a PDF research paper and returns a list of dictionaries.
    Uses Hierarchical tracking so sub-sections remember their parent sections,
    and extracts tables as a separate array for MongoDB storage.
    """
    # 1. Initialize LlamaParse
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
        result_type="markdown",
        verbose=True
    )
    
    print(f"Parsing {file_path} using LlamaParse...")
    documents = parser.load_data(file_path)
    
    # Join all pages into one giant Markdown string
    full_markdown = "\n".join([doc.text for doc in documents])
    
    # 2. Section-Aware Splitting (Hierarchical)
    lines = full_markdown.split('\n')
    sections = []
    
    current_h1 = ""
    current_h2 = ""
    current_section_name = "Title & Metadata"
    current_content = []
    
    for line in lines:
        match = re.match(r'^(#{1,3})\s+(.*)', line)
        if match:
            # We found a new heading! First, save the PREVIOUS section we were just reading
            text = "\n".join(current_content).strip()
            if len(text) > 20: 
                sections.append({
                    "section_name": current_section_name,
                    "content": text,
                    "tables_found": extract_markdown_tables(text) # Automatically pull tables out!
                })
            
            heading_text = match.group(2).strip()
            
            # --- SMART ACADEMIC LEVEL DETECTION ---
            numbering_match = re.search(r'^(\d+(?:\.\d+)*)\.?\s+', heading_text)
            
            if numbering_match:
                logical_level = len(numbering_match.group(1).split('.'))
            else:
                logical_level = len(match.group(1)) # fallback to number of '#'
                
            # Keep track of parents so we can build names like "Parent > Child"
            if logical_level == 1:
                current_h1 = heading_text
                current_h2 = ""
                current_section_name = heading_text
            elif logical_level == 2:
                current_h2 = heading_text
                current_section_name = f"{current_h1} > {heading_text}" if current_h1 else heading_text
            else:
                parent = current_h2 or current_h1
                current_section_name = f"{parent} > {heading_text}" if parent else heading_text
                
            current_content = [] # Reset the text collector for the new section
        else:
            current_content.append(line)
            
    # Save the absolute final section at the end of the document
    text = "\n".join(current_content).strip()
    if len(text) > 20:
        sections.append({
            "section_name": current_section_name,
            "content": text,
            "tables_found": extract_markdown_tables(text) # Automatically pull tables out!
        })
        
    print(f"✅ Successfully extracted {len(sections)} logical sections!")
    return sections

# --- Auto-Detect Local Test ---
if __name__ == "__main__":
    import os
    import glob
    
    # Automatically search the current folder for ANY file ending in '.pdf'
    pdf_files = glob.glob("*.pdf")
    
    if not pdf_files:
        print("Error: No PDF files found in the current directory. Please drop a PDF here!")
    else:
        # Just pick the very first PDF it found
        target_pdf = pdf_files[0]
        print(f"📄 Auto-detected PDF: {target_pdf}")
        
        # 1. Extract Images
        print(f"🖼️ Extracting all graphs and images...")
        saved_images = extract_images_from_pdf(target_pdf)
        print(f"✅ Downloaded {len(saved_images)} images into the 'extracted_images' folder!\n")
        
        # 2. Extract Text & Tables
        sections = parse_pdf_to_sections(target_pdf)
        for sec in sections:
            print(f"Section: [{sec['section_name']}] | Length: {len(sec['content'])} | Tables: {len(sec['tables_found'])}")
