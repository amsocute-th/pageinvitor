import os
import sys
import json
from flask import Flask, jsonify, request, send_from_directory

# Add parent directory to path to import auto_poster, news_fetcher, graphic_generator
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_fetcher import NewsFetcher
from graphic_generator import GraphicGenerator
from auto_poster import AutoPoster

app = Flask(__name__, static_folder='.')

# In-memory store for the current active draft
current_draft = {
    "headline": "",
    "description": "",
    "caption": "",
    "source": "",
    "original_title": "",
    "original_description": ""
}

# Use absolute font file paths from parent directory
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
generator = GraphicGenerator(
    regular_font_path=os.path.join(base_dir, "Kanit-Regular.ttf"),
    bold_font_path=os.path.join(base_dir, "Kanit-Bold.ttf")
)
fetcher = NewsFetcher()
poster = AutoPoster()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/style.css')
def style():
    return send_from_directory('.', 'style.css')

@app.route('/news_card.png')
def get_image():
    return send_from_directory('.', 'news_card.png')

@app.route('/api/draft', methods=['GET'])
def get_draft():
    global current_draft
    try:
        # 1. Fetch latest news
        news_items = fetcher.fetch_top_news(limit=1)
        if not news_items:
            return jsonify({"success": False, "error": "No news items found"}), 404
        
        top_news = news_items[0]
        
        # 2. Get AI content / Translation
        ai_content = poster.ask_gemini(top_news["title"], top_news["description"])
        
        # 3. Cache current draft status
        current_draft = {
            "headline": ai_content["thai_headline"],
            "description": ai_content["thai_description"],
            "caption": ai_content["thai_caption"],
            "source": top_news["source"],
            "original_title": top_news["title"],
            "original_description": top_news["description"]
        }

        # 4. Generate Image Card
        generator.generate_news_card(
            title=current_draft["headline"],
            description=current_draft["description"],
            source=current_draft["source"],
            output_path="news_card.png"
        )
        
        return jsonify({
            "success": True,
            "draft": current_draft
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/update', methods=['POST'])
def update_draft():
    global current_draft
    try:
        data = request.get_json() or {}
        headline = data.get('headline', current_draft["headline"])
        description = data.get('description', current_draft["description"])
        caption = data.get('caption', current_draft["caption"])
        
        # Update cache
        current_draft["headline"] = headline
        current_draft["description"] = description
        current_draft["caption"] = caption
        
        # Regenerate the image card with the updated text
        generator.generate_news_card(
            title=current_draft["headline"],
            description=current_draft["description"],
            source=current_draft["source"],
            output_path="news_card.png"
        )
        
        return jsonify({"success": True, "draft": current_draft})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/approve', methods=['POST'])
def approve_post():
    global current_draft
    try:
        if not current_draft["headline"]:
            return jsonify({"success": False, "error": "No draft content to approve"}), 400
            
        # Post the generated image card and caption to Facebook
        fb_response = poster.post_image_to_facebook("news_card.png", current_draft["caption"])
        
        if "error" in fb_response:
            return jsonify({"success": False, "error": fb_response["error"]}), 500
            
        return jsonify({
            "success": True,
            "facebook_response": fb_response
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # Run the dashboard on port 8002 to avoid conflicts with 8001
    print("[Dashboard] Running server on http://localhost:8002")
    app.run(host='0.0.0.0', port=8002)
