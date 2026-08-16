import os
import threading
import datetime
import requests
from flask import Flask, jsonify, request, send_from_directory

# Import variables and methods from automation module
from bulk_like_and_reply import (
    PAGE_ACCESS_TOKEN,
    PAGE_ID,
    stats,
    run_automation_task,
    has_already_replied,
    has_meaningful_text,
    generate_ai_reply,
    FRIENDLY_REPLIES
)

app = Flask(__name__, static_folder='.')

# Thread control variables
bot_thread = None
stop_event = threading.Event()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/style.css')
def style():
    return send_from_directory('.', 'style.css')

@app.route('/progress.json')
def progress():
    return send_from_directory('.', 'progress.json')

@app.route('/bot.html')
@app.route('/bot')
def bot_page():
    return send_from_directory('.', 'bot.html')

@app.route('/tokens.html')
@app.route('/tokens')
def tokens_page():
    return send_from_directory('.', 'tokens.html')

@app.route('/api/posts')
def get_posts():
    try:
        days_str = request.args.get('days', '7')
        if days_str == '24h':
            since_date = datetime.datetime.now() - datetime.timedelta(hours=24)
        else:
            try:
                days = float(days_str)
            except ValueError:
                days = 7.0
            since_date = datetime.datetime.now() - datetime.timedelta(days=days)
        since_timestamp = int(since_date.timestamp())
        
        # Fetch posts with message, picture, status type and light metrics (likes/comments summaries)
        url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/posts"
        params = {
            "fields": "id,message,created_time,permalink_url,full_picture,status_type,shares,likes.summary(true).limit(0),comments.summary(true).limit(0)",
            "since": since_timestamp,
            "limit": 100,
            "access_token": PAGE_ACCESS_TOKEN
        }
        res = requests.get(url, params=params).json()
        posts = res.get("data", [])
        return jsonify({"success": True, "posts": posts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/analyze-comments', methods=['POST'])
def analyze_comments():
    try:
        data = request.get_json() or {}
        post_ids = data.get('post_ids', [])
        generate = data.get('generate', False)
        
        if not post_ids:
            return jsonify({"success": False, "error": "No posts selected"}), 400
            
        total_likes_needed = 0
        total_replies_needed = 0
        detailed_comments = []
        
        for pid in post_ids:
            url = f"https://graph.facebook.com/v22.0/{pid}/comments"
            params = {
                "fields": "id,message,from,created_time,user_likes,comments{from,message}",
                "limit": 150,
                "access_token": PAGE_ACCESS_TOKEN
            }
            res = requests.get(url, params=params).json()
            comments = res.get("data", [])
            
            for c in comments:
                # Skip comments from the page itself
                if c.get("from", {}).get("id") == PAGE_ID:
                    continue
                
                is_liked = c.get("user_likes") is True
                is_replied = has_already_replied(c)
                has_text = has_meaningful_text(c.get("message", ""))
                
                likes_needed = 1 if not is_liked else 0
                replies_needed = 1 if (not is_replied and has_text) else 0
                
                total_likes_needed += likes_needed
                total_replies_needed += replies_needed
                
                proposed_reply = None
                if replies_needed > 0 and generate:
                    if total_replies_needed <= 15:
                        proposed_reply = generate_ai_reply(c.get("message", ""))
                    if not proposed_reply:
                        import random
                        proposed_reply = random.choice(FRIENDLY_REPLIES)
                
                detailed_comments.append({
                    "id": c.get("id"),
                    "user_name": c.get("from", {}).get("name", "User"),
                    "message": c.get("message", ""),
                    "likes_needed": likes_needed,
                    "replies_needed": replies_needed,
                    "proposed_reply": proposed_reply,
                    "is_emoji": not has_text,
                    "post_id": pid
                })
                
        return jsonify({
            "success": True,
            "summary": {
                "total_comments": len(detailed_comments),
                "likes_needed": total_likes_needed,
                "replies_needed": total_replies_needed
            },
            "comments": detailed_comments
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/start-bot', methods=['POST'])
def start_bot():
    global bot_thread, stop_event
    try:
        # Check if already running
        if bot_thread and bot_thread.is_alive():
            return jsonify({"success": False, "error": "Bot is already running"}), 400
            
        data = request.get_json() or {}
        post_ids = data.get('post_ids', [])
        only_like = data.get('only_like', False)
        target = data.get('target', 100)
        comment_whitelist = data.get('comment_whitelist', None)
        delete_spam = data.get('delete_spam', False)
        
        stop_event.clear()
        bot_thread = threading.Thread(
            target=run_automation_task,
            args=(post_ids, only_like, target, stop_event, comment_whitelist, delete_spam),
            daemon=True
        )
        bot_thread.start()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stop-bot', methods=['POST'])
def stop_bot():
    global stop_event
    try:
        stop_event.set()
        stats["status"] = "stopped"
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/status')
def get_status():
    return jsonify(stats)

@app.route('/api/daily-records')
def get_daily_records():
    import json
    file_path = "daily_records.json"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return jsonify({"success": True, "records": data})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
        return jsonify({"success": False, "error": str(e)}), 500

# CORS Headers Handler
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Token Database Helpers
TOKENS_FILE = "tokens.json"

def load_tokens():
    import json
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_tokens(tokens):
    import json
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=4, ensure_ascii=False)

def generate_random_code(value):
    import random
    import string
    rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RCG-{value}-{rand_part}"

# Token APIs
@app.route('/api/tokens', methods=['GET'])
def get_tokens_api():
    tokens = load_tokens()
    return jsonify({"success": True, "tokens": tokens})

@app.route('/api/tokens/generate', methods=['POST'])
def generate_token_api():
    try:
        data = request.get_json() or {}
        value = int(data.get('value', 100))
        
        tokens = load_tokens()
        code = generate_random_code(value)
        while code in tokens:
            code = generate_random_code(value)
            
        tokens[code] = {
            "value": value,
            "status": "valid",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "used_at": None,
            "remaining_tokens": value,
            "last_sync_at": None
        }
        save_tokens(tokens)
        return jsonify({"success": True, "code": code, "value": value})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tokens/validate', methods=['POST'])
def validate_token_api():
    try:
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        
        if not code:
            return jsonify({"success": False, "error": "กรุณาระบุรหัสเติมเงิน (Empty code)"}), 400
            
        tokens = load_tokens()
        if code not in tokens:
            return jsonify({"success": False, "error": "รหัสเติมเงินไม่ถูกต้อง (Invalid code)"}), 400
            
        token_info = tokens[code]
        if token_info["status"] != "valid":
            return jsonify({"success": False, "error": "รหัสเติมเงินนี้ถูกใช้งานไปแล้ว (Already used)"}), 400
            
        # Update token status
        token_info["status"] = "used"
        token_info["used_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        token_info["remaining_tokens"] = token_info["value"]
        token_info["last_sync_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tokens[code] = token_info
        save_tokens(tokens)
        
        return jsonify({
            "success": True, 
            "value": token_info["value"], 
            "code": code
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tokens/sync', methods=['POST'])
def sync_token_balance():
    try:
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        balance = int(data.get('balance', 0))
        
        if not code:
            return jsonify({"success": False, "error": "รหัสผ่านว่างเปล่า (Empty code)"}), 400
            
        tokens = load_tokens()
        if code not in tokens:
            return jsonify({"success": False, "error": "ไม่พบรหัสเติมเงินนี้ (Code not found)"}), 404
            
        token_info = tokens[code]
        token_info["remaining_tokens"] = balance
        token_info["last_sync_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tokens[code] = token_info
        
        save_tokens(tokens)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # Start Flask Server
    app.run(host='0.0.0.0', port=8001)
