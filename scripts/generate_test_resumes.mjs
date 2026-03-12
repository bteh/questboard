/**
 * Generate sample resume PDFs for testing with diverse user personas.
 * Run: node scripts/generate_test_resumes.mjs
 */
import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const KNOWLEDGE_DIR = join(ROOT, 'knowledge');

mkdirSync(KNOWLEDGE_DIR, { recursive: true });

// ─── Resume content for each persona ───

const PERSONAS = [
  {
    profile: 'junior_frontend',
    name: 'Alex Chen',
    title: 'Junior Frontend Developer',
    content: [
      { heading: 'ALEX CHEN', size: 18 },
      { text: 'Junior Frontend Developer | San Francisco, CA | alex.chen@email.com | github.com/alexchen' },
      { heading: 'SUMMARY' },
      { text: 'Recent computer science graduate from UC Berkeley with 1 year of internship experience building React applications. Passionate about creating accessible, performant user interfaces. Looking for my first full-time frontend role.' },
      { heading: 'EDUCATION' },
      { text: 'University of California, Berkeley -B.S. Computer Science, May 2025\nGPA: 3.6/4.0 | Relevant coursework: Web Development, Data Structures, Algorithms, Human-Computer Interaction' },
      { heading: 'EXPERIENCE' },
      { text: 'Frontend Engineering Intern -Startup Co, San Francisco, CA (Jun 2024 -Aug 2024)\n- Built 5 React components for the customer dashboard using TypeScript and Tailwind CSS\n- Improved Lighthouse performance score from 62 to 89 by implementing lazy loading and code splitting\n- Collaborated with design team to implement a responsive mobile navigation\n- Participated in code reviews and daily standups with a team of 6 engineers' },
      { text: 'Web Development Teaching Assistant -UC Berkeley (Jan 2024 -May 2024)\n- Helped 120 students debug HTML/CSS/JavaScript assignments during weekly office hours\n- Created 3 supplementary tutorial videos on React hooks that received 2,000+ views\n- Graded assignments and provided detailed feedback on code quality' },
      { heading: 'PROJECTS' },
      { text: 'TaskFlow -Personal Project (React, TypeScript, Firebase)\n- Built a Kanban-style task management app with drag-and-drop, real-time sync, and dark mode\n- Implemented user authentication with Google OAuth and role-based access control\n- Deployed on Vercel with CI/CD pipeline, 99.9% uptime over 3 months' },
      { text: 'Campus Events App -Hackathon Winner (Next.js, Prisma, PostgreSQL)\n- Led a team of 3 to build a campus event discovery app in 36 hours\n- Won "Best UI/UX" award out of 42 competing teams\n- Used Next.js App Router with server components for optimal loading performance' },
      { heading: 'TECHNICAL SKILLS' },
      { text: 'Languages: JavaScript, TypeScript, HTML, CSS, Python\nFrameworks: React, Next.js, Tailwind CSS, shadcn/ui\nTools: Git, VS Code, Figma, Vercel, Firebase\nTesting: Jest, React Testing Library, Playwright\nOther: REST APIs, GraphQL basics, Responsive Design, Web Accessibility (WCAG 2.1)' },
    ],
  },
  {
    profile: 'marketing_manager',
    name: 'Sarah Johnson',
    title: 'Marketing Manager',
    content: [
      { heading: 'SARAH JOHNSON', size: 18 },
      { text: 'Marketing Manager | Chicago, IL | sarah.johnson@email.com | linkedin.com/in/sarahjohnson' },
      { heading: 'PROFESSIONAL SUMMARY' },
      { text: 'Results-driven marketing manager with 6 years of experience in B2B SaaS marketing. Expertise in demand generation, content strategy, and marketing automation. Track record of increasing pipeline by 45% and reducing CAC by 30% through data-driven campaigns. Looking for a Senior Marketing Manager or Director of Marketing role at a growth-stage tech company.' },
      { heading: 'EXPERIENCE' },
      { text: 'Marketing Manager -CloudMetrics Inc., Chicago, IL (Mar 2022 -Present)\n- Manage a $2.4M annual marketing budget across paid, organic, and event channels\n- Built and lead a team of 3 marketers (content writer, demand gen specialist, designer)\n- Increased MQL-to-SQL conversion rate from 18% to 31% by redesigning lead scoring model\n- Launched account-based marketing program targeting Fortune 500 accounts, generating $4.2M in pipeline\n- Implemented HubSpot marketing automation, reducing manual campaign setup time by 60%\n- Manage relationships with 5 agency partners for paid media, SEO, and PR' },
      { text: 'Senior Marketing Specialist -TechStartup Labs, Chicago, IL (Jun 2020 -Feb 2022)\n- Owned content marketing strategy: blog, whitepapers, case studies, webinars\n- Grew organic traffic from 15K to 85K monthly visitors through SEO optimization\n- Managed $800K paid media budget across Google Ads, LinkedIn, and Facebook\n- Created quarterly competitive intelligence reports for the executive team\n- Organized 3 virtual conferences with 1,500+ attendees each' },
      { text: 'Marketing Coordinator -Digital Agency Co., Chicago, IL (Jul 2018 -May 2020)\n- Supported 8 client accounts with campaign execution, reporting, and analytics\n- Built email nurture sequences that achieved 42% open rate (industry avg: 21%)\n- Managed social media presence across LinkedIn, Twitter, and Instagram' },
      { heading: 'EDUCATION' },
      { text: 'Northwestern University -MBA, Marketing concentration, 2022\nUniversity of Illinois -B.A. Communications, 2018' },
      { heading: 'SKILLS & CERTIFICATIONS' },
      { text: 'Platforms: HubSpot (certified), Salesforce, Google Analytics 4, Marketo, Drift, 6sense\nSkills: Demand Generation, ABM, Content Strategy, SEO/SEM, Marketing Automation, A/B Testing\nAnalytics: Looker, Tableau, Google Data Studio, Excel (advanced)\nCertifications: HubSpot Inbound Marketing, Google Ads Search, Salesforce Administrator' },
    ],
  },
  {
    profile: 'nurse_practitioner',
    name: 'Maria Rodriguez',
    title: 'Nurse Practitioner',
    content: [
      { heading: 'MARIA RODRIGUEZ, MSN, FNP-C', size: 18 },
      { text: 'Family Nurse Practitioner | Austin, TX | maria.rodriguez@email.com | NPI: 1234567890' },
      { heading: 'PROFESSIONAL SUMMARY' },
      { text: 'Board-certified Family Nurse Practitioner with 9 years of nursing experience including 4 years in advanced practice. Specialized in primary care, chronic disease management, and telehealth. Experienced in both urban clinic and rural health settings. Bilingual English/Spanish. Seeking a lead NP or clinical director role in community health.' },
      { heading: 'LICENSES & CERTIFICATIONS' },
      { text: 'Family Nurse Practitioner -Texas Board of Nursing (Active)\nANCC Board Certification -Family Nurse Practitioner (FNP-C)\nDEA Registration (Active) | BLS, ACLS, PALS certified\nPrescriptive Authority -Texas (Schedule II-V)' },
      { heading: 'CLINICAL EXPERIENCE' },
      { text: 'Family Nurse Practitioner -Community Health Partners, Austin, TX (Aug 2022 -Present)\n- Manage panel of 1,200+ patients across 3 clinic locations\n- Diagnose and treat acute and chronic conditions including diabetes, hypertension, COPD, and depression\n- Perform comprehensive health assessments, order and interpret diagnostic tests\n- Prescribe medications and develop individualized treatment plans\n- Conduct 20-25 patient visits daily with 4.8/5.0 patient satisfaction score\n- Mentor 2 NP students per semester from UT Austin School of Nursing\n- Implemented diabetes management protocol that reduced average A1C by 1.2 points across panel' },
      { text: 'Registered Nurse, ICU -St. David\'s Medical Center, Austin, TX (Jun 2017 -Jul 2022)\n- Provided critical care for patients with complex medical, surgical, and trauma conditions\n- Managed ventilators, hemodynamic monitoring, vasoactive drips, and continuous renal replacement therapy\n- Served as charge nurse for 18-bed ICU (2020-2022)\n- Precepted 15+ new graduate nurses through 12-week orientation program\n- Led unit-based quality improvement project reducing CLABSI rate by 40%' },
      { text: 'Registered Nurse, Med-Surg -Dell Seton Medical Center, Austin, TX (May 2015 -May 2017)\n- Cared for 5-6 patients per shift on 36-bed medical-surgical unit\n- Administered medications, wound care, and patient education\n- Participated in rapid response and code blue teams' },
      { heading: 'EDUCATION' },
      { text: 'University of Texas at Austin -Master of Science in Nursing (FNP), 2022\nTexas State University -Bachelor of Science in Nursing, 2015' },
      { heading: 'SKILLS' },
      { text: 'Clinical: Primary care, Chronic disease management, Telehealth, Women\'s health, Pediatrics, Geriatrics\nEMR Systems: Epic, Cerner, Athenahealth\nLanguages: English (native), Spanish (fluent)\nLeadership: Clinical precepting, Quality improvement, Protocol development, Team training' },
    ],
  },
  {
    profile: 'product_manager',
    name: 'David Park',
    title: 'Senior Product Manager',
    content: [
      { heading: 'DAVID PARK', size: 18 },
      { text: 'Senior Product Manager | New York, NY | david.park@email.com | linkedin.com/in/davidpark' },
      { heading: 'SUMMARY' },
      { text: 'Product manager with 5 years of experience building B2B and B2C products at scale. Led cross-functional teams of 8-12 to ship features used by 2M+ users. Strong technical background (former software engineer) with expertise in data-driven product development, A/B testing, and user research. Looking for a Director of Product or Group PM role.' },
      { heading: 'EXPERIENCE' },
      { text: 'Senior Product Manager -FinanceApp Inc., New York, NY (Jan 2023 -Present)\n- Own the payments and checkout product line generating $180M ARR\n- Led redesign of checkout flow that increased conversion rate from 3.2% to 4.8% (+50%)\n- Defined and executed 18-month product roadmap aligned with company OKRs\n- Manage backlog of 200+ feature requests, conducting quarterly prioritization with RICE scoring\n- Partner with 3 engineering squads (12 engineers), design (2 designers), and data science (1 analyst)\n- Launched international payments in 5 new markets, contributing $12M in new ARR\n- Implemented feature flagging system enabling 40% faster experimentation cycles' },
      { text: 'Product Manager -SocialPlatform Co., New York, NY (Mar 2021 -Dec 2022)\n- Owned the creator monetization product serving 500K+ content creators\n- Shipped tipping feature that generated $8M in creator payouts within first 6 months\n- Conducted 50+ user interviews and 12 usability studies to inform product decisions\n- Reduced creator onboarding time from 15 minutes to 3 minutes through UX simplification\n- Collaborated with legal and compliance teams to ensure regulatory adherence across 30 countries' },
      { text: 'Software Engineer to Associate PM -TechCorp, San Francisco, CA (Jun 2019 - Feb 2021)\n- Transitioned from engineering to product management after 1.5 years as full-stack developer\n- Built internal analytics dashboard used by 200+ employees for product decision-making\n- As APM, managed the notification system product, improving engagement by 25%\n- Tech stack experience: Python, React, PostgreSQL, Redis, AWS' },
      { heading: 'EDUCATION' },
      { text: 'Stanford University -B.S. Computer Science, 2019\nRelevant coursework: HCI, Machine Learning, Databases, Product Management (GSB elective)' },
      { heading: 'SKILLS' },
      { text: 'Product: Roadmapping, A/B Testing, User Research, PRDs, OKRs, RICE prioritization, Jobs-to-be-Done\nTools: Figma, Amplitude, Mixpanel, Jira, Linear, Notion, Miro, Looker, dbt\nTechnical: SQL (advanced), Python, REST APIs, Data modeling, System design\nMethodologies: Agile/Scrum, Design Thinking, Lean Startup, Dual-Track Agile' },
    ],
  },
  {
    profile: 'career_changer',
    name: 'James Wilson',
    title: 'Aspiring Data Analyst (Former Teacher)',
    content: [
      { heading: 'JAMES WILSON', size: 18 },
      { text: 'Aspiring Data Analyst | Denver, CO | james.wilson@email.com | github.com/jameswilson-data' },
      { heading: 'SUMMARY' },
      { text: 'Former high school math teacher transitioning to data analytics after completing the Google Data Analytics Professional Certificate and a data science bootcamp. Strong foundation in statistics, problem-solving, and communicating complex concepts to diverse audiences. Eager to apply analytical skills in a junior data analyst or business intelligence role.' },
      { heading: 'EDUCATION & CERTIFICATIONS' },
      { text: 'DataCamp Data Science Bootcamp -Completed December 2025\n- 480 hours of intensive training in Python, SQL, statistics, and data visualization\n- Capstone project: Built a predictive model for student graduation rates using scikit-learn\n\nGoogle Data Analytics Professional Certificate -Coursera, 2025\nUniversity of Colorado -B.S. Mathematics, Minor in Education, 2016' },
      { heading: 'DATA PROJECTS' },
      { text: 'Denver Housing Market Analysis (Python, Pandas, Tableau)\n- Scraped 10,000+ property listings and analyzed price trends across 15 neighborhoods\n- Built interactive Tableau dashboard showing price-per-sqft, time-on-market, and seasonal patterns\n- Published findings on Medium, receiving 3,500+ reads\n- GitHub: 45 stars, featured in DataCamp student showcase' },
      { text: 'School District Performance Dashboard (SQL, Power BI)\n- Designed and built a Power BI dashboard for a school district tracking 12,000 student records\n- Wrote complex SQL queries joining 8 tables to calculate graduation rates, attendance trends, and test score analytics\n- Reduced the time administrators spent generating reports from 2 days to 15 minutes\n- Presented findings to school board of 9 members, leading to $500K reallocation of tutoring resources' },
      { text: 'Spotify Listening Habits Analysis (Python, Jupyter, Matplotlib)\n- Analyzed 3 years of personal Spotify data (50,000+ streams) to identify listening patterns\n- Applied k-means clustering to categorize music preferences by mood, energy, and tempo\n- Created automated weekly email report using Python and SendGrid API' },
      { heading: 'TEACHING EXPERIENCE' },
      { text: 'High School Math Teacher -Denver Public Schools (Aug 2016 -Jun 2025)\n- Taught Algebra II, Pre-Calculus, and AP Statistics to 150+ students annually\n- Improved AP Statistics pass rate from 52% to 78% over 4 years\n- Created data-driven lesson plans using student performance analytics\n- Mentored 8 student teachers and led professional development workshops on data literacy\n- Served as Math Department Chair (2021-2025), managing curriculum for 6 teachers' },
      { heading: 'TECHNICAL SKILLS' },
      { text: 'Languages: Python, SQL, R (basic)\nData Tools: Pandas, NumPy, scikit-learn, Matplotlib, Seaborn, Jupyter Notebooks\nVisualization: Tableau, Power BI, Google Data Studio\nDatabases: PostgreSQL, MySQL, BigQuery\nOther: Excel (advanced, pivot tables, VLOOKUP), Google Sheets, Git, Statistics (hypothesis testing, regression)' },
      { heading: 'TRANSFERABLE SKILLS' },
      { text: '- Explaining complex analytical concepts to non-technical stakeholders\n- Curriculum design translates directly to structured analytical frameworks\n- 9 years managing classroom data, assessments, and performance metrics\n- Strong presentation and public speaking skills (200+ presentations)\n- Collaborative team player with experience leading cross-departmental initiatives' },
    ],
  },
];

