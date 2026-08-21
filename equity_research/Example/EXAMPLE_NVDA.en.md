# NVIDIA (NVDA) Equity Research Report

**Report date: 2026-07-17 | Data cutoff: 2026-07-17 13:16 BST | Exchange: NASDAQ | Reporting currency: USD**

> This report separates facts from **my view**. Facts are cited with source and timestamp wherever possible. Model-based valuation is scenario analysis, not a deterministic result. This report is for research reference only and does not constitute personalized investment advice.

## 1. Executive Summary

NVIDIA has evolved from a GPU chip designer into a data-center-scale AI infrastructure platform. It sells compute capacity through GPUs/CPUs, NVLink, InfiniBand/Ethernet networking, full systems, and the CUDA software stack. The scarce asset is no longer a single chip, but the ability to deliver usable AI compute in large-scale clusters.

| Item | Value | Source / time |
|---|---:|---|
| Current price | **$201.55**, intraday -2.82% | IBKR, 2026-07-17 13:16 BST |
| Estimated market cap | **$4.88T** | Current price x 24.22B shares; share count from StockAnalysis / S&P Global, 2026-07-15 |
| 52-week range | **$164.04-$236.54** | IBKR, 2026-07-17 |
| YTD return | **+8.08%** | IBKR, 2026-07-17 |
| Current valuation | TTM P/E about **30.6x**; P/S about **19.3x**; EV/EBITDA about **29.2x** | Recalculated from IBKR price and latest TTM data |
| FY2027 consensus P/E | **about 22.4x** | $201.55 / FY2027 consensus EPS $8.98 |
| Morningstar | Fair value **$280**; **4 stars**; **wide moat**; uncertainty "very high" | Morningstar, 2026-05-21 |
| Comprehensive fair value | **$235-$285**, midpoint about **$260** | Weighted across four methods in this report |
| One-line conclusion | **Moderately undervalued; suitable for staged buying, not unlimited chasing** | My view |

### Core Bull Case

1. **Growth has not slowed yet.** Q1 FY2027 revenue was $81.6B, up 85% YoY; Data Center revenue was $75.2B, up 92%. Q2 guidance is $91B, about 11.5% above the prior quarter.
2. **The moat is full-stack.** CUDA's developer ecosystem, GPUs, NVLink/NVSwitch, Spectrum-X/InfiniBand, and full systems reinforce each other. Competitors must overcome hardware, networking, software, and developer-migration barriers at the same time.
3. **Cash generation and balance sheet strength are exceptional.** TTM FCF is about $119.1B. As of 2026-04-26, cash, cash equivalents, and marketable securities were about $80.6B, with debt carrying value of about $8.5B.

### Core Bear Case

1. **Customer and end-demand capex are highly concentrated.** In Q1 FY2027, three direct customers accounted for 21%, 17%, and 16% of revenue, or 54% combined. If hyperscale AI capex slows, NVIDIA's earnings sensitivity will cut the other way.
2. **Product cadence and supply-chain tolerance are low.** Delays in TSMC manufacturing, advanced packaging, HBM, networking, or liquid cooling could push out system revenue. Rumors in July 2026 about Rubin Ultra / Kyber delays were denied by the company, but execution risk remains something to verify.
3. **The long-term profit pool will not belong only to NVIDIA.** AMD, Broadcom and customer-designed ASICs, Google TPU, Amazon Trainium, and other alternatives will continue competing for training and inference workloads. China revenue is structurally constrained by export controls.

**My view:** At $201.55, the market has awarded NVIDIA a high-quality premium, but has not fully reflected the earnings and cash-flow upgrade after Q1 FY2027. Because uncertainty and customer concentration are very high, I would not take a full position at once. I would treat this as an outstanding asset at an acceptable price, not as a risk-free bargain.

## 2. Business Overview

### Business Model

NVIDIA is a fabless semiconductor and systems platform company. Its main revenue sources are:

- GPUs, CPUs, DPUs, networking chips, and full-system / rack-scale system sales;
- AI Enterprise, CUDA-X, and other software and support services;
- cloud services, licensing, and automotive software platforms.

Hardware still accounts for the vast majority of revenue. Software and services strengthen lock-in, increase system value, and add stability. NVIDIA keeps design, software, and system architecture in-house, while relying on partners such as TSMC for manufacturing, packaging, and part of system assembly.

