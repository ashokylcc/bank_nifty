"""
Indicator-based intraday scalping strategy (separate from Heikin Ashi file).

Key ideas (per our discussion):
- Uses normal 1-minute BankNifty futures candles as the base data.
- Uses EMA(20), EMA(50), RSI(14) for momentum / trend filtering.
- Optional PSAR calculation is included primarily for future stop/trail use.
- Entries are **options** (CALL/PUT) based on futures signals.
- Per-trade profit target is configured **per lot** in admin and auto-scales with num_lots:
    - 1 lot  → ₹500 (example)
    - 2 lots → ₹1000
- Daily target / stop-loss also come from admin (base per lot, scaled by num_lots)
  and use the same "Eff" effective P&L logic as the Heikin Ashi strategy.

This file is completely separate and does NOT modify `run_heikinashi_strategy.py`.
"""

import os
import sys
import time
import logging
from decimal import Decimal
from datetime import datetime, time as dt_time
from typing import Optional, Dict, Tuple

from django.core.management.base import BaseCommand

# Ensure project root is on path (same pattern as existing command)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.services.candle_aggregator import CandleAggregator
from trading.services.momentum import MomentumCalculator
from trading.services.data_ingest import CandleData
from trading.services.heikinashi_utils import calculate_pnl
from trading.utils.time_helpers import get_ist_now
from trading.management.commands.run_heikinashi_strategy import (
    HeikinAshiStrategy,
    LOT_SIZE,
)
from trading.models import Strategy

logger = logging.getLogger(__name__)


class ParabolicSARCalculator:
    """
    Lightweight Parabolic SAR implementation for candle-based data.

    This is NOT a pixel-perfect replica of TradingView, but it follows the
    standard PSAR mechanics (step 0.02, max 0.2) closely enough for live trading
    decisions and stop/trail logic.
    """

    def __init__(self, step: Decimal = Decimal("0.02"), max_step: Decimal = Decimal("0.2")):
        self.step = Decimal(str(step))
        self.max_step = Decimal(str(max_step))
        self.af: Optional[Decimal] = None  # acceleration factor
        self.ep: Optional[Decimal] = None  # extreme point (highest high / lowest low)
        self.psar: Optional[Decimal] = None
        self.trend: Optional[str] = None  # 'LONG' or 'SHORT'
        self._candles: list[CandleData] = []

    def update(self, candle: CandleData) -> Tuple[Optional[Decimal], Optional[str]]:
        """
        Update PSAR with a new completed candle.

        Returns:
            (psar_value, trend) or (None, None) if not enough data yet.
        """
        self._candles.append(candle)
        # Keep only last 3 candles for previous-high/low constraints
        if len(self._candles) > 3:
            self._candles = self._candles[-3:]

        if len(self._candles) < 2:
            return None, None

        # Initialize on the second candle
        if self.psar is None or self.trend is None or self.af is None or self.ep is None:
            first = self._candles[-2]
            second = self._candles[-1]
            if second.close >= first.close:
                # Start in LONG trend
                self.trend = "LONG"
                self.psar = first.low
                self.ep = max(first.high, second.high)
            else:
                # Start in SHORT trend
                self.trend = "SHORT"
                self.psar = first.high
                self.ep = min(first.low, second.low)
            self.af = self.step
            return self.psar, self.trend

        # Standard PSAR update
        prev1 = self._candles[-2]
        prev2 = self._candles[-3] if len(self._candles) >= 3 else self._candles[-2]
        current = self._candles[-1]

        psar_next = self.psar + self.af * (self.ep - self.psar)

        if self.trend == "LONG":
            # PSAR cannot be above the lows of the previous two candles
            lowest_prev = min(prev1.low, prev2.low)
            if psar_next > lowest_prev:
                psar_next = lowest_prev

            # Check for reversal
            if current.low < psar_next:
                # Flip to SHORT
                self.trend = "SHORT"
                self.psar = self.ep  # start from previous extreme
                self.ep = min(current.low, prev1.low, prev2.low)
                self.af = self.step
            else:
                # Continue LONG
                if current.high > self.ep:
                    self.ep = current.high
                    if self.af < self.max_step:
                        self.af += self.step
                self.psar = psar_next
        else:  # SHORT
            # PSAR cannot be below the highs of the previous two candles
            highest_prev = max(prev1.high, prev2.high)
            if psar_next < highest_prev:
                psar_next = highest_prev

            # Check for reversal
            if current.high > psar_next:
                # Flip to LONG
                self.trend = "LONG"
                self.psar = self.ep
                self.ep = max(current.high, prev1.high, prev2.high)
                self.af = self.step
            else:
                # Continue SHORT
                if current.low < self.ep:
                    self.ep = current.low
                    if self.af < self.max_step:
                        self.af += self.step
                self.psar = psar_next

        return self.psar, self.trend


