"""Tiny dependency-free PDF writer for career reports (A4, Helvetica, text + colored blocks)."""

W, H, M = 595, 842, 48  # A4 points, margin
BLUE, YELLOW, GREEN, INK, GREY = (0.16, 0.36, 0.92), (1.0, 0.78, 0.2), (0.09, 0.62, 0.36), (0.07, 0.07, 0.09), (0.45, 0.47, 0.5)

_SUBS = {"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "✓": "+", "✗": "x", "≥": ">=", "≤": "<=",
         "→": "->", "↗": "", "↘": "", "•": "-", "€": "EUR", "×": "x"}


def _clean(t):
    t = "".join(_SUBS.get(c, c) for c in str(t))
    t = t.encode("latin-1", "replace").decode("latin-1")
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text, size, width):
    max_chars = max(10, int(width / (size * 0.5)))
    out = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split():
            if len(line) + len(word) + 1 > max_chars:
                out.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        out.append(line)
    return out


class Doc:
    def __init__(self):
        self.pages, self.ops, self.y = [], [], H - M

    def _need(self, h):
        if self.y - h < M:
            self.pages.append(self.ops)
            self.ops, self.y = [], H - M

    def text(self, t, size=10, bold=False, color=INK, indent=0, gap=3):
        for line in _wrap(t, size, W - 2 * M - indent):
            self._need(size + gap)
            self.y -= size + gap
            self.ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf {color[0]} {color[1]} {color[2]} rg "
                            f"{M + indent} {self.y:.1f} Td ({_clean(line)}) Tj ET")

    def block(self, title, value, sub, color):
        """Rounded-ish colored card with a big value."""
        self._need(70)
        y0 = self.y - 64
        self.ops.append(f"{color[0]} {color[1]} {color[2]} rg {M} {y0:.1f} {W - 2 * M} 60 re f")
        tc = "1 1 1" if color != YELLOW else "0.07 0.07 0.09"
        self.ops.append(f"BT /F1 9 Tf {tc} rg {M + 14} {y0 + 44:.1f} Td ({_clean(title)}) Tj ET")
        self.ops.append(f"BT /F2 20 Tf {tc} rg {M + 14} {y0 + 20:.1f} Td ({_clean(value)}) Tj ET")
        self.ops.append(f"BT /F1 9 Tf {tc} rg {M + 14} {y0 + 7:.1f} Td ({_clean(sub)}) Tj ET")
        self.y = y0 - 10

    def space(self, h=8):
        self.y -= h

    def bytes(self):
        pages = self.pages + [self.ops]
        objs = ["<< /Type /Catalog /Pages 2 0 R >>", None,
                "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
        kids = []
        for ops in pages:
            stream = "\n".join(ops).encode("latin-1")
            objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
            objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Contents {len(objs)} 0 R "
                        f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>")
            kids.append(f"{len(objs)} 0 R")
        objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
        out, offs = bytearray(b"%PDF-1.4\n"), []
        for i, o in enumerate(objs, 1):
            offs.append(len(out))
            body = o if isinstance(o, bytes) else o.encode("latin-1")
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
        return bytes(out)


def money(n):
    return "$" + f"{round(n):,}"


def render_report(rep, user_name):
    d = Doc()
    d.text("tirek - Career report", 22, True, BLUE, gap=6)
    d.text(f"{user_name} - {rep.get('createdAt', '')[:10]} - {rep.get('currentRole')} -> {rep.get('targetRole')}", 10, color=GREY)
    d.space(10)
    v = rep.get("value") or {}
    if v.get("min"):
        d.block("YOUR MARKET VALUE NOW (per year)", f"{money(v['min'])} - {money(v['max'])}",
                f"median {money(v['median'])} - based on {v['n']} real US postings you match", GREEN)
    r = rep["risk"]
    d.block("CAREER RISK SCORE", f"{r['score']}/100 - {r['level']}", r.get("formula", ""), YELLOW)
    d.text("What affects the risk", 13, True, gap=6)
    for f in r["factors"]:
        d.text(f"{round(f['weight'] * 100)}%  {f['name']}  (value {f['value']}, {f['contribution']} pts)", 10, True)
        if f.get("explanation"):
            d.text(f["explanation"], 9, color=GREY, indent=12)
    d.space()
    d.text("Skills", 13, True, gap=6)
    for label, key in (("Growing", "growing"), ("Stable", "stable"), ("Declining", "declining")):
        items = ", ".join(x["skill"] for x in rep.get(key, [])) or "-"
        d.text(f"{label}: {items}", 10)
    d.space()
    d.text("Alternative directions", 13, True, gap=6)
    for a in rep.get("alternatives", []):
        sal = a.get("salary")
        d.text(f"{a['role']} - {a['match']}% skill match - {a.get('time', '')}"
               + (f" - median {money(sal['median'])}/yr" if sal else ""), 10, True)
        if a.get("missingSkills"):
            d.text("Missing: " + ", ".join(a["missingSkills"]), 9, color=GREY, indent=12)
    d.space()
    d.text("90-day protection plan", 13, True, gap=6)
    for p in rep.get("protectionPlan", []):
        d.text(f"{p['period']}: {p['focus']}", 10, True)
        d.text(f"{p['actions']}  Result: {p['result']}", 9, color=GREY, indent=12)
    d.space()
    d.text("Top vacancies", 13, True, gap=6)
    for j in rep.get("vacancies", [])[:8]:
        sy = j.get("salaryYear")
        d.text(f"{j['title']} - {j['company']}" + (f" - {money(sy['min'])}-{money(sy['max'])}/yr" if sy else ""), 10, True)
        d.text(f"Fit {j['fit']}% - missing: {', '.join(j['missing'][:5]) or 'none'} - {j['url']}", 8, color=GREY, indent=12)
    d.space(12)
    d.text("Risk score: fixed formula R = 0.3A + 0.25D + 0.25G + 0.2C (demonstration weights). Market value: salary ranges "
           "stated in real postings where you match at least half of the listed skills. Not financial or hiring advice.", 8, color=GREY)
    return d.bytes()
