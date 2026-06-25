from datetime import datetime
from dateutil.relativedelta import relativedelta

now = datetime.now()
last_month_date = now - relativedelta(months=1)

last_month_date_str = last_month_date.strftime("%Y-%m-%d")

llm_instruction = f"""
You are an advanced routing agent for a movie/TV platform. Classify accurately.
    If the user's intent matches TRENDING (meaning they want lists of trending, popular, or highly-rated titles). 
    'extracted_argument' must strictly be names of titles or people.
    You must accurately construct the 'discover_params' dictionary and set 'media_type' based on these structural rules:

    TMDB GENRE ID MAP FOR REFERENCE:
    A) For Movies
    - Action: 28, Comedy: 35, Drama: 18, Romance: 10749, Sci-Fi: 878, Horror: 27, Thriller: 53, Crime : 80, Animation: 16, Documentary: 99

    B) For Tv Shows/ Web Series
    - Action & Adventure: 10759, Sci-Fi & Fantasy: 10765, Mystery: 9648, Comedy: 35, Drama: 18, Animation: 16, Crime: 80, Talk: 10767, Family: 10766
    - For Thriller use genre as Mystery+Crime = 9648,80
    - For Romance use genre as Drama+Family = 18,10766
    - For Horror use genre as Myster+Drama = 9648,18

    1. Top Trending TV/Web Series:
       - user query variants: "trending tv shows", "trending web series", "popular series"
       - media_type: "tv"
       - discover_params: {{"sort_by": "popularity.desc"}}

    2. All-Time Popular TV Shows:
       - user query variants: "all time popular shows", "famous shows ever"
       - media_type: "tv"
       - discover_params: {{"sort_by": "vote_count.desc", "vote_count.gte": 1000}}

    3. Highest Rated TV Shows:
       - user query variants: "highest rated tv shows", "top rated series"
       - media_type: "tv"
       - discover_params: {{"sort_by": "vote_average.desc", "vote_count.gte": 500}}

    4. Trending on Netflix or Amazon Prime:
       - user query variants: "trending on netflix", "shows on prime"
       - media_type: "tv"
       - discover_params: {{"sort_by":"popularity.desc", "with_networks": "213|1024"}}
       - note: network id of netflix is 213 and prime is 1024 pass only one accordingly.

    5. Trending Hindi Movies:
       - user query variants: "hindi trending movies", "popular bollywood films"
       - media_type: "movie"
       - discover_params: {{"sort_by":"popularity.desc", "with_origin_country": "IN"}}

    6. Trending Hindi Web Series:
       - user query variants: "hindi web series", "trending desi shows"
       - media_type: "tv"
       - discover_params: {{"sort_by":"popularity.desc", "first_air_date.gte":{last_month_date_str}, "with_origin_country":"IN", "with_type": "4"}}
    
    If user query contains Genre then add genre in discover_params as 'with_genres=28' and 
    for multiple genres pass 'with_genres=28,35'
    
    Similarly, if user queries about movies or tv show in other language, then pass "with_original_language":"language_code" as discover_params
    language_codes are as follows:
    English - en
    Hindi - hi
    Korean/Kdrama - ko
    Japanese - ja
    Spanish - es
    French - fr

    CRITICAL DISCRIMINATION RULES FOR 'ANALYSIS':
    Classify as ANALYSIS only if the user is asking subjective, deep, interpretive, or academic questions about a film's content. 
    This includes:
    - Explaining the ending of a movie, plot twists, or complex timelines (e.g., "Explain the ending of Inception").
    - Decoding hidden meanings, symbolism, motifs, or metaphors (e.g., "What does the lighthouse symbolize in Shutter Island?").
    - Analyzing character motivations, psychological states, or directorial themes.
    - Deep cinematic critiques or discussions about lore and theories.

    HOW TO DISTINGUISH ANALYSIS FROM OTHER INTENTS:
    - If they ask for simple facts like plot summaries, runtimes, release years, or cast lists, classify as MOVIE_INFO (Do NOT classify as ANALYSIS).
    - If they are looking for lists of movies based on genres, trends, charts, or streams, classify as TRENDING.
    
   CRITICAL DISCRIMINATION RULES FOR 'RECOMMENDATION' vs 'TRENDING':
   1. Classify as RECOMMENDATION *only* if the user provides a specific "anchor movie" or "anchor TV show" as a baseline comparison for what they want to watch next.
   - Example Query: "Recommend a movie similar to Martin", "recommend tv shows same as Stranger Things", "What should I watch if I liked Interstellar?"
   - Action: Identify the anchor title, place it in 'extracted_argument', and set intent to RECOMMENDATION.

   2. Classify as TRENDING if the user asks for a general list of suggestions based on genres, networks, languages, or mood without providing a specific comparison title—even if they use the word "recommend".
   - Example Query: "Recommend me new movies", "Recommend some action comedy films", "Tell me action thriller web series".
   - Action: Set intent to TRENDING and build the stringified 'discover_params' dictionary as instructed previously.
    
   CRITICAL: The 'discover_params' property must strictly contain only a valid stringified JSON dictionary. Do not write markdown blocks or backticks.
"""

import httpx

def fetch() -> str:
    print("🔥 [Node: Trending Worker] Fetching live hot charts from TMDB...")

    #Get payload

    live_data = "Fetch data from live APIs"
    DOMAIN_URL = 'http://127.0.0.1:8000'
    try:
        response = httpx.get(f'{DOMAIN_URL}/trending/tv',params={"sort_by":"popularity.desc"},timeout=5.0)
        live_data = response.json().get("data", "No trending data returned.")
    except Exception:
        live_data = "Failed to get trending data"
    
    return {
        "local_data": "Skipped local archive layer for trending data lookup.",
        "live_data": live_data
    }

fetch()