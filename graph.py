from langgraph.graph import StateGraph, START, END
from state import AgentState, Intent
from nodes import router_node, fetch_actor_info_node, fetch_movie_info_node, fetch_trending_movies_node,fetch_analysis_node, final_compute_node

#Build a pipeline
workflow = StateGraph(AgentState)

#Register nodes
workflow.add_node("router_node", router_node)
workflow.add_node("fetch_movie_info_node", fetch_movie_info_node)
workflow.add_node("fetch_actor_info_node", fetch_actor_info_node)
workflow.add_node("fetch_trending_movies_node", fetch_trending_movies_node)
workflow.add_node("fetch_analysis_node", fetch_analysis_node)
workflow.add_node("final_compute_node", final_compute_node)

#Build Branch/ Edge logic
def intent_conditional_edge(state: AgentState):
    intent_flag = state["intent"]

    if intent_flag == Intent.MOVIE_INFO:
        return "route_to_movie"
    elif intent_flag == Intent.ACTOR_INFO:
        return "route_to_actor"
    elif intent_flag == Intent.TRENDING:
        return "route_to_trending"
    elif intent_flag == Intent.ANALYSIS:
        return "route_to_analysis"
    
    return "route_to_movie"

workflow.add_edge(START, "router_node")

#Condition Edge
workflow.add_conditional_edges(
    "router_node", 
    intent_conditional_edge, 
    {
        "route_to_movie":"fetch_movie_info_node",
        "route_to_actor":"fetch_actor_info_node",
        "route_to_trending":"fetch_trending_movies_node",
        "route_to_analysis":"fetch_analysis_node"
    }
)

workflow.add_edge("fetch_movie_info_node", "final_compute_node")
workflow.add_edge("fetch_actor_info_node", "final_compute_node")
workflow.add_edge("fetch_trending_movies_node", "final_compute_node")
workflow.add_edge("fetch_analysis_node", END)
workflow.add_edge("final_compute_node", END)

cinema_agent = workflow.compile()

if __name__ == "__main__":
    # Execution Test Run A: Triggers MOVIE_INFO path
    # print("=== PIPELINE INVOCATION A ===")
    # output_a = cinema_agent.invoke({"user_query": "Can you give me the data breakdown for Inception?"})
    # print("\nResult Text:\n", output_a["final_response"])
    
    # print("\n" + "="*50 + "\n")
    
    # Execution Test Run B: Triggers ACTOR_INFO path
    # Who is Christopher Nolan and what films has he done?

    print("=== PIPELINE INVOCATION B ===")
    # output_b = cinema_agent.invoke({"user_query": "Show me what web series and TV shows are trending right now"})
    # output_b = cinema_agent.invoke({"user_query": "What are the most famous all time popular TV shows ever made?"})
    # output_b = cinema_agent.invoke({"user_query": "Are there any good trending shows on Amazon Prime"})
    # output_b = cinema_agent.invoke({"user_query": "Recommend some popular trending movies from Bollywood"})
    # output_b = cinema_agent.invoke({"user_query": "Any popular french movie?"})
    # output_b = cinema_agent.invoke({"user_query": "Recommend me some action comedy movies to watch"})
    # output_b = cinema_agent.invoke({"user_query": "Recommend me romance kdrama"})
    # output_b = cinema_agent.invoke({"user_query": "In Tumbbad movie, the mythological horror elements of Hastar as a literal physical manifestation of generational greed, and how does the ending suggest that this cycle is impossible to break?"})
    # output_b = cinema_agent.invoke({"user_query": "Recommend me kdrama of action category"})
    output_b = cinema_agent.invoke({"user_query": "Recommend me web series of "})
    print("\nResult Text:\n", output_b["final_response"])