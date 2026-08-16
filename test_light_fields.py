import os
import requests
import datetime
from dotenv import load_dotenv

dotenv_path = "/Users/amsocute/Desktop/FaceBook/.env"
load_dotenv(dotenv_path)

PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")

days = 30
since_date = datetime.datetime.now() - datetime.timedelta(days=days)
since_timestamp = int(since_date.timestamp())

url_posts = f"https://graph.facebook.com/v22.0/{PAGE_ID}/posts"
# We query without attachments, likes summary, or comments summary. Only basic fields!
params_posts = {
    "fields": "id,message,created_time,permalink_url,full_picture,status_type",
    "since": since_timestamp,
    "limit": 100,
    "access_token": PAGE_ACCESS_TOKEN
}

res = requests.get(url_posts, params=params_posts).json()
if "error" in res:
    print("Facebook Error:", res["error"])
else:
    posts = res.get("data", [])
    print(f"Successfully loaded {len(posts)} posts in 30 days timeframe!")
    if posts:
        print("Sample post status_type:", posts[0].get("status_type"))
