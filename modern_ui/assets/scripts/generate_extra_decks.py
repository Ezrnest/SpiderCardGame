from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DISPLAY_W, DISPLAY_H = 96, 129
SCALE = 4
W, H = DISPLAY_W * SCALE, DISPLAY_H * SCALE
M = 5 * SCALE
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RED_SUITS = {1, 3}

ASSET_ROOT = Path(__file__).resolve().parents[1]

try:
    RESAMPLE = Image.Resampling.LANCZOS
except Exception:
    RESAMPLE = Image.LANCZOS


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def suit_color(s):
    return (215, 74, 74) if s in RED_SUITS else (230, 237, 255)


def draw_suit(draw, suit, cx, cy, size, fill):
    r = size // 3
    if suit == 1:  # heart
        draw.ellipse((cx - r - r // 2, cy - r, cx - r // 2, cy), fill=fill)
        draw.ellipse((cx + r // 2, cy - r, cx + r + r // 2, cy), fill=fill)
        draw.polygon([(cx - size // 2, cy), (cx + size // 2, cy), (cx, cy + size // 2 + size // 4)], fill=fill)
    elif suit == 3:  # diamond
        draw.polygon([(cx, cy - size // 2), (cx + size // 2, cy), (cx, cy + size // 2), (cx - size // 2, cy)], fill=fill)
    elif suit == 2:  # club
        rr = size // 4
        draw.ellipse((cx - rr - rr, cy - rr, cx - rr, cy + rr), fill=fill)
        draw.ellipse((cx + rr, cy - rr, cx + rr + rr, cy + rr), fill=fill)
        draw.ellipse((cx - rr, cy - rr - rr, cx + rr, cy + rr - rr), fill=fill)
        draw.rectangle((cx - rr // 3, cy + rr, cx + rr // 3, cy + size // 2), fill=fill)
    else:  # spade
        draw.ellipse((cx - r - r // 2, cy, cx - r // 2, cy + r), fill=fill)
        draw.ellipse((cx + r // 2, cy, cx + r + r // 2, cy + r), fill=fill)
        draw.polygon([(cx - size // 2, cy + r), (cx + size // 2, cy + r), (cx, cy - size // 2 + r // 2)], fill=fill)
        draw.rectangle((cx - r // 3, cy + r, cx + r // 3, cy + size // 2 + r // 3), fill=fill)


def draw_common_front(deck_name, suit, rank, bg, border, accent):
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), fill=bg, outline=border, width=2 * SCALE)
    d.rectangle((M, M, W - M - 1, H - M - 1), outline=accent, width=1 * SCALE)
    return img, d


def draw_front_neogrid(suit, rank_idx, out_hd, out_display):
    img, d = draw_common_front("neogrid", suit, rank_idx, (15, 22, 44), (58, 204, 255), (92, 125, 255))
    # neon grid
    for x in range(M, W - M, 18 * SCALE):
        d.line((x, M, x, H - M), fill=(35, 68, 120), width=1)
    for y in range(M, H - M, 18 * SCALE):
        d.line((M, y, W - M, y), fill=(26, 54, 98), width=1)

    color = suit_color(suit)
    rank = RANKS[rank_idx]
    f = font(17 * SCALE)
    d.text((12 * SCALE, 8 * SCALE), rank, fill=color, font=f)
    draw_suit(d, suit, 18 * SCALE, 30 * SCALE, 12 * SCALE, color)

    # center symbol band
    d.rectangle((M + 12 * SCALE, H // 2 - 15 * SCALE, W - M - 12 * SCALE, H // 2 + 15 * SCALE), fill=(23, 39, 72), outline=(74, 139, 255), width=1)
    draw_suit(d, suit, W // 2, H // 2, 18 * SCALE, color)

    out_hd.parent.mkdir(parents=True, exist_ok=True)
    out_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_display, "PNG")


def draw_back_neogrid(out_hd, out_display):
    img = Image.new("RGB", (W, H), (13, 20, 38))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), outline=(76, 226, 255), width=2 * SCALE)
    d.rectangle((M, M, W - M - 1, H - M - 1), outline=(104, 124, 255), width=1 * SCALE)
    for i in range(-H, W + H, 12 * SCALE):
        d.line((i, 0, i - H, H), fill=(40, 78, 133), width=1)
        d.line((i, 0, i + H, H), fill=(30, 56, 108), width=1)
    d.ellipse((W // 2 - 22 * SCALE, H // 2 - 22 * SCALE, W // 2 + 22 * SCALE, H // 2 + 22 * SCALE), outline=(99, 235, 255), width=2 * SCALE)
    out_hd.parent.mkdir(parents=True, exist_ok=True)
    out_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_display, "PNG")


def draw_front_vintage(suit, rank_idx, out_hd, out_display):
    img, d = draw_common_front("vintage", suit, rank_idx, (244, 233, 204), (92, 65, 36), (179, 143, 82))
    # parchment noise-like lines
    for y in range(M + 4 * SCALE, H - M, 8 * SCALE):
        tone = 232 if (y // (8 * SCALE)) % 2 == 0 else 238
        d.line((M + 2 * SCALE, y, W - M - 2 * SCALE, y), fill=(tone, tone - 8, tone - 20), width=1)

    color = (161, 39, 39) if suit in RED_SUITS else (52, 42, 34)
    rank = RANKS[rank_idx]
    f = font(16 * SCALE)
    d.text((11 * SCALE, 8 * SCALE), rank, fill=color, font=f)
    draw_suit(d, suit, 17 * SCALE, 29 * SCALE, 12 * SCALE, color)

    # old crest
    cx, cy = W // 2, H // 2
    d.ellipse((cx - 26 * SCALE, cy - 26 * SCALE, cx + 26 * SCALE, cy + 26 * SCALE), fill=(233, 214, 172), outline=(127, 95, 54), width=2 * SCALE)
    d.ellipse((cx - 18 * SCALE, cy - 18 * SCALE, cx + 18 * SCALE, cy + 18 * SCALE), outline=(145, 110, 64), width=1 * SCALE)
    d.text((cx - 9 * SCALE, cy - 15 * SCALE), rank, fill=color, font=font(22 * SCALE))
    draw_suit(d, suit, cx, cy + 12 * SCALE, 13 * SCALE, color)

    out_hd.parent.mkdir(parents=True, exist_ok=True)
    out_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_display, "PNG")


def draw_back_vintage(out_hd, out_display):
    img = Image.new("RGB", (W, H), (112, 74, 44))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), outline=(234, 204, 144), width=2 * SCALE)
    d.rectangle((M, M, W - M - 1, H - M - 1), outline=(212, 176, 115), width=1 * SCALE)
    for i in range(0, W, 9 * SCALE):
        d.line((i, M, i + H // 2, H - M), fill=(130, 88, 53), width=1)
    d.ellipse((W // 2 - 24 * SCALE, H // 2 - 24 * SCALE, W // 2 + 24 * SCALE, H // 2 + 24 * SCALE), fill=(185, 142, 82), outline=(236, 205, 146), width=2 * SCALE)
    out_hd.parent.mkdir(parents=True, exist_ok=True)
    out_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_display, "PNG")


def draw_front_sakuraink(suit, rank_idx, out_hd, out_display):
    img, d = draw_common_front("sakuraink", suit, rank_idx, (252, 246, 248), (96, 78, 86), (201, 168, 181))
    # soft washi paper strokes
    for y in range(M + 2 * SCALE, H - M, 10 * SCALE):
        tone = 242 if (y // (10 * SCALE)) % 2 == 0 else 246
        d.line((M + 2 * SCALE, y, W - M - 2 * SCALE, y), fill=(tone, tone - 4, tone - 6), width=1)
    for x in range(M + 6 * SCALE, W - M, 28 * SCALE):
        d.line((x, M + 2 * SCALE, x + 8 * SCALE, H - M - 2 * SCALE), fill=(238, 228, 232), width=1)

    color = (186, 52, 86) if suit in RED_SUITS else (44, 50, 62)
    rank = RANKS[rank_idx]
    d.text((11 * SCALE, 8 * SCALE), rank, fill=color, font=font(16 * SCALE))
    draw_suit(d, suit, 18 * SCALE, 30 * SCALE, 12 * SCALE, color)

    # ink circle + center symbol
    cx, cy = W // 2, H // 2
    d.ellipse((cx - 26 * SCALE, cy - 26 * SCALE, cx + 26 * SCALE, cy + 26 * SCALE), outline=(126, 101, 111), width=2 * SCALE)
    d.ellipse((cx - 18 * SCALE, cy - 18 * SCALE, cx + 18 * SCALE, cy + 18 * SCALE), outline=(198, 162, 177), width=1 * SCALE)
    draw_suit(d, suit, cx, cy, 18 * SCALE, color)

    out_hd.parent.mkdir(parents=True, exist_ok=True)
    out_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_display, "PNG")


def draw_back_sakuraink(out_hd, out_display):
    img = Image.new("RGB", (W, H), (71, 63, 72))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), outline=(230, 204, 214), width=2 * SCALE)
    d.rectangle((M, M, W - M - 1, H - M - 1), outline=(198, 160, 176), width=1 * SCALE)
    for i in range(-H, W + H, 14 * SCALE):
        d.line((i, M, i - H // 2, H - M), fill=(98, 83, 97), width=1)
    for i in range(-H, W + H, 18 * SCALE):
        d.line((i, M, i + H // 2, H - M), fill=(87, 74, 86), width=1)
    cx, cy = W // 2, H // 2
    d.ellipse((cx - 22 * SCALE, cy - 22 * SCALE, cx + 22 * SCALE, cy + 22 * SCALE), fill=(156, 115, 135), outline=(234, 215, 222), width=2 * SCALE)
    out_hd.parent.mkdir(parents=True, exist_ok=True)
    out_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_display, "PNG")


def build_deck(name, front_fn, back_fn):
    front_disp = ASSET_ROOT / "card_fronts" / name
    front_hd = ASSET_ROOT / "card_fronts" / f"{name}_hd"
    back_disp = ASSET_ROOT / "card_backs" / f"{name}_back.png"
    back_hd = ASSET_ROOT / "card_backs_hd" / f"{name}_back.png"

    for s in range(4):
        for n in range(13):
            front_fn(s, n, front_hd / f"s{s}_n{n}.png", front_disp / f"s{s}_n{n}.png")
    back_fn(back_hd, back_disp)


def main():
    build_deck("neogrid", draw_front_neogrid, draw_back_neogrid)
    build_deck("vintagegold", draw_front_vintage, draw_back_vintage)
    build_deck("sakuraink", draw_front_sakuraink, draw_back_sakuraink)
    print("Generated NeoGrid, VintageGold and SakuraInk decks (HD + display).")


if __name__ == "__main__":
    main()
