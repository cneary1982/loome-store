# Loomi Employment Verification Letter

A reusable employment verification letter on Loomi (loomi.ai) letterhead, addressed
"To Whom It May Concern" and signed by a company officer.

## Files

| File | Purpose |
|---|---|
| `Loomi-Employment-Verification-Letter.docx` | Editable Word version — fill in the placeholders here |
| `Loomi-Employment-Verification-Letter.pdf` | Rendered, send-ready version |
| `make_letter.js` | Generator script (docx-js) that produces the `.docx` |

## Placeholders to fill in

Everything in `[SQUARE BRACKETS]` must be replaced before the letter is sent:

- `[EMPLOYEE FULL LEGAL NAME]` — as it appears on government ID
- `[START DATE]`, `[BASE SALARY]`, and the other compensation / location fields
- `[REPORTING MANAGER / TITLE]`
- `[OFFICER FULL NAME]` and title — whoever signs
- `[Street Address]`, `[City, State ZIP]`, `[Phone]`, `[email@loomi.ai]` — letterhead
  and footer contact details
- `[his/her/their]` / `[He/She/They]` — pronouns

## Regenerating

```bash
npm install docx
node make_letter.js
```

To re-render the PDF (requires LibreOffice with `libreoffice-writer` installed):

```bash
soffice --headless --convert-to pdf Loomi-Employment-Verification-Letter.docx
```

## Note on the ownership paragraph

The letter includes a short paragraph disclosing that the employee also holds an
ownership interest in the company. This is deliberate — for an owner-employee, an
insurer or lender that later discovers an undisclosed ownership stake may treat the
omission as a material misrepresentation. Remove it only if it does not apply.
