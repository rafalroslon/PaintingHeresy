import sqlite3, os, io, requests, re
from PIL import Image, ImageDraw, ImageFont, ImageFilter

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PaintsReq.db')

# ============================================================
# POBIERANIE OFICJALNYCH HEX-ÓW
# ============================================================

def fetch_hex_from_warpaint_api():
    try:
        query = '{ paints(brand: "Citadel") { name type hex } }'
        r = requests.post(
            "https://warpaint.fergcb.uk/graphql",
            json={"query": query},
            timeout=15
        )
        data = r.json()
        paints = data.get("data", {}).get("paints", [])
        hex_map = {}
        for p in paints:
            if p.get("hex"):
                hex_map[p["name"]] = f"#{p['hex'].upper().lstrip('#')}"
        print(f"✅ Pobrano {len(hex_map)} kolorów z Warpaint API")
        return hex_map
    except Exception as e:
        print(f"⚠️  Warpaint API niedostępny: {e}")
        return {}

def fetch_hex_from_bolter():
    url = "https://bolterandchainsword.com/topic/352780-paint-color-hexadecimal-codes/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        matches = re.findall(
            r'([A-Z][A-Za-z\'\s\-!]+?)\s*[:\-]\s*#?([0-9A-Fa-f]{6})',
            r.text
        )
        hex_map = {}
        for name, hex_val in matches:
            name = name.strip()
            if 2 < len(name) < 50:
                hex_map[name] = f"#{hex_val.upper()}"
        print(f"✅ Pobrano {len(hex_map)} kolorów z Bolter & Chainsword")
        return hex_map
    except Exception as e:
        print(f"⚠️  Bolter & Chainsword niedostępny: {e}")
        return {}

# ============================================================
# WALIDACJA HEX
# ============================================================

def validate_hex(hex_color):
    return bool(re.match(r'^#[0-9A-Fa-f]{6}$', str(hex_color)))

def safe_hex(name, hex_color):
    if not validate_hex(hex_color):
        print(f"  ⚠️  BŁĄD HEX: {name} → '{hex_color}' — zamieniam na #888888")
        return "#888888"
    return hex_color

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def darken(rgb, factor=0.15):
    return tuple(max(0, int(c * factor)) for c in rgb)

def lighten(rgb, factor=1.6):
    return tuple(min(255, int(c * factor)) for c in rgb)

