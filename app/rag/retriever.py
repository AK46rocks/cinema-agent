from app.rag.vector_store import get_vectorstore

vectorstore = get_vectorstore()

retriever = vectorstore.as_retriever(
    search_kwargs={"k": 3}
)

def retrieve_movies(query: str):
    docs = retriever.get_relevant_documents(query)
    return docs