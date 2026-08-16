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
    FRIENDLY_REPLIES,
    delete_comment,
    like_comment,
    reply_to_comment,
    is_spam_comment
)

app = Flask(__name__, static_folder='.')

IS_CLOUD = os.getenv("RENDER") is not None

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
    if IS_CLOUD:
        return "ระบบ Live Comment Automation ถูกปิดการทำงานบนออนไลน์ชั่วคราวเพื่อความเสถียร กรุณารันบนระบบเครื่อง Local (localhost:8001) เท่านั้น", 403
    return send_from_directory('.', 'bot.html')

@app.route('/tokens.html')
@app.route('/tokens')
def tokens_page():
    return send_from_directory('.', 'tokens.html')

@app.route('/api/posts')
def get_posts():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
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
        res_raw = requests.get(url, params=params)
        print(f"DEBUG: Facebook API Response Status: {res_raw.status_code}")
        print(f"DEBUG: Facebook API Response Body: {res_raw.text[:1000]}")
        res = res_raw.json()
        posts = res.get("data", [])
        return jsonify({"success": True, "posts": posts})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/analyze-comments', methods=['POST'])
def analyze_comments():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    try:
        data = request.get_json() or {}
        post_ids = data.get('post_ids', [])
        generate = data.get('generate', False)
        
        if not post_ids:
            return jsonify({"success": False, "error": "No posts selected"}), 400
            
        total_likes_needed = 0
        total_replies_needed = 0
        like_only_count = 0
        reply_only_count = 0
        both_count = 0
        spam_count = 0
        detailed_comments = []
        
        for pid in post_ids:
            url = f"https://graph.facebook.com/v22.0/{pid}/comments"
            params = {
                "fields": "id,message,from,created_time,user_likes,message_tags,comments{from,message}",
                "limit": 150,
                "access_token": PAGE_ACCESS_TOKEN
            }
            res = requests.get(url, params=params).json()
            comments = res.get("data", [])
            
            for c in comments:
                # Skip comments from the page itself
                if c.get("from", {}).get("id") == PAGE_ID:
                    continue
                
                user_message = c.get("message", "")
                is_liked = c.get("user_likes") is True
                is_replied = has_already_replied(c)
                has_text = has_meaningful_text(user_message)
                
                # Detect tags/mentions (via Facebook's message_tags list)
                has_tags = len(c.get("message_tags", [])) > 0 if isinstance(c.get("message_tags"), (list, dict)) else False
                
                is_spam = is_spam_comment(user_message)
                
                likes_needed = 1 if not is_liked else 0
                
                # If it's a tag comment or spam, do NOT reply (replies_needed = 0). It becomes Like Only or Spam delete
                if has_tags or is_spam:
                    replies_needed = 0
                else:
                    replies_needed = 1 if (not is_replied and has_text) else 0
                
                # Calculate counts for summary
                if is_spam:
                    spam_count += 1
                else:
                    total_likes_needed += likes_needed
                    total_replies_needed += replies_needed
                    if likes_needed > 0 and replies_needed > 0:
                        both_count += 1
                    elif likes_needed > 0 and replies_needed == 0:
                        like_only_count += 1
                    elif likes_needed == 0 and replies_needed > 0:
                        reply_only_count += 1
                
                proposed_reply = None
                if replies_needed > 0 and generate:
                    if total_replies_needed <= 15:
                        proposed_reply = generate_ai_reply(user_message)
                    if not proposed_reply:
                        import random
                        proposed_reply = random.choice(FRIENDLY_REPLIES)
                
                detailed_comments.append({
                    "id": c.get("id"),
                    "user_name": c.get("from", {}).get("name", "User"),
                    "message": user_message,
                    "likes_needed": likes_needed,
                    "replies_needed": replies_needed,
                    "proposed_reply": proposed_reply,
                    "is_emoji": not has_text,
                    "is_spam": is_spam,
                    "has_tags": has_tags,
                    "post_id": pid
                })
                
        return jsonify({
            "success": True,
            "summary": {
                "total_comments": len(detailed_comments),
                "likes_needed": total_likes_needed,
                "replies_needed": total_replies_needed,
                "like_only_count": like_only_count,
                "reply_only_count": reply_only_count,
                "both_count": both_count,
                "spam_count": spam_count
            },
            "comments": detailed_comments
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/delete-comment', methods=['POST'])
def delete_comment_api():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    try:
        data = request.get_json() or {}
        comment_id = data.get('comment_id')
        if not comment_id:
            return jsonify({"success": False, "error": "Missing comment_id"}), 400
        
        success = delete_comment(comment_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Facebook API delete request failed"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/reply-single-comment', methods=['POST'])
def reply_single_comment_api():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    try:
        data = request.get_json() or {}
        comment_id = data.get('comment_id')
        reply_message = data.get('reply_message', '').strip()
        do_like = data.get('like', False)
        
        if not comment_id:
            return jsonify({"success": False, "error": "Missing comment_id"}), 400
            
        # Like if requested
        if do_like:
            like_comment(comment_id)
            
        # Reply if requested
        if reply_message:
            reply_to_comment(comment_id, reply_message)
            
        return jsonify({"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/reply-all-comments', methods=['POST'])
def reply_all_comments_api():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    try:
        data = request.get_json() or {}
        comments_data = data.get('comments', [])
        
        likes_done = 0
        replies_done = 0
        
        for item in comments_data:
            comment_id = item.get('comment_id')
            reply_message = item.get('reply_message', '').strip()
            do_like = item.get('like', False)
            
            if not comment_id:
                continue
                
            if do_like:
                if like_comment(comment_id):
                    likes_done += 1
            if reply_message:
                if reply_to_comment(comment_id, reply_message):
                    replies_done += 1
                    
        return jsonify({
            "success": True, 
            "likes_sent": likes_done, 
            "replies_sent": replies_done
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/generate-comment-reply', methods=['POST'])
def generate_comment_reply_api():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    try:
        data = request.get_json() or {}
        message = data.get('message', '').strip()
        if not message:
            return jsonify({"success": False, "error": "ไม่มีข้อความคอมเมนต์"}), 400
            
        reply = generate_ai_reply(message)
        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/start-bot', methods=['POST'])
def start_bot():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
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
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    global stop_event
    try:
        stop_event.set()
        stats["status"] = "stopped"
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/status')
def get_status():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
    return jsonify(stats)

@app.route('/api/daily-records')
def get_daily_records():
    if IS_CLOUD:
        return jsonify({"success": False, "error": "ระบบนี้ถูกกำหนดให้ทำงานบนเครื่อง Local เท่านั้น"}), 403
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

# MongoDB configuration (if MONGODB_URI is provided in environment variables)
MONGODB_URI = os.getenv("MONGODB_URI")
db_client = None
mongo_db = None
tokens_col = None
clients_col = None

if MONGODB_URI:
    try:
        from pymongo import MongoClient
        db_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        mongo_db = db_client["racego_db"]
        tokens_col = mongo_db["tokens"]
        clients_col = mongo_db["clients"]
        print("RaceGO Backend: Successfully connected to MongoDB Atlas!")
    except Exception as e:
        print(f"RaceGO Backend: Failed to connect to MongoDB: {e}")

# Clients Database Helpers
CLIENTS_FILE = "clients.json"
mongo_active = True

def load_clients():
    global mongo_active
    if mongo_active and clients_col is not None:
        try:
            clients = {}
            for doc in clients_col.find():
                cid = doc["_id"]
                clients[cid] = {
                    "approved": doc["approved"],
                    "registered_at": doc.get("registered_at"),
                    "last_seen_at": doc.get("last_seen_at"),
                    "remaining_tokens": doc.get("remaining_tokens", 0),
                    "invite_history": doc.get("invite_history", []),
                    "session_history": doc.get("session_history", [])
                }
            return clients
        except Exception as e:
            print(f"Error loading clients from Mongo: {e}. Deactivating MongoDB database fallback.")
            mongo_active = False
            
    # Local JSON fallback (Executed instantly)
    if os.path.exists(CLIENTS_FILE):
        try:
            import json
            with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_clients(clients):
    global mongo_active
    if mongo_active and clients_col is not None:
        try:
            for cid, info in clients.items():
                clients_col.update_one(
                    {"_id": cid},
                    {"$set": {
                        "approved": info["approved"],
                        "registered_at": info.get("registered_at"),
                        "last_seen_at": info.get("last_seen_at"),
                        "remaining_tokens": info.get("remaining_tokens", 0),
                        "invite_history": info.get("invite_history", []),
                        "session_history": info.get("session_history", [])
                    }},
                    upsert=True
                )
        except Exception as e:
            print(f"Error saving clients to Mongo: {e}. Deactivating MongoDB database fallback.")
            mongo_active = False
            
    # Always write to local file as backup/fallback
    try:
        import json
        with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(clients, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing clients JSON file: {e}")

# Token Database Helpers
TOKENS_FILE = "tokens.json"

def load_tokens():
    global mongo_active
    if mongo_active and tokens_col is not None:
        try:
            tokens = {}
            for doc in tokens_col.find():
                code = doc["_id"]
                tokens[code] = {
                    "value": doc["value"],
                    "status": doc["status"],
                    "created_at": doc["created_at"],
                    "used_at": doc.get("used_at"),
                    "remaining_tokens": doc.get("remaining_tokens", doc["value"]),
                    "last_sync_at": doc.get("last_sync_at"),
                    "plan_name": doc.get("plan_name", "Custom"),
                    "expiration_days": doc.get("expiration_days", 30),
                    "expires_at": doc.get("expires_at")
                }
            return tokens
        except Exception as e:
            print(f"RaceGO Backend: Error reading from MongoDB: {e}. Deactivating MongoDB database fallback.")
            mongo_active = False
            
    # Local JSON fallback (Executed instantly)
    import json
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_tokens(tokens):
    global mongo_active
    if mongo_active and tokens_col is not None:
        try:
            for code, info in tokens.items():
                tokens_col.update_one(
                    {"_id": code},
                    {"$set": {
                        "value": info["value"],
                        "status": info["status"],
                        "created_at": info["created_at"],
                        "used_at": info.get("used_at"),
                        "remaining_tokens": info.get("remaining_tokens", info["value"]),
                        "last_sync_at": info.get("last_sync_at"),
                        "plan_name": info.get("plan_name", "Custom"),
                        "expiration_days": info.get("expiration_days", 30),
                        "expires_at": info.get("expires_at")
                    }},
                    upsert=True
                )
        except Exception as e:
            print(f"RaceGO Backend: Error saving to MongoDB: {e}. Deactivating MongoDB database fallback.")
            mongo_active = False
            
    # Always write to local file as backup/fallback
    try:
        import json
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing tokens JSON file: {e}")

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
        value = int(data.get('value', 300))
        expiration_days = int(data.get('expiration_days', 7))
        plan_name = data.get('plan_name', 'Try 300Token')
        
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
            "last_sync_at": None,
            "plan_name": plan_name,
            "expiration_days": expiration_days,
            "expires_at": None
        }
        save_tokens(tokens)
        return jsonify({"success": True, "code": code, "value": value, "plan_name": plan_name, "expiration_days": expiration_days})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tokens/validate', methods=['POST'])
def validate_token_api():
    try:
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        client_id = data.get('client_id', '').strip().upper()
        
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
        
        # Calculate expiration timestamp
        days = int(token_info.get("expiration_days", 30))
        expire_date = datetime.datetime.now() + datetime.timedelta(days=days)
        token_info["expires_at"] = expire_date.strftime("%Y-%m-%d %H:%M:%S")
        
        token_info["remaining_tokens"] = token_info["value"]
        token_info["last_sync_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tokens[code] = token_info
        save_tokens(tokens)
        
        # Auto-approve client device if provided
        if client_id:
            clients = load_clients()
            if client_id not in clients:
                clients[client_id] = {
                    "approved": True,
                    "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_seen_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "remaining_tokens": token_info["value"]
                }
            else:
                clients[client_id]["approved"] = True
                clients[client_id]["last_seen_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                clients[client_id]["remaining_tokens"] = token_info["value"]
            save_clients(clients)
        
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
        client_id = data.get('client_id', '').strip().upper()
        invite_history = data.get('invite_history', [])
        session_history = data.get('session_history', [])
        
        if not code:
            return jsonify({"success": False, "error": "รหัสผ่านว่างเปล่า (Empty code)"}), 400
            
        tokens = load_tokens()
        if code not in tokens:
            return jsonify({"success": False, "error": "ไม่พบรหัสเติมเงินนี้ (Code not found)"}), 404
            
        token_info = tokens[code]
        
        # Check expiration date
        is_expired = False
        if token_info.get("expires_at"):
            try:
                exp_dt = datetime.datetime.strptime(token_info["expires_at"], "%Y-%m-%d %H:%M:%S")
                if datetime.datetime.now() > exp_dt:
                    is_expired = True
            except Exception:
                pass
                
        if is_expired:
            token_info["status"] = "expired"
            token_info["remaining_tokens"] = 0
            balance = 0
        else:
            token_info["remaining_tokens"] = balance
            
        token_info["last_sync_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tokens[code] = token_info
        save_tokens(tokens)
        
        # If client_id is present, sync their historical statistics
        if client_id:
            clients = load_clients()
            if client_id in clients:
                clients[client_id]["remaining_tokens"] = balance
                clients[client_id]["last_seen_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                clients[client_id]["invite_history"] = invite_history
                clients[client_id]["session_history"] = session_history
                save_clients(clients)
                
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Client Approval APIs
@app.route('/api/clients', methods=['GET'])
def get_clients_api():
    clients = load_clients()
    return jsonify({"success": True, "clients": clients})

@app.route('/api/clients/register', methods=['POST'])
def register_client_api():
    try:
        data = request.get_json() or {}
        cid = data.get('id', '').strip().upper()
        if not cid:
            return jsonify({"success": False, "error": "รหัสผู้ใช้ไม่ถูกต้อง (Invalid ID)"}), 400
            
        clients = load_clients()
        if cid not in clients:
            clients[cid] = {
                "approved": False,
                "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_seen_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_clients(clients)
        else:
            clients[cid]["last_seen_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_clients(clients)
            
        return jsonify({"success": True, "approved": clients[cid]["approved"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/clients/approve-all', methods=['POST'])
def approve_all_clients_api():
    try:
        clients = load_clients()
        count = 0
        for cid in clients:
            if not clients[cid].get("approved", False):
                clients[cid]["approved"] = True
                count += 1
        if count > 0:
            save_clients(clients)
        return jsonify({"success": True, "approved_count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/clients/approve', methods=['POST'])
def approve_client_api():
    try:
        data = request.get_json() or {}
        cid = data.get('id', '').strip().upper()
        action = data.get('action', 'approve') # 'approve' or 'revoke'
        
        if not cid:
            return jsonify({"success": False, "error": "รหัสผู้ใช้ไม่ถูกต้อง"}), 400
            
        clients = load_clients()
        if cid not in clients:
            return jsonify({"success": False, "error": "ไม่พบผู้ใช้ในระบบ"}), 404
            
        clients[cid]["approved"] = (action == 'approve')
        save_clients(clients)
        
        return jsonify({"success": True, "approved": clients[cid]["approved"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/clients/status', methods=['GET'])
def get_client_status_api():
    try:
        cid = request.args.get('id', '').strip().upper()
        tokens_val = request.args.get('tokens', '')
        code = request.args.get('code', '').strip().upper()
        
        if not cid:
            return jsonify({"success": False, "error": "ระบุ ID ไม่ครบถ้วน"}), 400
            
        # Check if the code they present has positive remaining tokens to trigger auto-approval
        auto_approve = False
        if code:
            tokens_db = load_tokens()
            if code in tokens_db:
                token_info = tokens_db[code]
                
                # Check expiration date
                is_expired = False
                if token_info.get("expires_at"):
                    try:
                        exp_dt = datetime.datetime.strptime(token_info["expires_at"], "%Y-%m-%d %H:%M:%S")
                        if datetime.datetime.now() > exp_dt:
                            is_expired = True
                    except Exception:
                        pass
                
                if is_expired:
                    token_info["status"] = "expired"
                    token_info["remaining_tokens"] = 0
                    tokens_db[code] = token_info
                    save_tokens(tokens_db)
                
                if not is_expired and token_info.get("status") == "used" and token_info.get("remaining_tokens", 0) > 0:
                    auto_approve = True
            
        clients = load_clients()
        if cid not in clients:
            clients[cid] = {
                "approved": auto_approve,
                "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_seen_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "remaining_tokens": int(tokens_val) if tokens_val.isdigit() else 0
            }
            save_clients(clients)
            return jsonify({"success": True, "approved": auto_approve})
            
        clients[cid]["last_seen_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if tokens_val.isdigit():
            clients[cid]["remaining_tokens"] = int(tokens_val)
        if auto_approve:
            clients[cid]["approved"] = True
        save_clients(clients)
        return jsonify({"success": True, "approved": clients[cid]["approved"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # Start Flask Server
    app.run(host='0.0.0.0', port=8001)
