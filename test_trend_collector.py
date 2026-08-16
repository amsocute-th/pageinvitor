import json
from trend_collector import TrendCollector

def test_collector():
    print("Initializing TrendCollector...")
    collector = TrendCollector()
    
    print("\nCollecting trends for Thailand (TH)...")
    try:
        trends = collector.collect_all(region="TH")
        
        # Print a clean summary
        print("\n--- Google Trends (TH) ---")
        for t in trends["google"][:5]:
            print(f"Rank {t['rank']}: {t['title']} ({t.get('traffic', 'N/A')}) - {t['source']}")
            
        print("\n--- X (Twitter) Trends (TH) ---")
        for t in trends["x"][:5]:
            print(f"Rank {t['rank']}: {t['title']} ({t.get('volume', 'N/A')}) - {t['source']}")
            
        print("\n--- TikTok Trends (TH) ---")
        for t in trends["tiktok"][:5]:
            print(f"Rank {t['rank']}: {t['title']} ({t.get('views', 'N/A')}) - {t['source']}")
            
        # Write to a output file for manual verification
        output_file = "trends_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(trends, f, indent=2, ensure_ascii=False)
        print(f"\nSaved full output to {output_file}")
        
    except Exception as e:
        print(f"Test failed with error: {e}")

if __name__ == "__main__":
    test_collector()
