# Momentum, Relative-Strength and Flow/Fundamental-Driven Swing Strategies in Indian Equities

Scope note: research was limited to ~20 tool calls. Many academic papers were only accessible as abstracts. Several topics (delivery %, F&O OI build-up, FII flow as stock-level signal, regime filters, India VIX) yielded NO rigorous source and are listed as gaps rather than filled with unsourced claims.

## Q1. Cross-sectional momentum / relative strength, sector rotation, short-term reversal in India

### Takeaway
Academic evidence consistently finds intermediate-horizon (6-12 month) momentum in India, with reversal at ~3-year horizons and (one study) at ~1-6 months after large monthly shocks. Index-provider momentum products exist (Nifty200 Momentum 30, Alpha 50), but practitioner evidence suggests the premium is concentrated in less liquid names and carries very deep drawdowns (60-75%) in long backtests.

### Cited Findings
**Academic: momentum**
- Joshipura (NSE research paper), NSE-listed firms, monthly data Jan 1995-Dec 2008 (CMIE Prowess; 260 to 576 firms): momentum profits at 6-month and 1-year horizons; contrarian profits at a 3-year horizon. 3-year loser-minus-winner spread peaks ~34.5% in month 35; 1-year formation shows loser-minus-winner significantly negative (about -29.4% at month 9), driven mostly by winners. Author argues risk (beta) does not explain it. — [NSE paper](https://nsearchives.nseindia.com/content/research/res_paperfinal223.pdf)
- Sehgal and Jain, "Dissecting sources of price momentum: evidence from India" (Int. J. Emerging Markets 2015): 6-6 momentum on 493 BSE 500 companies; CAPM and Fama-French fail to explain it; authors attribute part to overreaction and part to macro-variable (rational) sources. Sample period not stated on the page. — [IDEAS/RePEc](https://ideas.repec.org/a/eme/ijoemp/ijoem-04-2014-0046.html)
- Paper on momentum in stock and sector returns (Emerald, Sehgal-related; authorship not confirmed on page): 6-6 strategies stronger than 12-12; CAPM/FF3 don't explain; a sectoral momentum factor captures part of stock momentum, suggesting stock momentum may largely derive from sector momentum. Period not visible (paywalled). — [Emerald](https://www.emerald.com/insight/content/doi/10.1108/09727981111129327/full/html)
- Garg and Varshney, "Momentum Effect in Indian Stock Market: A Sectoral Study" (Global Business Review 2015), 2000-2013: momentum strategy robust, present across industries; no return figures available in abstract. — [IDEAS](https://ideas.repec.org/a/sae/globus/v16y2015i3p494-510.html)
- "A study of contrarian and momentum profits in Indian stock market" (IJFM), all NSE stocks Jan 1997-Mar 2013: significant short-term momentum and long-term overreaction (contrarian). Horizons undefined on page. — [Publishing India](https://www.publishingindia.com/archive/ijfm/a-study-of-contrarian-and-momentum-profits-in-indian-stock-market)

**Academic: short-term reversal**
- "On Stock Return Patterns Following Large Monthly Price Movements: Empirical Evidence from India": significant reversals for up to six months after large monthly moves (up or down); bigger shocks give bigger reversals; reversals after large declines may be economically exploitable. Sample period not stated on the page. — [CEEOL](https://ceeol.com/search/article-detail?id=1054639)
- Note tension: Joshipura finds 6-month momentum in 1995-2008 while this paper finds reversal over up to 6 months after *large* monthly moves — the difference likely reflects conditioning on extreme moves vs. ranking; this is my reading, not stated by the sources.

**Index-provider products**
- Nifty200 Momentum 30 methodology: top 30 of Nifty 200 by Normalised Momentum Score (6- and 12-month returns, volatility-adjusted); weights = free-float mcap x momentum score; cap = lower of 5% or 5x free-float-mcap weight; semi-annual rebalance (June/December); base 1 Apr 2005, launched 25 Aug 2020. Factsheet (dated 30 Sep 2026) shows TRI CAGR ~18.30% since inception, 9.28% 5-yr, -0.47% 1-yr, std dev ~19-22%, beta vs Nifty 50 ~1.18 (labels scrambled in extraction — treat risk figures as unverified). Pre-Aug 2020 history is back-tested. — [NSE factsheet](https://www.niftyindices.com/Factsheet/Factsheet_Nifty200_Momentum30.pdf)
- Nifty Alpha 50 methodology: eligibility = top 300 by avg free-float mcap and turnover, 1-year listing, traded 100% of days; ranks by alpha over trailing 1 year (ending last trading day of Feb/May/Aug/Nov); excludes negative alpha; top 50 selected, weights proportional to alpha, 100% buffer (existing constituent retained if rank within top 100); quarterly reconstitution; base 31 Dec 2003; no single-stock cap specified (only SEBI concentration-norm screening). Alpha formula and benchmark not stated in document. — [NSE methodology](https://www.niftyindices.com/Methodology/Method_Nifty_Alpha_50.pdf)
- PrimeInvestor: Alpha 50 TRI beat Nifty Midcap 150 TRI ~72% of rolling 3-yr windows; Alpha beat Momentum in 87% of rolling 3-yr windows but momentum led over rolling 5-yr from 2010; author calls it "a toss of coin"; both "significantly more volatile"; much data is back-tested. Drawdown/turnover not quantified. — [PrimeInvestor](https://primeinvestor.in/reports/should-you-invest-in-alpha-index-funds/)

**Practitioner backtests (not peer-reviewed)**
- Capitalmind, Jan 2007-2019, top-30 by 252-day return, monthly rebalance, equal weight, excluding costs/taxes, survivorship addressed: simple momentum ~12.6% CAGR, gain-loss ~14.7%, volatility-adjusted ~16.8% vs Nifty ~8.9%, Nifty 500 ~8.7%. Simple momentum beat indices in only 6 of 13 years, notably lagging 2008 and 2016. No regime filter tested. — [Capitalmind](https://www.capitalmind.in/insights/momentum-investing-basics-india)
- Freefincal/BacktestIndia (period Dec 2006-Jun 2025, annual rebalance, equal weight, net of costs and taxes): Momentum 30 net CAGR 14.60%, MDD -70.61%; Nifty 50 10.41%, MDD -55.12%. Splitting the 30 by scaled turnover: low-turnover half 19.43% CAGR (MDD -66.41%), high-turnover half 8.51% (MDD -75.09%, >8 years to recover). Author concludes momentum looks like an illiquidity premium. Caveats: promotional, byline inconsistency, single construction, no sensitivity tests. — [Freefincal](https://freefincal.com/is-indian-momentum-investing-just-a-liquidity-illusion/)

### Inferences
- A 6-12 month relative-strength rank with monthly-to-semi-annual rebalance is the best-supported rule in India; expect 60-75% drawdowns in unfiltered long-only form and weak years (2008, 2016 per Capitalmind).
- Capacity and execution matter: if the premium lives in low-turnover names, swing traders with small size may keep an edge that large index funds cannot; slippage in those names is also higher (inference).
- Short-term (1-month) reversal after extreme moves is plausible but weakly evidenced; use as an entry-timing refinement at most.

### Gaps
- No access to Alpha Architect / AQR / Fama-French-IIMA India factor data (Agarwalla-Jacob-Varma IIMA factor library) in this pass; no factor-level momentum (WML) return, turnover or crash statistics for India.
- No official NSE turnover/drawdown figures for Momentum 30 or Alpha 50 (factsheet labels scrambled).
- No quantitative sector-rotation backtest on Nifty sectoral indices found.
- No peer-reviewed evidence on a "RS rating" (IBD-style) specifically in India.

## Q2. Delivery %, volume spikes, bulk/block deals, FII/DII flows, insider buying, PEAD, results gap, F&O OI build-up

### Takeaway
Only bulk deals have solid NSE event-study evidence, and it shows gains accrue mainly BEFORE/around the public disclosure (front-running), so they are hard to capture after disclosure. PEAD evidence in India is mixed/negative, and I found no credible study for delivery %, OI build-up or insider-buy signals.

### Cited Findings
- Bulk deals, NSE, Jan 2010-Dec 2019 (81,506 records; ~12,229 used in regressions): pre-event volume rises ~90% above 30-day baseline by day before event; delivery rises ~1.2%; pre-event CAR [-7,-1] ~2.8% for individual Only Buy deals; cumulative return ~6.3% by day 0 and ~5.9% at day +7 (i.e., little additional drift after the event day); authors say front-runners can earn 5-7% within a week around the event. Volume and delivery changes significantly explain pre-event CAR. — [IIM Calcutta WP 863](https://studentlive.iimcal.ac.in/sites/all/files/pdfs/wp_863.pdf); [Emerald (MF 2021)](https://emerald.com/insight/content/doi/10.1108/MF-08-2021-0374/full/pdf)
- PEAD, NSE: a study of 100 NSE firms (1,130 observations, 2014-2018) finds abnormal returns negatively associated with surprise and concludes the market is efficient to earnings announcements; no consistent value-glamour profit. Small sample, short period. — [Trends Economics and Management](https://journals.lib.vutbr.cz/index.php/trends/article/view/541)
- A Nottingham repository study and an IIMB repository item on India earnings announcements/PEAD appeared in search results but I did not open them; their conclusions are unverified. — [Nottingham](https://eprints.nottingham.ac.uk/26569); [IIMB](https://repository.iimb.ac.in/handle/2074/17935)
- Insider trading: LEAP blog (2009-2023, NSE firms) studies reaction to SEBI/SAT enforcement orders, not insider buying. Finds no significant CAR (176 SEBI, 42 SAT events). This does NOT test whether SAST/PIT insider-purchase disclosures predict returns. — [LEAP blog](https://blog.theleapjournal.org/2026/05/market-reaction-to-insider-trading.html)
- NITK thesis "An Empirical Analysis of Legal Insider Trading in India" appeared in search; I did not read it. — [NITK](https://idr.nitk.ac.in/handle/123456789/14150)
- FII flows: several Indian journal abstracts on FII-Nifty linkages surfaced (e.g. [IUP](https://www.iupindia.in/305/IJAF_Foreign_Institutional_Investment_16.html)) but I did not read them; no verified conclusion.

### Inferences
- A rule "buy after bulk deal appears in end-of-day NSE data" likely captures little: most of the move precedes or coincides with disclosure (inference from the paper's cumulative-return path flattening after day 0).
- A delivery-percentage/volume-spike filter is theoretically supported only as an *ingredient* of pre-event front-running; not validated as a stand-alone signal.

### Gaps
- Delivery %: no academic or rigorous backtest found; only broker blog content (not cited as evidence).
- F&O OI long/short build-up: search returned only glossary/blog pages; no evidence. Treat as unverified.
- PEAD in India with large samples (e.g., SUE-sorted portfolios over 2000-2024) and earnings-gap continuation: not found.
- Promoter buying / SAST creeping acquisition returns: not found.
- FII/DII flow as stock- or sector-level swing signal: not verified; index-level flow studies unread.

## Q3. Market-regime filters (Nifty vs 200 DMA, breadth, India VIX)

### Takeaway
I found no credible, sourced backtest quantifying the effect of a Nifty-200DMA, breadth or India VIX filter on Indian momentum/swing results. The one practitioner momentum study retrieved explicitly tested no regime filter.

### Cited Findings
- Capitalmind's 2007-2019 momentum study tests no market-regime or trend filter, and states momentum has deeper drawdowns and lags in corrections. — [Capitalmind](https://www.capitalmind.in/insights/momentum-investing-basics-india)
- Long-only Momentum 30 backtest drawdowns of -66% to -75% (2006-2025) show the scale of risk a regime filter would need to address. — [Freefincal](https://freefincal.com/is-indian-momentum-investing-just-a-liquidity-illusion/)
- Search results for 200DMA/VIX filters returned only generic blog/TradingView/QuantConnect pages; none read or verified.

### Inferences
- Because Indian momentum drawdowns concentrate in crashes (2008 listed as a weak year), a trend filter is plausible, but its benefit, whipsaw cost and tax impact (STCG 20%, per Freefincal's assumption) are untested here.

### Gaps
- All quantitative regime-filter evidence (Nifty > 200 DMA, % stocks above 50/200 DMA, India VIX thresholds) is missing; recommend the coordinator treat these as hypotheses requiring the user's own backtest.
- No academic work found on momentum crashes / time-varying momentum in India.
