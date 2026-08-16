import os
import sys
import json
import time
import random
import argparse
import requests
from dotenv import load_dotenv
from facebook_api import FacebookAPI

# Load environment variables
load_dotenv()

PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")

# Friendly, natural-sounding replies to randomly select from (no emojis)
FRIENDLY_REPLIES = [
    "ขอบคุณมากเลยนะคะ",
    "ขอบคุณสำหรับกำลังใจนะคะ สู้ตายค่ะ!",
    "ขอบคุณค่า ตั้งใจซ้อมเพื่อสนามนี้มากๆ เลยค่ะ",
    "ดีใจที่ชอบนะคะ เน้นแข็งแรงไว้ก่อนค่ะช่วงนี้",
    "ขอบคุณที่คอยซัพพอร์ตนะคะ",
    "ขอบคุณมากค่ะ กล้ามต้องมาแล้วนาทีนี้",
    "ขอบคุณมากๆ เลยค่า",
    "ขอบคุณมากเลยนะคะ ใจฟูเลย",
    "ขอบคุณค่า เน้นสร้างกล้ามเนื้อไว้ลุยสนามต่อไปค่ะ",
    "ขอบคุณสำหรับแรงเชียร์นะคะ สู้ๆ เช่นกันค่ะ"
]

def fetch_latest_posts(limit=20):
    """Fetch the latest posts from the Page."""
    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/posts"
    params = {
        "limit": limit,
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.get(url, params=params).json()
    return res.get("data", [])

def fetch_post_comments(post_id, limit=100):
    """Fetch comments along with their nested replies for a given post."""
    url = f"https://graph.facebook.com/v22.0/{post_id}/comments"
    params = {
        "fields": "id,message,from,created_time,comments{from,message}",
        "limit": limit,
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.get(url, params=params).json()
    return res.get("data", [])

def has_already_replied(comment):
    """Check if the page has already replied to this comment."""
    nested_comments = comment.get("comments", {}).get("data", [])
    for reply in nested_comments:
        if reply.get("from", {}).get("id") == PAGE_ID:
            return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Bulk reply to Facebook comments with rate limiting.")
    parser.add_argument("--target", type=int, default=200, help="Total number of replies to send.")
    args = parser.parse_args()

    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("Error: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID is missing.")
        sys.exit(1)

    target_replies = args.target
    print(f"Starting bulk reply. Target replies: {target_replies}")

    # Step 1: Fetch latest posts
    print("Fetching latest posts from the Page...")
    posts = fetch_latest_posts(limit=20)
    if not posts:
        print("No posts found on this Page.")
        sys.exit(0)

    print(f"Found {len(posts)} posts. Starting traversal (newest first)...")

    # Initialize Facebook API
    api = FacebookAPI()
    replied_count = 0

    for post_index, post in enumerate(posts):
        if replied_count >= target_replies:
            break

        post_id = post.get("id")
        post_message = post.get("message", "(No text)")
        # Truncate post message for display
        display_message = (post_message[:40] + '...') if len(post_message) > 40 else post_message
        
        print("\n" + "="*70)
        print(f"Processing Post [{post_index + 1}/{len(posts)}]: ID {post_id}")
        print(f"Content: '{display_message}'")
        print("="*70)

        # Step 2: Fetch comments for the current post
        comments = fetch_post_comments(post_id, limit=100)
        if not comments:
            print("No comments found on this post. Moving to the next post.")
            continue

        # Step 3: Filter comments that need a reply
        pending_comments = []
        for c in comments:
            if c.get("from", {}).get("id") == PAGE_ID:
                continue
            if has_already_replied(c):
                continue
            pending_comments.append(c)

        print(f"Found {len(comments)} comments. Pending replies: {len(pending_comments)}")

        # Step 4: Reply to pending comments
        for comment in pending_comments:
            if replied_count >= target_replies:
                break

            comment_id = comment.get("id")
            user_name = comment.get("from", {}).get("name", "User")
            user_message = comment.get("message", "")
            
            # Select a random friendly reply
            message = random.choice(FRIENDLY_REPLIES)

            # Cool-off period: every 30 replies sent, sleep for 60 seconds (1 minute)
            if replied_count > 0 and replied_count % 30 == 0:
                print("\n" + "-"*50)
                print("COOL-OFF PERIOD: Sent 30 replies. Pausing for 60 seconds (1 minute)...")
                print("-"*50)
                time.sleep(60)

            # Random delay between 10 and 22 seconds before each reply (averages ~16s)
            delay = random.randint(10, 22)
            print(f"\nWaiting {delay} seconds before replying (Total progress: {replied_count + 1}/{target_replies})...")
            time.sleep(delay)

            print(f"[{replied_count + 1}/{target_replies}] Replying to {user_name} ({comment_id}):")
            print(f"  Comment: '{user_message}'")
            print(f"  Reply  : '{message}'")

            try:
                res = api.reply_to_comment(comment_id, message)
                if "id" in res:
                    print(f"  --> Success! Reply ID: {res['id']}")
                    replied_count += 1
                else:
                    print(f"  --> Failed! API Response: {res}")
            except Exception as e:
                print(f"  --> Error calling API: {e}")

    print(f"\nTraversal complete. Replied to {replied_count}/{target_replies} comments.")

if __name__ == "__main__":
    main()