### Latest Revenue Mix

| Market platform | Q1 FY2027 revenue | Share | YoY growth | Notes |
|---|---:|---:|---:|---|
| Data Center | $75.246B | **92.2%** | +92% | Blackwell 300, InfiniBand, Spectrum-X, NVLink |
| - Hyperscale | $37.869B | 46.4% | +115% | Public cloud and major internet companies |
| - AI Clouds, Industrial & Enterprise | $37.377B | 45.8% | +74% | Neocloud, enterprise, industrial, sovereign AI |
| Edge Computing | $6.369B | 7.8% | +29% | PC, workstations, gaming, autos, robotics, etc. |
| **Total** | **$81.615B** | **100%** | **+85%** | As of 2026-04-26 |

Sources: [NVIDIA Q1 FY2027 earnings release](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2027/default.aspx) and [SEC 10-Q](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000052/nvda-20260426.htm), 2026-05-20.

### Customer and Value-Chain Position

- **Upstream:** TSMC wafer manufacturing and advanced packaging, SK hynix / Micron / Samsung HBM, substrates, power, optical/copper interconnects, liquid cooling, and ODMs.
- **NVIDIA:** chip architecture, system design, interconnects, software stack, and ecosystem orchestration. It is the center of value capture and standard setting.
- **Downstream:** CSPs, consumer internet companies, AI model companies, neoclouds, sovereign AI, enterprises, and research institutions.
- **Concentration:** Three direct customers accounted for 54% of Q1 FY2027 revenue. These direct customers may be ODMs, system integrators, or cloud providers, so they should not be mechanically equated with end demand, but concentration risk is real.

## 3. Business and Competitive Analysis

### Industry Opportunity and Growth Drivers

NVIDIA management expects annual global AI infrastructure spending to reach $3T-$4T by 2030. This figure is management's long-term vision, not an independently verified TAM, and should be discounted. More verifiable near- and medium-term drivers include:

1. Large-model training continues to move toward higher parameter counts, more modalities, and longer context windows.
2. Inference is shifting from simple Q&A toward agentic AI, raising tokens and compute per task.
3. Data-center networking, storage, CPU, DPU, power, and cooling expand along with GPU clusters.
4. Sovereign AI, industrial, robotics, and automotive applications broaden the customer base beyond a small number of cloud giants.

### Competitive Landscape

- **AMD:** MI products keep narrowing the hardware gap and are price-competitive, but software, networking, and large-scale delivery ecosystem remain weaker than NVIDIA's.
- **Customer-designed ASICs:** Google TPU, Amazon Trainium, and internal chips from Meta / Microsoft may be more cost-efficient on fixed workloads. This is the main long-term share-eroding force.
- **Broadcom / Marvell:** Benefit from custom ASICs and networking as customers seek supplier diversification.
- **Traditional CPU / edge vendors:** Compete for AI server host value, edge inference, and automotive workloads.

### Moat Scorecard

| Moat source | Present? | Strength | Basis |
|---|---|---|---|
| Intangible assets | Yes | Strong | CUDA, compilers, libraries, system architecture, patents, and brand |
| Switching costs | Yes | Strong | Code, models, operations tooling, talent, and cluster architectures are costly to migrate |
| Network effects | Partial | Medium-strong | Developers, cloud services, software libraries, and hardware supply reinforce each other |
| Cost advantage | Partial | Medium | Scale spreads R&D and improves procurement, but manufacturing is outsourced and not structurally lowest-cost |
| Scale economies | Yes | Strong | Product cadence, supply lock-in, system validation, and channel reach |
| **Overall view** | **Yes** | **Wide** | Consistent with Morningstar's "Wide Moat" |

### Key Invalidation Points

- Data Center growth falls below 30% YoY quickly, and the decline is not only a base effect.
- Gross margin falls below 70% for two consecutive quarters while inventory and purchase commitments rise.
- Software ecosystems outside CUDA or customer-designed chips materially reduce NVIDIA share in mainstream inference.
- Vera Rubin / Rubin Ultra is delayed by more than one product-cycle phase.
- AI cloud customer financing worsens, causing order cancellations, slower collections, or channel inventory build.

## 4. Management and Governance

### Core Management Team

