"""Generate slide figures as SVG.

Dark ground to match the app. Import straight into Keynote or PowerPoint; for
Google Slides, open in a browser and export a PNG.

    python3 app/scripts/make_figures.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "figures"

BG      = "#060a1a"
PANEL   = "#0e1430"
PANEL_2 = "#161e42"
LINE    = "#2c3872"
FG      = "#e9edff"
MUTED   = "#a2acd8"
FAINT   = "#6a75a6"

GREEN  = "#67e3c4"
BLUE   = "#90aaff"
YELLOW = "#ffd76e"
PINK   = "#ff9dc0"
VIOLET = "#b9a3ff"

FONT = "Fira Sans, Segoe UI, Helvetica, Arial, sans-serif"
MONO = "Fira Code, SF Mono, Menlo, monospace"


def head(w, h, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
        f'height="{h}" font-family="{FONT}" role="img" aria-label="{title}">\n'
        f"  <title>{title}</title>\n"
        f'  <rect width="{w}" height="{h}" fill="{BG}"/>\n'
    )


def box(x, y, w, h, fill=PANEL, stroke=LINE, sw=1, step=6):
    """A rectangle with pixel-stepped corners."""
    s = step
    pts = [
        (x, y + 2 * s), (x + s, y + 2 * s), (x + s, y + s), (x + 2 * s, y + s), (x + 2 * s, y),
        (x + w - 2 * s, y), (x + w - 2 * s, y + s), (x + w - s, y + s), (x + w - s, y + 2 * s),
        (x + w, y + 2 * s),
        (x + w, y + h - 2 * s), (x + w - s, y + h - 2 * s), (x + w - s, y + h - s),
        (x + w - 2 * s, y + h - s), (x + w - 2 * s, y + h),
        (x + 2 * s, y + h), (x + 2 * s, y + h - s), (x + s, y + h - s), (x + s, y + h - 2 * s),
        (x, y + h - 2 * s),
    ]
    d = " ".join(f"{px},{py}" for px, py in pts)
    return f'  <polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>\n'


def text(x, y, s, size=15, fill=FG, weight="400", anchor="start", family=None, spacing=None):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    fam = f' font-family="{family}"' if family else ""
    return (f'  <text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{fam}{ls}>{s}</text>\n')


def arrow(x1, y1, x2, y2, colour=LINE, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
            f'stroke-width="2"{d} marker-end="url(#a)"/>\n')


def defs(colour=LINE):
    return (f'  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
            f'markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{colour}"/>'
            f"</marker></defs>\n")


# ---------------------------------------------------------------- 1. pipeline

def architecture():
    W, H = 1600, 760
    s = head(W, H, "CloudCleaner architecture") + defs()

    s += text(56, 62, "How CloudCleaner works", 30, FG, "700")
    s += text(56, 92, "Ten LangGraph nodes. Two gates stand between a verdict and an "
                      "irreversible action.", 16, MUTED)

    nodes = [
        ("DETECT",       "inventory + true cost",     BLUE),
        ("INVESTIGATE",  "CloudWatch + GitHub",       BLUE),
        ("ASSESS",       "LLM verdict, typed",        VIOLET),
        ("PLAN",         "ordered teardown",          GREEN),
        ("POLICY CHECK", "risk score, allow/block",   YELLOW),
        ("APPROVAL",     "human types the id",        PINK),
        ("EXECUTE",      "boto3, dry run default",    PINK),
        ("VERIFY",       "poll actual state",         BLUE),
        ("RECORD",       "history + memory",          VIOLET),
    ]

    x, y, bw, bh = 56, 150, 156, 96
    for i, (name, sub, colour) in enumerate(nodes):
        cx = x + i * (bw + 12)
        s += box(cx, y, bw, bh)
        s += f'  <rect x="{cx}" y="{y}" width="{bw}" height="4" fill="{colour}"/>\n'
        s += text(cx + bw / 2, y + 40, name, 13, colour, "700", "middle", spacing="0.06em")
        # wrap the caption
        words, line, lines = sub.split(), "", []
        for wd in words:
            if len(line + wd) > 18:
                lines.append(line.strip()); line = ""
            line += wd + " "
        lines.append(line.strip())
        for j, ln in enumerate(lines[:2]):
            s += text(cx + bw / 2, y + 62 + j * 15, ln, 11.5, FAINT, "400", "middle")
        if i < len(nodes) - 1:
            s += arrow(cx + bw + 1, y + bh / 2, cx + bw + 10, y + bh / 2)

    # the two gates
    s += f'  <rect x="{56 + 3*(bw+12) - 8}" y="{y - 14}" width="{2*bw + 12 + 16}" height="{bh + 28}" fill="none" stroke="{GREEN}" stroke-width="1.5" stroke-dasharray="5 4" rx="4"/>\n'
    s += text(56 + 3 * (bw + 12) + bw + 6, y - 24, "WHAT, AND IN WHAT ORDER  ·  WHETHER IT IS ALLOWED",
              12, GREEN, "700", "middle", spacing="0.05em")

    # supporting layers
    ly = 330
    layers = [
        ("TOOLS", "inventory · metrics · cost · volumes · addresses · actions · github", BLUE),
        ("POLICY", "risk scoring · safety rules · dependency ordering (Kahn)", GREEN),
        ("EVIDENCE", "typed reasoning trail, one event per decision", VIOLET),
        ("STORAGE", "SQLite: runs · decisions · events · snapshots · checkpoints", YELLOW),
    ]
    for i, (name, sub, colour) in enumerate(layers):
        by = ly + i * 74
        s += box(56, by, W - 112, 60)
        s += f'  <rect x="56" y="{by}" width="4" height="60" fill="{colour}"/>\n'
        s += text(84, by + 26, name, 13, colour, "700", spacing="0.06em")
        s += text(84, by + 46, sub, 14, MUTED)

    s += text(56, H - 34, "Nothing is executed without a human typing the resource id. "
                          "Dry run is the default.", 14, FAINT)
    return s + "</svg>\n"


# ------------------------------------------------------- 2. teardown ordering

def teardown():
    W, H = 1500, 720
    s = head(W, H, "Dependency-ordered teardown") + defs()

    s += text(56, 62, "Retiring one instance is five operations", 30, FG, "700")
    s += text(56, 92, "AWS refuses dependent deletions one blocker at a time. "
                      "CloudCleaner resolves the graph first.", 16, MUTED)

    # left: the tangle
    s += text(56, 152, "WHAT IT IS ENTANGLED WITH", 12, FAINT, "700", spacing="0.07em")
    ent = [
        ("i-0abc123", "t3.micro, stopped", 300, 210, PINK),
        ("eipalloc-0f2", "public IPv4, associated", 100, 330, YELLOW),
        ("vol-0a9b8c7", "16 GB, DeleteOnTermination=false", 300, 430, GREEN),
    ]
    for name, sub, cx, cy, colour in ent:
        s += box(cx - 110, cy - 34, 220, 68, PANEL_2)
        s += text(cx, cy - 8, name, 14, colour, "700", "middle", MONO)
        s += text(cx, cy + 14, sub, 11, FAINT, "400", "middle")
    s += f'  <line x1="300" y1="244" x2="300" y2="396" stroke="{LINE}" stroke-width="2"/>\n'
    s += f'  <line x1="210" y1="285" x2="300" y2="285" stroke="{LINE}" stroke-width="2"/>\n'
    s += text(300, 480, "three resources, two constraints", 12, FAINT, "400", "middle")

    # right: the sequence
    s += text(700, 152, "THE ORDER THAT ACTUALLY WORKS", 12, GREEN, "700", spacing="0.07em")
    steps = [
        ("1", "disassociate_address", "eipassoc-0c1b2a3", "", False),
        ("2", "release_address", "eipalloc-0f2e3d4", "$3.65", True),
        ("3", "snapshot_volume", "vol-0a9b8c7d6", "", False),
        ("4", "terminate_instance", "i-0abc123def456789", "$4.93", True),
        ("5", "delete_volume", "vol-0a9b8c7d6", "$1.28", True),
    ]
    for i, (n, act, res, save, irr) in enumerate(steps):
        by = 186 + i * 74
        s += box(700, by, 740, 60, PANEL_2)
        s += text(726, by + 37, n, 17, FAINT, "700")
        if irr:
            s += f'  <rect x="748" y="{by + 24}" width="10" height="10" fill="{PINK}"/>\n'
        s += text(772, by + 30, act, 15, FG, "600", family=MONO)
        s += text(772, by + 47, res, 11.5, FAINT, "400", family=MONO)
        if save:
            s += text(1412, by + 38, save, 16, GREEN, "700", "end")
        if i < len(steps) - 1:
            s += arrow(1070, by + 61, 1070, by + 72)

    s += f'  <rect x="700" y="{186 + 5*74 + 6}" width="740" height="3" fill="{LINE}"/>\n'
    s += text(700, 186 + 5 * 74 + 42, "3 of 5 steps cannot be undone", 14, PINK)
    s += text(1440, 186 + 5 * 74 + 42, "$9.86/mo", 22, GREEN, "700", "end")
    return s + "</svg>\n"


# ------------------------------------------------------------ 3. safety gates

def gates():
    W, H = 1440, 620
    s = head(W, H, "Three gates before anything is destroyed") + defs()

    s += text(56, 62, "Three gates before anything is destroyed", 30, FG, "700")
    s += text(56, 92, "A human can overrule the model. Nobody overrules the policy.", 16, MUTED)

    cols = [
        ("1", "THE MODEL ADVISES", VIOLET,
         ["Reads only the evidence", "Returns a typed verdict",
          "Can be wrong, and can be", "overruled by a human"]),
        ("2", "THE POLICY DECIDES", GREEN,
         ["Plain Python, no prompt", "Protected environments,", "tags, age, risk score",
          "Cannot be argued with"]),
        ("3", "A HUMAN COMMITS", PINK,
         ["Types the resource id", "exactly — never y/n", "Sees the ordered plan",
          "and what cannot be undone"]),
    ]
    for i, (n, title, colour, lines) in enumerate(cols):
        x = 56 + i * 448
        s += box(x, 150, 416, 300)
        s += f'  <rect x="{x}" y="150" width="416" height="4" fill="{colour}"/>\n'
        s += text(x + 30, 206, n, 34, colour, "700")
        s += text(x + 30, 244, title, 14, colour, "700", spacing="0.06em")
        for j, ln in enumerate(lines):
            s += text(x + 30, 288 + j * 30, ln, 15.5, MUTED)
        if i < 2:
            s += arrow(x + 418, 300, x + 440, 300)

    s += box(56, 486, W - 112, 78, PANEL_2)
    s += text(88, 520, "force_plan", 15, YELLOW, "700", family=MONO)
    s += text(88, 545, "A human who disagrees with the model can force a plan — and the policy "
                       "still refuses it on a protected resource.", 14.5, MUTED)
    return s + "</svg>\n"


# --------------------------------------------------------- 4. stopped is free

def stopped():
    W, H = 1412, 620
    s = head(W, H, "Stopping an instance does not stop the bill")

    s += text(56, 62, "Stopping an instance does not stop the bill", 30, FG, "700")
    s += text(56, 92, "Stop releases the compute. Storage and the public address keep "
                      "charging, indefinitely.", 16, MUTED)

    def stack(x, title, rows, total, colour):
        s2 = text(x + 190, 152, title, 14, colour, "700", "middle", spacing="0.06em")
        y = 180
        unit = 5.4
        for label, amount, active in rows:
            h = max(int(amount * unit), 26)
            fill = colour if active else "#1b2450"
            s2_text = FG if active else FAINT
            s2 += box(x, y, 380, h, fill if active else PANEL_2, LINE, 1, 5)
            s2 += text(x + 22, y + h / 2 + 6, label, 14.5,
                       "#0b1020" if active else s2_text, "600")
            s2 += text(x + 358, y + h / 2 + 6, f"${amount:.2f}", 15,
                       "#0b1020" if active else s2_text, "700", "end")
            y += h + 8
        s2 += f'  <rect x="{x}" y="{y + 6}" width="380" height="3" fill="{LINE}"/>\n'
        s2 += text(x, y + 44, "billed monthly", 13, FAINT)
        s2 += text(x + 380, y + 46, f"${total:.2f}", 24, colour, "700", "end")
        return s2

    s += stack(56, "WHILE RUNNING",
               [("compute  t3.micro", 7.59, True), ("storage  16 GB gp3", 1.28, True),
                ("public IPv4", 3.65, True)], 12.52, BLUE)

    s += stack(516, "AFTER PRESSING STOP",
               [("compute  released", 0.00, False), ("storage  16 GB gp3", 1.28, True),
                ("public IPv4", 3.65, True)], 4.93, PINK)

    s += stack(976, "AFTER CLOUDCLEANER",
               [("compute  terminated", 0.00, False), ("storage  deleted", 0.00, False),
                ("address  released", 0.00, False)], 0.00, GREEN)

    s += text(56, H - 40, "The middle column is the bill nobody expects. "
                          "CloudCleaner finds it, and works out the order to dismantle it in.",
              15, MUTED)
    return s + "</svg>\n"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (
        ("architecture", architecture),
        ("teardown-order", teardown),
        ("safety-gates", gates),
        ("stopped-is-not-free", stopped),
    ):
        path = OUT / f"fig-{name}.svg"
        path.write_text(fn())
        print(f"  {path.name:28} {path.stat().st_size // 1024:>4} KB")