def blend(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

# ============================================================
# GENEROWANIE KAFELKA — GRADIENT + METALICZNY EFEKT
# ============================================================

def make_paint_tile(name, category, hex_color="#888888"):
    W, H = 600, 600
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    rgb      = hex_to_rgb(hex_color)
    dark_rgb = darken(rgb, 0.12)
    mid_rgb  = blend(rgb, (20, 18, 30), 0.5)

    # ── TŁO: gradient pionowy kolor → ciemność ──────────────
    for y in range(H):
        t = y / H
        # Górna część: czysty kolor, dolna: bardzo ciemna
        if t < 0.5:
            c = blend(rgb, mid_rgb, t * 2)
        else:
            c = blend(mid_rgb, dark_rgb, (t - 0.5) * 2)
        draw.line([(0, y), (W, y)], fill=c + (255,))

    # ── METALICZNY POŁYSK (jasna ukośna smuga) ───────────────
    shine = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd    = ImageDraw.Draw(shine)
    # Ukośna smuga jasności
    for i in range(180):
        alpha = int(60 * (1 - abs(i - 90) / 90))
        sd.line([(i * 4 - 200, 0), (i * 4 - 200 + H, H)], fill=(255, 255, 255, alpha), width=2)
    shine = shine.filter(ImageFilter.GaussianBlur(18))
    img   = Image.alpha_composite(img, shine)
    draw  = ImageDraw.Draw(img)

    # ── ZŁOTA RAMKA ──────────────────────────────────────────
    gold      = (201, 168, 76)
    gold_dark = (100, 80, 30)
    for i, (color, width) in enumerate([(gold_dark, 6), (gold, 2)]):
        offset = i * 4 + 4
        draw.rectangle(
            [offset, offset, W - offset - 1, H - offset - 1],
            outline=color, width=width
        )

    # ── NAROŻNE DETALE (warhammer ornament) ──────────────────
    corner_size = 22
    for cx, cy in [(8, 8), (W-8, 8), (8, H-8), (W-8, H-8)]:
        draw.ellipse(
            [cx - corner_size//2, cy - corner_size//2,
             cx + corner_size//2, cy + corner_size//2],
            outline=gold, width=2
        )
        draw.line([(cx - corner_size, cy), (cx + corner_size, cy)], fill=gold, width=1)
        draw.line([(cx, cy - corner_size), (cx, cy + corner_size)], fill=gold, width=1)

    # ── ŚRODKOWY KRĄG Z KOLOREM ──────────────────────────────
    # Cień pod kręgiem
    shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd2 = ImageDraw.Draw(shadow_layer)
    r   = 160
    cx, cy = W // 2, H // 2 - 20
    sd2.ellipse([cx - r + 8, cy - r + 8, cx + r + 8, cy + r + 8],
                fill=(0, 0, 0, 120))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(16))
    img  = Image.alpha_composite(img, shadow_layer)
    draw = ImageDraw.Draw(img)

    # Główny krąg — gradient od jasnego koloru do ciemnego
    light_rgb = lighten(rgb, 1.3)
    for i in range(r, 0, -1):
        t     = 1 - (i / r)
        c     = blend(light_rgb, darken(rgb, 0.4), t)
        alpha = 255
        draw.ellipse(
            [cx - i, cy - i, cx + i, cy + i],
            fill=c + (alpha,)
        )

    # Połysk na kręgu (biały highlight u góry-lewej)
    highlight = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hr = int(r * 0.55)
    hd.ellipse(
        [cx - hr - 30, cy - hr - 30,
         cx + hr - 30, cy + hr - 30],
        fill=(255, 255, 255, 55)
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(22))
    img  = Image.alpha_composite(img, highlight)
    draw = ImageDraw.Draw(img)

    # Złota obwódka kręgu
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=gold, width=3)
    draw.ellipse([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4],
                 outline=gold_dark, width=1)

    # ── CZCIONKA ─────────────────────────────────────────────
    font_name = font_cat = None
    for font_path in ["Cinzel-Bold.ttf", "arialbd.ttf", "arial.ttf"]:
        try:
            font_name = ImageFont.truetype(font_path, 34)
            font_cat  = ImageFont.truetype(font_path, 20)
            break
        except Exception:
            pass
    if font_name is None:
        font_name = font_cat = ImageFont.load_default()

    # ── NAZWA — wycentrowana między kółkiem a dolną ramką ────
    circle_bottom = cy + r
    border_bottom = H - 12  # złota ramka

    # Najpierw oblicz linie
    words = name.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font_name)
        if bbox[2] - bbox[0] < W - 40:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)

    line_h     = 38
    total_h    = len(lines) * line_h
    space      = border_bottom - circle_bottom
    y_text     = circle_bottom + (space - total_h) // 2

    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font_name)
        lw   = bbox[2] - bbox[0]
        draw.text(((W - lw) / 2 + 2, y_text + 2), ln,
                  fill=(0, 0, 0, 180), font=font_name)
        draw.text(((W - lw) / 2, y_text), ln,
                  fill=(240, 220, 180, 255), font=font_name)
        y_text += line_h

    # ── ZAPIS ────────────────────────────────────────────────
    final = img.convert("RGB")
    bio   = io.BytesIO()
    final.save(bio, "PNG")
    return bio.getvalue()

# ============================================================
# FALLBACK COLORS
# ============================================================

