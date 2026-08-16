import os
import sys
import time
import random
import argparse
import requests
import json
import re
from dotenv import load_dotenv

def has_meaningful_text(text):
    """Check if the comment contains any Thai characters, English letters, or numbers."""
    if not text:
        return False
    return bool(re.search(r'[a-zA-Z0-9\u0e00-\u0e7f]', text))

def is_spam_comment(message):
    """Check if comment contains known spam link patterns like vk, whatsapp, wa.me, t.me, line.me, bit.ly, etc."""
    if not message:
        return False
    msg_lower = message.lower()
    spam_patterns = [
        r"vk\.com",
        r"vk\.cc",
        r"vkontakte",
        r"wa\.me",
        r"whatsapp",
        r"t\.me",
        r"telegram",
        r"line\.me",
        r"bit\.ly",
        r"http[s]?://[^\s]*vk",
        r"http[s]?://[^\s]*wa"
    ]
    for pattern in spam_patterns:
        if re.search(pattern, msg_lower):
            return True
    return False

def delete_comment(comment_id):
    """Delete a comment via Facebook Graph API."""
    url = f"https://graph.facebook.com/v22.0/{comment_id}"
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.delete(url, params=params, timeout=15).json()
    return res.get("success", False)

# Load environment variables
load_dotenv()

PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
PROGRESS_FILE = "progress.json"

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

stats = {
    "target": 200,
    "processed": 0,
    "likes_sent": 0,
    "replies_sent": 0,
    "spam_deleted": 0,
    "status": "running",
    "recent_logs": [],
    "current_post": None,
    "gemini_requests": 0,
    "gemini_tokens": 0,
    "gemini_request_limit": 1500,
    "facebook_requests": 0,
    "recent_replies": []
}

def update_progress_file(log_entry=None):
    """Write current stats and logs to progress.json."""
    global stats
    if log_entry:
        stats["recent_logs"].insert(0, log_entry)
        # Keep only the last 15 logs
        stats["recent_logs"] = stats["recent_logs"][:15]
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving progress file: {e}")

def increment_daily_stat(stat_name, amount=1):
    import datetime
    today = datetime.date.today().isoformat()
    file_path = "daily_records.json"
    
    records = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            pass
            
    if today not in records:
        records[today] = {
            "ai_requests": 0,
            "likes_sent": 0,
            "replies_sent": 0
        }
        
    records[today][stat_name] = records[today].get(stat_name, 0) + amount
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error updating daily records: {e}")

def fetch_latest_posts(limit=20):
    """Fetch the latest posts from the Page."""
    global stats
    stats["facebook_requests"] += 1
    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/posts"
    params = {
        "fields": "id,message,created_time,permalink_url,full_picture",
        "limit": limit,
        "access_token": PAGE_ACCESS_TOKEN
    }
    res = requests.get(url, params=params).json()
    return res.get("data", [])

