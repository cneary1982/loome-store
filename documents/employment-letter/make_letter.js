const {
  Document, Packer, Paragraph, TextRun, AlignmentType, BorderStyle,
  Footer, Header, TabStopType, TabStopPosition, Tab, ImageRun,
} = require('docx');
const fs = require('fs');

// ---- Brand palette -------------------------------------------------
const INK    = '11132B'; // near-black navy, wordmark + body
const ACCENT = '6D5AE6'; // violet accent (.ai, rules)
const MUTED  = '6B7185'; // gray for contact line / footer

const FONT = 'Calibri';

// ---- Helpers -------------------------------------------------------
const body = (children, opts = {}) =>
  new Paragraph({
    spacing: { after: opts.after ?? 150, line: 258 },
    alignment: opts.align ?? AlignmentType.LEFT,
    ...opts.extra,
    children,
  });

const t = (text, opts = {}) =>
  new TextRun({
    text,
    font: FONT,
    size: opts.size ?? 20, // half-points -> 10pt
    color: opts.color ?? INK,
    bold: opts.bold ?? false,
    italics: opts.italics ?? false,
    allCaps: opts.caps ?? false,
    characterSpacing: opts.spacing,
  });

const spacer = (after = 200) =>
  new Paragraph({ spacing: { after }, children: [t('')] });

// ---- Letterhead ----------------------------------------------------
// The head — woven mark, wordmark and the two-tone rule — is placed as a
// single image so the letter carries the real artwork rather than a border
// approximation of it. Drawn at 4x in make_letterhead.py, ~300 dpi here.
// The band is authored at exactly the 488 pt content measure of this page.
const BAND_PT_W = 488.0;
const PX = 96.0 / 72.0;                    // docx image units are px @ 96 dpi

// ---- Which brand this letter is issued under -----------------------
// Two identities live in this repo, so the letter is parameterised rather
// than hard-coded. Override with env vars; defaults to Loomi.
//   BRAND=loome node make_letter.js
const BRANDS = {
  loomi: {
    company: 'Loomi, Inc.',
    site: 'loomi.ai',
    email: '[email@loomi.ai]',
    band: 'band-1.png',
    aspect: 10.59375,                      // width / height, from band.pdf
    out: 'Loomi-Employment-Verification-Letter.docx',
  },
  loome: {
    company: 'LOOME Inc.',
    site: 'loome.com',
    email: '[email@loome.com]',
    band: 'loome-band-1.png',
    aspect: 10.60870,                      // from loome-band.pdf
    out: 'LOOME-Employment-Verification-Letter.docx',
  },
};
const B = BRANDS[(process.env.BRAND || 'loomi').toLowerCase()];
if (!B) throw new Error(`unknown BRAND: ${process.env.BRAND}`);
const BAND_ASPECT = B.aspect;

const band = new Paragraph({
  spacing: { after: 60 },
  children: [
    new ImageRun({
      type: 'png',
      data: fs.readFileSync(B.band),
      transformation: {
        width: BAND_PT_W * PX,
        height: (BAND_PT_W / BAND_ASPECT) * PX,
      },
    }),
  ],
});

const contactLine = new Paragraph({
  spacing: { after: 230 },
  children: [
    t(`[Street Address]  ·  [City, State ZIP]     [Phone]     ${B.email}     ${B.site}`, {
      size: 16, color: MUTED,
    }),
  ],
});