FALLBACK_COLORS = {
    # BASE
    "Abaddon Black":            "#231F20",
    "Averland Sunset":          "#F5A800",
    "Balthasar Gold":           "#8C6A3F",
    "Baneblade Brown":          "#8C7355",
    "Bugman's Glow":            "#8C4A3C",
    "Caledor Sky":              "#1E5FA8",
    "Caliban Green":            "#004F2D",
    "Castellan Green":          "#3C4A2A",
    "Catachan Fleshtone":       "#6B4F3A",
    "Celestra Grey":            "#8A9E9E",
    "Corax White":              "#E8E8E8",
    "Daemonette Hide":          "#6A5A7A",
    "Dark Reaper":              "#2A3F4A",
    "Death Guard Green":        "#5A6A3A",
    "Deathworld Forest":        "#4A5A2A",
    "Dryad Bark":               "#3A2A1A",
    "Eshin Grey":               "#3A3A3A",
    "Gal Vorbak Red":           "#5A1A1A",
    "Grey Seer":                "#C0C0C0",
    "Incubi Darkness":          "#0A3A3A",
    "Iron Hands Steel":         "#6A6A7A",
    "Iron Warriors":            "#5A5A6A",
    "Jokaero Orange":           "#D45A00",
    "Kantor Blue":              "#0A1A5A",
    "Khorne Red":               "#7A0A0A",
    "Leadbelcher":              "#7A7A8A",
    "Macragge Blue":            "#1A3A7A",
    "Mechanicus Standard Grey": "#4A4A4A",
    "Mephiston Red":            "#9A0A0A",
    "Mournfang Brown":          "#5A2A0A",
    "Naggaroth Night":          "#3A1A5A",
    "Nocturne Green":           "#0A2A1A",
    "Orruk Flesh":              "#6A8A3A",
    "Phoenician Purple":        "#4A0A5A",
    "Rakarth Flesh":            "#A09080",
    "Retributor Armour":        "#C89040",
    "Rhinox Hide":              "#3A1A0A",
    "Screamer Pink":            "#B03060",
    "Screaming Bell":           "#8A4A10",
    "Skavenblight Dinge":       "#5A4A3A",
    "Sons of Horus Green":      "#2A5A4A",
    "Steel Legion Drab":        "#7A6A3A",
    "Stormvermin Fur":          "#6A5A4A",
    "The Fang":                 "#3A5A6A",
    "Thousand Sons Blue":       "#0A5A8A",
    "Vulkan Green":             "#0A3A1A",
    "Waaagh! Flesh":            "#2A5A1A",
    "Warplock Bronze":          "#4A3A1A",
    "Word Bearers Red":         "#5A0A0A",
    "Wraithbone":               "#E8D8B0",
    "XV-88":                    "#7A5A20",
    "Zandri Dust":              "#9A8A5A",
    # LAYER
    "Administratum Grey":       "#8A8A8A",
    "Ahriman Blue":             "#0A6A8A",
    "Alaitoc Blue":             "#1A4A8A",
    "Altdorf Guard Blue":       "#1A3A9A",
    "Auric Armour Gold":        "#C8A030",
    "Baharroth Blue":           "#5A9ACA",
    "Balor Brown":              "#8A5A10",
    "Bestigor Flesh":           "#C08040",
    "Bloodreaver Flesh":        "#C07060",
    "Brass Scorpion":           "#8A5A1A",
    "Cadian Fleshtone":         "#C89070",
    "Calgar Blue":              "#3A6AB0",
    "Changeling Pink":          "#E060A0",
    "Deathclaw Brown":          "#A06040",
    "Dechala Lilac":            "#C090C0",
    "Dorn Yellow":              "#F0C820",
    "Elysian Green":            "#5A8A3A",
    "Emperor's Children":       "#D040A0",
    "Evil Sunz Scarlet":        "#C01020",
    "Fenrisian Grey":           "#6A8AAA",
    "Fire Dragon Bright":       "#E06010",
    "Flash Gitz Yellow":        "#F8D000",
    "Flayed One Flesh":         "#E0C09A",
    "Fulgrim Pink":             "#F080C0",
    "Gauss Blaster Green":      "#60E090",
    "Genestealer Purple":       "#8040A0",
    "Gorthor Brown":            "#6A4A2A",
    "Hashut Copper":            "#A06030",
    "Hoeth Blue":               "#4A7ABA",
    "Ironbreaker":              "#8A8A9A",
    "Kabalite Green":           "#0A6A4A",
    "Karak Stone":              "#A08A5A",
    "Kislev Flesh":             "#D0A880",
    "Liberator Gold":           "#D0A830",
    "Loren Forest":             "#4A6A2A",
    "Lucius Lilac":             "#C0A0D0",
    "Lugganath Orange":         "#E08040",
    "Moot Green":               "#60C020",
    "Nurgling Green":           "#8AAA5A",
    "Ogryn Camo":               "#8A9A5A",
    "Pallid Wych Flesh":        "#E0D0C0",
    "Phoenix Orange":           "#E07020",
    "Pink Horror":              "#C04080",
    "Russ Grey":                "#5A7A8A",
    "Runefang Steel":           "#A0A0B0",
    "Screaming Skull":          "#D0C090",
    "Skarsnik Green":           "#4A8A4A",
    "Skink Blue":               "#2A7AAA",
    "Skrag Brown":              "#8A4A10",
    "Sotek Green":              "#1A7A7A",
    "Squig Orange":             "#D04010",
    "Stormhost Silver":         "#C0C0D0",
    "Straken Green":            "#3A6A2A",
    "Sycorax Bronze":           "#9A6A30",
    "Sybarite Green":           "#2A8A5A",
    "Tau Light Ochre":          "#C0901A",
    "Temple Guard Blue":        "#1A9090",
    "Thunderhawk Blue":         "#2A5A6A",
    "Troll Slayer Orange":      "#E06000",
    "Ulthuan Grey":             "#D0DADA",
    "Ungor Flesh":              "#C0A070",
    "Ushabti Bone":             "#C0A860",
    "Warboss Green":            "#4A8A2A",
    "Wazdakka Red":             "#A01A1A",
    "White Scar":               "#F8F8F8",
    "Wych Flesh":               "#E0B090",
    "Xereus Purple":            "#5A0A7A",
    "Yriel Yellow":             "#F8C000",
    "Zephyr Grey":              "#9AAABA",
    # SHADE
    "Agrax Earthshade":         "#5A3A10",
    "Athonian Camoshade":       "#3A4A20",
    "Biel-Tan Green":           "#1A4A2A",
    "Carroburg Crimson":        "#7A1A3A",
    "Casandora Yellow":         "#D0A000",
    "Coelia Greenshade":        "#1A4A4A",
    "Drakenhof Nightshade":     "#1A2A5A",
    "Druchii Violet":           "#4A1A5A",
    "Fuegan Orange":            "#C04010",
    "Kroak Green":              "#3A6A3A",
    "Mortarion Grime":          "#6A7A3A",
    "Nuln Oil":                 "#1A1A1A",
    "Reikland Fleshshade":      "#8A4A2A",
    "Seraphim Sepia":           "#7A5020",
    "Targor Rageshade":         "#6A2A1A",
    "Tyran Blue":               "#1A3A8A",
    "Wyldwood Shade":           "#4A3A1A",
    # DRY
    "Astorath Red":             "#C03020",
    "Banshee Brown":            "#C0A060",
    "Eerie Green":              "#60A060",
    "Golgfag Brown":            "#8A5A20",
    "Hexos Palesun":            "#F0E060",
    "Imrik Blue":               "#4A80C0",
    "Longbeard Grey":           "#B0B0B0",
    "Lucius the Eternal":       "#D0C0E0",
    "Necron Compound":          "#8A8A9A",
    "Praxeti White":            "#F0F0F0",
    "Ryza Rust":                "#C04A00",
    "Sigmarite":                "#C09030",
    "Stormfang":                "#5A7A9A",
    "Sylvaneth Bark":           "#5A4A2A",
    "Terminatus Stone":         "#C0B080",
    "Tyrant Skull":             "#D0C090",
    "Underhive Ash":            "#A0A090",
    "Verminlord Hide":          "#7A6A4A",
    # CONTRAST
    "Aethermatic Blue":         "#3AB0E0",
    "Aggaros Dunes":            "#C0A050",
    "Akhelian Green":           "#00A080",
    "Apothecary White":         "#E0E8E8",
    "Basilicanum Grey":         "#4A4A5A",
    "Black Templar":            "#1A1A2A",
    "Blood Angels Red":         "#A00010",
    "Creed Camo":               "#4A5A2A",
    "Cygor Brown":              "#5A3A1A",
    "Dark Angels Green":        "#0A3A1A",
    "Flesh Tearers Red":        "#8A0010",
    "Fyreslayer Flesh":         "#D07040",
    "Gore-Grunta Fur":          "#6A4A2A",
    "Gryph-Charger Grey":       "#6A7A8A",
    "Gryph-Hound Orange":       "#D06010",
    "Guilliman Flesh":          "#D0907A",
    "Iyanden Yellow":           "#E0C020",
    "Leviadon Blue":            "#0A2A6A",
    "Leviathan Purple":         "#4A0A6A",
    "Magos Purple":             "#6A1A8A",
    "Militarum Green":          "#3A4A1A",
    "Nazdreg Yellow":           "#D0A000",
    "Nighthaunt Gloom":         "#3AB0A0",
    "Ork Flesh":                "#5A8A2A",
    "Plaguebearer Flesh":       "#8A9A4A",
    "Shyish Purple":            "#5A1A7A",
    "Skeleton Horde":           "#C0A850",
    "Snakebite Leather":        "#8A5A1A",
    "Talassar Blue":            "#1A4A8A",
    "Terradon Turquoise":       "#1A8A7A",
    "Ultramarines Blue":        "#1A3A9A",
    "Volupus Pink":             "#C03070",
    "Wyldwood":                 "#4A3A1A",
    # TECHNICAL
    "Agrellan Earth":           "#8A6A3A",
    "Astrogranite":             "#5A5A6A",
    "Astrogranite Debris":      "#5A5A6A",
    "Blood for the Blood God":  "#8A0000",
    "Lahmian Medium":           "#F0F0F0",
    "Liquid Green Stuff":       "#3A7A3A",
    "Martian Ironearth":        "#8A3A1A",
    "Mordant Earth":            "#3A2A1A",
    "Nihilakh Oxide":           "#3AAA8A",
    "Nurgle's Rot":             "#6A8A1A",
    "Soulstone Blue":           "#1A3ACA",
    "Typhus Corrosion":         "#3A3A1A",
    "Valhallan Blizzard":       "#E0F0F8",
    # PRIMER
    "Chaos Black":              "#0A0A0A",
}

