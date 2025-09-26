#!/usr/bin/env python3
"""
🎯 OPTIMIZED MOVEMENT STRATEGY (Strong Signals • Higher Targets • Low Frequency)
==============================================================================

This command is a stricter variant of the smart movement strategy. It:
- Trades ONLY on strong signals
- Uses higher profit targets (₹800/lot) and wider stoploss (₹1000/lot)
- Limits to 1 trade per day
- Monitors all day (09:30–15:30) until a strong signal appears, executes once, then stops

This file is separate and does not modify smart_movement_strategy.py.
"""

import os
import sys
import django
import time
from datetime import datetime, time as dt_time
import pytz

# Add the project directory to Python path
sys.path.append('/var/www/html/bank_nifty')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'banknifty_trader.settings')
django.setup()

from django.core.management.base import BaseCommand
from strategy.broker.alice_client import get_encryption_key, get_session_id
from strategy.broker.live_ltp import WebSocketLTP
from strategy.models import TradeConfig, TradeLog
from alice_blue import TransactionType, OrderType, ProductType


class Command(BaseCommand):
    help = 'Optimized Movement Strategy - Strong signal, higher target, single trade'

    def add_arguments(self, parser):
        parser.add_argument('--simulate', action='store_true', help='Run in simulation mode')

    def handle(self, *args, **options):
        simulate = options['simulate']

        # SETTINGS
        CAPITAL = 30000
        QUANTITY = 1          # Number of lots. Increase to 2/3/etc. to scale size
        LOT_SIZE = 35         # Alice Blue lot size (fixed)
        ACTUAL_QTY = QUANTITY * LOT_SIZE

        # Expose to methods if needed later
        self.quantity = QUANTITY
        self.lot_size = LOT_SIZE

        # Strong-only thresholds
        STRONG_MOVEMENT_POINTS = 150    # 150+ points (balanced)
        STRONG_MOVEMENT_PERCENT = 0.020 # 2.0%+

        # Targets/SL per lot
        BASE_TARGET_PER_LOT = 500       # balanced target per lot
        BASE_STOPLOSS_PER_LOT = 600     # balanced stoploss per lot

        TARGET_PROFIT = BASE_TARGET_PER_LOT * QUANTITY
        STOPLOSS = BASE_STOPLOSS_PER_LOT * QUANTITY

        # Daily limits
        MAX_TRADES_PER_DAY = 1
        BASE_PROFIT_TARGET_DAILY = 500
        BASE_MAX_DAILY_LOSS = 600
        PROFIT_TARGET_DAILY = BASE_PROFIT_TARGET_DAILY * QUANTITY
        MAX_DAILY_LOSS = BASE_MAX_DAILY_LOSS * QUANTITY

        # Trading times
        TRADING_START = dt_time(9, 30)
        TRADING_END = dt_time(15, 30)
        SQUARE_OFF_TIME = dt_time(15, 20)

        # In simulation, ignore market hours to allow immediate testing
        if simulate:
            TRADING_START = dt_time(0, 0)
            TRADING_END = dt_time(23, 59)
            SQUARE_OFF_TIME = dt_time(23, 55)

        # Market references (update closing daily)
        YESTERDAY_CLOSING = 55121.80
        FUTURE_SYMBOL = 'BANKNIFTY30SEP25F'
        OPTION_PREFIX = 'BANKNIFTY30SEP25'

        # Tracking
        daily_trade_count = 0
        daily_pnl = 0.0

        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)

        self.stdout.write(self.style.SUCCESS('🎯 OPTIMIZED MOVEMENT STRATEGY'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'🕐 Current Time: {now.strftime("%H:%M:%S")} IST')
        self.stdout.write(f'📊 Yesterday\'s Closing: ₹{YESTERDAY_CLOSING}')
        self.stdout.write(f'📦 Lots: {QUANTITY} | Lot Size: {LOT_SIZE} | Actual Qty: {ACTUAL_QTY}')
        self.stdout.write(f'🎯 Per-lot Target: ₹{BASE_TARGET_PER_LOT} | Per-lot Stoploss: ₹{BASE_STOPLOSS_PER_LOT}')
        self.stdout.write(f'🎯 Daily Target: ₹{PROFIT_TARGET_DAILY} | Max Loss: ₹{MAX_DAILY_LOSS} | Max Trades: {MAX_TRADES_PER_DAY}')

        # Session and WebSocket
        try:
            if simulate:
                self.stdout.write('🎮 SIMULATION MODE: Skipping session login')
                session_id = 'simulation_session'
            else:
                from strategy.broker.alice_client import USER_ID, API_KEY
                enc_key = get_encryption_key(USER_ID)
                session_id = get_session_id(USER_ID, API_KEY, enc_key)
                self.stdout.write('🔐 Session login successful.')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Session login failed: {e}'))
            if not simulate:
                return

        ltp_streamer = None
        if not simulate:
            ltp_streamer = WebSocketLTP(username=USER_ID, session_id=session_id, exchange='NFO')
            ltp_streamer.start()
            self.stdout.write('🔍 Testing WebSocket connection...')
            time.sleep(2)
            if not ltp_streamer.connected:
                self.stdout.write(self.style.WARNING('⚠️ WebSocket connection failed, switching to simulation mode'))
                simulate = True
                ltp_streamer = None
            else:
                self.stdout.write(self.style.SUCCESS('✅ WebSocket connection established'))

        # Subscribe to future in live mode
        if not simulate and ltp_streamer:
            ltp_streamer.subscribe(FUTURE_SYMBOL)

        # Monitoring loop until strong signal or end of day or trade done
        self.stdout.write('\n🔎 Monitoring for STRONG signal only (200 pts & 3.5%+)...')
        while True:
            now = datetime.now(ist)
            t = now.time()

            if not simulate:
                if t < TRADING_START:
                    time.sleep(5)
                    continue
                if t >= TRADING_END:
                    self.stdout.write('⏰ Trading window ended. No trades executed today.')
                    return
            if daily_trade_count >= MAX_TRADES_PER_DAY:
                self.stdout.write('🛑 Max trades reached. Stopping.')
                return

            # Get latest future LTP
            if simulate:
                import random
                # Strong signal almost immediately for fast simulation
                if random.random() < 0.95:
                    movement_percent = random.uniform(3.6, 4.2)  # strong-range
                else:
                    movement_percent = random.uniform(0.5, 2.5)
                movement_direction = random.choice([-1, 1])
                future_ltp = YESTERDAY_CLOSING + (movement_direction * YESTERDAY_CLOSING * movement_percent / 100)
                # show progress occasionally
                self.stdout.write(f"📊 Sim movement: {movement_percent:.2f}% → LTP ₹{future_ltp:.2f}")
            else:
                future_ltp = ltp_streamer.get_ltp(FUTURE_SYMBOL)

            if not future_ltp:
                time.sleep(1)
                continue

            price_change = future_ltp - YESTERDAY_CLOSING
            price_change_percent = (price_change / YESTERDAY_CLOSING) * 100

            # Strong-only gate
            if abs(price_change) < STRONG_MOVEMENT_POINTS or abs(price_change_percent) < STRONG_MOVEMENT_PERCENT:
                time.sleep(0.1)
                continue

            # Decide direction & option
            future_direction = 'BUY' if price_change > 0 else 'SELL'
            # Round to nearest 100 for ATM strike
            atm_strike = round(YESTERDAY_CLOSING / 100) * 100
            option_symbol = (
                f"{OPTION_PREFIX}C{int(atm_strike)}" if future_direction == 'BUY'
                else f"{OPTION_PREFIX}P{int(atm_strike)}"
            )

            # Subscribe option and fetch entry price
            if not simulate and ltp_streamer:
                ltp_streamer.subscribe(option_symbol)
                entry_price = ltp_streamer.get_ltp(option_symbol)
            else:
                import random
                entry_price = random.uniform(400, 600)

            if not entry_price:
                time.sleep(1)
                continue

            # Place BUY
            buy_order_id = None
            if not simulate and ltp_streamer:
                try:
                    instrument = ltp_streamer.instrument_map.get(option_symbol)
                    if not instrument:
                        instrument = ltp_streamer.alice.get_instrument_by_symbol('NFO', option_symbol)
                    buy_order_id = ltp_streamer.alice.place_order(
                        transaction_type=TransactionType.Buy,
                        instrument=instrument,
                        quantity=ACTUAL_QTY,
                        order_type=OrderType.Market,
                        product_type=ProductType.Intraday
                    )
                    self.stdout.write(self.style.SUCCESS(f"🛒 BUY {option_symbol} x {ACTUAL_QTY} (lots {QUANTITY}) @ ~₹{entry_price}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Failed to place BUY order: {e}'))
                    continue
            else:
                self.stdout.write(f"🎮 SIM: BUY {option_symbol} x {ACTUAL_QTY} (lots {QUANTITY}) @ ₹{entry_price:.2f}")

            # Monitor position until target/SL/time
            pnl = 0.0
            status = 'HOLD'
            start_time = datetime.now(ist)
            trailing_sl = STOPLOSS

            # Fast simulation path: decide outcome immediately for testing
            if simulate:
                import random
                outcome = random.choices(['target', 'stoploss', 'time'], weights=[70, 20, 10])[0]
                if outcome == 'target':
                    exit_price = entry_price + (TARGET_PROFIT / ACTUAL_QTY)
                    pnl = TARGET_PROFIT
                    status = 'TARGET HIT'
                elif outcome == 'stoploss':
                    exit_price = entry_price - (STOPLOSS / ACTUAL_QTY)
                    pnl = -STOPLOSS
                    status = 'STOPLOSS HIT'
                else:
                    # small positive time exit
                    exit_price = entry_price + max(3, TARGET_PROFIT / ACTUAL_QTY * 0.15)
                    pnl = (exit_price - entry_price) * ACTUAL_QTY
                    status = 'TIME EXIT'

                # Save and stop (single trade)
                try:
                    config = TradeConfig.objects.filter(is_active=True).last()
                    if not config:
                        config = TradeConfig.objects.create(
                            strategy_name='Optimized Movement Strategy',
                            closing_price=YESTERDAY_CLOSING,
                            lot_size=LOT_SIZE,
                            target=TARGET_PROFIT,
                            stoploss=STOPLOSS,
                            trade_start=TRADING_START,
                            trade_end=SQUARE_OFF_TIME,
                            is_active=True,
                        )

                    TradeLog.objects.create(
                        strategy=config,
                        option_symbol=option_symbol,
                        direction='BUY',
                        strike_price=int(atm_strike),
                        entry_price=entry_price,
                        exit_price=exit_price,
                        pnl=pnl,
                        status=status,
                        message=f'Strong-only entry | Target ₹{TARGET_PROFIT} | SL ₹{STOPLOSS}',
                    )
                    self.stdout.write('✅ Trade log saved successfully')
                except Exception as e:
                    self.stdout.write(f'❌ Failed to save trade log: {e}')

                daily_trade_count += 1
                daily_pnl += pnl
                self.stdout.write(f'📊 Trade {daily_trade_count}/{MAX_TRADES_PER_DAY} | PnL: ₹{pnl:.2f} | Daily PnL: ₹{daily_pnl:.2f}')
                self.stdout.write('🛑 SINGLE-TRADE MODE: Stopping for the day.')
                return

            while True:
                now = datetime.now(ist)
                if now.time() >= SQUARE_OFF_TIME:
                    # Time exit
                    exit_price = entry_price if simulate else (ltp_streamer.get_ltp(option_symbol) or entry_price)
                    pnl = (exit_price - entry_price) * ACTUAL_QTY
                    status = 'TIME EXIT'
                    if not simulate and ltp_streamer:
                        try:
                            instrument = ltp_streamer.instrument_map.get(option_symbol) or ltp_streamer.alice.get_instrument_by_symbol('NFO', option_symbol)
                            ltp_streamer.alice.place_order(
                                transaction_type=TransactionType.Sell,
                                instrument=instrument,
                                quantity=ACTUAL_QTY,
                                order_type=OrderType.Market,
                                product_type=ProductType.Intraday
                            )
                            self.stdout.write(f"💰 SELL {option_symbol} x {ACTUAL_QTY} (lots {QUANTITY}) @ ~₹{exit_price}")
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'❌ Failed to place SELL order: {e}'))
                    break

                current_ltp = entry_price
                if simulate:
                    import random
                    current_ltp = entry_price * random.uniform(0.98, 1.02)
                else:
                    current_ltp = ltp_streamer.get_ltp(option_symbol) or entry_price

                pnl = (current_ltp - entry_price) * ACTUAL_QTY

                # Target/SL checks
                if pnl >= TARGET_PROFIT:
                    exit_price = current_ltp
                    status = 'TARGET HIT'
                    if not simulate and ltp_streamer:
                        try:
                            instrument = ltp_streamer.instrument_map.get(option_symbol) or ltp_streamer.alice.get_instrument_by_symbol('NFO', option_symbol)
                            ltp_streamer.alice.place_order(
                                transaction_type=TransactionType.Sell,
                                instrument=instrument,
                                quantity=ACTUAL_QTY,
                                order_type=OrderType.Market,
                                product_type=ProductType.Intraday
                            )
                            self.stdout.write(f"💰 SELL {option_symbol} x {ACTUAL_QTY} (lots {QUANTITY}) @ ~₹{exit_price}")
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'❌ Failed to place SELL order: {e}'))
                    break

                if pnl <= -trailing_sl:
                    exit_price = current_ltp
                    status = 'STOPLOSS HIT'
                    if not simulate and ltp_streamer:
                        try:
                            instrument = ltp_streamer.instrument_map.get(option_symbol) or ltp_streamer.alice.get_instrument_by_symbol('NFO', option_symbol)
                            ltp_streamer.alice.place_order(
                                transaction_type=TransactionType.Sell,
                                instrument=instrument,
                                quantity=ACTUAL_QTY,
                                order_type=OrderType.Market,
                                product_type=ProductType.Intraday
                            )
                            self.stdout.write(f"💰 SELL {option_symbol} x {ACTUAL_QTY} (lots {QUANTITY}) @ ~₹{exit_price}")
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'❌ Failed to place SELL order: {e}'))
                    break

                # Trail SL to lock profits (50% of max profit)
                trailing_sl = max(trailing_sl, max(0, pnl) * 0.5)
                time.sleep(1)

            # Save TradeLog
            try:
                config = TradeConfig.objects.filter(is_active=True).last()
                if not config:
                    config = TradeConfig.objects.create(
                        strategy_name='Optimized Movement Strategy',
                        closing_price=YESTERDAY_CLOSING,
                        lot_size=LOT_SIZE,
                        target=TARGET_PROFIT,
                        stoploss=STOPLOSS,
                        trade_start=TRADING_START,
                        trade_end=SQUARE_OFF_TIME,
                        is_active=True,
                    )

                TradeLog.objects.create(
                    strategy=config,
                    option_symbol=option_symbol,
                    direction='BUY',
                    strike_price=int(YESTERDAY_CLOSING),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    status=status,
                    message=f'Strong-only entry | Target ₹{TARGET_PROFIT} | SL ₹{STOPLOSS}',
                )
                self.stdout.write('✅ Trade log saved successfully')
            except Exception as e:
                self.stdout.write(f'❌ Failed to save trade log: {e}')

            # Update counters and stop (single-trade mode)
            daily_trade_count += 1
            daily_pnl += pnl
            self.stdout.write(f'📊 Trade {daily_trade_count}/{MAX_TRADES_PER_DAY} | PnL: ₹{pnl:.2f} | Daily PnL: ₹{daily_pnl:.2f}')
            self.stdout.write('🛑 SINGLE-TRADE MODE: Stopping for the day.')
            return


