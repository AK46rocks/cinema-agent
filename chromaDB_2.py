import chromadb
import pandas as pd

chroma_client = chromadb.PersistentClient()

collection = chroma_client.get_or_create_collection(name="movie_collection_2")

if collection.count() == 0: 

    # df = pd.read_parquet("hf://datasets/CohereLabs/movies/movies.parquet")
    df = pd.read_csv("hf://datasets/drossi/EDA_on_IMDB_Movies_Dataset/imdb_top_1000.csv")
    df = df.fillna("Unknown")

    documents = []
    metadata = []
    ids= []
    id = 1

    # for title, overview, genres in df.items():
    for row in df.itertuples():
        content = f"""
        title:{row.Series_Title}
        release_year:{row.Released_Year}
        overview:{row.Overview}
        genres:{row.Genre}
        """

        documents.append(content)
        metadata.append({"title":row.Series_Title})
        ids.append(str(id))
        id+=1
    
    collection.add(
    documents=documents,
    metadatas=metadata,
    ids=ids
    )

    print("Collection populated successfully!")
else:
    print("Collection already persist!")



results = collection.query(
    query_texts=["Recommend latest trending movies"], # Chroma will embed this for you
    n_results=2, # how many results to return
    include=["documents"]
)
print(results)