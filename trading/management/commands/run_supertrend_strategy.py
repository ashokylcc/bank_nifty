"""
SuperTrend-based intraday option buying strategy (COMPLETELY SEPARATE).

Key points (matching your prompt exactly):
-----------------------------------------
- Uses **15-minute BankNifty futures candles** from Alice Blue WebSocket.
- Computes **SuperTrend(10,2)** with ATR using RMA (TradingView-style).
- ENTRY:
    - SuperTrend flips RED → GREEN  → BUY CALL (ATM).
    - SuperTrend flips GREEN → RED → BUY PUT (ATM).
    - Only ONE open trade at a time.
- EXIT:
    - +Target points on OPTION (default 15 points, configurable).
    - -Stoploss points on OPTION (default 10 points, configurable).
    - SuperTrend flip (trend reversal).
    - Time exit at 15:20 IST.
    - Daily profit target hit.
    - Daily loss limit hit.
- Position sizing:
    - quantity_per_lot = 35 (from Strategy.lot_size).
    - number_of_lots = Strategy.num_lots.
    - total_quantity = lot_size × num_lots.
    - daily_profit_target = num_lots × 1000 (using base_daily_target_per_lot).

This file does NOT modify existing strategy files. It integrates only via:
- `Strategy` model (for lot sizes and daily targets).
- `TradeLog` model (for logging entries/exits).
"""

import os
import sys
import time
import logging
from decimal import Decimal
from datetime import datetime, time as dt_time
from typing import Optional, Dict, Tuple

from django.core.management.base import BaseCommand

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.models import Strategy, TradeLog
from trading.services.candle_aggregator import CandleAggregator
from trading.services.heikin_ashi import HeikinAshiCalculator
from trading.services.super_trend import SuperTrendCalculator, detect_signal_change
from trading.services.strike_selector import StrikeSelector
from trading.utils.time_helpers import get_ist_now
from trading.utils.expiry_functions import round_to_nearest_strike

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Candle aggregation (15-minute futures candles)
# ---------------------------------------------------------------------------


class CandleAggregator15Min:
    """
    Thin wrapper over generic CandleAggregator to enforce 15-minute buckets.
    """

    def __init__(self):
        self._agg = CandleAggregator(candle_interval_minutes=15)

    def add_ltp(self, ltp: Decimal, timestamp: datetime) -> Optional[Dict]:
        """
        Add LTP and return a NEW completed 15-min candle when one closes.
        """
        return self._agg.add_ltp(ltp, timestamp)

    def get_last_candle(self) -> Optional[Dict]:
        return self._agg.get_last_candle()

    def get_candles(self, count: int = 50):
        return self._agg.get_candles(count)


# ---------------------------------------------------------------------------
#  ATM Option selector (BankNifty)
# ---------------------------------------------------------------------------


class OptionSelectorATM:
    """
    ATM option selector using existing StrikeSelector helpers.
    """

    def __init__(self):
        self._selector = StrikeSelector()

    def select_atm(self, futures_ltp: Decimal, direction: str, futures_symbol: Optional[str]) -> Tuple[str, int, datetime.date]:
        """
        Select ATM CALL/PUT option based on current futures LTP.

        Args:
            futures_ltp: Current futures price.
            direction: 'CALL' or 'PUT'.
            futures_symbol: BankNifty futures symbol (for matching expiry).
        """
        # ATM = round(futures_ltp / 100) * 100
        atm_strike = round_to_nearest_strike(futures_ltp, step=100)

        signal_type = "BUY" if direction == "CALL" else "SELL"

        option_symbol, strike, expiry_date = self._selector.select_strike(
            spot_price=Decimal(str(atm_strike)),
            signal_type=signal_type,
            strong_momentum=False,
            futures_symbol=futures_symbol,
        )

        # Ensure strike truly equals ATM (guard against momentum offset)
        if strike != atm_strike:
            from trading.utils.expiry_functions import build_option_symbol

            logger.info(f"Adjusting strike from {strike} to ATM {atm_strike}")
            strike = atm_strike
            option_type = "C" if direction == "CALL" else "P"
            option_symbol = build_option_symbol(expiry_date, strike, option_type)

        return option_symbol, strike, expiry_date


# ---------------------------------------------------------------------------
#  Daily P&L tracking and limits
# ---------------------------------------------------------------------------


