> **AMENDED 2026-07-03 at the owner's direction.** The original brief said "Your job is NOT to add features." That instruction is REMOVED. Feature development aimed at accuracy and long-term profitability is explicitly IN SCOPE for this audit and everything after it. Proposed features live in FUTURE.md under "Feature roadmap"; decision-affecting features ship log-first and flip on only at their pre-registered evidence gates, with a MODEL_VERSION bump. This file rides in every handback zip as AUDIT_ORIGINAL.md so no future chat re-derives the wrong stance.

Complete Model Audit
====================

Pretend you are reviewing a quantitative sports betting model for a hedge fund.

Your job is twofold:

1. Find every possible weakness, source of bias, hidden assumption, overfitting risk, data issue, statistical mistake, implementation flaw, or opportunity for improvement.
2. Identify, propose, and (at their evidence gates) implement features that increase accuracy and long-term profitability. Add every candidate to the FUTURE.md feature roadmap with impact, difficulty, confidence, dependencies, and a validation plan.

Assume nothing.

Challenge every decision.

* * *

1. Data Quality

---------------

Investigate:

* Missing data
* Duplicate games
* Bad timestamps
* API inconsistencies
* Scraping failures
* Incorrect line movements
* Time zone issues
* Weather delays
* Injury timing
* Line availability
* Closing line accuracy

Questions:

* Could any data leakage exist?
* Am I accidentally using information unavailable at bet time?
* Are all timestamps aligned correctly?

* * *

2. Feature Engineering

----------------------

Brainstorm every potentially useful feature.

Examples:

Market

* line movement
* steam moves
* reverse line movement
* sharp/public splits
* consensus disagreement
* bookmaker disagreement
* closing line distance

Team

* travel distance
* rest days
* altitude
* humidity
* temperature
* wind
* rain
* indoor/outdoor
* revenge games
* divisional familiarity
* pace
* coaching tendencies

Player

* injuries
* questionable players
* backup quality
* usage changes
* lineup continuity

Schedule

* back-to-back
* 3 games in 4 nights
* bye weeks
* playoff implications

* * *

3. Market Efficiency

--------------------

Determine:

Where is the betting market weakest?

Examples

* early lines
* overnight markets
* props
* alternate lines
* niche books
* weather markets
* halftime
* live betting
* player props

* * *

4. Probability Calibration

--------------------------

Determine whether predicted probabilities are actually calibrated.

Investigate:

Reliability diagrams

Brier score

Expected Calibration Error

Log loss

Calibration curves

Platt scaling

Isotonic regression

Bayesian calibration

* * *

5. Closing Line Value

---------------------

Can CLV become the primary evaluation metric?

Investigate:

* average CLV
* CLV by sportsbook
* CLV by league
* CLV by bet type
* CLV by model confidence
* CLV by market timing

* * *

6. Expected Value Calculations

------------------------------

Verify:

* implied probabilities
* vig removal
* expected value formulas
* fair odds estimation
* confidence intervals

* * *

7. Statistical Testing

----------------------

Investigate

Bootstrap testing

Monte Carlo simulation

Bayesian inference

Hypothesis testing

Confidence intervals

Variance estimation

Edge significance

Power analysis

* * *

8. Backtesting

--------------

Audit everything.

Look for:

Look-ahead bias

Survivorship bias

Selection bias

Confirmation bias

Data snooping

Multiple testing

Overfitting

Curve fitting

* * *

9. Machine Learning

-------------------

Should any ML models outperform my current approach?

Evaluate:

Gradient Boosting

XGBoost

LightGBM

CatBoost

Random Forest

Logistic Regression

Bayesian models

Neural Networks

Stacked ensembles

Model averaging

* * *

10. Ensemble Methods

--------------------

Should multiple models be combined?

Investigate:

Weighted averages

Bayesian Model Averaging

Stacking

Blending

Dynamic weighting

Context-aware weighting

* * *

11. Risk Management

-------------------

Review:

Kelly Criterion

Fractional Kelly

Maximum drawdown

Risk of ruin

Portfolio optimization

Correlation between bets

Exposure limits

Bankroll volatility

* * *

12. Market Microstructure

-------------------------

Investigate

Bid/ask spreads

Liquidity

Limits

Line freezes

Market makers

Latency

Execution timing

Book-specific behavior

* * *

13. Model Monitoring

--------------------

Suggest dashboards for

ROI

Expected ROI

CLV

Calibration

Feature drift

Prediction drift

Market drift

API failures

Data freshness

* * *

14. Continuous Learning

-----------------------

How should the model improve automatically?

Ideas:

Retraining schedule

Feature importance drift

Adaptive weighting

Online learning

Performance decay detection

Concept drift detection

* * *

15. Reddit & Quant Community Ideas

----------------------------------

Research ideas that experienced bettors, quantitative traders, prediction market traders, and machine learning practitioners frequently discuss.

Look for techniques such as:

* Removing bookmaker vig correctly
* Closing line prediction
* Market maker modeling
* Ensemble forecasts
* Bayesian updating
* Feature stability
* Probability calibration
* CLV optimization
* Market timing
* Correlated bet detection
* Bootstrap confidence intervals
* Monte Carlo bankroll simulation
* Kelly optimization
* Model explainability
* Drift detection
* Outlier detection
* Market regime detection
* Change-point detection
* Meta-models that decide when **not** to bet
* Confidence scoring
* Expected value confidence intervals

* * *

16. Architecture Review

-----------------------

Critique the software itself.

Questions:

* Is the database schema optimal?
* Is anything computed repeatedly that should be cached?
* Is there a better pipeline?
* What should be asynchronous?
* What belongs in SQL vs Python?
* Should I use feature stores?
* How should historical snapshots be versioned?

* * *

17. Challenge Every Assumption

------------------------------

For every assumption my model makes:

* Explain why it could be wrong.
* Suggest tests to verify it.
* Recommend experiments.
* Estimate the potential impact if the assumption fails.

* * *

Deliverables
------------

Provide:

1. A ranked list of the top 50 improvements by expected ROI.
2. Quick wins (1-2 hours).
3. Medium projects (1-2 days).
4. Major architectural improvements (1-4 weeks).
5. A technical debt assessment.
6. A roadmap to evolve this into an institutional-quality quantitative betting platform.
7. A list of ideas that are commonly discussed by advanced betting and quantitative communities but are often overlooked by hobbyist models.
8. For each recommendation, estimate:
   * Expected impact
   * Difficulty
   * Confidence
   * Dependencies
   * How to validate whether it actually improves performance.