// ─── PDF Generation ───

async function createResumePDF(persona) {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const fontBold = await doc.embedFont(StandardFonts.HelveticaBold);

  const PAGE_WIDTH = 612; // Letter size
  const PAGE_HEIGHT = 792;
  const MARGIN = 50;
  const MAX_WIDTH = PAGE_WIDTH - 2 * MARGIN;
  const LINE_HEIGHT = 14;
  const HEADING_SIZE = 12;
  const TEXT_SIZE = 9.5;

  let page = doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
  let y = PAGE_HEIGHT - MARGIN;

  function newPageIfNeeded(needed = 40) {
    if (y < MARGIN + needed) {
      page = doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
      y = PAGE_HEIGHT - MARGIN;
    }
  }

  function wrapText(text, fontSize, maxWidth, useFont = font) {
    const lines = [];
    const paragraphs = text.split('\n');
    for (const para of paragraphs) {
      if (!para.trim()) {
        lines.push('');
        continue;
      }
      const words = para.split(/\s+/);
      let currentLine = '';
      for (const word of words) {
        const testLine = currentLine ? `${currentLine} ${word}` : word;
        const width = useFont.widthOfTextAtSize(testLine, fontSize);
        if (width > maxWidth && currentLine) {
          lines.push(currentLine);
          currentLine = word;
        } else {
          currentLine = testLine;
        }
      }
      if (currentLine) lines.push(currentLine);
    }
    return lines;
  }

  for (const block of persona.content) {
    if (block.heading) {
      const size = block.size || HEADING_SIZE;
      const spacing = block.size ? 0 : 16;
      newPageIfNeeded(spacing + size + 8);
      y -= spacing;
      page.drawText(block.heading, {
        x: MARGIN,
        y,
        size,
        font: fontBold,
        color: rgb(0.1, 0.1, 0.1),
      });
      y -= size + 4;
      // Draw line under section headings (not name)
      if (!block.size) {
        page.drawLine({
          start: { x: MARGIN, y: y + 2 },
          end: { x: PAGE_WIDTH - MARGIN, y: y + 2 },
          thickness: 0.5,
          color: rgb(0.6, 0.6, 0.6),
        });
        y -= 6;
      }
    }
    if (block.text) {
      const lines = wrapText(block.text, TEXT_SIZE, MAX_WIDTH);
      for (const line of lines) {
        newPageIfNeeded(LINE_HEIGHT);
        if (line === '') {
          y -= LINE_HEIGHT * 0.5;
          continue;
        }
        // Detect bullet points
        const isBullet = line.startsWith('- ');
        const xOffset = isBullet ? 10 : 0;
        const displayText = isBullet ? `-  ${line.slice(2)}` : line;
        page.drawText(displayText, {
          x: MARGIN + xOffset,
          y,
          size: TEXT_SIZE,
          font,
          color: rgb(0.15, 0.15, 0.15),
        });
        y -= LINE_HEIGHT;
      }
      y -= 4; // spacing after text block
    }
  }

  const pdfBytes = await doc.save();
  const outPath = join(KNOWLEDGE_DIR, `${persona.profile}_resume.pdf`);
  writeFileSync(outPath, pdfBytes);
  console.log(`  ✓ ${outPath}`);
}

console.log('Generating test resume PDFs...\n');
for (const persona of PERSONAS) {
  await createResumePDF(persona);
}
console.log('\nDone! Created', PERSONAS.length, 'resume PDFs.');
