import os
import requests
import json
from dotenv import load_dotenv
from news_fetcher import NewsFetcher
from graphic_generator import GraphicGenerator
from config import GRAPH_API_BASE_URL, PAGE_ACCESS_TOKEN, PAGE_ID

load_dotenv()

class AutoPoster:
    def __init__(self):
        self.fetcher = NewsFetcher()
        self.generator = GraphicGenerator()
        self.gemini_key = os.getenv("GEMINI_API_KEY")

    def ask_gemini(self, title: str, description: str) -> dict:
        """Call Gemini API to translate and craft a catchy Thai headline and caption."""
        if not self.gemini_key:
            print("[AutoPoster] No GEMINI_API_KEY found. Using fallback.")
            return self._fallback_translation(title, description)

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
        headers = {"Content-Type": "application/json"}
        
        prompt = (
            f"You are a professional motorsport content creator. Translate this news to Thai:\n"
            f"Title: {title}\n"
            f"Description: {description}\n\n"
            f"Provide your response as a valid JSON object ONLY, with these keys:\n"
            f"1. 'thai_headline': A very catchy, concise Thai headline for a graphic card (max 80 chars).\n"
            f"2. 'thai_description': A brief summary of the news in Thai (max 200 chars).\n"
            f"3. 'thai_caption': An engaging Facebook post caption summarizing the news with hashtags.\n\n"
            f"Ensure the response is strictly valid JSON."
        )

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(text)
                return data
            else:
                print(f"[AutoPoster] Gemini API returned status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[AutoPoster] Error calling Gemini: {e}")

        return self._fallback_translation(title, description)

    def _fallback_translation(self, title: str, description: str) -> dict:
        # Simple heuristics for fallback translation
        return {
            "thai_headline": title, # fallback to original English
            "thai_description": description,
            "thai_caption": f"📢 อัปเดตข่าวสาร Motorsport วันนี้!\n\n{title}\n\n{description}\n\n#Motorsport #F1 #MotoGP"
        }

    def post_image_to_facebook(self, image_path: str, message: str) -> dict:
        """Upload a local image file and post it to the Facebook Page."""
        if not PAGE_ACCESS_TOKEN or not PAGE_ID:
            print("[AutoPoster] Facebook Page credentials not configured. Skipping post.")
            return {"error": "Missing Facebook credentials"}

        url = f"{GRAPH_API_BASE_URL}/{PAGE_ID}/photos"
        payload = {
            "message": message,
            "access_token": PAGE_ACCESS_TOKEN
        }
        
        try:
            with open(image_path, "rb") as img_file:
                files = {
                    "source": img_file
                }
                print(f"[AutoPoster] Uploading {image_path} to Facebook Page...")
                response = requests.post(url, data=payload, files=files, timeout=30)
                result = response.json()
                return result
        except Exception as e:
            print(f"[AutoPoster] Facebook API post failed: {e}")
            return {"error": str(e)}

    def run_pipeline(self) -> dict:
        """Run the complete news auto-posting pipeline with an approval step."""
        print("[AutoPoster] Starting Motorsport news pipeline...")
        
        # 1. Fetch news
        news_items = self.fetcher.fetch_top_news(limit=1)
        if not news_items:
            print("[AutoPoster] No news found.")
            return {}
        
        top_news = news_items[0]
        print(f"[AutoPoster] Selected news: {top_news['title']}")

        # 2. Process with AI
        content = self.ask_gemini(top_news["title"], top_news["description"])
        print("\n================== DRAFT CAPTION ==================")
        print(content["thai_caption"])
        print("===================================================\n")
        
        # 3. Generate Image
        image_path = "news_card.png"
        self.generator.generate_news_card(
            title=content["thai_headline"],
            description=content["thai_description"],
            source=top_news["source"],
            output_path=image_path
        )
        print(f"[AutoPoster] Draft image generated at: {image_path}")

        # 4. Interactive Approval Step
        user_input = input("\nDo you approve publishing this post to Facebook? (y/n): ").strip().lower()
        if user_input != 'y':
            print("[AutoPoster] Publishing cancelled by user. Draft saved.")
            return {
                "news": top_news,
                "thai_content": content,
                "image": image_path,
                "status": "Draft Saved (Not Published)"
            }

        # 5. Post to Facebook
        fb_result = self.post_image_to_facebook(image_path, content["thai_caption"])
        print(f"[AutoPoster] Facebook response: {json.dumps(fb_result, indent=2)}")
        
        return {
            "news": top_news,
            "thai_content": content,
            "image": image_path,
            "facebook": fb_result,
            "status": "Published"
        }

if __name__ == "__main__":
    poster = AutoPoster()
    poster.run_pipeline()