class DailyPnLTracker:
    """
    Tracks realised daily P&L and enforces daily profit / loss limits.
    """

    def __init__(self, strategy_obj: Strategy):
        self.strategy_obj = strategy_obj
        self.realised_pnl = Decimal("0")
        self.max_pnl_seen = Decimal("0")
        self.halted_for_day = False

        # Lot sizing
        lot_size = strategy_obj.lot_size or 35
        num_lots = strategy_obj.num_lots or 1
        
        # Daily profit target: num_lots × base_target_per_lot (default 1000 per lot)
        base_target_per_lot = getattr(
            strategy_obj, "base_daily_target_per_lot", Decimal("1000")
        )
        self.daily_profit_target = base_target_per_lot * Decimal(str(num_lots))
        
        # Daily loss limit: treat Strategy.max_daily_loss as **per-lot** loss limit
        # and scale it dynamically with num_lots, as requested:
        #   daily_loss_limit = 2000 × total_lots (configurable per lot in admin).
        base_loss_per_lot = getattr(strategy_obj, "max_daily_loss", Decimal("2000"))
        self.daily_loss_limit = base_loss_per_lot * Decimal(str(num_lots))

        logger.info(
            f"🧮 DailyPnLTracker: num_lots={num_lots}, lot_size={lot_size}, "
            f"daily_target=₹{self.daily_profit_target:.2f}, "
            f"daily_loss_limit=₹{self.daily_loss_limit:.2f}"
        )

    def update_after_trade(self, pnl_value: Decimal):
        """
        Update daily stats after each closed trade.
        """
        if pnl_value is None:
            return
        self.realised_pnl += pnl_value
        if self.realised_pnl > self.max_pnl_seen:
            self.max_pnl_seen = self.realised_pnl

        logger.info(
            f"📊 Daily P&L update: realised=₹{self.realised_pnl:.2f}, "
            f"max=₹{self.max_pnl_seen:.2f}, "
            f"target=₹{self.daily_profit_target:.2f}, "
            f"loss_limit=-₹{self.daily_loss_limit:.2f}"
        )

    def check_limits(self) -> Optional[str]:
        """
        Check if daily limits are hit.

        Returns:
            'DAILY_TARGET', 'DAILY_STOP', or None.
        """
        if self.halted_for_day:
            return None

        if self.realised_pnl >= self.daily_profit_target:
            self.halted_for_day = True
            logger.info("🎯 Daily profit target hit. Halting trading for the day.")
            return "DAILY_TARGET"

        if self.realised_pnl <= -self.daily_loss_limit:
            self.halted_for_day = True
            logger.info("🛑 Daily loss limit hit. Halting trading for the day.")
            return "DAILY_STOP"

        return None


# ---------------------------------------------------------------------------
#  Trade Manager (single-position state)
# ---------------------------------------------------------------------------


