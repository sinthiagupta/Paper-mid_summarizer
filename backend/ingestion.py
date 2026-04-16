import os
import uuid
import shutil
import time
from datetime import datetime
import concurrent.futures
from dotenv import load_dotenv

# Import the existing specialized parser tools
from parser import parse_pdf_to_sections, extract_images_from_pdf, extract_markdown_tables
from database import mongo_db, qdrant_client, embed_texts, embed_sparse_batch, COLLECTION_NAME
from summarizer import generate_paper_briefing
from qdrant_client.http import models as qdrant_models

load_dotenv()


def index_in_qdrant(qdrant_docs, qdrant_metadata, qdrant_ids):
    """Worker function: indexes with BOTH dense (BGE) + sparse (SPLADE) vectors via HuggingFace cloud."""
    batch_size = 8
    for i in range(0, len(qdrant_docs), batch_size):
        batch_docs = qdrant_docs[i:i + batch_size]
        batch_meta = qdrant_metadata[i:i + batch_size]
        batch_ids = qdrant_ids[i:i + batch_size]

        # Get dense embeddings from BGE via HuggingFace API
        dense_vectors = embed_texts(batch_docs)

        # Get sparse embeddings from SPLADE via HuggingFace API
        sparse_vectors = embed_sparse_batch(batch_docs)

        # Build Qdrant points with both dense and sparse vectors
        points = []
        for j in range(len(batch_docs)):
            meta_with_text = {**batch_meta[j], "document": batch_docs[j]}

            sparse_vec = qdrant_models.SparseVector(
                indices=sparse_vectors[j]["indices"],
                values=sparse_vectors[j]["values"],
            )

            points.append(qdrant_models.PointStruct(
                id=batch_ids[j],
                vector={
                    "dense": dense_vectors[j],
                    "sparse": sparse_vec,
                },
                payload=meta_with_text,
            ))

        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )
    return True


def ingest_paper(pdf_path: str, user_id: str, existing_paper_id: str = None):
    """
    Master Ingestion Orchestrator.
    Now with Explicit Global Table Extraction.
    """
    paper_id = existing_paper_id or str(uuid.uuid4())
    file_name = os.path.basename(pdf_path)

    # 1. SPECIALIZED PARSING
    print(f"[DOC] Step 1: Deep Parsing PDF & Tables: {file_name}...")

    # A. Extract Hierarchy
    sections = parse_pdf_to_sections(pdf_path)
    if not sections:
        return {"paper_id": paper_id, "summary": "Error: Paper could not be parsed.", "file_name": file_name}

    # B. Extract Global Images
    image_paths = extract_images_from_pdf(pdf_path)
    for img_path in image_paths:
        mongo_db.images.insert_one({
            "paper_id": paper_id,
            "user_id": user_id,
            "image_path": img_path,
            "extracted_at": datetime.utcnow()
        })

    # C. GLOBAL TABLE EXTRACTION
    full_text = "\n\n".join([sec["content"] for sec in sections])
    global_tables = extract_markdown_tables(full_text)

    # Store global tables
    for table_md in global_tables:
        if not mongo_db.tables.find_one({"paper_id": paper_id, "markdown_content": table_md}):
            mongo_db.tables.insert_one({
                "table_id": str(uuid.uuid4()),
                "paper_id": paper_id,
                "user_id": user_id,
                "markdown_content": table_md,
                "is_global": True
            })

    # 2. SAVE PAPER METADATA
    mongo_db.papers.insert_one({
        "paper_id": paper_id,
        "user_id": user_id,
        "file_name": file_name,
        "status": "PROCESSING",
        "upload_date": datetime.utcnow(),
        "metrics": {
            "sections": len(sections),
            "images": len(image_paths),
            "tables": len(global_tables)
        }
    })

    qdrant_docs, qdrant_metadata, qdrant_ids = [], [], []

    print(f"[MAP] Step 2: Mapping {len(sections)} Sections to Vector Database...")
    for i, sec in enumerate(sections):
        section_id = str(uuid.uuid4())

        # Save Section to MongoDB
        mongo_db.sections.insert_one({
            "section_id": section_id,
            "paper_id": paper_id,
            "user_id": user_id,
            "content": sec["content"],
            "section_name": sec["section_name"],
            "index": i
        })

        # Link section-specific tables
        section_tables = sec.get("tables_found", [])
        for table_md in section_tables:
            mongo_db.tables.update_one(
                {"paper_id": paper_id, "markdown_content": table_md},
                {"$set": {"section_id": section_id}}
            )

        qdrant_docs.append(sec["content"])
        qdrant_metadata.append({
            "section_id": section_id,
            "paper_id": paper_id,
            "user_id": user_id,
            "source_pdf": file_name,
            "section_name": sec["section_name"]
        })
        qdrant_ids.append(section_id)

    # 3. CONCURRENT INDEXING & SUMMARIZATION (PARALLEL FOR SPEED)
    print(f"[FAST] Step 3: Indexing {len(qdrant_docs)} Vectors & Generating Briefing in Parallel...")
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Start both tasks at the same time
        future_index = executor.submit(index_in_qdrant, qdrant_docs, qdrant_metadata, qdrant_ids)
        future_summary = executor.submit(generate_paper_briefing, paper_id)
        
        # Wait for both to finish
        future_index.result()
        briefing = future_summary.result()

    # 4. FINAL COMPLETION
    mongo_db.papers.update_one(
        {"paper_id": paper_id},
        {"$set": {
            "status": "ready",
            "auto_summary": briefing
        }}
    )

    print(f"[OK] INGESTION SUCCESS: {len(global_tables)} Tables found.")

    return {
        "paper_id": paper_id,
        "summary": briefing,
        "file_name": file_name,
        "tables_found": len(global_tables),
        "images_found": len(image_paths)
    }
