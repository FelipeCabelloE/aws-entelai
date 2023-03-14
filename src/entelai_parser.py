from socketserver import DatagramRequestHandler
from dotenv import load_dotenv
import os
import requests
load_dotenv()

ENTELAI_TOKEN = os.environ.get('ENTELAI_TOKEN')
ENTELAI_SECRETPASS = os.environ.get('ENTELAI_SECRETPASS')
ENTELAI_API_URL = os.environ.get('ENTELAI_API_URL')
headers = {'Accept': 'application/json', 'Authorization': f'Bearer {ENTELAI_TOKEN}'}
NULL_STRING = 'null'



def entelai_post_request(text:str):
    data = f'{{ "text": "{text}", "image":null, "user_id": "123" }}'
    if ENTELAI_API_URL is None:
        raise ValueError('No entelai URL given')
    else:
        try:
            response = requests.post(ENTELAI_API_URL, headers=headers, data=data)
            return response
        except Exception as e:
            print(e)