class IndicatorScalpingStrategy(HeikinAshiStrategy):
    """
    Intraday indicator-based scalping strategy.

    Reuses the existing HeikinAshiStrategy infrastructure for:
    - WebSocket connection (Alice Blue)
    - Futures LTP updates
    - Option strike selection & order placement
    - Trade logging and daily P&L tracking

    BUT overrides:
    - process_ltp      → to feed MomentumCalculator + PSAR on 1-minute candles.
    - check_entry_conditions → EMA/RSI-based entries (no Heikin Ashi).
    - check_exit_conditions  → per-trade TP + optional per-trade SL + time exit.
    """

    def __init__(
        self,
        dry_run: bool = True,
        strategy_name: str = "Indicator Scalping Strategy",
        debug: bool = False,
        candle_source: str = "futures",
        stdout_callback=None,
        quantity: int = LOT_SIZE,
        ema_fast: int = 20,
        ema_slow: int = 50,
        rsi_period: int = 14,
    ):
        super().__init__(
            dry_run=dry_run,
            strategy_name=strategy_name,
            debug=debug,
            candle_source=candle_source,
            stdout_callback=stdout_callback,
            quantity=quantity,
        )

        # Momentum / indicator calculators on 1-minute futures candles
        self.momentum_calc = MomentumCalculator(
            ema_fast=ema_fast, ema_slow=ema_slow, rsi_period=rsi_period
        )
        self.psar_calc = ParabolicSARCalculator()

        self.last_psar: Optional[Decimal] = None
        self.last_psar_trend: Optional[str] = None
        self.last_momentum_details: Optional[Dict] = None

        # Use same daily controls / trailing logic as base class.
        # Trade window & square-off time are loaded from DB via _load_parameters_from_db().

    # --- LIVE TICK PROCESSING -------------------------------------------------

    def process_ltp(self, ltp: Decimal, timestamp: datetime):
        """
        Process new futures LTP tick.

        - Feeds 1-minute candles into CandleAggregator.
        - On each completed candle, updates EMA/RSI & PSAR state.
        """
        new_candle = self.candle_aggregator.add_ltp(ltp, timestamp)

        if not new_candle:
            return

        # Build CandleData for momentum calculations
        end_ts = new_candle.get("end_time") or new_candle.get("timestamp") or timestamp
        candle = CandleData(
            timestamp=end_ts,
            open=Decimal(str(new_candle["open"])),
            high=Decimal(str(new_candle["high"])),
            low=Decimal(str(new_candle["low"])),
            close=Decimal(str(new_candle["close"])),
            volume=int(new_candle.get("volume", 0)),
        )

        self.momentum_calc.add_candle(candle)
        self.last_psar, self.last_psar_trend = self.psar_calc.update(candle)

    # --- ENTRY LOGIC ----------------------------------------------------------

    def check_entry_conditions(self) -> Optional[str]:
        """
        Indicator-based entry logic (1-minute futures candles).

        BUY (CALL) conditions:
            - Within trading window.
            - No current open position, not halted for the day.
            - Sufficient candles for EMA(20), EMA(50), RSI(14).
            - Momentum score for BUY == 4 (volume breakout, EMA alignment, RSI in range, bullish candle).

        SELL (PUT) conditions:
            - Same as above, but for SELL side.

        Returns:
            'BUY' for CALL entry, 'SELL' for PUT entry, or None.
        """
        if self.trading_halted_for_day:
            return None

        if self.current_position:
            return None

        # Need futures price for context
        if not self.futures_ltp:
            return None

        current_time = get_ist_now()
        current_time_obj = current_time.time()
        if (
            current_time_obj < self.trade_start_time
            or current_time_obj >= self.trade_end_time
        ):
            return None

        # Ensure we only use completed candles from today, once each
        prev_candle_dict = self.candle_aggregator.get_last_candle()
        if not prev_candle_dict:
            return None

        prev_start = prev_candle_dict.get("start_time") or prev_candle_dict.get(
            "timestamp"
        )
        if not prev_start:
            return None

        try:
            from trading.utils.time_helpers import IST
            from dateutil import parser

            if not isinstance(prev_start, datetime):
                prev_start = parser.parse(str(prev_start))
            if prev_start.tzinfo is None:
                prev_start = IST.localize(prev_start)

            prev_date = prev_start.date()
            today = current_time.date()
            if prev_date != today:
                return None
        except Exception:
            return None

        # Only evaluate each completed candle once
        if self.last_entry_candle_start and prev_start <= self.last_entry_candle_start:
            return None

        # We rely on MomentumCalculator's internal candle list, which is fed from
        # process_ltp() whenever a new candle closes.
        if len(self.momentum_calc.candles) < max(
            self.momentum_calc.ema_fast, self.momentum_calc.ema_slow
        ):
            return None

        if len(self.momentum_calc.candles) < self.momentum_calc.rsi_period + 1:
            return None

        current_candle = self.momentum_calc.candles[-1]
        ema_fast = self.momentum_calc.get_ema_fast()
        ema_slow = self.momentum_calc.get_ema_slow()
        rsi = self.momentum_calc.calculate_rsi()

        if not (ema_fast and ema_slow and rsi is not None):
            return None

        # Compute momentum scores for BUY and SELL using existing helper
        score_buy, details_buy = self.momentum_calc.calculate_momentum_score(
            signal_type="BUY",
            current_candle=current_candle,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
        )
        score_sell, details_sell = self.momentum_calc.calculate_momentum_score(
            signal_type="SELL",
            current_candle=current_candle,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
        )

        self.last_momentum_details = {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "rsi": rsi,
            "score_buy": score_buy,
            "score_sell": score_sell,
            "details_buy": details_buy,
            "details_sell": details_sell,
        }

        signal: Optional[str] = None

        # Prefer BUY if both sides give strong signals (very rare).
        if score_buy == 4:
            signal = "BUY"
        elif score_sell == 4:
            signal = "SELL"

        if signal:
            leg_text = "BUY CALL" if signal == "BUY" else "BUY PUT"
            logger.info(
                f"🏁 Indicator entry from candle [{prev_start.strftime('%H:%M')}]: "
                f"EMA20={ema_fast:.2f}, EMA50={ema_slow:.2f}, RSI={rsi:.2f}, "
                f"score_buy={score_buy}, score_sell={score_sell} → {leg_text}"
            )
            self.last_entry_candle_start = prev_start
            # We are not using HA color for this entry logic
            self.entry_candle_ha_color = None
            return signal

        return None

    # --- EXIT LOGIC -----------------------------------------------------------

    def check_exit_conditions(self) -> Optional[str]:
        """
        Exit conditions for this indicator strategy:

        - Per-trade profit target (₹ per lot from admin, auto-scaled by quantity).
        - Optional per-trade stop-loss (fraction of per-trade target).
        - Time-based square-off (square_off_time from admin/constant).
        - Daily limits (target/stop/trailing) are enforced separately in monitor_daily_limits().

        Returns:
            Exit reason string or None.
        """
        if not self.current_position:
            return None

        entry = self.current_position
        entry_premium = entry["entry_premium"]
        side = entry["side"]

        # Need live option LTP
        if not self.futures_ltp:
            return None

        current_option_ltp = self.get_option_ltp()
        if not current_option_ltp:
            return None

        # Current trade P&L (rupees, scaled by quantity)
        pnl_amount = calculate_pnl(
            entry_premium,
            current_option_ltp,
            side,
            self.quantity,
        )

        # Remember last open P&L so daily trailing logic can use it
        self.last_open_pnl = pnl_amount

        # 1) Per-trade profit target
        if pnl_amount >= self.per_trade_profit_target:
            logger.info(
                f"🎯 Per-trade profit target reached: P&L ₹{pnl_amount:.2f} >= "
                f"₹{self.per_trade_profit_target:.2f}"
            )
            return "PROFIT_TARGET"

        # 2) Optional per-trade stop-loss (use 60% of target as a starting point)
        #    Example: per_trade_target (per lot) = 500 → stop ≈ 300 per lot.
        #    This is purely trade-level risk; daily stop-loss still applies separately.
        stop_factor = Decimal("0.6")
        per_trade_stop = self.per_trade_profit_target * stop_factor
        if pnl_amount <= -per_trade_stop:
            logger.info(
                f"🛑 Per-trade stop-loss hit: P&L ₹{pnl_amount:.2f} <= -₹{per_trade_stop:.2f}"
            )
            return "STOPLOSS"

        # 3) Time-based square-off (safety check – main loop also enforces)
        current_time = get_ist_now()
        if current_time.time() >= self.square_off_time:
            logger.info(
                f"⏰ TIME EXIT (check_exit_conditions): {current_time.time()} >= "
                f"{self.square_off_time}"
            )
            return "TIME"

        return None


