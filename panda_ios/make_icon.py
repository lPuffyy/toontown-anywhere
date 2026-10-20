"""Draws the app icon (a cartoon toon with a party hat) and writes the sizes iOS wants.
  python make_icon.py <out dir>
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
S = 1024

# Preferred: a real screenshot of the game (icon_source.jpg next to this script), cropped square.
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon_source.jpg")
if os.path.exists(src):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    side = min(w, h) - 41                      # trim the bottom edge (joystick overlay) and a little off the sides
    left = (w - side) // 2
    im = im.crop((left, 0, left + side, side)).resize((S, S), Image.LANCZOS)
    im.resize((180, 180), Image.LANCZOS).save(os.path.join(out, "AppIcon60x60@3x.png"))
    im.resize((120, 120), Image.LANCZOS).save(os.path.join(out, "AppIcon60x60@2x.png"))
    im.save(os.path.join(out, "AppIcon-1024.png"))
    print("icons from game screenshot written to", out)
    sys.exit(0)

img = Image.new("RGB", (S, S))
px = img.load()
for y in range(S):
    t = y / S
    c = (int(110 - 80 * t), int(190 - 110 * t), int(255 - 60 * t))
    for x in range(S):
        px[x, y] = c
d = ImageDraw.Draw(img, "RGBA")
for cx, cy, r in ((180, 200, 150), (860, 260, 110), (780, 820, 170), (150, 780, 100)):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 40))
for cx in (250, 774):                                   # ears
    d.ellipse((cx - 120, 230, cx + 120, 470), fill=(240, 150, 40, 255), outline=(120, 60, 10, 255), width=14)
    d.ellipse((cx - 60, 290, cx + 60, 420), fill=(255, 190, 110, 255))
d.ellipse((180, 260, 844, 900), fill=(255, 205, 70, 255), outline=(120, 70, 10, 255), width=18)   # head
for cx in (400, 624):                                   # eyes
    d.ellipse((cx - 90, 430, cx + 90, 640), fill=(255, 255, 255, 255), outline=(40, 30, 20, 255), width=12)
    d.ellipse((cx - 38, 500, cx + 42, 600), fill=(25, 25, 30, 255))
    d.ellipse((cx - 10, 515, cx + 20, 545), fill=(255, 255, 255, 255))
d.ellipse((330, 630, 694, 860), fill=(255, 235, 170, 255), outline=(120, 70, 10, 255), width=10)   # muzzle
d.ellipse((470, 640, 554, 700), fill=(60, 40, 30, 255))
d.arc((380, 660, 644, 830), 20, 160, fill=(90, 30, 20, 255), width=18)                            # smile
d.polygon([(512, 60), (380, 300), (644, 300)], fill=(235, 60, 70, 255), outline=(100, 20, 20, 255))  # party hat
d.ellipse((490, 30, 540, 80), fill=(255, 230, 80, 255))
for ofs in (-60, 0, 60):
    d.ellipse((512 + ofs - 14, 170 + abs(ofs) // 3, 512 + ofs + 14, 198 + abs(ofs) // 3), fill=(255, 255, 255, 230))
img = img.filter(ImageFilter.SMOOTH)
img.resize((180, 180), Image.LANCZOS).save(os.path.join(out, "AppIcon60x60@3x.png"))
img.resize((120, 120), Image.LANCZOS).save(os.path.join(out, "AppIcon60x60@2x.png"))
img.save(os.path.join(out, "AppIcon-1024.png"))
print("icons written to", out)
