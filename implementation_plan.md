# PaperMind — Modernized Project Architecture

This architecture document retains your core choices (**MongoDB, Qdrant, Flask, React**) as foundational elements for your learning goals, while upgrading the surrounding LLM/Backend tooling to the most highly-demanded capabilities in the industry right now (Multimodal Parsing, Dual-Vector Embeddings, Rerankers, and Agentic Routing).

## Tech Stack Overview

### Formally Retained (Your Constraints)
* **Databases**: **MongoDB** (Structured, Graph, Memory) & **Qdrant** (Vector Store).
* **Backend**: **Flask** (Python API server).
* **Frontend**: **Normal React** (standard React setup with Vanilla CSS, no Next.js/Vite/Tailwind).

### High-Demand Industry Upgrades
1. **Document Parsing (Ingestion)**: `PDFPlumber` -> **`LlamaParse`** (or `Unstructured.io`). Extracting from 2-column academic PDFs is notoriously hard. LlamaParse natively understands complex structures, tables, and math algorithms, making it the supreme choice for advanced RAG architectures.
2. **Embeddings**: `all-MiniLM` -> **`BAAI/bge-m3`** or **`Nomic`**. BGE-M3 is the current state-of-the-art for open-source AI. It is unique because a single pass outputs *both* the Dense vectors and the Sparse (Lexical) vectors required for your Qdrant hybrid search native implementation.
3. **Retrieval Enhancement**: **`Cohere Rerank`** (or `BGE-Reranker`). In modern enterprise RAG, after you retrieve chunks from Qdrant, you pass them through a cross-encoder model to re-score them based on the exact user question. This vastly improves accuracy and is highly looked for on resumes.
4. **Orchestrator**: **`LangGraph`**. We are keeping this! Building an "Agentic Workflow" (where the system decides *how* to answer rather than just following a straight line) is the hottest topic in AI engineering right now.

---

## 🏗️ Refined Architecture Breakdown

### The 4 Retrieval Strategies (Agentic State Machine)
A **LangGraph** orchestrator agent running in Flask receives every question, analyzes intent, and routes it dynamically to one of four retrieval paths:

| Strategy | Trigger Example | Modern Implementation |
| :--- | :--- | :--- |
| **Hybrid RAG** | "How did they train the model?" | **Qdrant** Hybrid Search (BM25 Sparse + BGE-M3 Dense) → Reciprocal Rank Fusion → **Reranked via Cohere/BGE-Reranker**. |
| **Citation Graph Traversal** | "What prior work did they build on?" | **MongoDB** `$lookup` aggregation on citation graph edges → returns related metadata. |
| **Structured Table Lookup** | "What was the exact F1 score?" | Skip vector search. **MongoDB** aggregation directly on JSON extracted rows from `LlamaParse`. |
| **Multi-Paper Comparator** | "How does Paper A compare to B?" | ThreadPool parallel retrieval from **Qdrant** → Generates synthesized comparison via Gemini LLM. |

### Two-Database Design
* **Qdrant (Vector)**: Stores BGE-M3 dense and sparse named vectors per chunk. Payload filtering strictly constrains every search to the correct section, paper_id, page, etc.
* **MongoDB (Structured/Document)**: 
  1. `papers`: Metadata (authors, dates, source).
  2. `tables`: JSON rows perfectly extracted via `LlamaParse`.
  3. `citations`: Document arrays mapping `PaperA_id -> PaperB_id` allowing recursive `$lookup`.
  4. `chat_history`: Conversational memory (LangChain native integration).

### Backend Modules (Flask + LangGraph)
1. `parser.py` — `LlamaParse` parsing and chunking. Output per section: `{ title, type, text, page_start, tables[], source_pdf }`.
2. `chunker.py` — Markdown Header Splitting, hard splits at section boundaries. MongoDB writes for citations/metadata.
3. `indexer.py` — Dense + Sparse `bge-m3` embedding computation. Write named vectors to Qdrant.
4. `retriever.py` — 4 retrieval endpoints as LangChain tools, specifically returning strict Pydantic schemas. 
5. `graph_agent.py` — LangGraph initialization. Classifies intent → routes strategy → evaluates confidence. If confidence is low, falls back to a different strategy (self-correction).
6. `app.py` — **Flask** setup with `/upload`, `/query`, `/history`, and `/compare` endpoints.

---

## 🗓️ Upgraded 14-Day Plan

* **Day 1**: Setup — Standard React boilerplate, Flask repo, MongoDB Atlas, Qdrant Cloud.
* **Day 2**: `parser.py` — Implement **LlamaParse** layout-aware section detection & table extraction.
* **Day 3**: `chunker.py` — Build chunking pipeline, write paper records and `$lookup` citation structures to MongoDB.
* **Day 4**: `indexer.py` — Generate Dense/Sparse vectors via **BGE-M3** and upsert to Qdrant named collections.
* **Day 5**: `retriever.py` — Construct the 4 isolated retrieval schemas. Integrate Reranker into the Hybrid RAG pipeline.
* **Day 6**: `graph_agent.py` — Build LangGraph state machine with the `validate_confidence` + self-correction fallback loop.
* **Day 7**: `app.py` (Flask) — Build API endpoints + test completely with 3 papers / 20 questions.
* **Day 8**: Frontend (React) — Setup standard React Layout using normal CSS. PDF upload and Chat UI scaffolding.
* **Day 9**: Frontend Integration — Connect React to Flask endpoints. Show LangGraph's internal routing ("Strategy Used: Table Lookup") visually in the chat UI.
* **Day 10**: Dockerize — `Dockerfile` for Flask, `docker-compose` combining Flask + React for local dev.
* **Day 11**: Deploy — Render or EC2 for Flask backend + Vercel for React Frontend.
* **Day 12**: Benchmarks — Test Hybrid+Reranker vs Dense-only on 20 benchmark questions.
* **Day 13**: Write paper / Technical blog post.
* **Day 14**: GitHub README + Resume update.

---

## 🚀 Resume Bullets
When completed, these resume bullets will be absolutely premium:

* **Bullet 1**: Architected an Agentic **LangGraph** orchestrator within a **Flask** backend that natively routes queries across 4 distinct retrieval tools—including hybrid vector search, structured table extraction, and MongoDB `\$lookup` citation traversal—replacing standard linear RAG pipelines.
* **Bullet 2**: Engineered dual-indexed hybrid retrieval utilizing **Qdrant** and **BGE-M3**, combining dense semantics with sparse lexical matching via Reciprocal Rank Fusion, followed by cross-encoder **Reranking**, substantially outperforming dense-only search on technical academic datasets.
* **Bullet 3**: Scaled a multimodal data ingestion pipeline leveraging **LlamaParse** to extract complex mathematical formulas and nested tables from dual-column PDFs, storing heavily structured graph arrays in **MongoDB** and interacting via a reactive frontend built with standard **React**.