Jensen Huang has served as CEO and director since founding the company in 1993. His technical judgment, product cadence, and organizational culture provide unusual continuity. CFO Colette Kress has served since 2013, and operations leader Ajay Puri since 2009. The core team is stable.

### Ownership and Incentives

- As of 2026-03-23, Jensen Huang beneficially owned about **870.6M shares**, or **3.58%**.
- **96% of FY2026 CEO target pay was tied to company performance**. The economic incentive from founder ownership is far larger than annual cash compensation.
- FY2026 CEO total compensation was about $36.3M, small relative to the value of his shareholding.

Source: [NVIDIA 2026 DEF 14A](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000036/nvda-20260512.htm), 2026-05-12.

### Capital Allocation

- In Q1 FY2027, NVIDIA repurchased 108.3M shares for $20.2B, at an average price of about $184.6.
- On 2026-05-18, the board authorized an additional $80B buyback.
- Quarterly dividend was raised from $0.01 to $0.25, implying about 0.50% annual yield at the current price.
- Morningstar explicitly rates capital allocation as **Exemplary** in its 2026-03-18 report.

**My view:** R&D and supply-chain reinvestment come first, buybacks second, and dividends remain symbolic. The positive is that buybacks have more than offset equity-compensation dilution, with current share count down about 1.1% YoY to 24.22B. The risk is that large buybacks could consume cash near a cycle peak, but current net cash and FCF are sufficient.

### Governance Red Flags

- Founder-CEO dominance creates key-person risk.
- The CEO's children are employed by the company. The proxy discloses this and says they do not report directly to the CEO, but related-party governance should be monitored.
- Q1 FY2027 stock-based compensation was $1.93B, about 2.4% of revenue. The absolute amount is rising quickly, but buybacks currently cover it.

## 5. Financial Analysis

### Five-Year Trend

Amounts in $B; margins and ROIC are GAAP / standardized.

| Metric | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 | TTM to 2026-04 |
|---|---:|---:|---:|---:|---:|---:|
| Revenue | 26.9 | 27.0 | 60.9 | 130.5 | 215.9 | 253.5 |
| Revenue growth | 61.4% | 0.2% | 125.9% | 114.2% | 65.5% | 70.7% |
| Gross margin | 64.9% | 56.9% | 72.7% | 75.0% | 71.1% | 74.2% |
| Operating margin | 37.3% | 15.7% | 54.1% | 62.4% | 60.4% | 64.0% |
| Free cash flow | 8.1 | 3.8 | 27.0 | 60.9 | 96.7 | 119.1 |
| ROIC | 65.6% | 23.4% | 119.7% | 191.2% | 145.8% | 117.4% |

