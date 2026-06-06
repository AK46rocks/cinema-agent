from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings


embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

VECTOR_DB_PATH = "chroma_db"

def get_vectorstore():
    return Chroma(persist_directory=VECTOR_DB_PATH,
        embedding_function=embedding_model
    )