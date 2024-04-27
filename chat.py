import json, os, requests
from dotenv import load_dotenv
from celery.app import Celery
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import tool, AgentExecutor
from apify_client import ApifyClient
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import List
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from celery import shared_task

load_dotenv()
celery_app = Celery(
    __name__,
    broker=os.environ.get('REDISCLOUD_URL'),
    backend=os.environ.get('REDISCLOUD_URL')
)

# calculate starttimestamp for tiktok videos
def get_start_time():
    d = datetime.today() - timedelta(days=365)
    return d.strftime("%m/%d/%Y")


@tool
def get_tiktok_info(hashtag: str, query: str) -> List[str]:
    "search info in tiktok based on query and get list of results"
    client = ApifyClient(os.environ['APIFY_API_TOKEN'])
    run_input = {
        "hashtags": [
            hashtag
        ],
        "resultsPerPage": 150,
        "searchQueries": [
            query
        ],
        "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadVideos": False,
        "searchSection": "",
        "maxProfilesPerQuery": 10
    }
    # Run the Actor and wait for it to finish
    run = client.actor("clockworks/free-tiktok-scraper").call(run_input=run_input)
    dataset = client.dataset(run["defaultDatasetId"])
    restaurants = []
    for item in dataset.iterate_items():
        restaurants.append(f"{item['text']} {item['webVideoUrl']} {item['createTimeISO']}")
    return restaurants

@tool
def get_yelp_restaurants_reviews(restaurant_name: str, city: str) -> dict:
    "Fetch reviews for restaurant from yelp"
    client = ApifyClient(os.environ['APIFY_API_TOKEN'])
    run_input = {
        "debugLog": False,
        "locations": [
            city
        ],
        "maxImages": 0,
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": [
                "RESIDENTIAL"
            ]
        },
        "reviewLimit": 10,
        "reviewsLanguage": "ALL",
        "scrapeReviewerName": False,
        "scrapeReviewerUrl": False,
        "searchLimit": 1,
        "searchTerms": [
            restaurant_name
        ],
        "directUrls": [],
        "maxRequestRetries": 10
    }
    run = client.actor("tri_angle/yelp-scraper").call(run_input=run_input)
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        return item

@shared_task
def execute_agent(city):
    tools = [get_tiktok_info, get_yelp_restaurants_reviews]
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"""
                    Search tiktok for new restaurants in a given city string provided by the user.
                    For example, for user input of 'SF', you can search for query of 'san francisco newly opened restaurants'
                    and hashtag of 'sanfranciscorestaurants'.
                    For 10 posts posted after {get_start_time()}, verify EACH from yelp that it is indeed newly opened.
                    If the review count is greater than 50, you should not consider it as newly opened.
                    Output up to 5 restaurants that MUST pass all the verification as JSON:
                    ```
                    {{{{
                        "name": name of the restaurant, use yelp info to correct the spelling
                        "category": category of the restaurant,
                        "video_url": tiktok video url,
                        "address"(optional): string address info from yelp,
                        "date_opened"(optional): formatted like '2023-10-10'
                    }}}}, ..
                    ```
                    -------------------------------
                    ONLY JSON list IS ALLOWED as an answer. No explanation or other text is allowed. No leading json string added.
                """,
            ),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    llm = ChatOpenAI(model="gpt-4-turbo", temperature=0, api_key=os.environ['OPENAI_API_KEY'])
    llm_with_tools = llm.bind_tools(tools)
    agent = (
        {
            "input": lambda x: x["input"],
            "agent_scratchpad": lambda x: format_to_openai_tool_messages(
                x["intermediate_steps"]
            ),
        }
        | prompt
        | llm_with_tools
        | OpenAIToolsAgentOutputParser()
    )
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    result = agent_executor.invoke(
        {"input": city}
    )
    return result['output']
