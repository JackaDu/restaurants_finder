from fastapi import FastAPI
from chat import execute_agent
from celery.result import AsyncResult
from chat import celery_app
app = FastAPI()

@app.get("/search_restaurants/{city}")
def find_restaurants(city: str):
    t = execute_agent.delay(city)
    return {
        "city": city,
        "task_id": t.task_id
    }

@app.get("/tasks/{task_id}")
def get_restaurants(task_id: str):
    res = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "res": res.result,
        "ready": res.ready()
    }

