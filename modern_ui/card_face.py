from modern_ui.ui_config import NUMS, SUIT_SYMBOLS


class CardFaceRenderer:
    def suit_symbol(self, suit):
        return SUIT_SYMBOLS[suit]

    def draw_card(
        self,
        canvas,
        x,
        y,
        hidden,
        suit,
        num,
        selected,
        cw,
        ch,
        theme,
        card_style,
        font_scale,
        back_image,
        front_image,
    ):
        def fs(base):
            return max(8, int(base * font_scale))

        fill = theme["card_back"] if hidden else theme["card_front"]
        outline = theme["card_select"] if selected else theme["card_border"]
        width = 3 if selected else 1
        canvas.create_rectangle(x, y, x + cw, y + ch, fill=fill, outline=outline, width=width)

        if hidden:
            self.draw_card_back_pattern(canvas, x, y, cw, ch, theme, card_style, font_scale, back_image)
            return

        if front_image is not None:
            canvas.create_image(x, y, anchor="nw", image=front_image)
            if selected:
                canvas.create_rectangle(x, y, x + cw, y + ch, outline=theme["card_select"], width=3)
            return

        rank = NUMS[num]
        suit_text = self.suit_symbol(suit)
        suit_color = "#dc2626" if suit in (1, 3) else "#111827"

        if card_style == "Classic":
            canvas.create_text(x + 8, y + 8, anchor="nw", text=f"{rank}{suit_text}", fill=suit_color, font=f"Helvetica {fs(12)} bold")
            canvas.create_text(x + cw - 8, y + ch - 8, anchor="se", text=f"{rank}{suit_text}", fill=suit_color, font=f"Helvetica {fs(12)} bold")
            canvas.create_text(x + cw * 0.5, y + ch * 0.52, text=suit_text, fill=suit_color, font=f"Helvetica {fs(24)} bold")
        elif card_style == "Minimal":
            canvas.create_text(x + cw * 0.5, y + ch * 0.42, text=rank, fill=suit_color, font=f"Helvetica {fs(24)} bold")
            canvas.create_text(x + cw * 0.5, y + ch * 0.68, text=suit_text, fill=suit_color, font=f"Helvetica {fs(16)}")
            canvas.create_line(x + 8, y + 8, x + cw - 8, y + 8, fill=suit_color, width=1)
            canvas.create_line(x + 8, y + ch - 8, x + cw - 8, y + ch - 8, fill=suit_color, width=1)
        else:
            pill_w = max(36, cw * 0.45)
            canvas.create_rectangle(x + 8, y + 8, x + 8 + pill_w, y + 28, fill=theme["deck_fill"], outline="")
            canvas.create_text(x + 14, y + 18, anchor="w", text=rank, fill="#ffffff", font=f"Helvetica {fs(11)} bold")
            canvas.create_text(x + cw - 10, y + 16, anchor="ne", text=suit_text, fill=suit_color, font=f"Helvetica {fs(14)} bold")
            canvas.create_line(x + 8, y + ch * 0.55, x + cw - 8, y + ch * 0.55, fill=theme["deck_outline"], width=2)
            canvas.create_text(x + cw * 0.5, y + ch * 0.77, text=suit_text * 2, fill=suit_color, font=f"Helvetica {fs(18)}")

    def draw_card_back_pattern(self, canvas, x, y, cw, ch, theme, card_style, font_scale, back_image):
        def fs(base):
            return max(8, int(base * font_scale))

        # Prefer custom image-based card backs when selected and image is available.
        if back_image is not None:
            canvas.create_image(x, y, anchor="nw", image=back_image)
            return

        if card_style == "Classic":
            for i in range(4):
                yy = y + 12 + i * (ch - 24) / 3
                canvas.create_line(x + 10, yy, x + cw - 10, yy, fill=theme["deck_outline"], width=1)
            canvas.create_text(x + cw * 0.5, y + ch * 0.5, text="###", fill="#e5e7eb", font=f"Helvetica {fs(12)} bold")
        elif card_style == "Minimal":
            canvas.create_rectangle(x + 10, y + 10, x + cw - 10, y + ch - 10, outline=theme["deck_outline"], width=2)
            canvas.create_text(x + cw * 0.5, y + ch * 0.5, text="::", fill="#dbeafe", font=f"Helvetica {fs(16)} bold")
        else:
            step = max(8, int(cw / 6))
            for i in range(0, int(cw), step):
                canvas.create_line(x + i, y + 8, x + i + 10, y + ch - 8, fill=theme["deck_outline"], width=1)
            canvas.create_text(x + cw * 0.5, y + ch * 0.5, text="<>", fill="#fde68a", font=f"Helvetica {fs(14)} bold")
