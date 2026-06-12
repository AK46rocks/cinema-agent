from app.core.config import settings
import chromadb
from google import genai

chroma_client = chromadb.PersistentClient()
collection = chroma_client.get_or_create_collection(name="movie_collection")

client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
    )

def rag_pipeline(user_query):
   
    q_result = collection.query( query_texts=[user_query], n_results=5, include=['documents'])
    result_doc = q_result['documents']

    context = "\n---\n".join(result_doc[0])
    # for doc in result_doc:
    #     context.join(f"\n---\n{doc}")
    
    print(context)
    print("-----------------------")

    rag_prompt = f"""
    You are a professional movie recommendation assistant. Answer the user's question using ONLY the movie context provided below. 
    If the answer cannot be found in the context, politely state that you don't know based on the provided dataset.

    ---
    MOVIEDATA CONTEXT:
    {context}
    ---

    USER QUESTION: 
    {user_query}

    ANSWER:
    """ 

    model="gemini-3.5-flash"
    response = client.models.generate_content(model=model, contents=rag_prompt)
    return response.text


query = "recommend thriller movie"

res = rag_pipeline(query)
print(res)