class TradeManager:
    """
    Handles single open option trade (CALL or PUT) with fixed TP/SL.
    """

    def __init__(
        self,
        strategy_obj: Strategy,
        dry_run: bool,
        daily_tracker: DailyPnLTracker,
    ):
        self.strategy_obj = strategy_obj
        self.dry_run = dry_run
        self.daily_tracker = daily_tracker

        self.lot_size = strategy_obj.lot_size or 35
        self.num_lots = strategy_obj.num_lots or 1
        self.total_quantity = self.lot_size * self.num_lots

        # Use existing fields to configure TP/SL points (per option)
        # target_points → per-option target (default 15)
        # min_stoploss_points → per-option stop (default 10)
        self.target_points = getattr(strategy_obj, "target_points", 15) or 15
        self.stoploss_points = getattr(strategy_obj, "min_stoploss_points", 10) or 10

        # 15:20 time exit (can override via Strategy.square_off_time_ha if needed)
        self.square_off_time: dt_time = getattr(strategy_obj, "square_off_time_ha", dt_time(15, 20))

        # Current open position (None if flat)
        self.current_position: Optional[Dict] = None
        self.current_trade_log: Optional[TradeLog] = None

        logger.info(
            f"📦 TradeManager: lot_size={self.lot_size}, num_lots={self.num_lots}, "
            f"total_qty={self.total_quantity}, target_pts={self.target_points}, "
            f"stop_pts={self.stoploss_points}, square_off={self.square_off_time}"
        )

    # ----- entry / exit -----------------------------------------------------

    def has_open_position(self) -> bool:
        return self.current_position is not None

    def enter_trade(
        self,
        direction: str,
        futures_ltp: Decimal,
        option_symbol: str,
        strike: int,
        expiry_date,
        option_ltp: Decimal,
        dry_run_place_order,
    ):
        """
        Enter CALL/PUT option trade.

        direction: 'CALL' or 'PUT'
        """
        if self.has_open_position():
            logger.warning("Attempted to enter trade while position already open.")
            return

        entry_time = get_ist_now()
        side = "BUY_CE" if direction == "CALL" else "BUY_PE"

        # Place order (or mock)
        if not self.dry_run:
            dry_run_place_order(option_symbol, self.total_quantity)

        self.current_position = {
            "direction": direction,
            "side": side,
            "entry_time": entry_time,
            "entry_price": option_ltp,
            "entry_futures": futures_ltp,
            "option_symbol": option_symbol,
            "strike": strike,
            "expiry_date": expiry_date,
        }

        logger.info(
            f"✅ ENTER {direction} {option_symbol} qty={self.total_quantity} "
            f"at ₹{option_ltp:.2f} (fut ₹{futures_ltp:.2f})"
        )

        # Create TradeLog row (open)
        self.current_trade_log = TradeLog.objects.create(
            strategy=self.strategy_obj,
            entry_time=entry_time,
            exit_time=None,
            entry_price=option_ltp,
            exit_price=None,
            entry_symbol=option_symbol,
            entry_side=side,
            entry_quantity=self.total_quantity,
            strike=strike,
            expiry_date=expiry_date,
            futures_ltp_entry=futures_ltp,
            futures_ltp_exit=None,
            exit_reason=None,
            pnl_value=None,
            pnl_points=None,
            stoploss_price=None,
            target_price=None,
            is_open=True,
            dry_run=self.dry_run,
        )

    def compute_pnl_points(self, option_ltp: Decimal) -> Decimal:
        """
        Returns (exit - entry) option points (same for CALL/PUT since we are always BUY).
        """
        if not self.current_position:
            return Decimal("0")
        entry_price = self.current_position["entry_price"]
        return option_ltp - entry_price

    def compute_pnl_value(self, option_ltp: Decimal) -> Decimal:
        """
        P&L in rupees = points × total_quantity.
        """
        points = self.compute_pnl_points(option_ltp)
        return points * Decimal(str(self.total_quantity))

    def maybe_exit_on_price(
        self,
        option_ltp: Optional[Decimal],
    ) -> Optional[str]:
        """
        Check TP/SL on option price and time exit.
        Returns exit_reason or None.
        """
        if not self.current_position or option_ltp is None:
            return None

        now = get_ist_now()
        pnl_points = self.compute_pnl_points(option_ltp)

        # 1) Target
        if pnl_points >= Decimal(str(self.target_points)):
            logger.info(
                f"🎯 TARGET hit: +{pnl_points:.2f} pts "
                f"(target {self.target_points} pts)"
            )
            self._finalise_exit(option_ltp, "TARGET")
            return "TARGET"

        # 2) Stoploss
        if pnl_points <= -Decimal(str(self.stoploss_points)):
            logger.info(
                f"🛑 STOPLOSS hit: {pnl_points:.2f} pts "
                f"(stop {self.stoploss_points} pts)"
            )
            self._finalise_exit(option_ltp, "STOPLOSS")
            return "STOPLOSS"

        # 3) Time exit (15:20)
        if now.time() >= self.square_off_time:
            logger.info(
                f"⏰ TIME EXIT: {now.time()} >= {self.square_off_time}"
            )
            self._finalise_exit(option_ltp, "TIME")
            return "TIME"

        return None

    def exit_on_trend_reversal(self, option_ltp: Optional[Decimal]) -> Optional[str]:
        """
        Exit immediately on SuperTrend flip (trend reversal).
        """
        if not self.current_position or option_ltp is None:
            return None
        logger.info("🔁 SuperTrend flip → exit due to trend reversal")
        self._finalise_exit(option_ltp, "TREND_REVERSAL")
        return "TREND_REVERSAL"

    def _finalise_exit(self, exit_price: Decimal, exit_reason: str):
        """
        Internal helper to close position, log P&L, and update DailyPnLTracker.
        """
        if not self.current_position:
            return

        exit_time = get_ist_now()
        entry_price = self.current_position["entry_price"]
        pnl_points = exit_price - entry_price
        pnl_value = pnl_points * Decimal(str(self.total_quantity))

        logger.info(
            f"🚪 EXIT {self.current_position['direction']} {self.current_position['option_symbol']} "
            f"entry ₹{entry_price:.2f} → exit ₹{exit_price:.2f} "
            f"({pnl_points:.2f} pts, ₹{pnl_value:.2f}) reason={exit_reason}"
        )

        # Update TradeLog
        if self.current_trade_log:
            self.current_trade_log.exit_time = exit_time
            self.current_trade_log.exit_price = exit_price
            self.current_trade_log.exit_reason = exit_reason
            self.current_trade_log.pnl_points = pnl_points
            self.current_trade_log.pnl_value = pnl_value
            self.current_trade_log.is_open = False
            self.current_trade_log.futures_ltp_exit = self.current_position["entry_futures"]
            self.current_trade_log.save()

        # Update daily P&L
        self.daily_tracker.update_after_trade(pnl_value)

        # Clear open position
        self.current_position = None
        self.current_trade_log = None


