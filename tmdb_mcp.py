from fastapi import FastAPI, HTTPException, Request
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TMDB MCP server")

TMDB_API = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"


@app.get("/")
def test():
    return {"status": "success", "data": "AK"}


@app.get("/movies/popular")
async def get_popular_movies():
    if not TMDB_API:
        raise HTTPException(
            status_code=500,
            detail="TMDB_API_KEY not found in .env"
        )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/movie/popular",
            params={
                "api_key": TMDB_API,
                "language": "en-US",
                "page": 1
            }
        )

    response.raise_for_status()

    return response.json()

@app.get('/trending/{media_type}')
async def getTrending(media_type:str, request: Request):
    async with httpx.AsyncClient() as httpClient:

        #Query Params
        # query_params = {**request.query_params,"api_key":TMDB_API}
        query_params = request.query_params
        print("query_params: ",query_params)
        print("media_type: ",media_type)

        response = await httpClient.get(
                f"{BASE_URL}/discover/{media_type}?api_key={TMDB_API}&{query_params}"
            )
        
        print("TMDB response---------",response)
        
        if(response.status_code != 200):
            raise HTTPException(status_code=response.status_code, detail="TMDB api error, please check the api")
        
        data = response.json()
         
        if not data:
            return {"status":"failed","data":"None"}

        trending_movie_block = []

        title_key = "title" if media_type == "movie" else "name"
        date_key = "release_date" if media_type == "movie" else "first_air_date"
        
        for movie in data['results'][:10]:

            title = movie.get(title_key, "Unknown Title")
            date = movie.get(date_key, "N/A")
            overview = movie.get("overview", "No Plot overview found.")

            if len(overview) > 140:
                overview = overview[:137] + "..."

            movie_summary = f"- **{title}** ({date}) \n Plot: {overview}"
            trending_movie_block.append(movie_summary)
        
        clean_payload = '\n'.join(trending_movie_block)
        print("T:-",clean_payload)
        
        return {"status":"success","data": clean_payload}

@app.get("/search-movie/{movie_name}")
async def search_movie(movie_name: str):
    async with httpx.AsyncClient() as httpClient:
        try:
            response = await httpClient.get(
                f"{BASE_URL}/search/multi",
                params={"api_key":TMDB_API,
                        "query":movie_name,
                        "language":"en-US",
                        "page":"1",
                        "include_adult":"true"
                        }
            )

            data = response.json()
            search_block = []

            for movie in data['results'][:5]:
                if movie["media_type"] == "person":
                    known_for = ''
                    for content in movie['known_for']:
                        known_for += f"Type: {content['media_type']}| Title: {content['title']}|Overview: {content['overview']}|Release date: {content['release_date']},"
                    
                    person_data = f"Name: {movie["name"]}| Profession: {movie['known_for_department']}| Known for: {known_for}"
                    search_block.append(person_data)
                else:
                    movie_summary = f"Title: {movie['title']}|Overview: {movie['overview']}|Release date: {movie['release_date']}"
                    search_block.append(movie_summary)
            
            return {"status":"success","data": '\n\n'.join(search_block)}

        except HTTPException as e:
            raise HTTPException(status_code=e.status_code, detail="TMDB api error!")

if __name__ == "__main__":
    import uvicorn
    # Start the local API server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)