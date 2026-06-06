from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings  # ← changed
from langchain_core.documents import Document
import json

VECTOR_DB_PATH = "chroma_db"

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

with open("data/movies.json", "r", encoding="utf-8") as f:
    movies = json.load(f)

documents = []

for movie in movies:
    content = f"""
    Title: {movie['title']}
    Genre: {movie['genre']}
    Overview: {movie['overview']}
    Themes: {movie['themes']}
    """
    documents.append(
        Document(
            page_content=content,
            metadata={"title": movie["title"]}
        )
    )

db = Chroma.from_documents(
    documents=documents,
    embedding=embedding_model,
    persist_directory=VECTOR_DB_PATH
)

print("Movies embeddings created successfully!")