// ---- Letter body ---------------------------------------------------
const children = [
  band,
  contactLine,

  // Date
  body([t('July 31, 2026')], { after: 260 }),

  // Salutation
  body([t('To Whom It May Concern:')], { after: 220 }),

  // Re: line
  new Paragraph({
    spacing: { after: 250 },
    children: [
      t('RE:  ', { bold: true }),
      t('Verification of Employment — [EMPLOYEE FULL LEGAL NAME]', { bold: true }),
    ],
  }),

  // 1. Purpose
  body([
    t('This letter serves to confirm that '),
    t('[EMPLOYEE FULL LEGAL NAME]', { bold: true }),
    t(` is currently employed by ${B.company} (the “Company”) and is an active employee in good standing as of the date of this letter. This confirmation is provided at the employee’s request in connection with an insurance application or review.`),
  ]),

  // 2. Employment details
  body([t('The particulars of [his/her/their] employment are as follows:', {})]),

  // Detail block — indented, dot-leader style key/value lines
  ...[
    ['Position / Title', 'Investment Banker'],
    ['Department', 'Investment Banking & Capital Markets'],
    ['Employment Status', 'Full-time, salaried, exempt'],
    ['Date of Hire', '[START DATE]'],
    ['Current Status', 'Active and continuously employed since hire'],
    ['Base Compensation', '$[BASE SALARY] USD per year'],
    ['Other Compensation', '[Bonus / commission / equity — or “None”]'],
    ['Work Location', '[City, State] — [On-site | Hybrid | Remote]'],
    ['Typical Hours', '[40]+ hours per week'],
  ].map(([k, v]) =>
    new Paragraph({
      spacing: { after: 64, line: 250 },
      indent: { left: 460 },
      tabStops: [{ type: TabStopType.LEFT, position: 3260 }],
      children: [t(k, { bold: true }), new TextRun({ children: [new Tab()] }), t(v)],
    })
  ),

  spacer(110),

  // 3. Duties
  body([
    t('In this capacity, [EMPLOYEE FULL LEGAL NAME] originates, structures, and executes transactions for the Company and its clients. Core duties include financial modeling and valuation, due diligence, capital-raising, merger and acquisition advisory, preparation of offering materials, investor relations, and transaction negotiation and closing. [He/She/They] reports to [REPORTING MANAGER / TITLE].'),
  ]),

  // 4. Ownership disclosure
  body([
    t('In the interest of full transparency, [EMPLOYEE FULL LEGAL NAME] also holds an ownership interest in the Company in addition to [his/her/their] employee role. The title and compensation above are separate from, and in addition to, any distributions attributable to that interest.'),
  ]),

  // 5. Standing / outlook
  body([
    t('[EMPLOYEE FULL LEGAL NAME] remains in good standing, [his/her/their] position is ongoing, and the Company has no knowledge of any pending or anticipated change to [his/her/their] employment status, title, or compensation.'),
  ]),

  // 6. Verification contact
  body([
    t(`Should you require additional information or wish to verify this letter, please contact me directly at [PHONE] or ${B.email}. We are glad to complete any verification form you require.`),
  ], { after: 260 }),

  // Sign-off
  body([t('Sincerely,')], { after: 300 }),

  // Signature block
  new Paragraph({
    spacing: { after: 30, line: 250 },
    children: [t('[OFFICER FULL NAME]', { bold: true })],
  }),
  new Paragraph({
    spacing: { after: 20, line: 250 },
    children: [t('[Title — e.g. Chief Operating Officer / Head of People Operations]')],
  }),
  new Paragraph({
    spacing: { after: 20, line: 250 },
    children: [t(B.company)],
  }),
  new Paragraph({
    spacing: { after: 20, line: 250 },
    children: [t(`[PHONE]  ·  ${B.email}`)],
  }),
];

// ---- Footer --------------------------------------------------------
const footer = new Footer({
  children: [
    new Paragraph({
      spacing: { before: 120 },
      border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'D8DAE5', space: 6 } },
      alignment: AlignmentType.CENTER,
      children: [
        t(`${B.company}  ·  [Street Address], [City, State ZIP]  ·  ${B.site}`, { size: 15, color: MUTED }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        t('This letter is issued solely for the purpose of employment verification and is confidential.', { size: 14, color: MUTED, italics: true }),
      ],
    }),
  ],
});

// ---- Document ------------------------------------------------------
const doc = new Document({
  creator: B.company,
  title: 'Employment Verification Letter',
  description: `Verification of employment issued on ${B.company} letterhead`,
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 }, // US Letter
        margin: { top: 780, right: 1240, bottom: 600, left: 1240 },
      },
    },
    footers: { default: footer },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(B.out, buf);
  console.log('wrote', B.out);
});
