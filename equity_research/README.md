# Equity Research Skill

[![Stars](https://img.shields.io/github/stars/rollingSirius/equity-research-skill?style=flat)](https://github.com/rollingSirius/equity-research-skill/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/rollingSirius/equity-research-skill)](https://github.com/rollingSirius/equity-research-skill/commits/main)
[![License](https://img.shields.io/github/license/rollingSirius/equity-research-skill)](LICENSE)

Author: [@rollingSirius](https://x.com/rollingSirius)

中文文档：[README.zh-CN.md](README.zh-CN.md) ｜ Sample reports: [NVDA 中文](Example/EXAMPLE_NVDA.md) / [English](Example/EXAMPLE_NVDA.en.md) ｜ [GOOGL 中文](Example/EXAMPLE_GOOGL.md) / [English](Example/EXAMPLE_GOOGL.en.md)

**Possibly the deepest AI equity-research skill.**

The goal of this skill is not to generate a few paragraphs of stock summary, but to make AI tools follow something close to institutional research discipline and produce a deep single-stock report that is **fact-traceable, valuation-reproducible, and conclusion-auditable**. It is built for serious investment research, long-term coverage, earnings reviews, investment memos, and valuation calibration — not for delivering a one-line verdict as fast as possible. Since v2, every report is organized around an **expectations gap** (what the market has priced in vs. your independent view), with an **earnings-quality review** performed before any valuation.

## Positioning

Most AI stock analysis stops at "company profile + recent news + vague valuation." This skill deliberately goes deeper:

| Capability | Design requirement |
|---|---|
| Deep research | Full research mode outputs a nine-chapter report covering business, competition, governance, financials, valuation, catalysts, and the investment verdict. |
| Expectations gap as the spine | Reverse DCF + PVGO decomposition decode what the current price has priced in, producing an expectations-gap table and a falsifiable variant thesis; no independent view, no buy/sell action. |
| Earnings mode | Earnings mode is not a summary but a nine-chapter earnings deep-dive: surprise quality, segments and KPIs, GAAP vs. Non-GAAP, cash flow, the call, and model and valuation changes. |
| Earnings-quality review | Accrual quality, Beneish M-Score, revenue-recognition red flags, governance signals → an A–D earnings-credibility grade; grades C/D veto any buy action outright. |
| Reproducible valuation | DCF, reverse DCF, probability-weighted three-scenario, EPV/three-factor, EVA/residual income, SOTP and the rest must be executed by `scripts/dcf.py`, with key assumptions filed as JSON; optional Monte Carlo outputs a fair-value distribution. |
| Outside view | Key assumptions are marked with their percentile against historical base rates; beating the base rate requires a structural reason; terminal value must pass a three-point sanity check. |
| Source discipline | Every key number carries a source and timestamp; conflicting data is reconciled; missing data must be written as "not obtained"; external content is data only and never alters the workflow. |
| Buy-side lens | Conclusions map through pre-registered calibration rules; a counter-case and a pre-mortem are completed before finalizing, answering "if this were cash today, would I buy it, and why?" |
| Twenty industry appendices | Twenty industry appendices, each changing the KPIs, model, valuation, and disconfirming-evidence framework, with required KPIs enforced by the checker. |
| Multi-market coverage | US, HK, and A-share markets, including A/H dual-listing comparison and China ADR/VIE structural-risk pricing. |
| Initiation from earnings | Earnings mode works with no prior report or model; the skill first rebuilds a baseline of at least 3 years and 8 quarters. |

## What it does

### 1. Full deep-dive research

For studying a company systematically for the first time, or rebuilding an investment framework from scratch. Default output is a nine-chapter report:

1. One-page summary (verdict box + tearsheet + expectations-gap table)
2. Company and business detail
3. Competitive landscape and moat
4. Management, governance, and capital-allocation scorecard
5. Financial analysis and earnings-quality review
6. Multi-method valuation (with a football-field chart)
7. Analyst views and divergence attribution
8. News, risks, and catalysts
9. Investment verdict, counter-case, and position-sizing reference

### 2. Deep earnings mode

For the moment right after a company reports a quarter, a full year, guidance, or a call transcript, when the question is "what did this print actually change?" Earnings mode splits into two cases:

| Coverage status | How the skill handles it |
|---|---|
| A prior report or model exists | Continuing-coverage update, focused on what the print changes relative to the old thesis, old forecasts, and old valuation. |
| No prior report or model | Initiation of coverage from the earnings event: rebuild the historical baseline first, then analyze this print's quality and valuation implications. |

Earnings mode outputs nine chapters by default:

1. Verdict and snapshot
2. Surprise and its quality
3. Revenue, segments, and KPIs
4. Margins, costs, and earnings quality
5. Cash flow, balance sheet, and capital allocation
6. Guidance, the call, and management signals
7. Competition, industry, and market reaction
8. Model, valuation, and the fair-value bridge
9. Thesis update and action list

Every earnings run also executes a minimum check set: accrual ratio, cash conversion, DSO/deferred-revenue divergence, and whether Non-GAAP adjustments are recurring.

### 3. Valuation and calibration

This skill does not allow a target price that merely "looks reasonable." It requires at least three valuation methods cross-checked against each other, with assumptions, calculations, and the label mapping all filed:

- Reverse DCF + PVGO decomposition: what revenue growth, margin, or return on capital the current price implies, and how much of the price is paying for future growth.
- Three-scenario DCF: bull, base, and bear scenarios with a probability-weighted fair value, plus a robustness test that pushes the probabilities toward the extremes.
- EPV / three-factor method: the asset-reproduction floor · EPV · growth entry ladder; the multi-year EPV-to-adjusted-book trend as financial verification of the moat.
- EVA / residual income: incumbent ROIC vs. incremental ROIIC, with the "growth = reinvestment rate × ROIIC" consistency check.
- Relative valuation: warranted-multiple discipline — derive the multiple the company deserves from growth, returns, and risk rather than copying the peer median.
- SOTP: for multi-business or multi-asset companies, or where segments differ sharply.
- Monte Carlo (optional): the P10–P90 fair-value distribution and P(intrinsic value < current price).

The verdict label (undervalued / fairly valued / overvalued + action) maps through pre-registered calibration rules (a ±15% buffer band), overlaid with an action matrix and veto conditions; each action ships with expected value, upside/downside asymmetry, and a Kelly-lite (¼ Kelly) sizing-magnitude reference.

### 4. Earnings-quality review

Before valuing anything, answer whether the profit is real:

- Accrual quality (Sloan): total accruals ratio and the cash-conversion trend.
- The eight-variable Beneish M-Score (computed automatically by the checker).
- Revenue-recognition red flags: DSO divergence, deferred-revenue divergence, channel-stuffing signals.
- Expense capitalization and earnings smoothing; governance and audit signals.
- Output: an A–D earnings-credibility grade. Grade C caps the action at "wait and see," grade D is always "avoid" — "it's cheap" may never be used to offset a credibility problem.

### 5. Industry-specific deep appendices

The main report does not apply one template to every company. The skill first identifies where the company sits in its value chain, then loads the matching appendix on demand:

| Industry | Research focus |
|---|---|
| SaaS | ARR, NRR, RPO/cRPO, acquisition efficiency, Rule of 40, SBC, and reverse DCF. |
| Semiconductors | Products/end markets, units and ASP, inventory cycle, yield, capacity, roadmap, export controls, and through-cycle valuation. |
| Hardware / consumer electronics / AI servers | Units, ASP, BOM, channel inventory, customer/supplier concentration, and service attach. |
| Banks | NIM, deposit beta, asset quality, provisioning, CET1, liquidity, and P/TBV–ROTCE. |
| Insurance | Underwriting profit, reserves, combined ratio, VNB/CSM, solvency, investment portfolio, and P/EV. |
| Pharma | Clinical evidence, probability of success, patient funnel, patent/exclusivity, cash runway, and per-asset rNPV. |
| Healthcare services / medtech / CRO-CDMO | Patient/procedure volume, utilization, reimbursement, installed-base consumables, order conversion, and concentration. |
| Consumer | Volume/price mix, same-store sales, traffic, channel sell-through, inventory, brand share, and unit economics. |
| Energy | Production, reserves, decline, costs, differentials/hedging, maintenance capex, commodity-price sensitivity, and NAV. |
| Utilities | Rate base, allowed vs. earned ROE, rate cases, capital projects, financing dilution, and dividend coverage. |
| Internet / platforms | Users × engagement × monetization rate, GMV/take rate, unit economics, segment SOTP, regulatory risk, and post-SBC FCF. |
| Gaming / media / content IP | Audience and payer funnels, content ROI, development capitalization, lifetime revenue, and IP SOTP. |
| Payments / fintech | TPV, net take rate, incentives and rebates, loss-rate vintages, funding cost, and the penetration ceiling. |
| Capital-markets infrastructure | AUM/net flows, trading volume, fee rates, market data, net capital, and rate sensitivity. |
| Real estate / REITs | FFO/AFFO, same-store NOI, occupancy and leasing spreads, cap rate, the debt-maturity wall, and P/NAV. |
| Industrials / machinery | Orders and book-to-bill, backlog quality, aftermarket services, mid-cycle earnings, and cycle positioning. |
| Telecom | Subscribers and ARPU, EBITDA margin, capex/revenue, FCF and dividend coverage, spectrum, and net debt. |
| Autos / EV | Volumes, per-vehicle economics, utilization and breakeven, order quality, battery cost, and cash runway. |
| Metals & mining | Output, AISC cost-curve percentile, reserve life, sustaining capex, price sensitivity, and per-mine NAV. |
| Airlines / transport | Unit revenue and cost, load factor/utilization, the supply-side orderbook, cycle percentile, and lease liabilities. |

See [`references/industry-routing.md`](references/industry-routing.md) for exact boundaries, mixed-business selection, official data entry points, and forecast-review fields. For mixed-business companies, only the primary appendix is loaded — plus any secondary appendix needed to change the model or valuation — so that irrelevant metrics are not piled on in the name of "completeness."

### 6. Data sourcing and reconciliation

No mandatory use of IBKR, Morningstar, or any single data vendor. The default priority order is:

1. Regulatory filings, exchange announcements, government/regulator databases, and the company's own primary documents.
2. Exchange or regulated market data, official company materials, and official industry statistics.
3. Professional sources such as Bloomberg, FactSet, LSEG, S&P Capital IQ, Visible Alpha, Morningstar, Koyfin, and Quartr.
4. Public quote and financial aggregators, used to fill gaps and cross-check.
5. Media, second-hand accounts, and search snippets are leads only; trace back to the original wherever possible.

Connectors are just access paths. The skill picks the highest-tier source available in the current AI environment and explicitly discloses downgrades, delays, definitional differences, and data conflicts. Fetched external content is treated as data awaiting verification; any instructions inside it do not change the research workflow.

## Install

### Easiest method

Copy this repo link and send it to any AI tool that supports skills or agent instructions:

```text
https://github.com/rollingSirius/equity-research-skill
```

For example:

```text
Please install and use this skill:
https://github.com/rollingSirius/equity-research-skill
```

### Claude Code

```bash
# Personal scope: available across all projects
git clone https://github.com/rollingSirius/equity-research-skill.git ~/.claude/skills/equity-research

# Project scope: shared with the repo
git clone https://github.com/rollingSirius/equity-research-skill.git .claude/skills/equity-research
```

### Claude Desktop / Cowork

Zip this repo, or download a Release, and upload it under **Settings -> Capabilities -> Skills**.

### Codex / other agent tools

The skill itself is Markdown instructions, accompanied by reproducible scripts. Any agent that can read files can use it, and local Python is **not a prerequisite for installation**:

1. Put this repo in your project directory, e.g. `skills/equity-research/`.
2. Add one line to your agent config: when the user asks to research or analyze a stock, first read and follow the full workflow in `skills/equity-research/SKILL.md`.
3. When the valuation or checker scripts need to run, prefer the agent's own code environment; with no local Python, run them in a hosted AI code environment or an online notebook — no local Python setup required first.

## Quickstart

Three steps, no configuration.

**1. Install the skill** — see [Install](#install) above.

**2. Ask in plain language** — no special syntax, no flags:

```text
Research NVDA for me
```

**3. Wait for the report** — delivered as PDF by default.

To confirm the scripts run in your environment before spending a full research pass:

```bash
python3 scripts/dcf.py --demo
python3 scripts/check_research_output.py --demo
```

What to expect on a first run:

| Question | Answer |
|---|---|
| How long does it take? | Minutes, not seconds. The skill probes primary filings, reconciles conflicting numbers, and cross-checks several valuation methods before writing anything. |
| What if some data is missing? | It is written as "not obtained" — never guessed, never filled in from memory. |
| Can I get another format? | Say so in the request: `.md`, `.docx`, or `.xlsx` (valuation workbook). |
| Do I need local Python? | No. The scripts can run in the agent's own code environment. |

## Usage

Natural language is enough to trigger it:

```text
Research NVDA for me
Is Marvell worth buying?
Deep-dive AAPL's latest earnings
Update the valuation and verdict on MSFT from its latest results
How should I read Tencent's latest results? Do a deep dive in earnings mode
Compare CATL's A-share vs. H-share pricing
Deep-dive Salesforce / CRM using the SaaS appendix
Analyze TSMC's cycle position and valuation using the semiconductor appendix
Review China Merchants Bank's latest results using the banking appendix
```

You can also invoke the skill explicitly:

| Tool | Example invocation |
|---|---|
| Claude Code | `/equity-research analyze NVDA`, or "use the equity-research skill to research TSLA." |
| Claude Desktop / Cowork | "Use the equity-research skill to tell me whether AAPL is worth buying." |
| Codex CLI | "Read `skills/equity-research/SKILL.md` first, then analyze NVDA following it." |
| Other agents | "Read `skills/equity-research/SKILL.md` and follow its workflow strictly, then research \<ticker\>." |

When no output format is specified, the report is delivered as **PDF** by default; you can ask for `.md`, `.docx`, or `.xlsx` (valuation workbook) in the request. The report language defaults to the user's request language or the current working conversation language, and can be explicitly set, e.g. "write the report in English" or "用中文输出".

## When it fits

| Scenario | Fit | Notes |
|---|---|---|
| Researching a company for the first time | Yes | Builds a complete working file across business, financials, valuation, and verdict. |
| Post-earnings review | Yes | Earnings mode unpacks the surprise, its quality, guidance, the call, and valuation changes. |
| Investment memo | Yes | Suited to conclusions that can be audited and revisited later. |
| Long-term coverage | Yes | Continuously updates thesis, forecasts, and fair value on top of an earlier report. |
| A one-line question about the stock going up | No | The skill prioritizes depth and source discipline. |
| High-frequency trading signals | No | It is not a quant or intraday trading system. |

## Outputs

**The user receives exactly one report, PDF by default** (`.md`/`.docx`/`.xlsx` on request; language can be auto-detected or explicitly specified). The report itself contains:

- The verdict box, tearsheet, and expectations-gap table (the three-part report header).
- Cross-validation across at least three valuation methods, plus a football-field chart.
- The earnings-credibility grade with item-by-item evidence.
- The counter-case, a monitoring checklist, and a self-assessed confidence level.
- A list of key sources with timestamps, valuation assumptions, and a summary of checker results (appendix).

The assumption JSON, raw `scripts/dcf.py` output, checker results, financial CSVs, and similar files are **internal working files**: kept in the working directory for reproduction and traceability, not treated as deliverables, and handed over only when the user asks.

## Repository structure

```text
equity-research-skill/
├── SKILL.md                        # Skill entry point: triggers + discipline + six-step workflow
├── references/
│   ├── report-template.md          # Nine-chapter report template and table skeletons
│   ├── earnings-mode.md            # Deep earnings mode: coverage routing, analysis protocol, model-change bridge, nine-chapter template
│   ├── expectations-investing.md   # Expectations gap as the spine: reverse DCF, PVGO, gap table, independent-view test
│   ├── forensic-accounting.md      # Earnings-quality review: accruals, M-Score, red flags, credibility grading
│   ├── base-rates.md               # Historical base rates: constraining forecasts with the outside view
│   ├── cost-of-capital.md          # Cost of capital: WACC construction and discount-rate discipline
│   ├── valuation-methods.md        # Valuation methods: DCF, reverse DCF, scenario weighting, EPV, EVA, SOTP, and label calibration
│   ├── output-format.md            # Output format: readability rules and delivery rules (PDF by default)
│   ├── data-sources.md             # Sourcing handbook: source tiers, tool downgrades, quotes, filings, industry data, reconciliation
│   ├── industry-routing.md         # 20-industry routing, official data entry points, and forecast-review protocol
│   ├── industry-rules.json         # Industry slugs and required KPI rules consumed by the checker
│   └── markets-cn-hk.md            # A-share/HK/A+H handbook, including China ADR/VIE structural risk
├── industries/                     # 20 industry appendices (see table above)
├── scripts/
│   ├── dcf.py                      # Valuation calculator: DCF, reverse DCF, sensitivity, probability weighting, EPV, EVA, PVGO, Monte Carlo, sizing
│   └── check_research_output.py    # Financial/valuation, language, and industry-KPI checker + earnings-quality review
└── Example/
    ├── EXAMPLE_NVDA.md             # NVIDIA sample output, not part of skill execution
    ├── EXAMPLE_NVDA.en.md          # NVIDIA English sample output, not part of skill execution
    ├── EXAMPLE_GOOGL.md            # Alphabet sample output (v2 full mode), not part of skill execution
    └── EXAMPLE_GOOGL.en.md         # Alphabet English sample output, not part of skill execution
```

[`Example/EXAMPLE_NVDA.md`](Example/EXAMPLE_NVDA.md) / [`Example/EXAMPLE_NVDA.en.md`](Example/EXAMPLE_NVDA.en.md) and [`Example/EXAMPLE_GOOGL.md`](Example/EXAMPLE_GOOGL.md) / [`Example/EXAMPLE_GOOGL.en.md`](Example/EXAMPLE_GOOGL.en.md) (v2 full-mode examples with the expectations-gap table, earnings-quality review, valuation methods, and the counter-case) exist only to show what the final output looks like; `SKILL.md` never loads them automatically. The data sources used in the samples reflect the environment of that particular run and do not imply the same connectors are required to install or run the skill.

## Dependencies

| Dependency | Required? | Notes |
|---|---|---|
| Web search / page fetching | Recommended | For live quotes, regulatory filings, industry data, analyst ratings, and news; offline use requires the user to supply the materials. |
| An executable Python environment | Needed to run the scripts | The agent's own environment, a hosted AI environment, an online notebook, or local Python all work; no local install required. The scripts use the standard library only. |
| PDF generation | Needed for the default output | A PDF skill or an md→PDF toolchain; if unavailable, delivery downgrades to `.md` with an explanation. |
| IBKR or other market-data connectors | Optional | One quote path among several; without it, use exchanges, professional data APIs, or public quote sources. |
| Morningstar or other professional data connectors | Optional | Used for an external valuation anchor, moat ratings, consensus, and standardized data; none are required. |
| docx / xlsx skills | Optional | Only when the user asks for a Word report or an Excel valuation workbook. |

## Design stance

This skill is designed **depth first**: it would rather be slow than give up clear sources, transparent assumptions, reproducible valuation, accountable conclusions, and falsifiable disagreements. It suits serious investment research, long-term coverage, and investment memos, and is not for anyone who just wants a one-line quote or general market commentary.

## Disclaimer

Everything this skill produces is research reference only and **does not constitute investment advice**. Neither the author nor this skill is a licensed investment advisor; investment decisions and their consequences are the user's own.

## License

[MIT](LICENSE)
