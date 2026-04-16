import os
from dotenv import load_dotenv
from qdrant_client.http import models

from database import mongo_db, qdrant_client, embed_query, embed_sparse, COLLECTION_NAME

load_dotenv()

# --- RETRIEVAL TOOLS ---


def vector_search_tool(query: str, user_id: str, paper_id: str = None, top_k: int = 10):
    """
    Skill: Hybrid Semantic + Keyword Search (BGE dense + SPLADE sparse).
    Uses HuggingFace cloud API for both embedding models.
    Fuses results using Reciprocal Rank Fusion (RRF) for best quality.
    """
    print(f"[SEARCH] Hybrid Search: '{query}' (User: {user_id}, Paper: {paper_id})")

    # Build filter conditions
    conditions = [
        models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))
    ]
    if paper_id:
        conditions.append(models.FieldCondition(key="paper_id", match=models.MatchValue(value=paper_id)))

    search_filter = models.Filter(must=conditions)

    # Get dense embedding (BGE) via HuggingFace cloud
    dense_vector = embed_query(query)

    # Get sparse embedding (SPLADE) via HuggingFace cloud
    sparse_result = embed_sparse(query)
    sparse_vector = models.SparseVector(
        indices=sparse_result["indices"],
        values=sparse_result["values"],
    )

    # Hybrid search: combine dense + sparse with Reciprocal Rank Fusion
    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(
                query=dense_vector,
                using="dense",
                filter=search_filter,
                limit=top_k,
            ),
            models.Prefetch(
                query=sparse_vector,
                using="sparse",
                filter=search_filter,
                limit=top_k,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
    )

    output = []
    for res in results.points:
        output.append({
            "section_id": res.payload.get("section_id"),
            "section_name": res.payload.get("section_name"),
            "text": res.payload.get("document", "")
        })
    return output


def get_all_tables_tool(paper_id: str):
    """
    Skill: Global Table Retrieval.
    Use this to retrieve EVERY table found in a specific paper.
    """
    print(f"[TABLE] Global Table Retrieval for Paper: {paper_id}")
    tables = mongo_db.tables.find({"paper_id": paper_id})
    return [t["markdown_content"] for t in tables]


def structured_table_tool(section_id: str):
    """
    Skill: Data Extraction.
    Use this if the Agent notices a section contains tables.
    """
    print(f"[TABLE] Table Tool Access for Section: {section_id}")
    tables = mongo_db.tables.find({"section_id": section_id})
    return [t["markdown_content"] for t in tables]


def metadata_lookup_tool(paper_id: str = None):
    """
    Skill: Metadata Analysis.
    Use this to find Paper titles, counts, or specific citations.
    """
    if paper_id:
        return mongo_db.papers.find_one({"paper_id": paper_id})
    return list(mongo_db.papers.find())