# ---------------------------------------------------------------------------
#  SuperTrend Option Strategy (ties everything together)
# ---------------------------------------------------------------------------


class SuperTrendOptionStrategy:
    """
    FULLY automated SuperTrend option buying strategy.
    """

    def __init__(self, strategy_obj: Strategy, dry_run: bool = True):
        self.strategy_obj = strategy_obj
        self.dry_run = dry_run

        self.candles = CandleAggregator15Min()
        self.ha_calc = HeikinAshiCalculator()
        # Dual SuperTrend structure:
        # - Fast:  ST(7,  2.0)
        # - Slow:  ST(10, 1.5)
        self.st_fast = SuperTrendCalculator(atr_period=7, multiplier=Decimal("2.0"))
        self.st_slow = SuperTrendCalculator(atr_period=10, multiplier=Decimal("1.5"))
        self.option_selector = OptionSelectorATM()
        self.daily_tracker = DailyPnLTracker(strategy_obj)
        self.trade_manager = TradeManager(strategy_obj, dry_run, self.daily_tracker)

        # Live prices
        self.futures_symbol: Optional[str] = None
        self.option_symbol: Optional[str] = None
        self.futures_ltp: Optional[Decimal] = None
        self.option_ltp: Optional[Decimal] = None

        # SuperTrend state
        self.last_fast_supertrend: Optional[Dict] = None
        self.last_slow_supertrend: Optional[Dict] = None
        # Last combined arrow signal: 'BUY', 'SELL', or None
        self.last_arrow_signal: Optional[str] = None

        # Alice Blue client
        self.alice_client = None
        self.ws_connected = False

    # ----- Historical warmup -----------------------------------------------

    def load_historical_candles(self):
        """
        Load yesterday's 1-minute futures data, resample to 15-minute candles,
        and warm up Heikin Ashi + SuperTrend so that ST(10,2) is READY
        immediately when live trading starts (no need to wait for 10+ bars).
        """
        try:
            from datetime import timedelta, date
            from alice_blue import HistoricalDataType
            import pandas as pd
        except ImportError as e:
            logger.warning(f"Cannot import modules for historical data: {e}")
            return

        if not self.alice_client:
            logger.warning("Alice Blue client not initialized, skipping historical warmup")
            return

        try:
            # Use yesterday's session (skip weekends)
            today = get_ist_now().date()
            yesterday = today - timedelta(days=1)
            while yesterday.weekday() >= 5:  # Sat/Sun
                yesterday = yesterday - timedelta(days=1)

            # Find BankNifty futures instrument
            all_instruments = self.alice_client.search_instruments("NFO", "BANKNIFTY")
            banknifty_futures = [
                inst
                for inst in all_instruments
                if inst.symbol.startswith("BANKNIFTY") and inst.symbol.endswith("F")
            ]
            if not banknifty_futures:
                logger.warning("SuperTrend warmup: could not find BankNifty futures instrument")
                return

            instrument = banknifty_futures[0]

            # Fetch 1-minute data from yesterday (12:00–15:30 for speed)
            from datetime import datetime as dt

            start_time = dt.combine(yesterday, dt.min.time()).replace(hour=12, minute=0)
            end_time = dt.combine(yesterday, dt.min.time()).replace(hour=15, minute=30)

            logger.info(
                f"📊 SuperTrend warmup: loading historical futures candles from "
                f"{yesterday.strftime('%Y-%m-%d')} (12:00–15:30)..."
            )

            historical_data = self.alice_client.historical_data(
                instrument=instrument,
                ffrom=start_time,
                to=end_time,
                type=HistoricalDataType.Minute,
            )

            if not historical_data:
                logger.warning("SuperTrend warmup: no historical data returned")
                return

            # Convert to DataFrame
            if isinstance(historical_data, dict):
                if "result" in historical_data:
                    df = pd.DataFrame(historical_data["result"])
                else:
                    df = pd.DataFrame(historical_data)
            else:
                df = pd.DataFrame(historical_data)

            if df.empty:
                logger.warning("SuperTrend warmup: historical data is empty")
                return

            # Ensure datetime index
            df["datetime"] = pd.to_datetime(df.get("datetime", df.get("time", df.index)))
            df = df.set_index("datetime")

            # Resample to 15-minute candles to match live ST logic
            df_15 = df.resample("15min").agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            ).dropna()

            if df_15.empty:
                logger.warning("SuperTrend warmup: 15-min resample is empty")
                return

            # Use last ~50 candles for context
            df_15 = df_15.tail(50)
            logger.info(f"📊 SuperTrend warmup: loading {len(df_15)} historical 15-min candles...")

            candles_loaded = 0
            for idx, row in df_15.iterrows():
                candle = {
                    "open": Decimal(str(row["open"])),
                    "high": Decimal(str(row["high"])),
                    "low": Decimal(str(row["low"])),
                    "close": Decimal(str(row["close"])),
                    "timestamp": idx.to_pydatetime(),
                    "start_time": idx.to_pydatetime(),
                    "end_time": idx.to_pydatetime(),
                    "volume": int(row.get("volume", 0)),
                }

                # Warm up HA and SuperTrend state (both fast and slow)
                ha_candle = self.ha_calc.add_candle(candle)
                self.st_fast.add_candle(ha_candle)
                self.st_slow.add_candle(ha_candle)
                candles_loaded += 1

            logger.info(
                f"✅ SuperTrend warmup completed with {candles_loaded} historical 15-min candles. "
                f"ST_Fast(7,2) & ST_Slow(10,1.5) ready."
            )
        except Exception as e:
            logger.warning(f"SuperTrend warmup error (non-fatal): {e}")

    # ----- WebSocket setup --------------------------------------------------

    def initialize_alice_blue(self) -> bool:
        """
        Initialize Alice Blue client and subscribe to BankNifty futures.
        """
        try:
            from alice_blue import AliceBlue, LiveFeedType
            from strategy.broker.alice_client import (
                USER_ID,
                API_KEY,
                get_encryption_key,
                get_session_id,
            )
            from trading.utils.expiry_functions import get_banknifty_futures_symbol

            enc_key = get_encryption_key(USER_ID)
            session_id = get_session_id(USER_ID, API_KEY, enc_key)

            self.alice_client = AliceBlue(
                username=USER_ID,
                session_id=session_id,
                master_contracts_to_download=["NFO"],
            )

            # Start WebSocket
            self.alice_client.start_websocket(
                subscribe_callback=self._tick_callback,
                socket_open_callback=self._ws_open_callback,
                socket_error_callback=self._ws_error_callback,
                socket_close_callback=self._ws_close_callback,
            )

            time.sleep(2)

            # Subscribe to BankNifty futures
            self.futures_symbol = get_banknifty_futures_symbol()
            if self.futures_symbol:
                fut_inst = self.alice_client.get_instrument_by_symbol("NFO", self.futures_symbol)
                if fut_inst:
                    self.alice_client.subscribe(fut_inst, LiveFeedType.TICK_DATA)
                    logger.info(f"✅ Subscribed to futures: {self.futures_symbol}")

            return True
        except Exception as e:
            logger.error(f"Failed to initialize Alice Blue: {e}")
            return False

    def _ws_open_callback(self):
        self.ws_connected = True
        logger.info("✅ WebSocket connected")

    def _ws_error_callback(self, error):
        logger.error(f"❌ WebSocket error: {error}")
        self.ws_connected = False

    def _ws_close_callback(self):
        logger.warning("🔌 WebSocket closed")
        self.ws_connected = False

    def _tick_callback(self, tick):
        """
        Handle incoming ticks for futures and option.
        """
        try:
            instrument = tick.get("instrument")
            if not instrument or "ltp" not in tick:
                return

            symbol = instrument.symbol
            ltp = Decimal(str(tick["ltp"]))

            now = get_ist_now()

            if symbol == self.futures_symbol:
                self.futures_ltp = ltp

                # Feed into 15-min candle aggregator
                new_candle = self.candles.add_ltp(ltp, now)
                if new_candle:
                    self._on_new_futures_candle(new_candle)

            elif symbol == self.option_symbol:
                self.option_ltp = ltp
        except Exception as e:
            logger.error(f"Error in tick callback: {e}")

    # ----- SuperTrend & signals --------------------------------------------

    def _on_new_futures_candle(self, candle: Dict):
        """
        Called when a new 15-min futures candle is completed.
        - Convert to Heikin Ashi.
        - Update **both** SuperTrends (fast & slow).
        - Detect BUY/SELL arrows based on dual ST rules.
        - Check for flips → exit/enter.
        """
        # Convert to HA
        ha_candle = self.ha_calc.add_candle(candle)
        st_fast = self.st_fast.add_candle(ha_candle)
        st_slow = self.st_slow.add_candle(ha_candle)
        if not st_fast or not st_slow:
            return

        fast_change = st_fast.get("signal_change")  # 'BUY', 'SELL', 'HOLD'
        fast_color = st_fast["color"]
        slow_color = st_slow["color"]

        # Save state for status display
        self.last_fast_supertrend = st_fast
        self.last_slow_supertrend = st_slow

        # Dual SuperTrend arrow logic:
        # BUY arrow  → ST_Fast flips RED→GREEN AND ST_Slow already GREEN
        # SELL arrow → ST_Fast flips GREEN→RED AND ST_Slow already RED
        arrow_signal: Optional[str] = None
        if fast_change == "BUY" and slow_color == "GREEN":
            arrow_signal = "BUY"
            logger.info("📈 SuperTrend UP ARROW (Fast: RED→GREEN, Slow: GREEN) – CALL setup")
        elif fast_change == "SELL" and slow_color == "RED":
            arrow_signal = "SELL"
            logger.info("📉 SuperTrend DOWN ARROW (Fast: GREEN→RED, Slow: RED) – PUT setup")
        else:
            logger.info(
                f"ℹ️ SuperTrend update: Fast={fast_color}, Slow={slow_color}, "
                f"fast_change={fast_change} → no arrow"
            )

        self.last_arrow_signal = arrow_signal

        # Outside time window? just update state.
        now = get_ist_now()
        start_time = getattr(self.strategy_obj, "trade_start_time", dt_time(9, 15))
        end_time = getattr(self.strategy_obj, "trade_end_time", dt_time(15, 20))
        if not (start_time <= now.time() <= end_time):
            return

        # If daily limits hit, do nothing
        if self.daily_tracker.halted_for_day:
            return
        
        # 1) If we have open position and opposite arrow appears → exit on trend reversal
        if self.trade_manager.has_open_position() and arrow_signal in ("BUY", "SELL"):
            current_dir = self.trade_manager.current_position["direction"]  # 'CALL' or 'PUT'
            # Opposite arrow logic:
            #   In CALL  → SELL arrow (down) exits.
            #   In PUT   → BUY arrow (up) exits.
            if (current_dir == "CALL" and arrow_signal == "SELL") or (
                current_dir == "PUT" and arrow_signal == "BUY"
            ):
                self.trade_manager.exit_on_trend_reversal(self.option_ltp)

        # Re-check daily limits after exit
        daily_reason = self.daily_tracker.check_limits()
        if daily_reason:
            logger.info(f"Daily limit reached after trend reversal: {daily_reason}")
            return

        # 2) If we are flat and we got a valid arrow, open new trade (one trade per arrow)
        if not self.trade_manager.has_open_position() and arrow_signal in ("BUY", "SELL"):
            direction = "CALL" if arrow_signal == "BUY" else "PUT"
            self._enter_on_supertrend_flip(direction)

    def _enter_on_supertrend_flip(self, direction: str):
        """
        Helper to enter trade when SuperTrend flips.
        direction: 'CALL' or 'PUT'
        """
        if not self.futures_ltp:
            logger.warning("No futures LTP available for entry.")
            return

        # Select ATM option
        option_symbol, strike, expiry_date = self.option_selector.select_atm(
            self.futures_ltp, direction, self.futures_symbol
        )

        # Subscribe to option LTP
        if self.alice_client:
            try:
                from alice_blue import LiveFeedType

                inst = self.alice_client.get_instrument_by_symbol("NFO", option_symbol)
                if inst:
                    self.alice_client.subscribe(inst, LiveFeedType.TICK_DATA)
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not subscribe to option {option_symbol}: {e}")

        self.option_symbol = option_symbol

        # Get option LTP (wait briefly if needed)
        option_ltp = self.option_ltp
        if option_ltp is None and self.alice_client:
            try:
                inst = self.alice_client.get_instrument_by_symbol("NFO", option_symbol)
                quote = self.alice_client.get_quote(inst)
                if quote and "ltp" in quote:
                    option_ltp = Decimal(str(quote["ltp"]))
            except Exception as e:
                logger.warning(f"Could not fetch option LTP via API: {e}")

        if option_ltp is None:
            logger.error(f"Cannot enter trade: no LTP for {option_symbol}")
            return

        def dry_run_place_order(symbol: str, qty: int):
            if not self.dry_run and self.alice_client:
                try:
                    inst = self.alice_client.get_instrument_by_symbol("NFO", symbol)
                    order = self.alice_client.place_order(
                        instrument=inst,
                        transaction_type=self.alice_client.TRANSACTION_TYPE_BUY,
                        quantity=qty,
                        order_type=self.alice_client.ORDER_TYPE_MARKET,
                        product_type=self.alice_client.PRODUCT_TYPE_INTRADAY,
                    )
                    logger.info(f"✅ Order placed: {order}")
                except Exception as e:
                    logger.error(f"Order placement failed: {e}")

        # Enter via TradeManager
        self.trade_manager.enter_trade(
            direction=direction,
            futures_ltp=self.futures_ltp,
            option_symbol=option_symbol,
            strike=strike,
            expiry_date=expiry_date,
            option_ltp=option_ltp,
            dry_run_place_order=dry_run_place_order,
        )

    # ----- Periodic checks --------------------------------------------------

    def periodic_checks(self):
        """
        Called from main loop every few seconds:
        - Enforce TP/SL/time exits on option price.
        - Enforce daily limits.
        """
        # If open position, check TP/SL/time
        if self.trade_manager.has_open_position():
            exit_reason = self.trade_manager.maybe_exit_on_price(self.option_ltp)
            if exit_reason:
                logger.info(f"Exit due to {exit_reason}")

        # Check daily limits (may set halted_for_day)
        self.daily_tracker.check_limits()


