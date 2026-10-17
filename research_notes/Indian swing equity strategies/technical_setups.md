# Technical/price-action swing setups for NSE cash equities (daily, 2-20 day hold)

Scope note: ~17 tool calls. Credible, quantified Indian evidence for these specific retail setups is thin. Most "strategy" articles found give rules but no backtest. Rule specs below are labelled by source; where I give a "typical" parameter without a source, it is marked UNSOURCED (general practice, not verified).

## Q1. Exact rules and win-rate / expectancy / drawdown evidence on NSE stocks

### Takeaway
Only two of the requested setups have any quantified NSE-wide evidence found: Supertrend (broker blog, Nifty 500, 2012-2025, win rate ~41-43%, big winners) and simple/displaced moving-average trend rules (XLRI paper, 1991-2005). RSI(2), Bollinger squeeze/pullback, NR7/inside day, Donchian, VCP and gap-fill rules were found only as rule descriptions with no real Indian backtest. Win rates and expectancies for those on NSE are therefore unknown from this research.

### Cited Findings

**Supertrend (best quantified Indian item, but promotional and not peer-reviewed)**
- Universe Nifty 500, period 2012-2025, daily closes, Period 3-21 and Multiplier 1-3 tested; ~65,000 trades for (3,1) and ~15,000 for (3,3). — [PhonePe Invest / Share.Market](https://www.phonepeinvest.com/buzz/insights/i-backtested-200000-trades-using-the-supertrend-indicator-here-is-what-actually-works)
- (3,1): win rate 40.7%, avg win 8.54%, avg loss -3.64%, hold ~15 days. (3,1.5): 41.1%, +11.69%/-4.69%. (3,3): 42.9%, +25.53%/-7.40%, hold ~69 days. Win rate stayed ~40.7%-43.2% across all settings; the multiplier drives average win size more than the period. — same source
- My arithmetic from that table (not in source, pre-cost): expectancy ~+1.3% per trade for (3,1) and ~+6.7% for (3,3). Drawdown not reported; costs, slippage, taxes and out-of-sample testing not discussed; the source calls (10,3) and (14,3) "more stable alternatives". — same source (caveats from the page; calculation mine)
- Implication: only the (3,1) setting (~15-day hold) falls inside the 2-20 day window; (3,3) holds ~69 days, outside scope. Survivorship/current-constituent bias is not addressed by the source (UNVERIFIED either way).

**RSI (not RSI(2))**
- 25-year backtest (published 25 Sep 2025) on Nifty 50, Next 50, Midcap 150, Smallcap 250, Nifty 500, daily; rules: RSI cross 30->70, RSI 50 cross, RSI vs RSI-EMA cross. Long-only worked; short-only and long/short combined lost money. RSI(21) 30/70 cross: win rate 79.05%, 15.65% per trade but ~1 trade/stock/year. RSI(7) 50-cross best per-day returns. Uses current index constituents (survivorship bias), no costs/slippage. Source says "directional, not plug-and-play". Other tables only in images, unreadable. — [PhonePe Invest / Share.Market RSI Myth pt 2](https://www.phonepeinvest.com/buzz/insights/the-rsi-myth-is-this-popular-indicator-worth-using-part-2-research-report)
- Academic: RSI and MACD on BSE Sensex daily Feb 2000-May 2018 (index, not stocks): RSI rule gave no positive return even before costs; MACD sell signal in bear markets beat unconditional mean pre-cost; Sharpe analysis says returns did not compensate for risk. — [Colombo Business Journal](https://cbj.sljol.info/articles/56)

**RSI(2) / short-term mean reversion**
- Rule spec (Connors-style, as written by an Indian blog): long only if close > 200-day SMA; buy at close when RSI(2) < 10 (stricter <5); optional second tranche if lower next day with RSI(2)<10; exit when close > 5-day SMA; hard stop ~3-5% for stocks; risk 1-2% capital per trade; hold typically 1-5 days; liquid names (Nifty 50, large caps). No backtest statistics; worked examples are labelled illustrative and contain internal inconsistencies (Bank Nifty profit and lot-size mismatches). — [OneTradeJournal RSI-2](https://onetradejournal.com/strategies/rsi-2-strategy)
- Bollinger/z-score mean-reversion variant: buy daily close below lower BB(20,2) or z-score <= -2, index above 200DMA and ADX(14)<20, stop = signal-day low or 1xATR(14) whichever wider, target 20-day mean, 5-session time stop; claims "60-70% win" unsourced; examples have arithmetic/lot-size errors. — [OneTradeJournal mean reversion](https://onetradejournal.com/strategies/mean-reversion-strategy)
- Indian academic daily-reversal evidence (cross-sectional, not RSI(2)): NSE 500 universe 2014-2021, long-short "physical momentum" paper found best daily-horizon portfolio was contrarian (reversal), final wealth ~16x, mean monthly return ~6.04%; weekly/monthly/yearly best portfolios were continuation. All Sharpe ratios <1; transaction costs not modelled; best-of-1,177 portfolios selection (data-mining risk). — [arXiv 2302.13245](https://www.arxiv.org/pdf/2302.13245)

**Bollinger squeeze / pullback to 20 EMA**
- Algotest blog: squeeze breakout (tightest bands, close beyond band, rising volume; exit on close back through middle band; stop inside squeeze range) is described for Nifty/BankNifty 5/15-min charts, not daily stocks. Swing "middle band trend follow": sloping 20 SMA required; long on bullish candle at 20 SMA in uptrend; exit on close on the other side of the middle band; daily/hourly on large/midcaps. BB(20,2). No backtest numbers. — [Algotest](https://algotest.in/blog/bollinger-bands-strategies-for-indian-traders.md)
- No Indian bandwidth-percentile or Keltner-squeeze backtest found. Non-Indian Quantified Strategies posts on squeeze exist (search result only; not read). — [Quantified Strategies](https://quantifiedstrategies.substack.com/p/bollinger-band-squeeze-strategy-backtest-4a6)

**Moving-average trend rules (oldest Indian stock-level evidence)**
- Sundhar & Kakani, XLRI WP 06-02 (2006): SMA (3,5,10,50,200) and displaced MA (e.g. 50X11) on Nifty, Sensex and 14 large-cap NSE stocks, 1991-2005 (portfolio test 2001-2005). No SMA exceeded 50% success ratio; 50-day SMA had best risk-reward; DMA 50X11 ~60% success with fewer whipsaws; best DMA beat buy-and-hold in 11 of 13 stocks; costs 0.1% per side (paper inconsistent, sometimes 0.2%). Authors admit data-snooping / ex-post rule selection and need for out-of-sample test. — [XLRI paper PDF](https://c.mql5.com/forextsd/forum/214/Profiting%20from%20Technical%20Analysis%20in%20Indian%20Equity%20Market%20-%20Using%20Moving%20Averages.pdf)
- Another Nottingham eprint, "Testing weak form of market efficiency by simple technical trading rules on the Indian stock market", exists (not read; redirect not followed). — [Nottingham eprint](https://eprints.nottingham.ac.uk/20281)

**52-week-high / breakout**
- The only Indian 52-week-high paper found studies NSE single-stock OPTIONS around 52W highs/lows (Jan 2011-Dec 2019; 1,547 high events, 1,030 low events): risk-neutral skew and OTM-call volume fall near the high and reverse after breach; RND volatility rises after breakthrough; consistent with anchoring. It reports no stock returns, so it does not give a tradable expectancy. — [Saurav, ACFR/AUT](https://acfr.aut.ac.nz/__data/assets/pdf_file/0004/686812/3b-Sumit-Saurav.pdf)
- A Griffith/Massey/other 52-week-high index-prediction paper appeared in search results but was not read; Indian applicability unknown. — [Griffith repository](https://research-repository.griffith.edu.au/items/41995ba4-ea62-565b-bc6a-9233b7978ae0)

**VCP / Minervini**
- TradingView "Minervini VCP Pattern - Indian Context" script: 13 trend conditions (price > 50/150/200 MA; 50>150>200; 200MA rising vs 20 bars ago; within 25% of 52W high; >=30% above 52W low; price >= Rs50; avg volume >= 100,000 on 50-day; RS vs Nifty improving; Nifty above its 50MA; weekly uptrend), volatility contraction + volume dry-up. Example risk rules (illustrative, not tested): 1% account risk, 8% stop, sell 1/3 at +20%, 1/3 at +40%, trail rest, exit on close below 10MA on heavy volume. No backtest. — [TradingView](https://de.tradingview.com/script/ZDW7dMhF-Minervini-VCP-Pattern-Indian-Context)

**Gap fill**
- OneTradeJournal explicitly states it has no verified Nifty/Bank Nifty fill-rate dataset and no claimed win rate; example is fictional. — [OneTradeJournal gap fill](https://onetradejournal.com/strategies/gap-fill-strategy)

**NR7 / inside day; Donchian/turtle**
- Searches returned only generic TradingView scripts and non-Indian pages; no Indian backtest numbers found. (Search results only: [thepatternsite NR7](https://thepatternsite.com/nr7.html), [StrategyQuant on turtles](https://strategyquant.com/blog/from-the-turtles-to-today-how-a-40-year-old-strategy-still-works/); neither read, not Indian.)

### Inferences
- Supertrend's profile (win rate ~41%, avg win ~2.3x avg loss at (3,1)) is a classic low-hit-rate trend-follower; the same payoff logic probably applies to Donchian/52W-high breakouts, but that is inference, not evidence.
- The 2006 XLRI result (SMA <50% success; displaced MA ~60%) and the 2018 Sensex RSI/MACD result (no edge) together suggest pure indicator rules on indices give weak edge; stock-level, trend-filtered setups are untested in rigorous Indian literature found here.
- Daily-horizon cross-sectional reversal (NSE 500, 2014-2021) is mild support for RSI(2)-type mean reversion in Indian stocks, but the paper is data-mined, ignores costs, and is long-short (shorting single stocks in cash is not available to retail holding multiple days; would need futures).

### Gaps
- No Indian backtest found for: Bollinger bandwidth-percentile/Keltner squeeze on daily stocks, 20/50 EMA pullback, RSI(2) on NSE stocks, NR7/inside-day, Donchian 20/55-day, VCP, gap-fill.
- Zerodha Varsity, QuantInsti, Quantsapp, Trendlyne, Streak: searched indirectly; only a Trendlyne backtest URL surfaced (not read) and no QuantInsti/Varsity quantified results for these setups were retrieved. Treat as not checked in depth.
- No drawdown data for any Indian setup except none reported; Supertrend article omits it.
- Survivorship bias, costs (STT, brokerage, impact), and out-of-sample splits are absent from the retail articles.

## Q2. Credible Indian backtests vs folklore

### Takeaway
Semi-credible: XLRI 2006 MA paper (peer-style working paper, admits data snooping, old), Colombo Business Journal RSI/MACD Sensex study (index only), arXiv NSE-500 momentum/reversal paper (selection-biased, no costs), and the broker Supertrend/RSI studies (large samples but promotional, current-constituent bias, no costs). Everything else found is folklore: rules without evidence.

### Cited Findings
- Credibility rating basis: the Supertrend and RSI articles are published on a broker/fintech site, disclose no costs/out-of-sample, and RSI study states it used current constituents. — [Supertrend](https://www.phonepeinvest.com/buzz/insights/i-backtested-200000-trades-using-the-supertrend-indicator-here-is-what-actually-works), [RSI](https://www.phonepeinvest.com/buzz/insights/the-rsi-myth-is-this-popular-indicator-worth-using-part-2-research-report)
- XLRI authors state ex-post rule selection and need for out-of-sample test. — [XLRI](https://c.mql5.com/forextsd/forum/214/Profiting%20from%20Technical%20Analysis%20in%20Indian%20Equity%20Market%20-%20Using%20Moving%20Averages.pdf)
- Folklore (rules only, no stats): OneTradeJournal RSI-2, mean reversion, gap fill; Algotest Bollinger; TradingView VCP script. — links above.

### Inferences
- OneTradeJournal pages contain arithmetic/lot-size errors, so should not be cited for numbers.

### Gaps
- Could not verify any SSRN paper specific to Indian swing setups; searches surfaced none.

## Q3. Parameters, stops, position sizing

### Takeaway
Sourced parameters: Supertrend ATR period 3-21 / multiplier 1-3; BB(20,2); RSI(2)<10 above 200DMA exit >5DMA; ATR(14) stops; 1-2% risk per trade. These are blog conventions, not optimised on validated Indian data.

### Cited Findings
- Supertrend grid: period 3-21, multiplier 1-3; higher multiplier = bigger wins, longer holds (~15 days at 3,1; ~69 days at 3,3). — [PhonePe Invest](https://www.phonepeinvest.com/buzz/insights/i-backtested-200000-trades-using-the-supertrend-indicator-here-is-what-actually-works)
- RSI(2) stops 3-5% hard stop, 1-2% account risk, 1-5 day hold. — [OneTradeJournal RSI-2](https://onetradejournal.com/strategies/rsi-2-strategy)
- Mean reversion stop: 1xATR(14) or signal-day low whichever wider; 5-session time stop; ADX<20 regime filter; risk 1-2%. — [OneTradeJournal](https://onetradejournal.com/strategies/mean-reversion-strategy)
- VCP script: 1% risk, 8% stop example, scale-outs at +20%/+40%, 10MA trail; min price Rs50, min avg volume 100,000. — [TradingView](https://de.tradingview.com/script/ZDW7dMhF-Minervini-VCP-Pattern-Indian-Context)
- Bollinger swing: BB(20,2), exit on close through the 20 SMA. — [Algotest](https://algotest.in/blog/bollinger-bands-strategies-for-indian-traders.md)
- XLRI used 0.1% per side cost assumption (2006-era); current NSE costs (STT etc.) differ and should be checked from NSE. — [XLRI](https://c.mql5.com/forextsd/forum/214/Profiting%20from%20Technical%20Analysis%20in%20Indian%20Equity%20Market%20-%20Using%20Moving%20Averages.pdf)

### Inferences
- Because a ~41% hit-rate system needs fixed-fraction risk (1-2%) to survive losing streaks, ATR-based stops with position size = risk/stop distance is the coherent design; ATR multiples of 1-3 are the only range with any Indian-data anchor (Supertrend).

### Gaps
- No Indian evidence comparing ATR stop multiples, position sizing methods or portfolio-level drawdown for these setups.
- Typical Donchian (20/55), NR7, 20/50 EMA pullback parameters: not sourced here (UNSOURCED general practice).
