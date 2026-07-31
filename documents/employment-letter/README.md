# Loomi Employment Verification Letter

A reusable employment verification letter on a purpose-designed Loomi (loomi.ai)
letterhead, addressed "To Whom It May Concern" and signed by a company officer.

## Files

| File | Purpose |
|---|---|
| `Loomi-Employment-Verification-Letter.docx` | Editable Word version — fill in the placeholders here |
| `Loomi-Employment-Verification-Letter.pdf` | Rendered, send-ready version (one page) |
| `Loomi-Letterhead.pdf` | The identity: the letterhead sheet, and the mark studied |
| `DESIGN-PHILOSOPHY.md` | "Woven Signal" — the philosophy the identity is built on |
| `make_letterhead.py` | Draws the mark, wordmark, letterhead and head band (reportlab) |
| `make_letter.js` | Builds the `.docx`, embedding the head band (docx-js) |
| `band-1.png` | The head band — mark, wordmark and rule, at the letter's 488 pt measure |
| `loomi-lockup.png` | Mark + wordmark alone, 300 dpi, for reuse elsewhere |

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
- `[Street Address]`, `[City, State ZIP]`, `[Phone]`, `[email@loomi.ai]` — the
  contact line under the rule, and the footer
- `[his/her/their]` / `[He/She/They]` — pronouns

## Regenerating

The letterhead art first, then the document — `make_letter.js` reads `band-1.png`.

```bash
pip install reportlab
python3 make_letterhead.py                 # -> Loomi-Letterhead.pdf, band.pdf, lockup.pdf
pdftoppm -png -r 75 band.pdf band          # -> band-1.png (~300 dpi at final size)

npm install docx
node make_letter.js                        # -> .docx
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