Sources: FY2026/FY2025/FY2024 primarily from [SEC FY2026 10-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm); five-year and TTM series cross-checked with [StockAnalysis/Fiscal.ai](https://stockanalysis.com/stocks/nvda/financials/) and its [cash-flow statement](https://stockanalysis.com/stocks/nvda/financials/cash-flow-statement/), updated through 2026-05-20. FY2026 FCF = operating cash flow $102.718B minus capex and related intangible purchases $6.042B.

### Latest Quarter and Earnings Quality

Q1 FY2027:

- Revenue $81.615B, gross margin 74.9%, operating income $53.536B.
- GAAP net income $58.321B, GAAP EPS $2.39.
- Non-GAAP net income $45.548B, EPS $1.87.
- Operating cash flow $50.344B.

**Important reconciliation:** "Other income, net" was about $15.929B this quarter, mainly from mark-to-market gains on equity securities. This made GAAP net income higher than operating income. Therefore TTM GAAP P/E of about 30.6x appears low but should not be fully treated as sustainable operating earnings. Relative valuation should rely more on adjusted EPS, future EPS, and FCF.

### Balance Sheet

As of 2026-04-26:

| Item | Value |
|---|---:|
| Cash and cash equivalents | $13.237B |
| Marketable debt securities | $37.098B |
| Marketable equity securities | $30.237B |
| Debt carrying value | $8.470B |
| Traditional net cash: cash + debt securities - debt | about $41.9B |
| Net financial assets including marketable equity securities | about $72.1B |

The company has no meaningful leverage pressure. However, $30.2B of marketable equity securities will introduce volatility into net income and book value.

### Peer Comparison

Metrics are as of around 2026-07-15. Fiscal-year definitions differ and the table is for cross-sectional reference only.

| Company | TTM gross margin | Operating margin | ROIC | TTM P/E | Forward P/E | EV/EBITDA |
|---|---:|---:|---:|---:|---:|---:|
| **NVIDIA** | **74.2%** | **64.0%** | **about 117%** | **about 30.6x** | **about 20-22x** | **about 29x** |
| Broadcom | 76.3% | 44.2% | 24.2% | 64.8x | 24.7x | 45.4x |
| AMD | 53.1% | 11.8% | 7.8% | 176.5x | 60.3x | 115.0x |
| TSMC | Not obtained in the same snapshot | Not obtained in the same snapshot | about 53% | 32.9x | 22.4x | 21.2x |

Sources: [NVIDIA](https://stockanalysis.com/stocks/nvda/statistics/), [Broadcom](https://stockanalysis.com/stocks/avgo/statistics/), [AMD](https://stockanalysis.com/stocks/amd/statistics/), [TSMC](https://stockanalysis.com/stocks/tsm/statistics/), S&P Global Market Intelligence, 2026-07-15. NVIDIA multiples recalculated using the IBKR price on 2026-07-17.

## 6. Valuation

The biggest valuation variable is not next quarter's revenue. It is the 2028-2031 AI infrastructure growth rate and NVIDIA's steady-state margin. All results below should be read as ranges.

### Method 1: Relative Valuation

Market consensus for FY2027 is revenue of about $392.8B and EPS of $8.98. Considering:

- FY2027 revenue is still expected to grow more than 80%;
- margins, ROIC, and balance sheet are materially better than key peers;
- growth will decelerate from a high base, and customer concentration plus export restrictions deserve a discount;

my justified FY2027 P/E range is **24-30x**, implying **$216-$269/share**. That implies **+7% to +34%** upside from the current price.

### Method 2: 10-Year DCF

**Model assumptions:**

- FY2027 revenue $392.8B, equal to market consensus.
- FY2028-FY2036 revenue growth: 35%, 27%, 20%, 15%, 12%, 10%, 8%, 7%, 6%.
- FCF margin gradually moves from 42% in FY2027 to 44%.
- Base WACC 9.5%, terminal growth 3.0%.
- Net cash $40.4B; diluted share count 24.22B.
- Unrealized gains on marketable equity securities are not capitalized separately to avoid double counting.

Base DCF value is **$261/share**.

#### WACC x Terminal Growth Sensitivity (per share, USD)

| WACC \ g | 2.0% | 3.0% | 4.0% |
|---|---:|---:|---:|
| 8.5% | 280 | 315 | 364 |
| 9.5% | 238 | **261** | 293 |
| 10.5% | 206 | 222 | 243 |

The core usable range is **$238-$293**. The extreme sensitivity range is $206-$364, showing that long-term assumptions matter a great deal.

#### Near-Term Growth Offset x Steady-State FCF Margin

"Growth offset" means FY2028-FY2031 revenue growth is shifted up or down by 5 percentage points versus the base case. WACC 9.5%, g 3%.

| Growth offset \ Steady-state FCF margin | 42% | 44% | 46% |
|---|---:|---:|---:|
| -5 pct | 216 | 225 | 233 |
| Base | 251 | **261** | 271 |
| +5 pct | 291 | 302 | 314 |

### Method 3: Mid-Cycle Earnings

Market consensus for FY2028 EPS is about $12.79. To avoid simply making high-growth-period earnings permanent, I use a **20-25x mid-cycle P/E**, giving 2028 value of $256-$320. Discounted back about 1.5 years at 9.5%, current value is about **$223-$279**.

The risk in this method is that the FY2028 consensus itself may change materially with AI capex and product cadence.

### Method 4: Morningstar Anchor

Morningstar raised its fair value estimate from $260 to **$280** on 2026-05-21 and rates NVIDIA 4 stars, wide moat, with very high uncertainty. Relative to $201.55, that implies about **+39%** upside.

**Data conflict note:** Morningstar's dynamic quote page search snippets showed clearly anomalous figures such as $791 / $968, likely due to parsing or split-adjustment issues. This report uses the dated analyst article from 2026-05-21 with explicit fair value of $280, not the dynamic-page anomaly.

Source: [Morningstar 2026-05-21 analysis](https://www.morningstar.com/stocks/nvidia-earnings-massive-ai-adoption-remains-track-shares-undervalued).

### Valuation Summary

| Method | Fair value range | Implied upside vs. $201.55 | Weight | Notes |
|---|---:|---:|---:|---|
| FY2027 relative valuation | $216-$269 | +7% to +34% | 30% | 24-30x x EPS $8.98 |
| DCF | $238-$293 | +18% to +45% | 35% | WACC 9.5%, g 2%-4% |
| FY2028 mid-cycle earnings | $223-$279 | +11% to +38% | 20% | 20-25x, discounted 1.5 years |
| Morningstar | $280 | +39% | 15% | 2026-05-21 |
| **Comprehensive view** | **$235-$285** | **+17% to +41%** | **100%** | Midpoint about $260 |

**My view:** The current price is below the fair-value range, but the margin of safety is not overwhelming. If the next three years of growth are cut by 5 percentage points and steady-state FCF margin falls to 42%, model value is about $216, close to the current price. That is why the action should be staged buying rather than a full position at once.

## 7. Analyst View Summary

| Item | Value | Source / time |
|---|---:|---|
| Buy / strong buy / hold / sell | 48 / 2 / 3 / 0 | MarketBeat, 2026-07-17 |
| Target price range | $218-$500 | MarketBeat, 2026-07-17 |
| Average target price | $304.26 | MarketBeat, 2026-07-17 |
| Median target price | Not obtained | - |
| Another source | 61 analysts, average $301.62 | StockAnalysis / S&P Global, 2026-07-15 |

Sources: [MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/NVDA/forecast/) and [StockAnalysis](https://stockanalysis.com/stocks/nvda/statistics/).

**Definition reconciliation:** The two platforms use different analyst counts, 53 vs. 61, but average target prices are close, about $302-$304, so the direction is consistent. Sell-side targets usually reflect 12-month growth realization and should not be treated as intrinsic value.

**My difference from the market:** The sell-side average target is about 17% above my comprehensive midpoint. My midpoint is lower because:

1. I am more conservative on growth deceleration after FY2028.
2. I do not treat Q1 FY2027 equity-investment gains as core earnings.
3. I apply a larger discount for customer concentration, export restrictions, and long-term erosion from customer-designed ASICs.

## 8. Recent News and Catalysts

| Timing | Event | Bull / bear | Impact logic |
|---|---|---|---|
| 2026-05-20 | Q1 FY2027 revenue $81.6B; Q2 guidance $91B | Bullish | Growth accelerated even on a high base and excluded China data-center compute revenue |
| 2026-05/06 | Vera Rubin entered production ramp | Bullish | Extends annual product cadence and lifts value across GPU, CPU, networking, and full systems |
| 2026-06-22 | Multiple system vendors and research institutions announced Vera Rubin systems | Bullish | Customer validation and ecosystem expansion |
| 2026-07-06 to 07-15 | Rumors of Rubin Ultra / Kyber delays; company said roadmap intact and Rubin is in production | Two-way | Need to distinguish 2026 Rubin from 2027 Rubin Ultra rack systems; the latter still needs verification |
| Expected 2026-08-26 | Q2 FY2027 earnings, not yet officially confirmed by the company | Two-way | Watch delivery of $91B guidance, Q3 guidance, gross margin, and Rubin orders |
| 2026 H2 | Vera Rubin cloud instances and full-system deployment | Bullish | On-time delivery would validate product cadence and supply-chain execution |

Sources: [NVIDIA Q1 FY2027](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2027/default.aspx), [Vera Rubin production announcement](https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory), [Vera Rubin scientific systems](https://nvidianews.nvidia.com/news/nvidia-vera-rubin-delivers-world-class-supercomputers-for-science), [Rubin delay coverage and company response](https://www.tomshardware.com/tech-industry/artificial-intelligence/nvidias-huang-vows-to-deliver-giant-amounts-of-vera-rubin-company-says-that-our-roadmap-is-intact), [expected earnings date](https://www.benzinga.com/quote/NVDA/earnings).

## 9. Investment Conclusion

### Clear Conclusion

**Rating: moderately undervalued. Suggested action: staged buying / continue holding existing positions. I do not suggest initiating a full position at once.**

Comprehensive fair value is **$235-$285**, with a midpoint around **$260**. At $201.55, the range implies roughly 17%-41% upside. However, DCF is highly sensitive to long-term growth and margin assumptions, and the 52-week trading range is wide. The midpoint should not be treated as a guaranteed target price.

### If This Were Cash Today, Would I Buy?

**Yes, but only in stages.**

My execution framework:

1. Deploy about one-third of the intended position first.
2. If the price returns to $180-$190 and fundamentals have not deteriorated, add another tranche.
3. Keep the remaining allocation for after Q2 FY2027 earnings verify the $91B guide, gross margin, and Q3 outlook.
4. For a diversified portfolio, I would keep the initial position around 3%-5%. I would consider increasing it only after additional performance validation and if valuation remains reasonable. The upper limit depends on the investor's risk tolerance.

This is not because the business quality is insufficient. It is because NVIDIA is already a nearly $5T market-cap company. Future returns depend more on how long extremely high profitability can persist than on the simple statement that "AI will grow."

### Monitoring Indicators

| Indicator | Current level | Threshold / signal | Meaning |
|---|---:|---|---|
| Data Center growth | Q1 FY2027 +92% YoY | Below +30% for two consecutive quarters without a base-effect explanation | Risk that AI capex or share has peaked |
| Gross margin | 74.9% | Below 70% for two consecutive quarters | Product mix, supply cost, or competition worsening |
| ACIE growth and share | +74%; 45.8% of revenue | Growth stays above Hyperscale | Customer diversification and lower hyperscaler concentration |
| Inventory / receivables vs. revenue | Inventory $25.8B; receivables $40.7B | Growth materially above revenue, worsening DSO | Channel buildup or collection risk |
| Rubin / Rubin Ultra cadence | Rubin production ramp | Key cloud deployments or rack deliveries delayed by more than two quarters | Product-cycle and competitive-position risk |
| Valuation | About 22.4x FY2027 EPS | >30x while consensus stops rising | Worse risk/reward; <20x with stable fundamentals becomes more attractive |

---

## Appendix: Sources and Timestamps

| Data item | Source | Time |
|---|---|---|
| Real-time price, 52-week high/low, YTD, historical price | Interactive Brokers | 2026-07-17 13:16 BST |
| Q1 FY2027 financials and guidance | [NVIDIA IR](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2027/default.aspx) | 2026-05-20 |
| Q1 FY2027 10-Q, customer concentration, balance sheet | [SEC](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000052/nvda-20260426.htm) | As of 2026-04-26 |
| FY2026 10-K, annual financials | [SEC](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm) | As of 2026-01-25 |
| Ownership, executive compensation, governance | [SEC 2026 Proxy](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000036/nvda-20260512.htm) | 2026-05-12 |
| Morningstar fair value / moat | [Morningstar](https://www.morningstar.com/stocks/nvidia-earnings-massive-ai-adoption-remains-track-shares-undervalued) | 2026-05-21 |
| TTM financials, share count, peer multiples | [StockAnalysis / S&P Global](https://stockanalysis.com/stocks/nvda/statistics/) | Around 2026-07-15 |
| Sell-side consensus | [MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/NVDA/forecast/) | 2026-07-17 |
| Vera Rubin product updates | [NVIDIA Newsroom](https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory) | 2026-05/06 |

### Data Quality Notes

1. NVIDIA's fiscal year is not the calendar year. FY2027 Q1 ended 2026-04-26, and FY2026 ended 2026-01-25.
2. Current valuation multiples are recalculated using the IBKR real-time quote and may differ from aggregation-site closing-price snapshots from 2026-07-15/16.
3. The IBKR snapshot showed dividend yield of 0.14%, inconsistent with the new annual dividend of $1.00/share after 2026-05-18. I treat this as a stale field and use the company announcement, which implies about 0.50% at the current price.
4. Morningstar's dynamic page showed anomalous parsed values. This report uses only the dated 2026-05-21 fair value of $280 with explicit analyst text.
5. Analyst target-price coverage differs by platform. This report keeps those differences visible.

> Disclaimer: The author is not a licensed investment adviser. Valuation models depend on assumptions, and actual outcomes may differ materially. Please make independent decisions based on your own financial position, tax situation, time horizon, and risk tolerance.
