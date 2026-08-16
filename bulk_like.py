import os
import sys
import time
import random
import argparse
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")

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
    """Fetch comments with user_likes field to check if we already liked them."""
    url = f"https://graph.facebook.com/v22.0/{post_id}/comments"
    params = {
        "fields": "id,message,from,user_likes",
        "limit": limit,
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.get(url, params=params).json()
    return res.get("data", [])

def like_comment(comment_id):
    """Like a comment using the Page Access Token."""
    url = f"https://graph.facebook.com/v22.0/{comment_id}/likes"
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.post(url, params=params, timeout=10).json()
    return res

def main():
    parser = argparse.ArgumentParser(description="Bulk like Facebook comments with rate limiting.")
    parser.add_argument("--target", type=int, default=100, help="Total number of likes to send.")
    args = parser.parse_args()

    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("Error: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID is missing.")
        sys.exit(1)

    target_likes = args.target
    print(f"Starting bulk like task. Target: {target_likes} likes.")
    print("Speed: 100 likes per minute (approx. 0.6 seconds delay per like).")

    # Step 1: Fetch latest posts
    print("Fetching latest posts from the Page...")
    posts = fetch_latest_posts(limit=20)
    if not posts:
        print("No posts found on this Page.")
        sys.exit(0)

    print(f"Found {len(posts)} posts. Starting traversal...")

    liked_count = 0

    for post_index, post in enumerate(posts):
        if liked_count >= target_likes:
            break

        post_id = post.get("id")
        post_message = post.get("message", "(No text)")
        display_message = (post_message[:40] + '...') if len(post_message) > 40 else post_message
        
        print("\n" + "="*70)
        print(f"Processing Post [{post_index + 1}/{len(posts)}]: ID {post_id}")
        print(f"Content: '{display_message}'")
        print("="*70)

        # Step 2: Fetch comments for this post
        comments = fetch_post_comments(post_id, limit=150)
        if not comments:
            print("No comments found on this post. Moving to next.")
            continue

        # Step 3: Filter comments that are NOT liked by the page yet
        pending_comments = []
        for c in comments:
            # Skip page's own comments
            if c.get("from", {}).get("id") == PAGE_ID:
                continue
            # Skip if already liked
            if c.get("user_likes") is True:
                continue
            pending_comments.append(c)

        print(f"Found {len(comments)} comments. Pending likes: {len(pending_comments)}")

        # Step 4: Like comments sequentially with delay
        for comment in pending_comments:
            if liked_count >= target_likes:
                break

            comment_id = comment.get("id")
            user_name = comment.get("from", {}).get("name", "User")
            user_message = comment.get("message", "")

            # Sleep delay targeting a safer speed of 20-30 likes per minute to avoid timeouts (~2.5 seconds average)
            delay = random.uniform(1.5, 3.5)
            time.sleep(delay)

            try:
                res = like_comment(comment_id)
                if res.get("success") is True:
                    liked_count += 1
                    print(f"[{liked_count}/{target_likes}] Liked comment {comment_id} by {user_name} (Delay: {delay:.2f}s)")
                else:
                    print(f"  --> Failed to like comment {comment_id}. Response: {res}")
            except Exception as e:
                print(f"  --> Error liking comment {comment_id}: {e}")

    print(f"\nBulk like completed. Successfully liked {liked_count}/{target_likes} comments.")

if __name__ == "__main__":
    main()
