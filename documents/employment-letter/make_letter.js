const {
  Document, Packer, Paragraph, TextRun, AlignmentType, BorderStyle,
  Footer, Header, TabStopType, TabStopPosition, Tab,
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
const wordmark = new Paragraph({
  spacing: { after: 40 },
  children: [
    new TextRun({ text: 'loomi', font: FONT, size: 48, bold: true, color: INK, characterSpacing: -20 }),
    new TextRun({ text: '.ai', font: FONT, size: 48, bold: true, color: ACCENT, characterSpacing: -20 }),
  ],
});

const tagline = new Paragraph({
  spacing: { after: 120 },
  children: [
    t('ARTIFICIAL INTELLIGENCE  ·  CAPITAL  ·  ADVISORY', {
      size: 14, color: MUTED, caps: true, spacing: 30,
    }),
  ],
});

// Accent rule under the letterhead
const rule = new Paragraph({
  spacing: { after: 160 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 1 } },
  children: [t('')],
});

const contactLine = new Paragraph({
  spacing: { after: 230 },
  children: [
    t('[Street Address]  ·  [City, State ZIP]     [Phone]     [email@loomi.ai]     loomi.ai', {
      size: 16, color: MUTED,
    }),
  ],
});

// ---- Letter body ---------------------------------------------------
const children = [
  wordmark,
  tagline,
  rule,
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
    t(' is currently employed by Loomi, Inc. (the “Company”) and is an active employee in good standing as of the date of this letter. This confirmation is provided at the employee’s request in connection with an insurance application or review.'),
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
    t('Should you require additional information or wish to verify this letter, please contact me directly at [PHONE] or [email@loomi.ai]. We are glad to complete any verification form you require.'),
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
    children: [t('Loomi, Inc.')],
  }),
  new Paragraph({
    spacing: { after: 20, line: 250 },
    children: [t('[PHONE]  ·  [email@loomi.ai]')],
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
        t('Loomi, Inc.  ·  [Street Address], [City, State ZIP]  ·  loomi.ai', { size: 15, color: MUTED }),
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
  creator: 'Loomi, Inc.',
  title: 'Employment Verification Letter',
  description: 'Verification of employment issued on Loomi, Inc. letterhead',
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
  fs.writeFileSync('Loomi-Employment-Verification-Letter.docx', buf);
  console.log('wrote Loomi-Employment-Verification-Letter.docx');
});
