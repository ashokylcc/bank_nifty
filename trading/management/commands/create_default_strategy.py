"""
Create default strategy with recommended parameters
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from trading.models import Strategy


class Command(BaseCommand):
    help = 'Create a default strategy with recommended parameters'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            type=str,
            default='BankNifty Momentum Breakout',
            help='Strategy name',
        )
        parser.add_argument(
            '--enabled',
            action='store_true',
            help='Enable strategy immediately',
        )
    
    def handle(self, *args, **options):
        name = options.get('name', 'BankNifty Momentum Breakout')
        enabled = options.get('enabled', False)
        
        # Check if strategy already exists
        existing = Strategy.objects.filter(name=name).first()
        if existing:
            self.stdout.write(self.style.WARNING(f"⚠️  Strategy '{name}' already exists (ID: {existing.id})"))
            response = input("Create new strategy anyway? (y/n): ")
            if response.lower() != 'y':
                self.stdout.write("Cancelled")
                return
        
        # Create strategy with recommended defaults
        strategy = Strategy.objects.create(
            name=name,
            enabled=enabled,
            
            # Risk parameters (recommended defaults)
            capital=Decimal('30000'),  # ₹30,000
            risk_per_trade_pct=Decimal('1.00'),  # 1%
            max_daily_loss=Decimal('600'),  # 2% of ₹30,000 = ₹600
            max_concurrent_trades=1,
            
            # Trading parameters
            lot_size=35,
            tick_value=Decimal('1.00'),
            breakout_buffer=10,  # 10 pts
            min_stoploss_points=40,  # 40 pts
            stoploss_range_multiplier=Decimal('0.6'),
            target_multiplier=Decimal('1.5'),
            
            # Momentum parameters
            volume_multiplier=Decimal('1.5'),  # 1.5x avg volume
            ema_fast=20,
            ema_slow=50,
            rsi_period=14,
            rsi_buy_min=55,  # RSI 55-70 for BUY
            rsi_buy_max=70,
            rsi_sell_min=30,  # RSI 30-45 for SELL
            rsi_sell_max=45,
            
            # Time windows
            range_start_time="09:15:00",  # 9:15 AM
            range_end_time="09:30:00",  # 9:30 AM
            trade_start_time="09:30:00",  # 9:30 AM
            trade_end_time="10:30:00",  # 10:30 AM
            square_off_time="14:45:00",  # 2:45 PM
        )
        
        self.stdout.write(self.style.SUCCESS(f"✅ Strategy created: {strategy.name} (ID: {strategy.id})"))
        self.stdout.write("\n📊 Recommended Default Parameters:")
        self.stdout.write(f"   Capital: ₹{strategy.capital:,}")
        self.stdout.write(f"   Risk per trade: {strategy.risk_per_trade_pct}%")
        self.stdout.write(f"   Max daily loss: ₹{strategy.max_daily_loss:,} (2% of capital)")
        self.stdout.write(f"   Breakout buffer: {strategy.breakout_buffer} pts")
        self.stdout.write(f"   Min stoploss: {strategy.min_stoploss_points} pts")
        self.stdout.write(f"   Volume multiplier: {strategy.volume_multiplier}x")
        self.stdout.write(f"   RSI BUY range: {strategy.rsi_buy_min}-{strategy.rsi_buy_max}")
        self.stdout.write(f"   RSI SELL range: {strategy.rsi_sell_min}-{strategy.rsi_sell_max}")
        self.stdout.write(f"   Trading window: {strategy.trade_start_time} - {strategy.trade_end_time}")
        self.stdout.write(f"   Square-off: {strategy.square_off_time}")
        self.stdout.write(f"\n   Enabled: {strategy.enabled}")
        
        if not enabled:
            self.stdout.write(self.style.WARNING("\n⚠️  Strategy is disabled. Enable it in Django Admin to start trading."))
        
        self.stdout.write(f"\n💡 Next steps:")
        self.stdout.write(f"   1. Review strategy in Django Admin: /admin/trading/strategy/{strategy.id}/")
        self.stdout.write(f"   2. Adjust parameters if needed")
        self.stdout.write(f"   3. Enable strategy when ready")
        self.stdout.write(f"   4. Run: python manage.py run_momentum_strategy --dry-run")

