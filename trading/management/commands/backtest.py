"""
Backtesting command for historical data analysis
"""
import os
import glob
from decimal import Decimal
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from trading.models import Strategy, TradeLog, DailyStats
from trading.services.strategy_engine import StrategyEngine
from trading.services.execution_adapter import AliceBlueMockAdapter
import csv
import statistics


class Command(BaseCommand):
    help = 'Backtest strategy on historical CSV data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-dir',
            type=str,
            required=True,
            help='Directory containing historical CSV files (YYYY-MM-DD format)',
        )
        parser.add_argument(
            '--strategy-id',
            type=int,
            help='Strategy ID to backtest (default: latest)',
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD), default: 3 months ago',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD), default: today',
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file for backtest results (CSV)',
        )
    
    def handle(self, *args, **options):
        csv_dir = options['csv_dir']
        strategy_id = options.get('strategy_id')
        start_date = options.get('start_date')
        end_date = options.get('end_date')
        output_file = options.get('output')
        
        # Get strategy
        if strategy_id:
            try:
                strategy = Strategy.objects.get(id=strategy_id)
            except Strategy.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Strategy with ID {strategy_id} not found"))
                return
        else:
            strategy = Strategy.objects.last()
            if not strategy:
                self.stdout.write(self.style.ERROR("❌ No strategy found"))
                return
        
        self.stdout.write(self.style.SUCCESS(f"📊 Backtesting Strategy: {strategy.name}"))
        self.stdout.write("=" * 70)
        
        # Parse dates
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end = datetime.now().date()
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            # Default: 3 months ago
            start = end - timedelta(days=90)
        
        self.stdout.write(f"📅 Date Range: {start} to {end}")
        self.stdout.write(f"📁 CSV Directory: {csv_dir}")
        
        # Find CSV files
        csv_files = self.find_csv_files(csv_dir, start, end)
        
        if not csv_files:
            self.stdout.write(self.style.ERROR(f"❌ No CSV files found in {csv_dir}"))
            return
        
        self.stdout.write(f"📊 Found {len(csv_files)} CSV files")
        
        # Run backtest
        results = self.run_backtest(strategy, csv_files)
        
        # Calculate metrics
        metrics = self.calculate_metrics(results)
        
        # Display results
        self.display_results(metrics)
        
        # Save to file if requested
        if output_file:
            self.save_results(results, metrics, output_file)
            self.stdout.write(self.style.SUCCESS(f"💾 Results saved to {output_file}"))
    
    def find_csv_files(self, csv_dir, start_date, end_date):
        """Find CSV files in date range"""
        files = []
        current = start_date
        
        while current <= end_date:
            # Try different filename formats
            patterns = [
                f"{current.strftime('%Y-%m-%d')}.csv",
                f"{current.strftime('%Y%m%d')}.csv",
                f"*{current.strftime('%Y-%m-%d')}*.csv",
            ]
            
            for pattern in patterns:
                path = os.path.join(csv_dir, pattern)
                matches = glob.glob(path)
                if matches:
                    files.extend(matches)
                    break
            
            current += timedelta(days=1)
        
        return sorted(set(files))
    
    def run_backtest(self, strategy, csv_files):
        """Run backtest on all CSV files"""
        results = []
        
        for csv_file in csv_files:
            self.stdout.write(f"\n📈 Processing: {os.path.basename(csv_file)}")
            
            # Create fresh adapter for each day
            adapter = AliceBlueMockAdapter(dry_run=True)
            
            # Create engine
            engine = StrategyEngine(strategy, execution_adapter=adapter, dry_run=True)
            engine.initialize()
            
            # Load CSV
            try:
                engine.data_service.load_from_csv(csv_file)
                
                if engine.data_service.candles:
                    latest_candle = engine.data_service.candles[-1]
                    adapter.set_mock_ltp("BANKNIFTY", latest_candle.close)
                
                # Run strategy cycle
                cycle_results = engine.run_single_cycle()
                
                # Get trades for this day
                date = self.extract_date_from_filename(csv_file)
                day_trades = TradeLog.objects.filter(
                    strategy=strategy,
                    entry_time__date=date
                )
                
                results.append({
                    'date': date,
                    'file': csv_file,
                    'trades': day_trades.count(),
                    'cycle_results': cycle_results
                })
                
                engine.shutdown()
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
                continue
        
        return results
    
    def extract_date_from_filename(self, filename):
        """Extract date from filename"""
        basename = os.path.basename(filename)
        # Try YYYY-MM-DD format
        try:
            return datetime.strptime(basename[:10], '%Y-%m-%d').date()
        except:
            # Try YYYYMMDD format
            try:
                return datetime.strptime(basename[:8], '%Y%m%d').date()
            except:
                return datetime.now().date()
    
    def calculate_metrics(self, results):
        """Calculate backtest metrics"""
        from trading.utils.time_helpers import get_today_date
        
        # Get all trades from backtest period
        # Get strategy from first result or use latest
        if results:
            strategy = Strategy.objects.last()  # Use the strategy we backtested
        else:
            strategy = Strategy.objects.last()
        
        all_trades = TradeLog.objects.filter(
            strategy=strategy
        ).exclude(pnl_value__isnull=True)
        
        if not all_trades.exists():
            return {
                'total_trades': 0,
                'error': 'No trades found'
            }
        
        # Basic metrics
        total_trades = all_trades.count()
        winning_trades = all_trades.filter(pnl_value__gt=0).count()
        losing_trades = all_trades.filter(pnl_value__lt=0).count()
        
        # P&L
        total_pnl = sum([t.pnl_value for t in all_trades])
        gross_profit = sum([t.pnl_value for t in all_trades.filter(pnl_value__gt=0)])
        gross_loss = abs(sum([t.pnl_value for t in all_trades.filter(pnl_value__lt=0)]))
        
        # Win rate
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Average win/loss
        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0
        
        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Daily PnL distribution
        daily_pnls = []
        dates = set([t.entry_time.date() for t in all_trades])
        for date in dates:
            day_trades = all_trades.filter(entry_time__date=date)
            day_pnl = sum([t.pnl_value for t in day_trades])
            daily_pnls.append(float(day_pnl))
        
        # Sharpe-like metric (mean / SD)
        if len(daily_pnls) > 1:
            import statistics
            mean_pnl = statistics.mean(daily_pnls)
            std_pnl = statistics.stdev(daily_pnls) if len(daily_pnls) > 1 else 1
            sharpe_like = mean_pnl / std_pnl if std_pnl > 0 else 0
        else:
            sharpe_like = 0
        
        # Max drawdown
        running_pnl = 0
        peak_pnl = 0
        max_drawdown = 0
        
        for trade in all_trades.order_by('entry_time'):
            running_pnl += float(trade.pnl_value)
            if running_pnl > peak_pnl:
                peak_pnl = running_pnl
            drawdown = peak_pnl - running_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # CAGR (if we have start/end dates)
        if results:
            start_date = min([r['date'] for r in results])
            end_date = max([r['date'] for r in results])
            days = (end_date - start_date).days
            years = days / 365.25
            
            # Assume initial capital
            initial_capital = float(Strategy.objects.first().capital)
            final_capital = initial_capital + float(total_pnl)
            
            if years > 0 and initial_capital > 0:
                cagr = ((final_capital / initial_capital) ** (1 / years) - 1) * 100
            else:
                cagr = 0
        else:
            cagr = 0
        
        # Trade frequency
        trading_days = len(dates)
        trade_frequency = total_trades / trading_days if trading_days > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'sharpe_like': sharpe_like,
            'cagr': cagr,
            'trade_frequency': trade_frequency,
            'trading_days': trading_days,
            'daily_pnls': daily_pnls,
            'mean_daily_pnl': (statistics.mean(daily_pnls) if daily_pnls else 0),
            'std_daily_pnl': (statistics.stdev(daily_pnls) if len(daily_pnls) > 1 else 0),
        }
    
    def display_results(self, metrics):
        """Display backtest results"""
        if 'error' in metrics:
            self.stdout.write(self.style.ERROR(f"❌ {metrics['error']}"))
            return
        
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("📊 BACKTEST RESULTS"))
        self.stdout.write("=" * 70)
        
        # Trade Statistics
        self.stdout.write("\n📈 Trade Statistics:")
        self.stdout.write(f"   Total Trades: {metrics['total_trades']}")
        self.stdout.write(f"   Winning: {metrics['winning_trades']} ({metrics['win_rate']:.2f}%)")
        self.stdout.write(f"   Losing: {metrics['losing_trades']}")
        self.stdout.write(f"   Trade Frequency: {metrics['trade_frequency']:.2f} trades/day")
        self.stdout.write(f"   Trading Days: {metrics['trading_days']}")
        
        # P&L Metrics
        self.stdout.write("\n💰 P&L Metrics:")
        self.stdout.write(f"   Total PnL: ₹{metrics['total_pnl']:,.2f}")
        self.stdout.write(f"   Gross Profit: ₹{metrics['gross_profit']:,.2f}")
        self.stdout.write(f"   Gross Loss: ₹{metrics['gross_loss']:,.2f}")
        self.stdout.write(f"   Average Win: ₹{metrics['avg_win']:,.2f}")
        self.stdout.write(f"   Average Loss: ₹{metrics['avg_loss']:,.2f}")
        self.stdout.write(f"   Profit Factor: {metrics['profit_factor']:.2f}")
        
        # Risk Metrics
        self.stdout.write("\n⚠️  Risk Metrics:")
        self.stdout.write(f"   Max Drawdown: ₹{metrics['max_drawdown']:,.2f}")
        self.stdout.write(f"   Sharpe-like (Mean/SD): {metrics['sharpe_like']:.2f}")
        
        # Performance Metrics
        self.stdout.write("\n🚀 Performance Metrics:")
        self.stdout.write(f"   CAGR: {metrics['cagr']:.2f}%")
        self.stdout.write(f"   Mean Daily PnL: ₹{metrics['mean_daily_pnl']:,.2f}")
        self.stdout.write(f"   Std Daily PnL: ₹{metrics['std_daily_pnl']:,.2f}")
        
        # Daily PnL Distribution
        if metrics['daily_pnls']:
            self.stdout.write("\n📊 Daily PnL Distribution:")
            self.stdout.write(f"   Min: ₹{min(metrics['daily_pnls']):,.2f}")
            self.stdout.write(f"   Max: ₹{max(metrics['daily_pnls']):,.2f}")
            self.stdout.write(f"   Median: ₹{statistics.median(metrics['daily_pnls']):,.2f}")
    
    def save_results(self, results, metrics, output_file):
        """Save results to CSV"""
        import statistics
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow(['Metric', 'Value'])
            
            # Metrics
            writer.writerow(['Total Trades', metrics['total_trades']])
            writer.writerow(['Win Rate', f"{metrics['win_rate']:.2f}%"])
            writer.writerow(['Total PnL', f"₹{metrics['total_pnl']:,.2f}"])
            writer.writerow(['CAGR', f"{metrics['cagr']:.2f}%"])
            writer.writerow(['Max Drawdown', f"₹{metrics['max_drawdown']:,.2f}"])
            writer.writerow(['Sharpe-like', f"{metrics['sharpe_like']:.2f}"])
            writer.writerow(['Profit Factor', f"{metrics['profit_factor']:.2f}"])
            
            # Daily PnL
            writer.writerow([])
            writer.writerow(['Date', 'Daily PnL'])
            for i, pnl in enumerate(metrics['daily_pnls']):
                date = list(set([r['date'] for r in results]))[i] if i < len(results) else ''
                writer.writerow([date, f"₹{pnl:,.2f}"])

