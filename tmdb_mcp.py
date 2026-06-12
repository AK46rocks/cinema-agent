from fastapi import FastAPI, HTTPException
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

@app.get('/trending')
async def getTrending():
    async with httpx.AsyncClient() as httpClient:
        response = await httpClient.get(
            f"{BASE_URL}/trending/movie/week",
            params={"api_key":TMDB_API}
            )
        
        print("response---------",response)
        
        if(response.status_code != 200):
            raise HTTPException(status_code=response.status_code, detail="TMDB api error, please check the api")
        
        data = response.json()
        
        trending_movie_block = []
        for movie in data['results'][:5]:
            movie_summary = f"Title: {movie['title']}|Overview: {movie['overview']}|Release date: {movie['release_date']}"
            trending_movie_block.append(movie_summary)
        
        return {"status":"success","data": '\n\n'.join(trending_movie_block)}

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