# ![freqtrade](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/docs/assets/freqtrade_poweredby.svg)

# Production-Grade Algorithmic Trading Ecosystem for Freqtrade

  <!-- Thay bằng link ảnh banner của bạn, có thể tạo trên Canva -->

Welcome to the public portfolio version of my advanced algorithmic crypto trading system. This repository showcases the architecture, structure, and capabilities of a complete, automated trading ecosystem built around the Freqtrade platform.

This is **more than just a trading strategy**; it's an intelligent, multi-component system designed for performance, reliability, and dynamic risk management.

> **Note on Intellectual Property:** To protect proprietary logic, the core mathematical formulas, specific threshold values, and complex decision-making algorithms within key functions have been programmatically obscured. This version is intended to demonstrate architectural competence and code quality.

---

## 🚀 Key Features & System Capabilities

This ecosystem is engineered to operate autonomously, providing a sophisticated framework for executing complex trading logic.

### 🧠 **1. The "Advisory" - Advanced Market Scanner (`ichimoku_scanner.py`)**
The heart of the system is a powerful, multi-timeframe market scanner that acts as the central "brain". It continuously analyzes the market to identify high-probability opportunities.
- **Multi-Timeframe Analysis:** Concurrently analyzes market structure on Weekly, Daily, 4H, 1H, and 15m charts.
- **Complex Pattern Recognition:** Automatically detects high-conviction patterns like **Triple Bottoms**, **Double Bottoms**, and predictive **Ichimoku Kumo Twists**.
- **Consensus-Based BTC Analysis:** Employs a "Council of Experts" model to synthesize data from multiple indicators (RSI, ADX, EMA structures, Divergence) on BTC to form a single, coherent market thesis.
- **Quantitative Scoring System:** Every potential trade is assigned a `final_score` based on dozens of factors, ensuring only the highest-quality setups are considered.

### 🛡️ **2. The "General" - Dynamic Risk Manager (`automation_manager.py`)**
This component acts as the strategic command center, translating the "Advisory's" analysis into actionable commands for the Freqtrade bot.
- **DEFCON Risk System:** Implements a 5-level risk management protocol (`DEFCON 1` to `5`) based on real-time market conditions. The system automatically adjusts its behavior, becoming more aggressive in favorable markets (`DEFCON 5`) and extremely defensive during high-risk periods (`DEFCON 1`).
- **Automated Whitelist Management:** Dynamically generates and updates the Freqtrade `pair_whitelist` based on the highest-scoring opportunities that align with the current DEFCON level.
- **Autonomous Trade Plan Generation:** For each whitelisted pair, it calculates precise `entry`, `stoploss`, and `take-profit` levels, creating a `trade_plan.json` file for the strategy to consume.
- **Proactive Trade Management:** Automatically detects manually opened trades, analyzes their context, generates a safe SL/TP plan, and takes over management.

### ⚔️ **3. The "Soldier" - Adaptive Freqtrade Strategy (`external_signal_strategy.py`)**
This is the execution layer—a highly advanced and flexible Freqtrade strategy that does the "fighting" on the front lines.
- **External Signal Consumption:** It doesn't make decisions in a vacuum. Its primary function is to read the `trade_plan.json` and execute the commands from the "General".
- **Multi-Strategy Execution Engine:** Capable of executing diverse setups identified by the scanner, including `Breakout-Pre`, `Instant-Explosion`, `Trending-Pullback`, and `Reversal-Scout`.
- **Dynamic Stoploss Management:** Features sophisticated, multi-stage stoploss logic, including delayed stoploss for reversal entries, breakeven triggers, and ATR-based trailing stops that adapt to the current `tactical_stance` (Aggressive, Standard, Defensive).
- **Advanced Exit Logic:** Utilizes a "Trade Health Check" system to monitor the momentum of open trades and can trigger early exits if momentum fades, even before hitting SL/TP.

---

## 📊 System Architecture & Data Flow

The system is designed with a clear separation of concerns, ensuring modularity and scalability.

```
+---------------------------+      +-------------------------+      +---------------------------+
|                           |      |                         |      |                           |
|   Automation Manager      |----->|   Ichimoku Scanner      |----->|      Trade Plan (JSON)    |
|   (The General)           |      |   (The Advisory)        |      |      (The Battle Plan)    |
|   - DEFCON Risk System    |      |   - Multi-timeframe     |      |      - Entry, SL, TP        |
|   - Whitelist Generation  |      |   - Pattern Recognition |      |      - Strategy Type        |
|   - Telegram Reporting    |      |   - Quantitative Score  |      |      - Tactical Stance      |
|                           |      |                         |      |                           |
+-------------+-------------+      +-----------+-------------+      +-------------+-------------+
              |                                                                   |
              | (Reloads Config)                                                  | (Reads Plan)
              |                                                                   |
              v                                                                   v
+-------------+-------------+                                       +-------------+-------------+
|                           |                                       |                           |
|   Freqtrade Core          |<--------------------------------------|   External Signal Strategy|
|                           |                                       |   (The Soldier)           |
|                           |                                       |   - Executes Entries      |
|                           |                                       |   - Manages Exits         |
|                           |                                       |   - Dynamic Stoploss      |
+---------------------------+                                       +---------------------------+

```

1.  **`automation_manager.py`** runs on a schedule (e.g., hourly).
2.  It calls **`ichimoku_scanner.py`** to perform a full market scan.
3.  Based on the scan results and market risk (DEFCON level), it generates a **`trade_plan.json`**.
4.  It updates the Freqtrade `whitelist` and issues a `/reload_config` command.
5.  **`external_signal_strategy.py`**, running inside Freqtrade, continuously reads the `trade_plan.json` and executes trades with pinpoint precision based on the provided plan.

---

## 🛠️ Tech Stack

- **Language:** Python 3.9+
- **Core Framework:** [Freqtrade](https://www.freqtrade.io/)
- **Key Libraries:**
  - `pandas`, `numpy` for data manipulation
  - `ccxt` for exchange connectivity
  - `TA-Lib`, `pandas-ta` for technical indicators
  - `scipy` for pattern detection (peak/trough finding)
  - `python-telegram-bot` for notifications
  - `ast` (for the script that generates this public version)

---

Thank you for reviewing my work. I am passionate about building robust, data-driven solutions for algorithmic trading. Let's connect and discuss how I can bring this level of engineering to your project.
