# Indian Market Rules, Costs and Data Constraints for Swing Equity Strategies (as of Oct 2026)

Research date 2026-10-17. Research budget was about 15 tool calls; several items rest on secondary sources and are flagged. Items I could not source are in Gaps.

## 1. Transaction costs: delivery (CNC) vs intraday vs F&O

### Takeaway
For a delivery swing trade at Zerodha, explicit round-trip cost is roughly 0.24% of trade value plus a flat ~Rs 15.34 DP fee on the sell. Brokerage is zero for individuals. STT (0.1% each side) dominates. Budget 2026 raised F&O STT from 1 April 2026 but left equity delivery and intraday STT unchanged. Add slippage/impact separately.

### Cited Findings
- Zerodha official charges page. Equity delivery: brokerage zero; STT 0.1% on buy and sell; NSE exchange transaction charge 0.00307% (BSE 0.00375%); SEBI turnover fee Rs 10 per crore; stamp duty 0.015% (Rs 1,500 per crore), buy side only; GST 18% on (brokerage + SEBI fee + transaction charges). — [Zerodha charges](https://zerodha.com/charges)
- Zerodha intraday equity: brokerage lower of 0.03% or Rs 20 per executed order; STT 0.025% sell side; stamp duty 0.003% buy side. — [Zerodha charges](https://zerodha.com/charges)
- Zerodha futures: brokerage lower of 0.03% or Rs 20; STT 0.05% sell side; NSE transaction charge 0.00183%; stamp 0.002% buy side. — [Zerodha charges](https://zerodha.com/charges)
- Zerodha options: flat Rs 20 per executed order; STT 0.15% of premium on sell side (0.15% of intrinsic value if bought and exercised); NSE transaction charge 0.03553% of premium; stamp 0.003% buy side. Brokerage also applies to expired/exercised/assigned options. — [Zerodha charges](https://zerodha.com/charges)
- DP charges at Zerodha: Rs 15.34 per scrip per sell day (Rs 3.5 CDSL + Rs 9.5 Zerodha + Rs 2.34 GST), regardless of quantity. Charged only on sells (debits). — [Zerodha charges](https://zerodha.com/charges)
- Non-individual delivery clients (companies, partnerships, trusts, HUFs) pay 0.1% or Rs 20 brokerage, whichever is less, instead of zero. Call-and-trade Rs 50 per order. — [Zerodha charges](https://zerodha.com/charges)
- MTF at Zerodha: interest 0.04% per day (Rs 40 per lakh) on the funded amount from T+1 until sold; brokerage 0.3% or Rs 20 per order; pledge/unpledge Rs 15 + GST per ISIN per request. General pledging Rs 30 + GST per request per ISIN. — [Zerodha charges](https://zerodha.com/charges)
- Budget 2026 STT change on derivatives, scheduled from 1 April 2026: futures (sell) 0.02% to 0.05%; options premium 0.10% to 0.15%; options exercise 0.125% to 0.15%. Equity delivery 0.1% and intraday 0.025% unchanged. — [Finnovate](https://www.finnovate.in/learn/blog/budget-2026-stt-hike-fno-trades-explained); the Zerodha page's current 0.05% / 0.15% figures corroborate the new rates. — [Zerodha charges](https://zerodha.com/charges)
- Conflict: a StockCalc article dated 17 Oct 2026 still lists old F&O STT (futures 0.0125%, options 0.0625%), exchange charge 0.00322% for equity, and DP Rs 13.5 + GST. These disagree with Zerodha's own page and with the Finnovate source; treat StockCalc as stale/unreliable. — [StockCalc](https://stockcalc.in/blog/zerodha-brokerage-charges-2026-full-breakdown)
- The Oct 2024 change (futures STT 0.0125% to 0.02%, options 0.0625% to 0.1%, effective 1 Oct 2024) is from my background knowledge; I did not retrieve a primary source in this session. It is consistent with the "old" rates in the Finnovate table (0.02% / 0.10%).

### Inferences
- My calculation from Zerodha's rates, delivery round trip on a notional N bought and sold at the same value: buy side = 0.1% STT + 0.00307% exch + 0.001% SEBI + 18% GST on (0.00407%) = ~0.00073% + 0.015% stamp = ~0.1198%. Sell side = 0.1% + 0.00307% + 0.001% + 0.00073% = ~0.1048% plus Rs 15.34 DP. Round trip about 0.2246% + Rs 15.34 (about 0.24% on a Rs 1 lakh trade including DP; DP is negligible above ~Rs 5 lakh per scrip). Model as a ~0.22-0.25% fixed round-trip cost.
- Model spread/slippage on top: roughly 0.05-0.15% per side for liquid Nifty 500 names is a plausible assumption, not sourced; larger for small caps. Total all-in friction is likely 0.4-0.7% round trip, which means a swing needs a gross edge well above that. This is an assumption and should be calibrated against paper-trade fills.
- Costs vary by broker (Dhan, etc. have similar statutory components but different brokerage/DP). The statutory parts (STT, stamp, SEBI fee, exchange fee) are broker-independent.
- Selling in multiple partial lots on one day incurs only one DP charge per scrip per day.

### Gaps
- I did not retrieve Dhan's own charge sheet; confirm Dhan delivery brokerage and DP fee before live use.
- No primary Gazette/Finance Act text for the 1 April 2026 STT change was fetched.
- No primary source retrieved for the Oct 2024 STT change or for exchange-charge revisions in 2025-26 (exchange fee schedules change periodically).

## 2. Short selling, margin, settlement

### Takeaway
Delivery short selling is not permitted; in cash, swings are long-only. Shorting requires intraday (must square off same day), stock futures/options, or securities lending and borrowing. Settlement is T+1; BTST sales carry short-delivery/auction risk.

### Cited Findings
- Under T+1, a Monday purchase is delivered Tuesday; BTST lets you sell on Tuesday before delivery, with the sale settling Wednesday. Proceeds of a BTST sale cannot be used the same day. If shares are not delivered, the seller faces short delivery. — [Zerodha support: BTST](https://support.zerodha.com/category/trading-and-markets/trading-faqs/articles/btst-meaning)
- Zerodha has dedicated pages on short-delivery consequences (auction penalties) - [Zerodha support: short delivery](https://support.zerodha.com/category/trading-and-markets/trading-faqs/general/articles/what-is-short-delivery-and-what-are-its-consequences) - but I did not read the numbers.
- MTF interest at Zerodha is 0.04% per day (about 14.6% annualised, my arithmetic), charged from T+1 until sale. — [Zerodha charges](https://zerodha.com/charges)
- Futures carry sell-side STT 0.05% and options 0.15% of premium after April 2026 (see section 1), raising the cost of using derivatives as the short leg.

### Inferences
- Backtest/paper engine should: allow only long entries in cash equity; model shorts only via futures (lot sizes, rollover, F&O-eligible universe, margin) or exclude them; treat any intraday short as same-day square-off only.
- Model T+1 cash availability: sale proceeds are usable for new delivery buys in a way that depends on broker (typically a usable-margin credit); BTST proceeds cannot be reused same day.
- Pledge/MTF add real costs (pledge fees, 0.04%/day interest) - include if the strategy uses leverage.

### Gaps
- Peak-margin framework rules (SEBI, phased 2020-21 and intraday monitoring from 2025) not retrieved; I only know them from background knowledge, unverified here.
- SLB mechanics, eligible-stock list and borrow rates not retrieved; practically SLB is thinly used by retail.
- Auction penalty percentages and exact short-delivery rules not fetched.
- Current T+0 optional settlement status not checked.

## 3. Surveillance, circuits, T2T, F&O ban, holidays

### Takeaway
A swing universe must exclude or penalise stocks in GSM/ASM/ESM/T2T and tight price bands; these can cut liquidity to once a week or force 100% upfront deposits. F&O ban affects only derivative positions, not cash.

### Cited Findings
- Zerodha's August 2026 surveillance bulletin: ESM Stage II moves scrips to T2T with a 2% price band and periodic call auction trading daily; GSM Stage III allows trading only once a week (Monday or first trading day of the week) and the buyer must deposit an Additional Surveillance Deposit of 100% of trade value; ASM scrips under IBC insolvency process also trade once a week. Holdings in such scrips are not visible on Kite on other days. 25 scrips were listed that month (21 under GSM Stage III). — [Zerodha Market Intel](https://zerodha.com/marketintel/bulletin/454257/surveillance-measure-on-scrips-august-2026)
- NSE publishes surveillance circulars (SURV series) regularly in 2026, i.e. the lists change frequently. — [NSE circular](https://nsearchives.nseindia.com/content/circulars/SURV75054.pdf)
- F&O ban: stock enters ban when open interest reaches 95% of Market-Wide Position Limit; ban lifts when OI falls below 80% of MWPL. In ban no new positions that increase OI; existing positions can be closed; cash market trading is unaffected. Brokers warn at 80/85/90%. — [Tradejini](https://www.tradejini.com/blogs/what-causes-a-stock-to-enter-an-fo-ban)
- NSE equity trading holidays 2026 (weekdays): Jan 15, Jan 26, Mar 3, Mar 26, Mar 31, Apr 3, Apr 14, May 1, May 28, Jun 26, Sep 14, Oct 2, Oct 20, Nov 10, Nov 24, Dec 25. The source's FAQ says 15 but the table lists 16. Remaining in 2026 after 17 Oct: Oct 20, Nov 10, Nov 24, Dec 25. — [ClearTax](https://cleartax.in/s/nse-holidays-2026) (secondary; verify against NSE's official holiday circular)

### Inferences
- Universe filter: require not-in-GSM/ASM/ESM/T2T on both entry date and holding window; model point-in-time membership (the lists are dated). Backtests that ignore this overstate fills in illegal-to-exit stocks.
- Gap risk: stocks in 2% band or call auction can lock; a stop-loss may not execute. Model exit failure/slippage on circuit-hit days.
- Use the NSE holiday calendar to compute holding days and avoid signal dates on non-trading days; holiday weekends raise overnight gap exposure.
- Results-season gap risk: no source retrieved; handle by event calendar (earnings dates) and wider slippage/gap assumptions.

### Gaps
- Daily price band tiers (2/5/10/20%) and rules for revision, and index-stock exemption, not sourced (only the 2% T2T band appeared).
- Liquidity threshold norms (e.g. minimum ADV/impact cost) not sourced; set by strategy design.
- Corporate action treatment (split/bonus/rights/dividend adjustment methodology) not sourced; see Data section.
- Official NSE holiday circular not fetched.

## 4. Tax

### Takeaway
Equity delivery gains: STCG (held 12 months or less) 20%; LTCG (more than 12 months) 12.5% above Rs 1.25 lakh per year exemption. Intraday equity is speculative business income; F&O is non-speculative business income, taxed at slab rates with audit rules based on turnover.

### Cited Findings
- STCG on listed equity (s.111A) 20%; LTCG (s.112A) 12.5% with Rs 1.25 lakh annual exemption; long-term means more than 12 months for listed equity; grandfathering for assets bought on or before 31 Jan 2018; Budget 2024 changes apply to transfers after 23 July 2024. — [ClearTax](https://cleartax.in/s/long-term-capital-gains-ltcg-tax)
- The same page does not describe any 2026 change to these rates under the Income Tax Act 2025 (112A becomes Section 198; the 1961 Act applies to income up to 31 March 2026). — [ClearTax](https://cleartax.in/s/long-term-capital-gains-ltcg-tax)
- Zerodha Varsity: intraday equity is speculative (turnover = absolute sum of profit and loss differences); F&O is non-speculative (turnover = total of favourable and unfavourable differences, plus option premium received); delivery trades treated as business income count total sale value as turnover. Audit threshold quoted as Rs 10 crore turnover for FY2023-25 (may have changed), with a further 6% profit test below that. — [Zerodha Varsity](https://zerodha.com/varsity/?p=2148)

### Inferences
- Swing trades held under 12 months are taxed 20% on net gains; losses can be set off against gains per capital-gains rules (set-off and carry-forward years not verified here). Model a post-tax return as gross minus costs times 0.8 for winners.
- The tax treatment (investment vs business) is a taxpayer choice constrained by consistency; confirm with a CA.
- STT is not deductible against capital gains.

### Gaps
- Capital-loss set-off and carry-forward period (commonly 8 years) not sourced here.
- Whether a swing trader's delivery gains may be reclassified as business income not sourced.
- Current tax-audit thresholds (44AB) for FY2026-27 not verified.

## 5. SEBI retail algo trading framework

### Takeaway
Retail API access is only via broker-registered static IP, with 2FA daily, an exchange Algo-ID tag on all algo orders, and a 10 orders-per-second line separating ordinary API users from algos needing exchange registration. Full mandatory enforcement started 1 April 2026. A low-frequency daily swing system sits comfortably below the threshold.

### Cited Findings
- SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/2025/0000013 dated 4 Feb 2025; fully mandatory for brokers from 1 April 2026 (phased milestones from Oct 2025 to Jan 2026). — [Sahi](https://www.sahi.com/blogs/sebi-algo-trading-rules-2026-what-every-retail-trader-must-know-before-april)
- Orders under 10 OPS: regular API user, not requiring registration; above, algo registration applies. Every algo order carries an Algo-ID from 1 April 2026. White-box algos registered once; black-box requires SEBI Research Analyst registration; providers must go through a registered broker. — [Sahi](https://www.sahi.com/blogs/sebi-algo-trading-rules-2026-what-every-retail-trader-must-know-before-april)
- FYERS notice dated 10 March 2026: orders accepted only from a registered App ID mapped to a whitelisted static IP; daily 2FA once per trading day (continuous refresh-token sessions no longer supported); max 10 orders per second; market orders auto-converted to MPP (Market Price Protection) orders; third-party platforms must be empanelled and hosted in broker infrastructure. — [FYERS](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/)
- TrueData summary of the NSE implementation standards: one primary and one secondary static IP per trader; IP changes at most once a week (except emergencies); family members may share a static IP with broker approval; the page cites NSE circular INVG67858 but dates it inconsistently (says effective 1 Aug 2025 while other sources say 1 April 2026). — [TrueData](https://www.truedata.in/blog/new-nse-rules-on-retail-algo-trading-what-traders-platforms-and-brokers-need-to-know) (secondary; conflicts on dates)
- Dhan rate limits: order APIs 10/sec, 250/min, 1,000/hr, 7,000/day; data APIs 5/sec and 100,000/day; quote APIs 1/sec; up to 25 modifications per order. — [Dhan docs](https://dhanhq.co/docs/v2/)

### Inferences
- A swing system placing a few dozen orders per day needs only: a registered static IP at the broker, daily token/2FA flow (automation must handle daily re-login), market orders replaced by limit or MPP-converted orders, and respect of the 10/sec Dhan limit. Paper trading should simulate MPP behaviour (market order = limit within protection band) and rejection on rate limits.
- Cloud/dynamic-IP hosting needs a fixed egress IP; changing it is limited to once a week - an operational risk for failover.

### Gaps
- I did not read the SEBI/NSE circulars themselves; details above are from broker/vendor summaries, which disagree on some dates.
- Dhan-specific static IP and token validity docs not retrieved (the page fetched did not cover them).
- Exact tolerance for the 10 OPS threshold and any 2026 extension/relaxation not verified.

## 6. Data: OHLCV, bhavcopy, adjustments, survivorship

### Takeaway
Dhan's historical API provides daily OHLCV; NSE bhavcopy (sec_bhavdata_full) provides delivery quantities. NSE is changing bhavcopy distribution formats in Nov 2026. Whether Dhan daily candles are corporate-action adjusted is undocumented in the page I read - verify before use. Nifty 500 is rebalanced semi-annually, so using today's constituents creates survivorship bias.

### Cited Findings
- Dhan: POST /charts/historical returns daily OHLC + volume (open, high, low, close, volume, timestamp, open_interest); params securityId, exchangeSegment, instrument, expiryCode, oi, fromDate, toDate (non-inclusive); data available back to scrip inception; the 90-day cap applies only to the intraday endpoint. Adjustment status, rate limits and static-IP rules not stated on that page. — [Dhan historical data docs](https://dhanhq.co/docs/v2/historical-data/)
- NSE notification NSE/MSD/76457 dated 21 Sep 2026: new .DAT format CM Bhavcopy (FCM_INTRM_BCDDMMYYYY.DAT) from 12 Oct 2026; legacy .MS/.MD bhavcopy on Extranet and NNF broadcasts discontinued on 16 Nov 2026 (moved from 12 Oct). — [TeamLease RegTech summary](https://teamleaseregtech.com/updates/article/59714/nse-notified-regarding-the-streamlining-of-eod-information-disseminati)
- Community posts in Aug 2026 show daily NSE bhavcopy delivery-percentage data is still being shared (sec_bhavdata_full style). — [TradingQnA](https://tradingqna.com/t/sharing-daily-nse-bhavcopy-delivery-data-useful-for-swing-traders-07-aug-2026/196866) (title only; file layout not verified)
- Nifty 500 is reviewed and rebalanced semi-annually; top-10 composition churned (only 5 stocks stayed in the top 10 from 2021 to 2026; TCS dropped out by July 2026). — [Bajaj Broking](https://www.bajajbroking.in/share-market-news/inside-the-nifty-500-index-how-it-changed-from-2021-to-2026)
- An arXiv paper (2603.19380) appeared in search results on this topic but I did not read it. — [arXiv](https://arxiv.org/abs/2603.19380)

### Inferences
- Use point-in-time constituents (NSE index-change circulars / archived factsheets) rather than the current list; include delisted/merged names with their final prices; otherwise survivorship inflates returns. 
- Build adjusted prices yourself from raw bhavcopy plus corporate-action records (splits, bonuses, rights, dividends) and compare against Dhan's candles on known split dates to learn whether Dhan adjusts.
- Pipeline for bhavcopy should be tolerant to format changes around 16 Nov 2026 (legacy broadcast shutdown affects exchange-member feeds; the public archive path for sec_bhavdata_full was not stated to change, but verify).
- Delivery % is T-day information published after close, so using it requires a one-day lag in signals.

### Gaps
- Whether Dhan daily candles are adjusted: not documented in the fetched page.
- Source for official NSE bhavcopy URL/column names (SYMBOL, SERIES, DELIV_QTY, DELIV_PER) not fetched.
- Historical Nifty 500 constituent archive source (NSE indices site) not verified.
- Corporate actions data source (NSE corporate-actions API / BSE) not researched.
