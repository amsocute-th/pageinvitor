import os
from PIL import Image, ImageDraw, ImageFont

class GraphicGenerator:
    """Generates image banners (News Cards) with text overlays."""
    
    def __init__(self, regular_font_path: str = "Kanit-Regular.ttf", bold_font_path: str = "Kanit-Bold.ttf"):
        self.regular_font_path = regular_font_path
        self.bold_font_path = bold_font_path
        
        # Verify font files exist, fallback to default if not found
        if not os.path.exists(self.regular_font_path):
            print(f"[Warning] Font {self.regular_font_path} not found. Falling back to default.")
            self.regular_font_path = None
        if not os.path.exists(self.bold_font_path):
            print(f"[Warning] Font {self.bold_font_path} not found. Falling back to default.")
            self.bold_font_path = None

    def create_gradient_background(self, width: int, height: int) -> Image.Image:
        """Create a dark sporty gradient background (black to dark red/grey)."""
        base = Image.new("RGBA", (width, height), (15, 15, 18, 255))
        draw = ImageDraw.Draw(base)
        
        # Draw a subtle linear gradient from top-left (dark charcoal) to bottom-right (deep red-grey)
        for y in range(height):
            # Calculate interpolation ratio
            r_ratio = y / height
            r = int(15 + (35 * r_ratio)) # Fade from 15 to 50
            g = int(15 + (5 * r_ratio))  # Fade from 15 to 20
            b = int(18 + (5 * r_ratio))  # Fade from 18 to 23
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
            
        # Draw a bright red racing accent bar on the left edge
        draw.rectangle([0, 0, 15, height], fill=(220, 38, 38, 255)) # Tail wind red-600
        
        return base

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Wrap text to fit within a maximum pixel width."""
        words = text.split(" ")
        lines = []
        current_line = []
        
        for word in words:
            # Check length of line if word is added
            test_line = " ".join(current_line + [word])
            # Use font.getbbox to measure text width
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
            
            if w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    def generate_news_card(self, title: str, description: str, source: str, output_path: str = "news_card.png") -> str:
        """Draw news details onto a canvas and save to disk."""
        # 1. Create base canvas
        width, height = 1200, 1200
        img = self.create_gradient_background(width, height)
        draw = ImageDraw.Draw(img)
        
        # 2. Setup fonts
        title_font_size = 54
        body_font_size = 32
        meta_font_size = 24
        
        if self.bold_font_path:
            title_font = ImageFont.truetype(self.bold_font_path, title_font_size)
            meta_font = ImageFont.truetype(self.bold_font_path, meta_font_size)
        else:
            title_font = ImageFont.load_default()
            meta_font = ImageFont.load_default()
            
        if self.regular_font_path:
            body_font = ImageFont.truetype(self.regular_font_path, body_font_size)
        else:
            body_font = ImageFont.load_default()

        # 3. Draw Brand/Category Header
        draw.rectangle([60, 60, 240, 100], fill=(220, 38, 38, 255))
        draw.text((75, 65), "HOT NEWS", fill=(255, 255, 255), font=meta_font)
        draw.text((260, 65), f"|  {source.upper()}", fill=(156, 163, 175), font=meta_font) # Grey text

        # 4. Wrap & Draw Headline Title (Allowing up to 850px width)
        max_text_width = 1000
        title_lines = self.wrap_text(title, title_font, max_text_width)
        
        y_cursor = 180
        for line in title_lines[:3]: # Limit to 3 lines for title
            draw.text((60, y_cursor), line, fill=(255, 255, 255), font=title_font)
            # Increment by height of line plus spacing
            bbox = title_font.getbbox(line)
            line_h = bbox[3] - bbox[1]
            y_cursor += line_h + 15
            
        # Draw a separator line
        y_cursor += 30
        draw.line([(60, y_cursor), (300, y_cursor)], fill=(220, 38, 38, 255), width=6)
        y_cursor += 60

        # 5. Wrap & Draw Description
        desc_lines = self.wrap_text(description, body_font, max_text_width)
        for line in desc_lines[:6]: # Limit to 6 lines for description
            draw.text((60, y_cursor), line, fill=(209, 213, 219), font=body_font) # light grey
            bbox = body_font.getbbox(line)
            line_h = bbox[3] - bbox[1]
            y_cursor += line_h + 12

        # 6. Draw Footer Info
        draw.text((60, 1100), "MOTORSPORT AUTO-POSTER", fill=(156, 163, 175), font=meta_font)
        draw.text((1000, 1100), "LIVE UPDATES", fill=(220, 38, 38), font=meta_font)

        # 7. Save Image
        img.save(output_path, "PNG")
        print(f"[GraphicGenerator] News Card successfully generated: {output_path}")
        return output_path

if __name__ == "__main__":
    import sys
    # Test generator if run directly
    generator = GraphicGenerator()
    generator.generate_news_card(
        title="Alex Albon reflects on Williams' difficult start to 2026 F1 season",
        description="Alexander Albon has described the first half of the 2026 season as putting out fires for Williams as they grapple with technical issues and search for a faster car setup.",
        source="Autosport",
        output_path="test_news_card.png"
    )
