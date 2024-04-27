from celery import Celery
from dotenv import load_dotenv
from chat import *
import os

load_dotenv()
celery_app = Celery('worker', backend=os.environ.get('REDIS_URL'), broker=os.environ.get('REDIS_URL'))

@celery_app.task
def hello():
    return 'hello world'