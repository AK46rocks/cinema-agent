import chromadb
import httpx
from google import genai
from google.genai import types
from app.core.config import settings
from datetime import datetime

chroma_client = chromadb.PersistentClient()
collection = chroma_client.get_collection('movie_collection')

llm_client = genai.Client(api_key=settings.GEMINI_API_KEY)

DOMAIN_URL = 'http://127.0.0.1:8000'

def fetch_trending_movies() -> str:
    try:
        response = httpx.get(f'{DOMAIN_URL}/trending',timeout=10.0)
        return response.json().get("data", "No trending data returned.")
    except Exception:
        return "Failed to get trending data"

def fetch_searched_movie_or_person(content: str) -> str:
    try:
        print("ARGUMENT:-", content)
        response = httpx.get(f'{DOMAIN_URL}/search-movie/{content}',timeout=10.0)
        return response.json().get("data", "No movie or person data returned.")
    except Exception:
        return "Failed to get searched movie or person data"

def skip_live_api_call(reason: str) -> str:
    """
    Call this function ONLY if the user's query can be perfectly answered by the 
    data available in the LOCAL DATA ARCHIVE block, meaning NO real-time streaming information is required.
    """
    return "Local context is fully sufficient. Skipping TMDB fetch."

def run_cinemaverse_llm_agent(user_query: str):
    print("User query: ", user_query)
    model="gemini-3.1-flash-lite"

    # fetch data locally from ChormaDB
    db_result = collection.query(
        query_texts=[user_query], 
        n_results=2, 
        include=["documents"]
    )
    local_result = db_result['documents'][0][0] if db_result['documents'][0] else "No matching local archive data found."
    # local_result = "\n---\n".join(db_result['documents'][0])
    print(local_result)
    
    #check is local data satisfies user's query
    current_date = f"{datetime.now().month} {datetime.now().month}" 
    current_year = datetime.now().year

    system_instruction = f"""
    You are an advanced real-time movie assistant agent. Today's date is {current_date}.
    
    CRITICAL RULE: The LOCAL ARCHIVE SNIPPET FOR REFERENCE contains static historical movie entries from past years. 
    If the USER QUERY is asking for 'trending', 'latest', 'new', 'live', or 'current stream movies or tv show data, 
    you MUST call the corresponding external tool which are config and passes as tools.
    """

    # 3. Present the data cleanly to the model
    content_prompt = f"""
    LOCAL ARCHIVE SNIPPET FOR REFERENCE:
    {local_result}
    
    USER QUERY: 
    {user_query}
    """

    #fetch real-time data from TMDB MCP APIs
    mcp_tools = [fetch_trending_movies, fetch_searched_movie_or_person]

    print("🧠 Gemini is analyzing which mcp tool to use...")
    response = llm_client.models.generate_content(
        model=model,
        contents=content_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=mcp_tools,
            temperature=0.0, # Keep it precise for routing
        )
    )

    # live_data = ""

    # print("RESPONSE GENERATED :--", response)
    # print("FUNCTION CALLS:--", response.function_calls)
    # if response.function_calls:
    #     for function in response.function_calls:
    #         name = function.name
    #         args = dict(function.args)

    #         match name:
    #             case "skip_live_api_call":
    #                 print("✅ Local data is sufficient! Skipping external API call entirely.")
    #                 live_data = "No real-time network search needed. Local files are up-to-date."
    #             case "fetch_trending_movies":
    #                 live_data = fetch_trending_movies(**args)
    #             case "fetch_searched_movie_or_person":
    #                 live_data = fetch_searched_movie_or_person(**args)

    # else:
    #   print("NO need of MCP server function call, local data is sufficent!")

    # final_prompt = f"""
    # You are an expert movie guide. Answer the user's question using ONLY the movie context provided below. 
    # If the answer cannot be found in the context, politely state that you don't know based on the provided dataset.
    
    # LOCAL ARCHIVE:
    # {local_result}
    
    # LIVE DATA ATTAINED:
    # {live_data}
    
    # USER QUERY: {user_query}
    # """ 

    # final_response = llm_client.models.generate_content(model=model, contents=final_prompt)
    return response.text


user_query = "Who directed Interstellar?"
print(user_query)
llm_result = run_cinemaverse_llm_agent(user_query)
print("AI response:--",llm_result)