def fetch_post_comments(post_id, limit=100):
    """Fetch comments along with their nested replies and user_likes status."""
    global stats
    stats["facebook_requests"] += 1
    url = f"https://graph.facebook.com/v22.0/{post_id}/comments"
    params = {
        "fields": "id,message,from,created_time,user_likes,comments{from,message}",
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

def like_comment(comment_id):
    """Like a comment using the Page Access Token."""
    global stats
    stats["facebook_requests"] += 1
    url = f"https://graph.facebook.com/v22.0/{comment_id}/likes"
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    rand_timeout = random.uniform(20.0, 30.0)
    res = requests.post(url, params=params, timeout=rand_timeout).json()
    return res.get("success", False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def generate_ai_reply(comment_text):
    """Generate a custom reply using Gemini 2.5 Flash API based on comment content."""
    if not GEMINI_API_KEY:
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = (
        f"คุณคือ โนเกีย สุธาสินี (Nokia Sutasinee) เน็ตไอดอลสายออกกำลังกายและนักแข่งรถชาวไทยที่มีชื่อเสียง "
        f"จงเขียนข้อความตอบกลับความคิดเห็นของผู้ติดตามคนนี้บนเพจเฟซบุ๊กของคุณ "
        f"เงื่อนไขด้านภาษาการตอบกลับ:\n"
        f"1. หากความคิดเห็นส่งมาเป็นภาษาไทย: ให้ตอบกลับเป็นภาษาไทยที่เป็นกันเอง น่ารัก ดูเป็นธรรมชาติและอบอุ่น\n"
        f"2. หากความคิดเห็นส่งมาเป็นภาษาอังกฤษ: ให้ตอบกลับเป็นภาษาอังกฤษ (English) ที่น่ารัก เป็นกันเองและกระชับ\n"
        f"3. หากความคิดเห็นส่งมาเป็นภาษาต่างประเทศอื่นๆ (เช่น สเปน, ฝรั่งเศส, ญี่ปุ่น, จีน ฯลฯ): ให้ตอบกลับเป็นภาษาอังกฤษ (English) เท่านั้น ห้ามเขียนตอบเป็นภาษาอื่น\n"
        f"เงื่อนไขทั่วไป:\n"
        f"- ห้ามใช้สัญลักษณ์ อีโมจิ หรือไอคอนใดๆ ทั้งสิ้น (ห้ามใส่ 💖, 🤣, 💪, 🤍, 😊 ฯลฯ)\n"
        f"- เขียนสั้นๆ กระชับ เพียง 1 ถึง 2 ประโยค\n"
        f"- อ้างอิงคำตอบตามเนื้อหาคอมเมนต์ที่เขาส่งมา ห้ามตอบสุ่มเดา\n\n"
        f"คอมเมนต์ของลูกเพจ: \"{comment_text}\"\n"
        f"คำตอบกลับของคุณ:"
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        global stats
        stats["gemini_requests"] += 1
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        res = response.json()
        if "candidates" in res:
            # Add token usage count
            tokens = res.get("usageMetadata", {}).get("totalTokenCount", 0)
            stats["gemini_tokens"] += tokens
            
            # Record daily cumulative AI usage
            try:
                increment_daily_stat("ai_requests")
            except Exception:
                pass
                
            reply_text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
            return reply_text
        else:
            print(f"  --> Error: Gemini API response missing candidates: {res}")
            return None
    except Exception as e:
        print(f"  --> Error calling Gemini API: {e}")
        return None

def reply_to_comment(comment_id, message):
    """Reply to a comment using the Page Access Token."""
    global stats
    stats["facebook_requests"] += 1
    url = f"https://graph.facebook.com/v22.0/{comment_id}/comments"
    params = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN
    }
    rand_timeout = random.uniform(20.0, 30.0)
    res = requests.post(url, params=params, timeout=rand_timeout).json()
    return res

def run_automation_task(post_ids=None, only_like=False, target=100, stop_event=None, comment_whitelist=None, delete_spam=False):
    global stats
    
    # Preserve today's cumulative stats across script restarts
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                old_stats = json.load(f)
                stats["gemini_requests"] = old_stats.get("gemini_requests", 0)
                stats["gemini_tokens"] = old_stats.get("gemini_tokens", 0)
                stats["facebook_requests"] = old_stats.get("facebook_requests", 0)
        except Exception:
            pass

    stats["target"] = target
    stats["processed"] = 0
    stats["likes_sent"] = 0
    stats["replies_sent"] = 0
    stats["status"] = "running"
    stats["current_post"] = None
    stats["recent_logs"] = []
    stats["recent_replies"] = []
    
    mode_str = "Liking Only" if only_like else "Like & Reply"
    print(f"Starting Bulk Task ({mode_str}). Target: {target} comments.")
    update_progress_file(f"Starting Bulk Task ({mode_str}). Target: {target} comments.")

    # If post_ids are provided, fetch just those posts
    posts = []
    if post_ids:
        for pid in post_ids:
            if stop_event and stop_event.is_set():
                break
            try:
                url = f"https://graph.facebook.com/v22.0/{pid}"
                params = {
                    "fields": "id,message,created_time,permalink_url,full_picture",
                    "access_token": PAGE_ACCESS_TOKEN
                }
                stats["facebook_requests"] += 1
                res = requests.get(url, params=params).json()
                if "id" in res:
                    posts.append(res)
            except Exception as e:
                print(f"Error fetching post details for {pid}: {e}")
    else:
        posts = fetch_latest_posts(limit=25)

    if not posts:
        print("No posts found or provided.")
        stats["status"] = "finished"
        update_progress_file("No posts found or provided.")
        return

    print(f"Processing {len(posts)} posts. Starting traversal...")
    update_progress_file(f"Processing {len(posts)} posts. Starting traversal...")

    consecutive_likes = 0
    for post_index, post in enumerate(posts):
        if stop_event and stop_event.is_set():
            print("Stop event detected. Stopping automation...")
            update_progress_file("Automation stopped by user.")
            break

        if stats["processed"] >= stats["target"]:
            break

        post_id = post.get("id")
        post_message = post.get("message", "(No text)")
        display_message = (post_message[:40] + '...') if len(post_message) > 40 else post_message
        permalink = post.get("permalink_url", "#")
        created_time = post.get("created_time", "")
        
        # Update current post details in stats
        stats["current_post"] = {
            "id": post_id,
            "message": post_message,
            "permalink_url": permalink,
            "created_time": created_time,
            "full_picture": post.get("full_picture", ""),
            "index": post_index + 1,
            "total_posts": len(posts)
        }
        
        print("\n" + "="*80)
        print(f"Processing Post [{post_index + 1}/{len(posts)}]: ID {post_id}")
        print("="*80)
        update_progress_file(f"Scanning Post [{post_index + 1}/{len(posts)}]: {display_message}")

        comments = fetch_post_comments(post_id, limit=150)
        if not comments:
            print("No comments found on this post. Moving to next.")
            continue

        pending_comments = []
        for c in comments:
            if stop_event and stop_event.is_set():
                break
            if c.get("from", {}).get("id") == PAGE_ID:
                continue
            
            liked = c.get("user_likes") is True
            replied = has_already_replied(c)
            
            is_pending = (not liked) if only_like else (not liked or not replied)
            if is_pending:
                pending_comments.append((c, liked, replied))

        print(f"Found {len(comments)} comments. Pending actions: {len(pending_comments)}")

        for comment_data in pending_comments:
            if stop_event and stop_event.is_set():
                break
            if stats["processed"] >= stats["target"]:
                break

            comment, is_liked, is_replied = comment_data
            comment_id = comment.get("id")
            if comment_whitelist is not None and comment_id not in comment_whitelist:
                # Skip comments not whitelisted by the user
                continue
            user_name = comment.get("from", {}).get("name", "User")
            user_message = comment.get("message", "")

            # 0. Spam Detection & Deletion Check
            if delete_spam and is_spam_comment(user_message):
                log_str = f"  --> [SPAM DETECTED] Comment from {user_name} contains spam links: '{user_message}'"
                print(log_str)
                update_progress_file(log_str)
                try:
                    success = delete_comment(comment_id)
                    if success:
                        stats["spam_deleted"] += 1
                        try:
                            increment_daily_stat("spam_deleted")
                        except Exception:
                            pass
                        log_deleted = f"  --> [SPAM DELETED] Deleted spam comment successfully!"
                        print(log_deleted)
                        update_progress_file(log_deleted)
                    else:
                        print("  --> [SPAM DELETED] Failed to delete comment.")
                        update_progress_file("  --> Failed to delete spam comment.")
                except Exception as e:
                    print(f"  --> [SPAM DELETED] Error: {e}")
                    update_progress_file(f"  --> Error deleting comment: {e}")
                continue

            # Increment count
            stats["processed"] += 1
            stats["latest_comment"] = {
                "user_name": user_name,
                "message": user_message
            }
            log_str = f"[{stats['processed']}/{stats['target']}] Processing {user_name}: '{user_message}'"
            print(log_str)
            update_progress_file(log_str)

            # 1. Handle Liking
            if not is_liked:
                success = False
                for attempt in range(1, 4):
                    if stop_event and stop_event.is_set():
                        break
                    if only_like:
                        # 5x faster delay inside bursts (0.12s-0.22s), with a human-like break after 4-7 likes
                        if consecutive_likes >= random.randint(4, 7):
                            delay = random.uniform(3.5, 6.0)
                            consecutive_likes = 0
                        else:
                            delay = random.uniform(0.12, 0.22)
                    else:
                        delay = random.uniform(1.5, 3.5)
                    time.sleep(delay)
                    try:
                        success = like_comment(comment_id)
                        if success:
                            stats["likes_sent"] += 1
                            consecutive_likes += 1
                            try:
                                increment_daily_stat("likes_sent")
                            except Exception:
                                pass
                            print("  --> Liked successfully.")
                            update_progress_file(f"  --> Liked comment from {user_name}")
                            break
                        else:
                            print(f"  --> Failed to like comment (Attempt {attempt}/3).")
                            update_progress_file(f"  --> Failed to like (Attempt {attempt}/3)")
                    except Exception as e:
                        print(f"  --> Error liking comment (Attempt {attempt}/3): {e}")
                        update_progress_file(f"  --> Error liking (Attempt {attempt}/3): {e}")
                    
                    if attempt < 3:
                        time.sleep(2.0) # Small pause before retry
                
                if not success:
                    print("  --> Liking failed after 3 attempts. Skipping.")
                    update_progress_file(f"  --> Liking failed after 3 attempts for {user_name}")
            else:
                print("  --> Already liked. Skipping.")
                update_progress_file(f"  --> Already liked by page. Skipping like.")

            # 2. Handle Replying
            if only_like:
                print("  --> Liking only mode. Skipping reply.")
            elif not is_replied:
                if stop_event and stop_event.is_set():
                    break
                if not has_meaningful_text(user_message):
                    print("  --> Comment is emoji/symbol only. Skipping reply.")
                    update_progress_file(f"  --> Emoji-only comment from {user_name}. Skipped reply.")
                else:
                    delay = random.uniform(1.5, 3.5)
                    time.sleep(delay)
                    
                    # Try using custom reply from the whitelist if provided as a dict
                    custom_reply = None
                    if isinstance(comment_whitelist, dict):
                        custom_reply = comment_whitelist.get(comment_id)
                        if isinstance(custom_reply, bool) or not custom_reply:
                            custom_reply = None

                    if custom_reply:
                        reply_message = custom_reply
                        print(f"  --> Using custom user reply: '{reply_message}'")
                    else:
                        # Try generating custom AI reply based on user's comment text
                        reply_message = generate_ai_reply(user_message)
                        if reply_message:
                            print(f"  --> Generated AI reply: '{reply_message}'")
                        else:
                            reply_message = random.choice(FRIENDLY_REPLIES)
                            print(f"  --> Using template fallback reply: '{reply_message}'")
                    
                    try:
                        res = reply_to_comment(comment_id, reply_message)
                        if "id" in res:
                            stats["replies_sent"] += 1
                            try:
                                increment_daily_stat("replies_sent")
                            except Exception:
                                pass
                            
                            # Verify if the reply is visible on Facebook immediately
                            verify_status = "Pending Verify"
                            try:
                                check_url = f"https://graph.facebook.com/v22.0/{res['id']}"
                                chk_res = requests.get(check_url, params={"access_token": PAGE_ACCESS_TOKEN}, timeout=20).json()
                                if "id" in chk_res:
                                    verify_status = "Verified (แสดงผลแล้ว)"
                                else:
                                    verify_status = f"Not Found: {chk_res.get('error', {}).get('message', 'Unknown error')}"
                            except Exception as ve:
                                verify_status = f"Verify Failed: {str(ve)}"

                            stats.setdefault("recent_replies", []).append({
                                "post_id": pid,
                                "comment_id": comment_id,
                                "reply_id": res["id"],
                                "user_name": user_name,
                                "user_message": user_message,
                                "reply_message": reply_message,
                                "verify_status": verify_status
                            })

                            print(f"  --> Replied successfully. Verify Status: {verify_status}. Reply: '{reply_message}'")
                            update_progress_file(f"  --> Replied: '{reply_message}' (Verify: {verify_status})")
                        else:
                            print(f"  --> Failed to reply. Response: {res}")
                            update_progress_file(f"  --> Failed to reply.")
                    except Exception as e:
                        print(f"  --> Error replying: {e}")
                        update_progress_file(f"  --> Error replying: {e}")
            else:
                print("  --> Already replied. Skipping.")
                update_progress_file(f"  --> Already replied by page. Skipping reply.")

    print(f"\nBulk task completed. Processed {stats['processed']}/{stats['target']} comments.")
    stats["status"] = "finished"
    update_progress_file(f"Completed! Processed {stats['processed']} comments.")

def main():
    parser = argparse.ArgumentParser(description="Bulk like and reply to Facebook comments.")
    parser.add_argument("--target", type=int, default=200, help="Total number of comments to process.")
    parser.add_argument("--only-like", action="store_true", help="Only like comments, do not reply.")
    args = parser.parse_args()

    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("Error: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID is missing.")
        sys.exit(1)

    run_automation_task(only_like=args.only_like, target=args.target)

if __name__ == "__main__":
    main()
