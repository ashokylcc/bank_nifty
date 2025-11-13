"""
Management command to sync trades from CSV to TradeLog model
"""
import os
import csv
import logging
from decimal import Decimal
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from trading.models import Strategy, TradeLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync trades from CSV file to TradeLog model'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-file',
            type=str,
            help='Path to CSV file (default: trade_logs/trade_log.csv)',
            default=None
        )
        parser.add_argument(
            '--strategy-id',
            type=int,
            help='Strategy ID to associate trades with (default: latest active strategy)',
            default=None
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip trades that already exist (based on entry_time and entry_symbol)',
        )
    
    def handle(self, *args, **options):
        csv_file = options.get('csv_file')
        strategy_id = options.get('strategy_id')
        dry_run = options.get('dry_run', False)
        skip_existing = options.get('skip_existing', False)
        
        # Get strategy
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id)
            except Strategy.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Strategy with ID {strategy_id} not found"))
                return
        else:
            strategy = Strategy.objects.filter(enabled=True).first()
            if not strategy:
                strategy = Strategy.objects.first()
            if not strategy:
                self.stdout.write(self.style.ERROR("❌ No strategy found. Create one first."))
                return
        
        self.stdout.write(self.style.SUCCESS(f"📊 Using Strategy: {strategy.name} (ID: {strategy.id})"))
        
        # Determine CSV file path
        if not csv_file:
            try:
                BASE_DIR = settings.BASE_DIR
            except:
                from pathlib import Path
                BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            
            csv_file = os.path.join(BASE_DIR, 'trade_logs', 'trade_log.csv')
        
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"❌ CSV file not found: {csv_file}"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"📄 Reading CSV: {csv_file}"))
        
        # Parse CSV
        trades_imported = 0
        trades_skipped = 0
        trades_errors = 0
        
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    try:
                        # Parse row
                        timestamp_str = row.get('timestamp', '').strip()
                        side = row.get('side', '').strip()
                        action = row.get('action', '').strip()
                        entry_price_str = row.get('entry_price', '').strip()
                        exit_price_str = row.get('exit_price', '').strip()
                        pnl_str = row.get('pnl', '').strip()
                        reason = row.get('reason', '').strip()
                        symbol = row.get('symbol', '').strip()
                        futures_ltp_str = row.get('futures_ltp', '').strip()
                        strike_str = row.get('strike', '').strip()
                        
                        if not timestamp_str or not side or not action:
                            self.stdout.write(self.style.WARNING(f"⚠️  Row {row_num}: Missing required fields, skipping"))
                            trades_errors += 1
                            continue
                        
                        # Parse timestamp
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                            except ValueError:
                                self.stdout.write(self.style.WARNING(f"⚠️  Row {row_num}: Invalid timestamp format: {timestamp_str}"))
                                trades_errors += 1
                                continue
                        
                        # Handle ENTRY
                        if action == 'ENTRY':
                            if skip_existing:
                                existing = TradeLog.objects.filter(
                                    entry_symbol=symbol or 'UNKNOWN',
                                    entry_time=timestamp,
                                    strategy=strategy
                                ).exists()
                                if existing:
                                    trades_skipped += 1
                                    continue
                            
                            if not dry_run:
                                TradeLog.objects.create(
                                    strategy=strategy,
                                    entry_time=timestamp,
                                    entry_price=Decimal(entry_price_str) if entry_price_str else Decimal('0'),
                                    entry_symbol=symbol or 'UNKNOWN',
                                    entry_side=side,
                                    entry_quantity=25,  # Default lot size
                                    strike=int(strike_str) if strike_str and strike_str.isdigit() else None,
                                    futures_ltp_entry=Decimal(futures_ltp_str) if futures_ltp_str else None,
                                    is_open=True,
                                    dry_run=True  # CSV imports are always dry-run
                                )
                            trades_imported += 1
                            self.stdout.write(f"  ✅ Row {row_num}: ENTRY - {side} {symbol} @ ₹{entry_price_str}")
                        
                        # Handle EXIT
                        elif action == 'EXIT':
                            # Find matching open trade
                            if not symbol:
                                symbol = 'UNKNOWN'
                            
                            if not dry_run:
                                # Try to find by symbol and approximate time (within 1 hour)
                                trade = TradeLog.objects.filter(
                                    entry_symbol=symbol,
                                    is_open=True,
                                    strategy=strategy
                                ).order_by('-entry_time').first()
                                
                                if trade:
                                    # Map exit reason
                                    exit_reason_map = {
                                        'TARGET': 'TARGET',
                                        'STOPLOSS': 'STOPLOSS',
                                        'TIME': 'TIME',
                                        'MARKET_CLOSE': 'MARKET_CLOSE',
                                        'MANUAL': 'MANUAL',
                                        'TRAILING': 'TRAILING'
                                    }
                                    mapped_reason = exit_reason_map.get(reason, 'MANUAL')
                                    
                                    entry_price = trade.entry_price
                                    exit_price = Decimal(exit_price_str) if exit_price_str else entry_price
                                    pnl_points = exit_price - entry_price
                                    pnl_value = Decimal(pnl_str) if pnl_str else Decimal('0')
                                    
                                    trade.exit_time = timestamp
                                    trade.exit_price = exit_price
                                    trade.exit_reason = mapped_reason
                                    trade.pnl_points = pnl_points
                                    trade.pnl_value = pnl_value
                                    trade.futures_ltp_exit = Decimal(futures_ltp_str) if futures_ltp_str else None
                                    trade.is_open = False
                                    trade.save()
                                    
                                    trades_imported += 1
                                    self.stdout.write(f"  ✅ Row {row_num}: EXIT - {symbol} @ ₹{exit_price_str}, P&L: ₹{pnl_str}")
                                else:
                                    self.stdout.write(self.style.WARNING(f"⚠️  Row {row_num}: No open trade found for EXIT: {symbol}"))
                                    trades_errors += 1
                            else:
                                trades_imported += 1
                                self.stdout.write(f"  ✅ Row {row_num}: EXIT - {symbol} @ ₹{exit_price_str}, P&L: ₹{pnl_str} (dry-run)")
                        
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"❌ Row {row_num}: Error - {e}"))
                        trades_errors += 1
                        logger.error(f"Error processing CSV row {row_num}: {e}")
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error reading CSV: {e}"))
            return
        
        # Summary
        self.stdout.write(self.style.SUCCESS("\n" + "="*50))
        self.stdout.write(self.style.SUCCESS("📊 Import Summary"))
        self.stdout.write(self.style.SUCCESS("="*50))
        self.stdout.write(f"  ✅ Imported: {trades_imported}")
        self.stdout.write(f"  ⏭️  Skipped: {trades_skipped}")
        self.stdout.write(f"  ❌ Errors: {trades_errors}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY-RUN mode - no data was actually imported"))
            self.stdout.write("Run without --dry-run to import trades")

