from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DISPLAY_W, DISPLAY_H = 96, 129
SCALE = 4
W, H = DISPLAY_W * SCALE, DISPLAY_H * SCALE
M = 5 * SCALE
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["spade", "heart", "club", "diamond"]
RED_SUITS = {1, 3}

FRONT_DIR = Path(__file__).resolve().parents[1] / "card_fronts" / "artdeck"
FRONT_HD_DIR = Path(__file__).resolve().parents[1] / "card_fronts" / "artdeck_hd"
BACK_DIR = Path(__file__).resolve().parents[1] / "card_backs"
BACK_HD_DIR = Path(__file__).resolve().parents[1] / "card_backs_hd"

try:
    RESAMPLE = Image.Resampling.LANCZOS
except Exception:
    RESAMPLE = Image.LANCZOS


def get_font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def suit_color(idx):
    return (190, 40, 40) if idx in RED_SUITS else (35, 35, 45)


def draw_heart(draw, cx, cy, s, fill):
    r = s // 3
    draw.ellipse((cx - r - r//2, cy - r, cx - r//2, cy), fill=fill)
    draw.ellipse((cx + r//2, cy - r, cx + r + r//2, cy), fill=fill)
    draw.polygon([(cx - s//2, cy), (cx + s//2, cy), (cx, cy + s//2 + s//4)], fill=fill)


def draw_diamond(draw, cx, cy, s, fill):
    draw.polygon([(cx, cy - s//2), (cx + s//2, cy), (cx, cy + s//2), (cx - s//2, cy)], fill=fill)


def draw_club(draw, cx, cy, s, fill):
    r = s // 4
    draw.ellipse((cx - r - r, cy - r, cx - r, cy + r), fill=fill)
    draw.ellipse((cx + r, cy - r, cx + r + r, cy + r), fill=fill)
    draw.ellipse((cx - r, cy - r - r, cx + r, cy + r - r), fill=fill)
    draw.rectangle((cx - r//3, cy + r, cx + r//3, cy + s//2), fill=fill)


def draw_spade(draw, cx, cy, s, fill):
    # upside-down heart + stem
    r = s // 3
    draw.ellipse((cx - r - r//2, cy, cx - r//2, cy + r), fill=fill)
    draw.ellipse((cx + r//2, cy, cx + r + r//2, cy + r), fill=fill)
    draw.polygon([(cx - s//2, cy + r), (cx + s//2, cy + r), (cx, cy - s//2 + r//2)], fill=fill)
    draw.rectangle((cx - r//3, cy + r, cx + r//3, cy + s//2 + r//3), fill=fill)


def draw_suit(draw, suit_idx, cx, cy, s, fill):
    if suit_idx == 0:
        draw_spade(draw, cx, cy, s, fill)
    elif suit_idx == 1:
        draw_heart(draw, cx, cy, s, fill)
    elif suit_idx == 2:
        draw_club(draw, cx, cy, s, fill)
    else:
        draw_diamond(draw, cx, cy, s, fill)


def pip_layout(rank):
    # normalized positions in card body
    m = 0.22
    c = 0.50
    b = 0.78
    l = 0.33
    r = 0.67
    layouts = {
        1: [(c, c)],
        2: [(c, m), (c, b)],
        3: [(c, m), (c, c), (c, b)],
        4: [(l, m), (r, m), (l, b), (r, b)],
        5: [(l, m), (r, m), (c, c), (l, b), (r, b)],
        6: [(l, m), (r, m), (l, c), (r, c), (l, b), (r, b)],
        7: [(l, m), (r, m), (l, c), (r, c), (c, c-0.12), (l, b), (r, b)],
        8: [(l, m), (r, m), (l, c-0.12), (r, c-0.12), (l, c+0.12), (r, c+0.12), (l, b), (r, b)],
        9: [(l, m), (r, m), (c, m+0.06), (l, c), (r, c), (c, c), (l, b), (r, b), (c, b-0.06)],
        10: [(l, m), (r, m), (c, m+0.06), (l, c-0.10), (r, c-0.10), (l, c+0.10), (r, c+0.10), (c, b-0.06), (l, b), (r, b)],
    }
    return layouts.get(rank, [(0.5, 0.5)])


def draw_front(suit_idx, rank_idx, out_path_hd, out_path_display):
    img = Image.new("RGB", (W, H), (242, 235, 222))
    d = ImageDraw.Draw(img)

    # Frame + subtle inner gradient bands
    d.rectangle((0, 0, W - 1, H - 1), fill=(250, 245, 236), outline=(70, 58, 50), width=2)
    d.rectangle((M, M, W - M - 1, H - M - 1), outline=(154, 120, 76), width=1)
    for y in range(M + 1, H - M - 1, 6):
        tone = 248 if (y // 6) % 2 == 0 else 242
        d.line((M + 1, y, W - M - 2, y), fill=(tone, tone - 3, tone - 8), width=1)

    color = suit_color(suit_idx)
    rank_text = RANKS[rank_idx]
    corner_font = get_font((16 if rank_idx < 9 else 14) * SCALE)

    d.text((10 * SCALE, 8 * SCALE), rank_text, fill=color, font=corner_font)
    draw_suit(d, suit_idx, 16 * SCALE, 27 * SCALE, 12 * SCALE, color)

    # mirrored corner
    mirror = Image.new("RGBA", (24 * SCALE, 28 * SCALE), (0, 0, 0, 0))
    md = ImageDraw.Draw(mirror)
    md.text((3 * SCALE, 0), rank_text, fill=color, font=corner_font)
    draw_suit(md, suit_idx, 9 * SCALE, 19 * SCALE, 12 * SCALE, color)
    mirror = mirror.rotate(180)
    img.paste(mirror, (W - 24 * SCALE - 8 * SCALE, H - 28 * SCALE - 8 * SCALE), mirror)

    rank = rank_idx + 1
    if rank <= 10:
        for nx, ny in pip_layout(rank):
            px = int(nx * W)
            py = int(ny * H)
            draw_suit(d, suit_idx, px, py, 16 * SCALE, color)
    else:
        # stylized face card emblem
        emblem = (120, 88, 44)
        d.ellipse((W//2 - 24 * SCALE, H//2 - 24 * SCALE, W//2 + 24 * SCALE, H//2 + 24 * SCALE), outline=emblem, width=3 * SCALE, fill=(245, 235, 210))
        letter_font = get_font(30 * SCALE)
        d.text((W//2 - 10 * SCALE, H//2 - 18 * SCALE), RANKS[rank_idx], fill=color, font=letter_font)
        draw_suit(d, suit_idx, W//2, H//2 + 16 * SCALE, 14 * SCALE, color)

    out_path_hd.parent.mkdir(parents=True, exist_ok=True)
    out_path_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_path_display, "PNG")


def draw_back(out_path_hd, out_path_display):
    img = Image.new("RGB", (W, H), (44, 72, 108))
    d = ImageDraw.Draw(img)

    d.rectangle((0, 0, W - 1, H - 1), fill=(35, 65, 96), outline=(220, 196, 142), width=2)
    d.rectangle((M, M, W - M - 1, H - M - 1), outline=(224, 206, 160), width=1)

    # lattice
    for i in range(-H, W + H, 10 * SCALE):
        d.line((i, 0, i - H, H), fill=(78, 118, 164), width=max(1, SCALE // 2))
        d.line((i, 0, i + H, H), fill=(58, 96, 138), width=max(1, SCALE // 2))

    # center badge
    cx, cy = W // 2, H // 2
    d.ellipse((cx - 22 * SCALE, cy - 22 * SCALE, cx + 22 * SCALE, cy + 22 * SCALE), fill=(224, 206, 160), outline=(140, 108, 60), width=2 * SCALE)
    d.ellipse((cx - 15 * SCALE, cy - 15 * SCALE, cx + 15 * SCALE, cy + 15 * SCALE), fill=(37, 66, 100), outline=(140, 108, 60), width=1 * SCALE)

    out_path_hd.parent.mkdir(parents=True, exist_ok=True)
    out_path_display.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path_hd, "PNG")
    img.resize((DISPLAY_W, DISPLAY_H), RESAMPLE).save(out_path_display, "PNG")


def main():
    for s in range(4):
        for n in range(13):
            draw_front(
                s,
                n,
                FRONT_HD_DIR / f"s{s}_n{n}.png",
                FRONT_DIR / f"s{s}_n{n}.png",
            )
    draw_back(BACK_HD_DIR / "artdeck_back.png", BACK_DIR / "artdeck_back.png")
    print("Generated ArtDeck fronts/back (HD + display size).")


if __name__ == "__main__":
    main()
