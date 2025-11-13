"""
Management command to run BankNifty Momentum Breakout Strategy
"""
import os
import time
import logging
import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from trading.models import Strategy
from trading.services.strategy_engine import StrategyEngine
from trading.services.concurrency_guard import ConcurrencyGuard

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run BankNifty Momentum Breakout Strategy'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode (no real orders)',
        )
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Run continuously (loop mode)',
        )
        parser.add_argument(
            '--simulate',
            action='store_true',
            help='Run in simulation mode (use CSV data)',
        )
        parser.add_argument(
            '--csv',
            type=str,
            help='Path to CSV file for simulation (required with --simulate)',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run single cycle and exit (useful with --simulate)',
        )
        parser.add_argument(
            '--strategy-id',
            type=int,
            help='Strategy ID to run (default: latest active strategy)',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Loop interval in seconds (default: 5)',
        )
    
    def handle(self, *args, **options):
        # Concurrency guard - ensure single authoritative process
        guard = ConcurrencyGuard()
        
        # Check if another instance is running
        if guard.is_another_instance_running():
            self.stdout.write(self.style.ERROR(
                "❌ Another strategy runner is already running!"
            ))
            self.stdout.write("Only one strategy runner should be active at a time.")
            self.stdout.write("Stop the other instance or check for stale lock file.")
            sys.exit(1)
        
        # Acquire lock
        try:
            with guard:
                self._run_strategy(options)
        except RuntimeError as e:
            self.stdout.write(self.style.ERROR(f"❌ {e}"))
            sys.exit(1)
    
    def _run_strategy(self, options):
        """Run strategy (called within lock context)"""
        # Determine dry-run mode
        dry_run = options.get('dry_run', True)
        
        # Check environment variables
        env_dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
        confirm_real = os.getenv('CONFIRM_REAL_TRADES', 'false').lower() == 'true'
        
        # Final dry-run decision
        if not dry_run and not env_dry_run and confirm_real:
            dry_run = False
            self.stdout.write(self.style.WARNING("⚠️  LIVE TRADING MODE - Real orders will be placed!"))
        else:
            dry_run = True
            self.stdout.write(self.style.SUCCESS("✅ DRY-RUN MODE - No real orders"))
        
        # Get strategy
        strategy_id = options.get('strategy_id')
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id)
            except Strategy.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Strategy with ID {strategy_id} not found"))
                return
        else:
            strategy = Strategy.objects.filter(enabled=True).last()
            if not strategy:
                self.stdout.write(self.style.ERROR("❌ No active strategy found"))
                self.stdout.write("Create a strategy in Django Admin and enable it")
                return
        
        self.stdout.write(self.style.SUCCESS(f"📊 Running Strategy: {strategy.name}"))
        self.stdout.write(f"   Enabled: {strategy.enabled}")
        self.stdout.write(f"   Capital: ₹{strategy.capital}")
        self.stdout.write(f"   Risk per trade: {strategy.risk_per_trade_pct}%")
        self.stdout.write(f"   Max daily loss: ₹{strategy.max_daily_loss}")
        
        if not strategy.enabled:
            self.stdout.write(self.style.WARNING("⚠️  Strategy is disabled (kill switch)"))
            self.stdout.write("Enable it in Django Admin to start trading")
            return
        
        # Handle simulation mode
        simulate = options.get('simulate', False)
        csv_path = options.get('csv')
        
        if simulate:
            if not csv_path:
                self.stdout.write(self.style.ERROR("❌ --csv path required when using --simulate"))
                return
            
            if not os.path.exists(csv_path):
                self.stdout.write(self.style.ERROR(f"❌ CSV file not found: {csv_path}"))
                return
            
            self.stdout.write(self.style.SUCCESS(f"🎮 SIMULATION MODE: Loading data from {csv_path}"))
            dry_run = True  # Force dry-run in simulation
        
        # Initialize strategy engine
        engine = StrategyEngine(strategy, dry_run=dry_run)
        engine.initialize()
        
        # Load CSV data if in simulation mode
        if simulate:
            try:
                engine.data_service.load_from_csv(csv_path)
                self.stdout.write(self.style.SUCCESS(f"✅ Loaded {len(engine.data_service.candles)} candles from CSV"))
                
                # Set mock LTP from latest candle for simulation
                if engine.data_service.candles:
                    latest_candle = engine.data_service.candles[-1]
                    if hasattr(engine.execution_adapter, 'set_mock_ltp'):
                        engine.execution_adapter.set_mock_ltp("BANKNIFTY", latest_candle.close)
                        self.stdout.write(self.style.SUCCESS(f"✅ Set mock LTP: ₹{latest_candle.close}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error loading CSV: {e}"))
                return
        
        loop_mode = options.get('loop', False)
        once_mode = options.get('once', False)
        interval = options.get('interval', 5)
        
        try:
            if once_mode or (simulate and not loop_mode):
                # Run single cycle
                self.stdout.write(self.style.SUCCESS("▶️  Running single cycle"))
                results = engine.run_single_cycle()
                self._log_cycle_results(results)
            elif loop_mode:
                self.stdout.write(self.style.SUCCESS(f"🔄 Starting continuous loop (interval: {interval}s)"))
                self.stdout.write("Press Ctrl+C to stop")
                
                while True:
                    try:
                        results = engine.run_single_cycle()
                        self._log_cycle_results(results)
                        time.sleep(interval)
                    except KeyboardInterrupt:
                        self.stdout.write(self.style.WARNING("\n⏹️  Stopping strategy..."))
                        break
            else:
                self.stdout.write(self.style.SUCCESS("▶️  Running single cycle"))
                results = engine.run_single_cycle()
                self._log_cycle_results(results)
        
        finally:
            engine.shutdown()
            self.stdout.write(self.style.SUCCESS("✅ Strategy stopped"))
            # Lock is released automatically by context manager
    
    def _log_cycle_results(self, results: dict):
        """Log cycle results"""
        if results['range_captured']:
            self.stdout.write("✅ Range captured")
        if results['breakout_detected']:
            self.stdout.write("🎯 Breakout detected")
        if results['signal_created']:
            self.stdout.write("📝 Signal created")
        if results['trade_executed']:
            self.stdout.write("✅ Trade executed")
        if results['trades_exited'] > 0:
            self.stdout.write(f"🔚 {results['trades_exited']} trade(s) exited")