class Command(BaseCommand):
    help = "Indicator-based Intraday Scalping Strategy (EMA/RSI, separate from Heikin Ashi)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (no real orders)",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run continuously (default: single cycle)",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
            help="Loop interval in seconds (default: 5)",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug mode (note: this strategy does not print HA data)",
        )
        parser.add_argument(
            "--quantity",
            type=int,
            default=LOT_SIZE,
            help="Total option quantity (multiple of 35). Used for order sizing and daily targets.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", True)
        loop = options.get("loop", False)
        interval = options.get("interval", 5)
        debug = options.get("debug", False)

        mode_str = "DRY-RUN" if dry_run else "LIVE"
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {mode_str} MODE - "
                f"{'No real orders' if dry_run else 'REAL ORDERS ENABLED'}"
            )
        )
        if debug:
            self.stdout.write(
                self.style.SUCCESS(
                    "🐛 DEBUG MODE ENABLED - Indicator state will be logged"
                )
            )

        # Get or create a dedicated Strategy row for this indicator strategy
        strategy_obj, _ = Strategy.objects.get_or_create(
            name="Indicator Scalping Strategy",
            defaults={"enabled": True},
        )

        # Determine quantity: use CLI override if provided, otherwise DB lot_size * num_lots
        quantity_arg = options.get("quantity")
        if quantity_arg and quantity_arg != LOT_SIZE:
            quantity = quantity_arg
            self.stdout.write(
                self.style.SUCCESS(f"📊 Using quantity from command line: {quantity}")
            )
        else:
            db_lot_size = strategy_obj.lot_size if strategy_obj.lot_size else LOT_SIZE
            db_num_lots = strategy_obj.num_lots if strategy_obj.num_lots else 1
            quantity = db_lot_size * db_num_lots
            self.stdout.write(
                self.style.SUCCESS(
                    f"📊 Quantity from DB: lot_size={db_lot_size} × "
                    f"num_lots={db_num_lots} = {quantity}"
                )
            )

        strategy = IndicatorScalpingStrategy(
            dry_run=dry_run,
            strategy_name="Indicator Scalping Strategy",
            debug=debug,
            candle_source="futures",
            stdout_callback=lambda msg: self.stdout.write(self.style.SUCCESS(msg)),
            quantity=quantity,
        )

        # Attach strategy_obj and reload parameters from DB (daily targets, trailing, etc.)
        strategy.strategy_obj = strategy_obj
        strategy._load_parameters_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"🧮 Quantity: {strategy.quantity} | "
                f"Daily target ₹{strategy.daily_profit_target:.2f} | "
                f"Stop-loss -₹{strategy.daily_stop_loss:.2f}"
            )
        )

        # Initialize Alice Blue connection
        if not strategy.initialize_alice_blue():
            self.stdout.write(self.style.ERROR("❌ Failed to initialize Alice Blue"))
            return

        # (Optional) we can still load historical candles for internal HA calc;
        # not strictly needed for this indicator strategy, but harmless.
        self.stdout.write("📊 Loading historical candles (for internal warmup)...")
        try:
            strategy.load_historical_candles()
        except Exception as e:
            logger.warning(f"Error in historical load (non-fatal): {e}")

        # Check if trading window already closed
        current_time = get_ist_now()
        current_time_obj = current_time.time()
        if current_time_obj > strategy.trade_end_time:
            self.stdout.write(
                self.style.WARNING(
                    f"⏰ Trading window already closed: Current time "
                    f"{current_time_obj.strftime('%H:%M:%S')} > "
                    f"End time {strategy.trade_end_time.strftime('%H:%M:%S')}"
                )
            )
            self.stdout.write(
                self.style.SUCCESS("✅ Strategy stopped (outside trading window)")
            )
            return

        self.stdout.write("🔄 Starting indicator scalping strategy loop...")
        self.stdout.write("Press Ctrl+C to stop")

        try:
            while True:
                current_time = get_ist_now()
                current_time_obj = current_time.time()

                # Stop after end of trading window
                if current_time_obj > strategy.trade_end_time:
                    self.stdout.write(
                        self.style.WARNING(
                            f"\n⏰ Trading window closed: Current time "
                            f"{current_time_obj.strftime('%H:%M:%S')} > "
                            f"End time {strategy.trade_end_time.strftime('%H:%M:%S')}"
                        )
                    )
                    if strategy.current_position:
                        strategy.exit_trade("TIME")
                    break

                # Safety: square-off any open position at/after square_off_time
                if strategy.current_position and current_time_obj >= strategy.square_off_time:
                    logger.info(
                        f"⏰ TIME EXIT: Current time {current_time_obj} >= "
                        f"Square-off time {strategy.square_off_time}"
                    )
                    strategy.exit_trade("TIME")

                # Enforce daily limits (target, stop-loss, trailing)
                strategy.monitor_daily_limits()

                # Feed latest futures LTP into strategy
                if strategy.futures_ltp:
                    strategy.process_ltp(strategy.futures_ltp, current_time)

                # Entry / exit
                if not strategy.trading_halted_for_day and not strategy.current_position:
                    signal = strategy.check_entry_conditions()
                    if signal and strategy.futures_ltp:
                        strategy.enter_trade(signal, strategy.futures_ltp)
                elif strategy.current_position:
                    exit_reason = strategy.check_exit_conditions()
                    if exit_reason:
                        strategy.exit_trade(exit_reason)

                # Status line
                status_parts = []
                if strategy.futures_ltp:
                    status_parts.append(f"Futures: ₹{strategy.futures_ltp:,.2f}")

                # Show last completed 1-minute candle (from today)
                prev_candle = strategy.candle_aggregator.get_last_candle()
                if prev_candle:
                    candle_time = (
                        prev_candle.get("start_time")
                        or prev_candle.get("timestamp")
                        or current_time
                    )
                    try:
                        from trading.utils.time_helpers import IST
                        from dateutil import parser

                        if not isinstance(candle_time, datetime):
                            candle_time = parser.parse(str(candle_time))
                        if candle_time.tzinfo is None:
                            candle_time = IST.localize(candle_time)
                        else:
                            candle_time = candle_time.astimezone(IST)

                        today = get_ist_now().date()
                        candle_date = candle_time.date()
                        if candle_date == today:
                            prev_open = prev_candle.get("open")
                            prev_close = prev_candle.get("close")
                            prev_high = prev_candle.get("high")
                            prev_low = prev_candle.get("low")
                            if (
                                prev_open is not None
                                and prev_close is not None
                                and prev_high is not None
                                and prev_low is not None
                            ):
                                try:
                                    po = float(prev_open)
                                    pc = float(prev_close)
                                    ph = float(prev_high)
                                    pl = float(prev_low)
                                    if pc > po:
                                        prev_dir = "UP"
                                    elif pc < po:
                                        prev_dir = "DOWN"
                                    else:
                                        prev_dir = "DOJI"
                                    time_str_prev = candle_time.strftime("%H:%M")
                                    status_parts.append(
                                        f"Prev 1m [{time_str_prev}] "
                                        f"O:{po:.2f} H:{ph:.2f} L:{pl:.2f} "
                                        f"C:{pc:.2f} Dir:{prev_dir}"
                                    )
                                except (TypeError, ValueError):
                                    pass
                    except Exception:
                        pass

                if strategy.current_position:
                    entry = strategy.current_position
                    option_ltp = strategy.get_option_ltp() or entry["entry_premium"]
                    pnl = calculate_pnl(
                        entry["entry_premium"],
                        option_ltp,
                        entry["side"],
                        strategy.quantity,
                    )
                    status_parts.append(
                        f"IN TRADE: {entry['option_symbol']} | "
                        f"Entry: ₹{entry['entry_premium']:.2f} | "
                        f"Current: ₹{option_ltp:.2f} | P&L: ₹{pnl:.2f}"
                    )

                # Show latest indicator state (when available) so you can see
                # WHEN a trade is likely to execute and WHY it is not entering yet.
                if strategy.last_momentum_details:
                    md = strategy.last_momentum_details
                    try:
                        ema_fast_f = float(md["ema_fast"])
                        ema_slow_f = float(md["ema_slow"])
                        rsi_f = float(md["rsi"])
                        score_buy = md["score_buy"]
                        score_sell = md["score_sell"]
                        status_parts.append(
                            f"Ind: EMA20:{ema_fast_f:.2f} EMA50:{ema_slow_f:.2f} "
                            f"RSI:{rsi_f:.1f} SB:{score_buy}/4 SS:{score_sell}/4"
                        )
                        # Simple hint about next possible entry
                        if (
                            not strategy.current_position
                            and not strategy.trading_halted_for_day
                        ):
                            if score_buy == 4:
                                status_parts.append("Next entry: BUY CALL ready")
                            elif score_sell == 4:
                                status_parts.append("Next entry: BUY PUT ready")
                            else:
                                status_parts.append("Next entry: waiting (scores < 4)")
                    except Exception:
                        # If any conversion fails, skip indicator display quietly
                        pass

                # Daily P&L + trailing info (same semantics as HeikinAshiStrategy)
                effective_pnl = strategy.daily_pnl
                if strategy.current_position and strategy.last_open_pnl is not None:
                    effective_pnl = strategy.daily_pnl + strategy.last_open_pnl

                status_parts.append(
                    f"Daily P&L: ₹{strategy.daily_pnl:.2f} / "
                    f"₹{strategy.daily_profit_target:.2f} | "
                    f"Stop: -₹{strategy.daily_stop_loss:.2f} | "
                    f"Trail: ON≥₹{strategy.trailing_active_after:.2f}, "
                    f"Buff ₹{strategy.trailing_buffer:.2f}, "
                    f"Max ₹{strategy.max_daily_pnl_seen:.2f}, "
                    f"Eff ₹{effective_pnl:.2f}"
                )
                if strategy.trading_halted_for_day:
                    status_parts.append("Status: HALTED")

                if status_parts:
                    time_str = current_time.strftime("%H:%M:%S")
                    self.stdout.write(f"[{time_str}] {' | '.join(status_parts)}")

                if not loop:
                    break

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⏹️  Stopping strategy..."))
            if strategy.current_position:
                strategy.exit_trade("TIME")

        self.stdout.write(self.style.SUCCESS("✅ Indicator scalping strategy stopped"))


