# Employment Verification Letter

A reusable employment verification letter, addressed "To Whom It May Concern"
and signed by a company officer. One page.

## Two brands — pick one

The letter is parameterised, because two identities are in play:

```bash
node make_letter.js               # Loomi, Inc. — loomi.ai   (default)
BRAND=loome node make_letter.js   # LOOME Inc.  — loome.com
```

`BRAND` switches the company name, website, email, and the letterhead artwork
together. **`LOOME Inc.` is the brand that actually exists in this repo** — the
logo and palette are transcribed from `src/App.jsx`, the site Vercel deploys.
`Loomi, Inc.` uses a mark designed from scratch, since no loomi.ai asset was
reachable from the build environment.

Note that the site describes LOOME as a consumer deals marketplace, while the
letter's stated title is Investment Banker. Confirm which entity is the actual
employer before sending.

## Files

| File | Purpose |
|---|---|
| `make_letter.js` | Builds the `.docx` for either brand, embedding the head band (docx-js) |
| **LOOME** | |
| `LOOME-Employment-Verification-Letter.docx` / `.pdf` | The letter, LOOME branded |
| `LOOME-Letterhead.pdf` | The sheet, and the logo with its palette |
| `make_loome_letterhead.py` | Redraws the LOOME logo and head band from the `src/App.jsx` spec |
| `loome-band-1.png` | LOOME head band at the letter's 488 pt measure |
| **Loomi** | |
| `Loomi-Employment-Verification-Letter.docx` / `.pdf` | The letter, Loomi branded |
| `Loomi-Letterhead.pdf` | The sheet, and the woven mark studied |
| `DESIGN-PHILOSOPHY.md` | "Woven Signal" — the philosophy the Loomi mark is built on |
| `make_letterhead.py` | Draws the woven mark, wordmark, letterhead and head band |
| `band-1.png` | Loomi head band at the letter's 488 pt measure |
| `loomi-lockup.png` | Loomi mark + wordmark alone, 300 dpi |

## The LOOME logo

Transcribed from the `<Logo/>` component in `src/App.jsx` — `L` + two ring-dots +
`ME`, so the *OO* of LOOME are the marks. Each dot is a wheat ring (`#C8B896`,
r 7.5/18, stroke 2) around a sage centre (`#3DAA6A`, r 3.5/18) with a white glint
at 85%. Palette is the `C` object from the same file: iron `#232F3E`, wheat
`#C8B896`, sage `#3DAA6A`, amber `#E8973A`, teal `#1B8FA8`.

The wordmark is set in Outfit Bold; the app itself uses the browser's default
sans, so this is a deliberate substitution for print.

## The identity

The name carries its own reference: **loomi** contains *loom*. The mark is a plain
weave — four warp threads, four weft, interlacing over and under on the rule that
the weft rides over the warp wherever `(i + j)` is even. Ink crossing ink shows
nothing, so every pass-under is cut with a hairline of ground: the thread visibly
goes behind and comes back.

A single accent thread runs through the ink weave — the signal in the fabric.

Palette is an ink (`#11132B`), a light (`#6D5AE6`), and the paper between them
(`#FBFAF8`). Wordmark is Outfit Bold, tracked −12/1000; annotation is IBM Plex Mono.

## Placeholders to fill in

Everything in `[SQUARE BRACKETS]` must be replaced before the letter is sent:

- `[EMPLOYEE FULL LEGAL NAME]` — as it appears on government ID
- `[START DATE]`, `[BASE SALARY]`, and the other compensation / location fields
- `[REPORTING MANAGER / TITLE]`
- `[OFFICER FULL NAME]` and title — whoever signs
- `[Street Address]`, `[City, State ZIP]`, `[Phone]`, and the email — the
  contact line under the rule, and the footer
- `[his/her/their]` / `[He/She/They]` — pronouns

## Regenerating

The letterhead art first, then the document — `make_letter.js` reads the band PNG.

```bash
pip install reportlab && npm install docx

# Loomi
python3 make_letterhead.py                       # -> Loomi-Letterhead.pdf, band.pdf, lockup.pdf
pdftoppm -png -r 75 band.pdf band                # -> band-1.png (~300 dpi at final size)
node make_letter.js

# LOOME
python3 make_loome_letterhead.py                 # -> LOOME-Letterhead.pdf, loome-band.pdf
pdftoppm -png -r 75 loome-band.pdf loome-band    # -> loome-band-1.png
BRAND=loome node make_letter.js
```

To re-render the PDF (needs LibreOffice **with `libreoffice-writer`** — the base
`libreoffice-core` package cannot open Writer documents):

```bash
soffice --headless --convert-to pdf Loomi-Employment-Verification-Letter.docx
```

Fonts come from the `canvas-design` skill's `canvas-fonts` directory (Outfit,
IBM Plex Mono). Adjust `FONTS` at the top of `make_letterhead.py` if they live
elsewhere.

## Note on the ownership paragraph

The letter includes a short paragraph disclosing that the employee also holds an
ownership interest in the company. This is deliberate — for an owner-employee, an
insurer or lender that later discovers an undisclosed ownership stake may treat the
omission as a material misrepresentation. Remove it only if it does not apply.