# ============================================================
# LISTA FARB
# ============================================================

PAINTS = [
    # BASE
    ("Abaddon Black", "Base"), ("Averland Sunset", "Base"), ("Balthasar Gold", "Base"),
    ("Baneblade Brown", "Base"), ("Bugman's Glow", "Base"), ("Caledor Sky", "Base"),
    ("Caliban Green", "Base"), ("Castellan Green", "Base"), ("Catachan Fleshtone", "Base"),
    ("Celestra Grey", "Base"), ("Corax White", "Base"), ("Daemonette Hide", "Base"),
    ("Dark Reaper", "Base"), ("Death Guard Green", "Base"), ("Deathworld Forest", "Base"),
    ("Dryad Bark", "Base"), ("Eshin Grey", "Base"), ("Gal Vorbak Red", "Base"),
    ("Grey Seer", "Base"), ("Incubi Darkness", "Base"), ("Iron Hands Steel", "Base"),
    ("Iron Warriors", "Base"), ("Jokaero Orange", "Base"), ("Kantor Blue", "Base"),
    ("Khorne Red", "Base"), ("Leadbelcher", "Base"), ("Macragge Blue", "Base"),
    ("Mechanicus Standard Grey", "Base"), ("Mephiston Red", "Base"), ("Mournfang Brown", "Base"),
    ("Naggaroth Night", "Base"), ("Nocturne Green", "Base"), ("Orruk Flesh", "Base"),
    ("Phoenician Purple", "Base"), ("Rakarth Flesh", "Base"), ("Retributor Armour", "Base"),
    ("Rhinox Hide", "Base"), ("Screamer Pink", "Base"), ("Screaming Bell", "Base"),
    ("Skavenblight Dinge", "Base"), ("Sons of Horus Green", "Base"), ("Steel Legion Drab", "Base"),
    ("Stormvermin Fur", "Base"), ("The Fang", "Base"), ("Thousand Sons Blue", "Base"),
    ("Vulkan Green", "Base"), ("Waaagh! Flesh", "Base"), ("Warplock Bronze", "Base"),
    ("Word Bearers Red", "Base"), ("Wraithbone", "Base"), ("XV-88", "Base"),
    ("Zandri Dust", "Base"),
    # LAYER
    ("Administratum Grey", "Layer"), ("Ahriman Blue", "Layer"), ("Alaitoc Blue", "Layer"),
    ("Altdorf Guard Blue", "Layer"), ("Auric Armour Gold", "Layer"), ("Baharroth Blue", "Layer"),
    ("Balor Brown", "Layer"), ("Bestigor Flesh", "Layer"), ("Bloodreaver Flesh", "Layer"),
    ("Brass Scorpion", "Layer"), ("Cadian Fleshtone", "Layer"), ("Calgar Blue", "Layer"),
    ("Changeling Pink", "Layer"), ("Deathclaw Brown", "Layer"), ("Dechala Lilac", "Layer"),
    ("Dorn Yellow", "Layer"), ("Elysian Green", "Layer"), ("Emperor's Children", "Layer"),
    ("Evil Sunz Scarlet", "Layer"), ("Fenrisian Grey", "Layer"), ("Fire Dragon Bright", "Layer"),
    ("Flash Gitz Yellow", "Layer"), ("Flayed One Flesh", "Layer"), ("Fulgrim Pink", "Layer"),
    ("Gauss Blaster Green", "Layer"), ("Genestealer Purple", "Layer"), ("Gorthor Brown", "Layer"),
    ("Hashut Copper", "Layer"), ("Hoeth Blue", "Layer"), ("Ironbreaker", "Layer"),
    ("Kabalite Green", "Layer"), ("Karak Stone", "Layer"), ("Kislev Flesh", "Layer"),
    ("Liberator Gold", "Layer"), ("Loren Forest", "Layer"), ("Lucius Lilac", "Layer"),
    ("Lugganath Orange", "Layer"), ("Moot Green", "Layer"), ("Nurgling Green", "Layer"),
    ("Ogryn Camo", "Layer"), ("Pallid Wych Flesh", "Layer"), ("Phoenix Orange", "Layer"),
    ("Pink Horror", "Layer"), ("Russ Grey", "Layer"), ("Runefang Steel", "Layer"),
    ("Screaming Skull", "Layer"), ("Skarsnik Green", "Layer"), ("Skink Blue", "Layer"),
    ("Skrag Brown", "Layer"), ("Sotek Green", "Layer"), ("Squig Orange", "Layer"),
    ("Stormhost Silver", "Layer"), ("Straken Green", "Layer"), ("Sycorax Bronze", "Layer"),
    ("Sybarite Green", "Layer"), ("Tau Light Ochre", "Layer"), ("Temple Guard Blue", "Layer"),
    ("Thunderhawk Blue", "Layer"), ("Troll Slayer Orange", "Layer"), ("Ulthuan Grey", "Layer"),
    ("Ungor Flesh", "Layer"), ("Ushabti Bone", "Layer"), ("Warboss Green", "Layer"),
    ("Wazdakka Red", "Layer"), ("White Scar", "Layer"), ("Wych Flesh", "Layer"),
    ("Xereus Purple", "Layer"), ("Yriel Yellow", "Layer"), ("Zephyr Grey", "Layer"),
    # SHADE
    ("Agrax Earthshade", "Shade"), ("Athonian Camoshade", "Shade"), ("Biel-Tan Green", "Shade"),
    ("Carroburg Crimson", "Shade"), ("Casandora Yellow", "Shade"), ("Coelia Greenshade", "Shade"),
    ("Drakenhof Nightshade", "Shade"), ("Druchii Violet", "Shade"), ("Fuegan Orange", "Shade"),
    ("Kroak Green", "Shade"), ("Mortarion Grime", "Shade"), ("Nuln Oil", "Shade"),
    ("Reikland Fleshshade", "Shade"), ("Seraphim Sepia", "Shade"), ("Targor Rageshade", "Shade"),
    ("Tyran Blue", "Shade"), ("Wyldwood Shade", "Shade"),
    # DRY
    ("Astorath Red", "Dry"), ("Banshee Brown", "Dry"), ("Eerie Green", "Dry"),
    ("Golgfag Brown", "Dry"), ("Hexos Palesun", "Dry"), ("Imrik Blue", "Dry"),
    ("Longbeard Grey", "Dry"), ("Lucius the Eternal", "Dry"), ("Necron Compound", "Dry"),
    ("Praxeti White", "Dry"), ("Ryza Rust", "Dry"), ("Sigmarite", "Dry"),
    ("Stormfang", "Dry"), ("Sylvaneth Bark", "Dry"), ("Terminatus Stone", "Dry"),
    ("Tyrant Skull", "Dry"), ("Underhive Ash", "Dry"), ("Verminlord Hide", "Dry"),
    # CONTRAST
    ("Aethermatic Blue", "Contrast"), ("Aggaros Dunes", "Contrast"),
    ("Akhelian Green", "Contrast"), ("Apothecary White", "Contrast"),
    ("Basilicanum Grey", "Contrast"), ("Black Templar", "Contrast"),
    ("Blood Angels Red", "Contrast"), ("Creed Camo", "Contrast"),
    ("Cygor Brown", "Contrast"), ("Dark Angels Green", "Contrast"),
    ("Flesh Tearers Red", "Contrast"), ("Fyreslayer Flesh", "Contrast"),
    ("Gore-Grunta Fur", "Contrast"), ("Gryph-Charger Grey", "Contrast"),
    ("Gryph-Hound Orange", "Contrast"), ("Guilliman Flesh", "Contrast"),
    ("Iyanden Yellow", "Contrast"), ("Leviadon Blue", "Contrast"),
    ("Leviathan Purple", "Contrast"), ("Magos Purple", "Contrast"),
    ("Militarum Green", "Contrast"), ("Nazdreg Yellow", "Contrast"),
    ("Nighthaunt Gloom", "Contrast"), ("Ork Flesh", "Contrast"),
    ("Plaguebearer Flesh", "Contrast"), ("Shyish Purple", "Contrast"),
    ("Skeleton Horde", "Contrast"), ("Snakebite Leather", "Contrast"),
    ("Talassar Blue", "Contrast"), ("Terradon Turquoise", "Contrast"),
    ("Ultramarines Blue", "Contrast"), ("Volupus Pink", "Contrast"),
    ("Wyldwood", "Contrast"),
    # TECHNICAL
    ("Agrellan Earth", "Technical"), ("Astrogranite", "Technical"),
    ("Astrogranite Debris", "Technical"), ("Blood for the Blood God", "Technical"),
    ("Lahmian Medium", "Technical"), ("Liquid Green Stuff", "Technical"),
    ("Martian Ironearth", "Technical"), ("Mordant Earth", "Technical"),
    ("Nihilakh Oxide", "Technical"), ("Nurgle's Rot", "Technical"),
    ("Soulstone Blue", "Technical"), ("Typhus Corrosion", "Technical"),
    ("Valhallan Blizzard", "Technical"),
    # PRIMER
    ("Chaos Black", "Primer"), ("Corax White", "Primer"), ("Grey Seer", "Primer"),
    ("Leadbelcher", "Primer"), ("Macragge Blue", "Primer"),
    ("Wraithbone", "Primer"), ("Zandri Dust", "Primer"),
]

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 55)
    print("  CITADEL PAINT LIBRARY — SETUP DATABASE")
    print("=" * 55)
    print()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🗑  Usunięto stary plik PaintsReq.db")

    print("🔍 Pobieram oficjalne kolory Citadel...\n")
    hex_map = fetch_hex_from_warpaint_api()
    if len(hex_map) < 50:
        print("   Mało wyników — próbuję backup źródło...\n")
        hex_map.update(fetch_hex_from_bolter())
    if len(hex_map) < 10:
        print("⚠️  Brak połączenia — używam kolorów fallback\n")
        hex_map = FALLBACK_COLORS

    print("\n🔍 Walidacja kolorów...")
    for name in list(hex_map.keys()):
        if not validate_hex(hex_map[name]):
            hex_map[name] = FALLBACK_COLORS.get(name, "#888888")
    print("✅ Walidacja zakończona\n")

    matched   = sum(1 for name, _ in PAINTS if name in hex_map)
    unmatched = len(PAINTS) - matched
    print(f"📊 Dopasowano: {matched}/{len(PAINTS)} farb")
    print(f"   Fallback:   {unmatched} farb\n")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE paints
                 (id INTEGER PRIMARY KEY, name TEXT, category TEXT, image BLOB)''')
    conn.commit()
    print("✅ Nowa baza utworzona\n")

    print("🎨 Generuję kafelki...\n")
    print("=" * 55)

    for i, (name, category) in enumerate(PAINTS, 1):
        raw_hex   = hex_map.get(name, FALLBACK_COLORS.get(name, "#888888"))
        hex_color = safe_hex(name, raw_hex)
        source    = "API" if name in hex_map else ("fallback" if name in FALLBACK_COLORS else "default")
        print(f"[{i:>3}/{len(PAINTS)}] {name:<40} {hex_color}  ({source})")
        blob = make_paint_tile(name, category, hex_color)
        c.execute("INSERT INTO paints (name, category, image) VALUES (?, ?, ?)",
                  (name, category, blob))

    conn.commit()
    conn.close()

    print("\n" + "=" * 55)
    print(f"✅ Gotowe! {len(PAINTS)} farb zapisanych w PaintsReq.db")
    print("   Uruchom app.py")
    print("=" * 55)

if __name__ == "__main__":
    main()