# ---------------------------------------------------------------------------
#  Django management command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Run SuperTrend(10,2) ATM option-buying strategy (separate from other strategies)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (no real orders)",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run continuously (loop mode)",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
            help="Loop interval in seconds (default: 5)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", True)
        loop = options.get("loop", False)
        interval = options.get("interval", 5)

        # Simple ANSI color helper for partial coloring in console
        RESET = "\033[0m"
        COLORS = {
            "green": "\033[92m",
            "red": "\033[91m",
            "yellow": "\033[93m",
            "cyan": "\033[96m",
            "magenta": "\033[95m",
        }

        def color(text: str, name: str) -> str:
            code = COLORS.get(name)
            return f"{code}{text}{RESET}" if code else text

        mode_str = "DRY-RUN" if dry_run else "LIVE"
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {mode_str} MODE - "
                f"{'No real orders' if dry_run else 'REAL ORDERS ENABLED'}"
            )
        )

        # Get or create dedicated Strategy config
        strategy_obj, _ = Strategy.objects.get_or_create(
            name="SuperTrend Option Buying Strategy",
            defaults={
                "enabled": True,
                "lot_size": 35,
                "num_lots": 1,
                "base_daily_target_per_lot": Decimal("1000"),
                "max_daily_loss": Decimal("2000"),
                "target_points": 15,  # option TP points
                "min_stoploss_points": 10,  # option SL points
                "square_off_time_ha": dt_time(15, 20),
                "trade_start_time": dt_time(9, 15),
                "trade_end_time": dt_time(15, 20),
            },
        )

        if not strategy_obj.enabled:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  Strategy is DISABLED in admin. Enable it to run."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"📊 Strategy: {strategy_obj.name} | "
                f"Lots: {strategy_obj.num_lots} × {strategy_obj.lot_size}"
            )
        )

        # Show per-lot TP/SL in rupees for clarity (1 lot reference)
        tp_1lot = (strategy_obj.target_points or 0) * (strategy_obj.lot_size or 35)
        sl_1lot = (strategy_obj.min_stoploss_points or 0) * (strategy_obj.lot_size or 35)
        self.stdout.write(
            self.style.SUCCESS(
                f"🎯 Per-trade TP/SL (1 lot): TP ≈ ₹{tp_1lot:.0f}, SL ≈ ₹{sl_1lot:.0f}"
            )
        )

        strategy = SuperTrendOptionStrategy(strategy_obj, dry_run=dry_run)

        # Initialize WebSocket / Alice Blue
        if not strategy.initialize_alice_blue():
            self.stdout.write(self.style.ERROR("❌ Failed to initialize Alice Blue"))
            return

        # Load historical candles to warm up SuperTrend so GREEN/RED is ready immediately
        self.stdout.write("📊 Loading historical candles for SuperTrend warmup...")
        try:
            strategy.load_historical_candles()
        except Exception as e:
            logger.warning(f"SuperTrend warmup threw an error (continuing anyway): {e}")

        self.stdout.write("🔄 Starting SuperTrend strategy loop...")
        self.stdout.write("Press Ctrl+C to stop")

        try:
            while True:
                strategy.periodic_checks()

                # Stop entire strategy after configured trading end time
                now_loop = get_ist_now()
                end_time = getattr(strategy_obj, "trade_end_time", dt_time(15, 20))
                if now_loop.time() > end_time:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⏰ Trading window closed: current time {now_loop.strftime('%H:%M:%S')} "
                            f"> end time {end_time.strftime('%H:%M:%S')}"
                        )
                    )
                    break

                # --- Status line: show futures LTP + SuperTrend + position + daily P&L
                status_parts = []
                now = get_ist_now()

                if strategy.futures_ltp is not None:
                    status_parts.append(
                        color(f"Fut: ₹{strategy.futures_ltp:,.2f}", "cyan")
                    )

                # Show dual SuperTrend status when available
                if strategy.last_fast_supertrend and strategy.last_slow_supertrend:
                    try:
                        stf = strategy.last_fast_supertrend
                        sts = strategy.last_slow_supertrend
                        f_val = float(stf["value"])
                        s_val = float(sts["value"])
                        f_col = stf["color"]  # 'GREEN' or 'RED'
                        s_col = sts["color"]
                        f_trend = "UP" if f_col == "GREEN" else "DOWN"
                        s_trend = "UP" if s_col == "GREEN" else "DOWN"
                        stf_text = f"STf(7,2): {f_trend} ({f_col}) @ {f_val:.2f}"
                        sts_text = f"STs(10,1.5): {s_trend} ({s_col}) @ {s_val:.2f}"
                        status_parts.append(color(stf_text, "green" if f_col == "GREEN" else "red"))
                        status_parts.append(color(sts_text, "green" if s_col == "GREEN" else "red"))
                        if strategy.last_arrow_signal in ("BUY", "SELL"):
                            arrow_txt = (
                                "Arrow: BUY (CALL)" if strategy.last_arrow_signal == "BUY"
                                else "Arrow: SELL (PUT)"
                            )
                            status_parts.append(color(arrow_txt, "magenta"))
                    except Exception:
                        pass

                # Open position details
                if strategy.trade_manager.has_open_position():
                    pos = strategy.trade_manager.current_position
                    opt_ltp = strategy.option_ltp or pos["entry_price"]
                    try:
                        pnl_pts = strategy.trade_manager.compute_pnl_points(opt_ltp)
                        pnl_val = strategy.trade_manager.compute_pnl_value(opt_ltp)
                        trade_text = (
                            f"IN TRADE: {pos['option_symbol']} {pos['direction']} "
                            f"Entry ₹{pos['entry_price']:.2f} Cur ₹{opt_ltp:.2f} "
                            f"P&L: {pnl_pts:.2f} pts / ₹{pnl_val:.2f}"
                        )
                        pnl_color = (
                            "green" if pnl_val > 0 else "red" if pnl_val < 0 else None
                        )
                        status_parts.append(
                            color(trade_text, pnl_color) if pnl_color else trade_text
                        )
                    except Exception:
                        pass

                # Daily P&L / limits + per-lot TP/SL reference (1 lot)
                dt = strategy.daily_tracker
                tp_1lot = (strategy_obj.target_points or 0) * (strategy_obj.lot_size or 35)
                sl_1lot = (strategy_obj.min_stoploss_points or 0) * (strategy_obj.lot_size or 35)
                daily_text = (
                    f"Daily P&L: ₹{dt.realised_pnl:.2f} / ₹{dt.daily_profit_target:.2f} "
                    f"LossLimit:-₹{dt.daily_loss_limit:.2f} | "
                    f"TP/SL (1 lot): TP≈₹{tp_1lot:.0f}, SL≈₹{sl_1lot:.0f}"
                )
                daily_color = (
                    "green" if dt.realised_pnl > 0 else "red" if dt.realised_pnl < 0 else None
                )
                status_parts.append(
                    color(daily_text, daily_color) if daily_color else daily_text
                )
                if dt.halted_for_day:
                    status_parts.append("Status: HALTED")

                if status_parts:
                    self.stdout.write(
                        f"[{now.strftime('%H:%M:%S')}] {' | '.join(status_parts)}"
                    )

                if not loop:
                    break

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⏹️  Stopping SuperTrend strategy..."))
            # On manual stop, attempt time exit if a position is open
            if strategy.trade_manager.has_open_position():
                strategy.trade_manager.maybe_exit_on_price(strategy.option_ltp)

        self.stdout.write(self.style.SUCCESS("✅ SuperTrend strategy stopped"))


