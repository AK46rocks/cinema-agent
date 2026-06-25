import chromadb
import httpx
from google import genai
from google.genai import types
from app.core.config import settings
from datetime import datetime
from state import RouterOutput, AgentState
from prompts import llm_instruction
import json

chroma_client = chromadb.PersistentClient()
collection = chroma_client.get_collection('movie_collection_2')

llm_client = genai.Client(api_key=settings.GEMINI_API_KEY)

DOMAIN_URL = 'http://127.0.0.1:8000'
model="gemini-3.1-flash-lite"

def router_node(user_query: str) -> dict:

    prompt = f"USER_QUERY:{user_query}"
    system_instruction = llm_instruction

    response = llm_client.models.generate_content(
        model=model,
        contents= prompt,
        config= types.GenerateContentConfig(
            system_instruction= system_instruction,
            response_mime_type='application/json',
            response_schema=RouterOutput,
            temperature=0.0
        )
    )

    print("RESPONSE for INTENT:-", response)

    try:
        parsed_payload = json.loads(response.parsed.discover_params)
    except Exception:
        parsed_payload = {"sort_by": "popularity.desc"} # Safe fallback map
        
    print(f"🎯 Router Identified: {response.parsed.intent.value} | Decoded payload: {parsed_payload}")


    return {
        "intent": response.parsed.intent.value,
        "extracted_argument":response.parsed.extracted_argument,
        "media_type": response.parsed.media_type,
        "discover_params": parsed_payload
    }

def fetch_analysis_node(state: AgentState) -> str:
    print("INside ANALYSIS")
    analysis_prompt = f"""
    You are an elite film critic and cinema academic. Provide a profound, thematic, 
    and spoiler-filled analysis answering the user's deep query.
    
    USER QUERY: {state.get('user_query')}
    
    Structure your answer beautifully using Markdown:
    - Break down the core meaning or ending clearly.
    - Explain hidden symbols, motifs, or directorial intent.
    - Keep it engaging, intellectual, and completely thorough.

    CRITICAL: If user query is not related to flim/tv show content related, politely refuse to answer and tell you are a Cinema Agent.
    """

    response = llm_client.models.generate_content(
        model=model,
        contents=analysis_prompt,
        config=types.GenerateContentConfig(
            temperature=0.3
        )
    )

    return {
        "final_response": response.text,
        "local_data": "Bypassed archive for internal analytical processing.",
        "live_data": "Bypassed live APIs for internal analytical processing."
    }

def fetch_trending_movies_node(state: AgentState) -> str:
    print("🔥 [Node: Trending Worker] Fetching live hot charts from TMDB...")

    #Get payload
    media_type = state.get("media_type", "movie")
    payload = state.get("discover_params", {"sort_by":"popularity.desc"})

    live_data = "Fetch data from live APIs"
    try:
        response = httpx.get(f'{DOMAIN_URL}/trending/{media_type}', params=payload,timeout=10.0)
        live_data = response.json().get("data", "No trending data returned.")
    except Exception:
        live_data = "Failed to get trending data"
    
    return {
        "local_data": "Skipped local archive layer for trending data lookup.",
        "live_data": live_data
    }

def fetch_movie_info_node(state: AgentState) -> dict:
    
    extracted_argument = state.get('extracted_argument')
    print("ARGUMENT_MOVIE_INFO:-", extracted_argument)

    #Get data from ChromaDB
    db_result = collection.query(query_texts=extracted_argument,n_results=2,include=['documents'])
    local_data = db_result['documents'][0][0] if db_result['documents'][0] else "No local data found!"
    print("LOCAL_DATA:-", local_data)

    live_data = "Fetch data from live APIs"
    try:
        response = httpx.get(f'{DOMAIN_URL}/search-movie/{extracted_argument}',timeout=5.0)
        live_data = response.json().get("data", "No movie data returned.")
    except Exception:
        live_data = "Failed to get searched movie data from API"

    return {
        "local_data": local_data,
        "live_data": live_data
    }

def fetch_actor_info_node(state: AgentState) -> str:
    extracted_argument = state.get('extracted_argument')
    print("ARGUMENT_ACTOR_INFO:-", extracted_argument)

    live_data = "Fetch data from live APIs"
    try:
        response = httpx.get(f'{DOMAIN_URL}/search-movie/{extracted_argument}',timeout=5.0)
        live_data = response.json().get("data", "No person data returned.")
    except Exception:
        live_data = "Failed to get searched person data"
    
    return {
        "local_data": "Skipped local archive layer for actor data lookup.",
        "live_data": live_data
    }

def final_compute_node(state: AgentState) -> str:
    final_prompt = f"""
    You are an expert movie guide. Answer the user's question using ONLY the movie context provided below. 
    If the answer cannot be found in the context, politely state that you don't know based on the provided dataset.
    
    LOCAL ARCHIVE:
    # {state.get('local_data')}
    
    # LIVE DATA ATTAINED:
    # {state.get('live_data')}
    
    # USER QUERY: {state.get('user_query')}

    CRITICAL: If user query is not related to flim/tv show content related, politely refuse to answer and tell you are a Cinema Agent.
    """

    system_instruction = "If the data contains duplicate titles, merge them into a single, comprehensive entry."

    print("FINAL:-",final_prompt)
    final_response = llm_client.models.generate_content(
        model=model, 
        contents=final_prompt, 
        config=types.GenerateContentConfig(
            system_instruction=system_instruction
        )
    )

    return {"final_response": final_response.text}