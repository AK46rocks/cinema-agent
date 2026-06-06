import chromadb
import pandas as pd

chroma_client = chromadb.PersistentClient()

collection = chroma_client.get_or_create_collection(name="movie_collection")

if collection.count() == 0: 

    df = pd.read_parquet("hf://datasets/CohereLabs/movies/movies.parquet")
    df = df.fillna("Unknown")

    documents = []
    metadata = []
    ids= []
    id = 1

    # for title, overview, genres in df.items():
    for row in df.itertuples():
        content = f"""
        title:{row.title}
        overview:{row.overview}
        genres:{row.genres}
        """

        documents.append(content)
        metadata.append({"title":row.title})
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
    query_texts=["Inception"], # Chroma will embed this for you
    n_results=2, # how many results to return
    include=["distances"]
)
print(results)