"""
Django admin interface for trading app
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db import models
from decimal import Decimal
from trading.models import Strategy, Signal, Order, TradeLog, DailyStats
from trading.models_ha import HeikinAshiCandle


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    """Admin interface for Strategy"""
    list_display = ['name', 'enabled', 'capital', 'risk_per_trade_pct', 'max_daily_loss', 'num_lots', 'yesterday_closing_price', 'created_at']
    list_filter = ['enabled', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'enabled')
        }),
        ('Risk Parameters', {
            'fields': ('capital', 'risk_per_trade_pct', 'max_daily_loss', 'max_concurrent_trades')
        }),
        ('Trading Parameters', {
            'fields': ('lot_size', 'num_lots', 'tick_value', 'breakout_buffer', 'min_stoploss_points',
                      'stoploss_range_multiplier', 'target_multiplier')
        }),
        ('Momentum Parameters', {
            'fields': ('volume_multiplier', 'ema_fast', 'ema_slow', 'rsi_period',
                      'rsi_buy_min', 'rsi_buy_max', 'rsi_sell_min', 'rsi_sell_max')
        }),
        ('Time Windows', {
            'fields': ('range_start_time', 'range_end_time', 'trade_start_time',
                      'trade_end_time', 'square_off_time', 'trade_cooldown_minutes')
        }),
        ('Reference Price', {
            'fields': ('yesterday_closing_price',),
            'description': "Yesterday's futures closing price (used for ATM strike selection)"
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['enable_strategy', 'disable_strategy']
    
    def enable_strategy(self, request, queryset):
        """Enable selected strategies"""
        queryset.update(enabled=True)
        self.message_user(request, f"{queryset.count()} strategy(ies) enabled")
    enable_strategy.short_description = "Enable selected strategies (kill switch OFF)"
    
    def disable_strategy(self, request, queryset):
        """Disable selected strategies (kill switch)"""
        queryset.update(enabled=False)
        self.message_user(request, f"{queryset.count()} strategy(ies) disabled (kill switch ON)")
    disable_strategy.short_description = "Disable selected strategies (kill switch ON)"


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    """Admin interface for Signal"""
    list_display = ['id', 'strategy', 'signal_type', 'breakout_price', 'momentum_score',
                   'selected_symbol', 'executed', 'timestamp']
    list_filter = ['signal_type', 'executed', 'timestamp', 'strategy']
    search_fields = ['selected_symbol', 'execution_reason']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Signal Information', {
            'fields': ('strategy', 'signal_type', 'timestamp', 'executed', 'execution_reason')
        }),
        ('Range Data', {
            'fields': ('first_high', 'first_low', 'range_value')
        }),
        ('Breakout Data', {
            'fields': ('breakout_price', 'breakout_volume', 'avg_volume')
        }),
        ('Momentum Data', {
            'fields': ('ema_fast_value', 'ema_slow_value', 'rsi_value', 'momentum_score')
        }),
        ('Strike Selection', {
            'fields': ('spot_price', 'selected_strike', 'selected_symbol', 'expiry_date')
        }),
        ('Risk Calculation', {
            'fields': ('stoploss_points', 'target_points', 'calculated_qty')
        }),
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin interface for Order"""
    list_display = ['order_id', 'symbol', 'side', 'quantity', 'status', 'filled_price',
                   'dry_run', 'created_at']
    list_filter = ['status', 'side', 'dry_run', 'created_at', 'execution_adapter']
    search_fields = ['order_id', 'symbol']
    readonly_fields = ['created_at', 'filled_at']
    date_hierarchy = 'created_at'


@admin.register(TradeLog)
class TradeLogAdmin(admin.ModelAdmin):
    """Admin interface for TradeLog"""
    list_display = ['id', 'dry_run_badge', 'entry_symbol', 'entry_side', 'entry_price', 
                   'exit_price', 'pnl_display', 'status_badge', 'exit_reason', 'entry_time', 'duration_display']
    list_filter = ['is_open', 'exit_reason', 'entry_side', 'dry_run', 'entry_time', 'strategy']
    search_fields = ['entry_symbol', 'entry_side']
    readonly_fields = ['entry_time', 'exit_time', 'created_at', 'updated_at', 'pnl_percentage_display', 'duration_display']
    date_hierarchy = 'entry_time'
    list_per_page = 50
    change_list_template = 'admin/trading/tradelog/change_list.html'
    
    fieldsets = (
        ('Trade Information', {
            'fields': ('strategy', 'signal', 'entry_order', 'exit_order', 'is_open', 'dry_run')
        }),
        ('Entry Details', {
            'fields': ('entry_time', 'entry_price', 'entry_symbol', 'entry_side', 'entry_quantity')
        }),
        ('Option Details', {
            'fields': ('strike', 'expiry_date', 'futures_ltp_entry', 'futures_ltp_exit'),
            'classes': ('collapse',)
        }),
        ('Exit Details', {
            'fields': ('exit_time', 'exit_price', 'exit_reason')
        }),
        ('Risk Management', {
            'fields': ('stoploss_price', 'target_price', 'trailing_stoploss_price', 'breakeven_triggered')
        }),
        ('P&L', {
            'fields': ('pnl_points', 'pnl_value', 'pnl_percentage_display', 'commission', 'slippage_estimate')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'duration_display'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related('strategy', 'signal', 'entry_order', 'exit_order')
    
    def changelist_view(self, request, extra_context=None):
        """Override to add P&L summary"""
        response = super().changelist_view(request, extra_context=extra_context)
        
        try:
            # Get the filtered queryset (respects date filters, search, etc.)
            qs = response.context_data['cl'].queryset
            
            # Calculate summary for closed trades only
            closed_trades = qs.filter(is_open=False, pnl_value__isnull=False)
            
            total_trades = closed_trades.count()
            winning_trades = closed_trades.filter(pnl_value__gt=0).count()
            losing_trades = closed_trades.filter(pnl_value__lt=0).count()
            
            # Calculate totals
            from decimal import Decimal
            total_pnl = closed_trades.aggregate(
                total=models.Sum('pnl_value')
            )['total'] or Decimal('0.00')
            
            gross_profit = closed_trades.filter(pnl_value__gt=0).aggregate(
                total=models.Sum('pnl_value')
            )['total'] or Decimal('0.00')
            
            gross_loss = closed_trades.filter(pnl_value__lt=0).aggregate(
                total=models.Sum('pnl_value')
            )['total'] or Decimal('0.00')
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate profit factor
            if gross_loss != 0:
                profit_factor = float(abs(gross_profit / gross_loss))
            elif gross_profit > 0:
                profit_factor = float('inf')
            else:
                profit_factor = 0.0
            
            # Calculate averages
            avg_win = gross_profit / winning_trades if winning_trades > 0 else Decimal('0.00')
            avg_loss = abs(gross_loss / losing_trades) if losing_trades > 0 else Decimal('0.00')
            
            # Open trades count
            open_trades = qs.filter(is_open=True).count()
            
            # Add summary to context
            response.context_data['pnl_summary'] = {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'total_pnl': total_pnl,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'open_trades': open_trades,
            }
        except (AttributeError, KeyError):
            # If there's an error, set empty summary
            response.context_data['pnl_summary'] = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': Decimal('0.00'),
                'gross_profit': Decimal('0.00'),
                'gross_loss': Decimal('0.00'),
                'win_rate': 0,
                'profit_factor': 0,
                'avg_win': Decimal('0.00'),
                'avg_loss': Decimal('0.00'),
                'open_trades': 0,
            }
        
        return response
    
    def dry_run_badge(self, obj):
        """Display dry-run badge"""
        if obj.dry_run:
            return format_html('<span style="background-color: #ffc107; color: #000; padding: 3px 8px; border-radius: 3px; font-size: 11px;">DRY-RUN</span>')
        return format_html('<span style="background-color: #28a745; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">LIVE</span>')
    dry_run_badge.short_description = 'Mode'
    
    def pnl_display(self, obj):
        """Display P&L with color coding"""
        if obj.pnl_value is None:
            return "-"
        # Format the number first, then pass to format_html
        pnl_formatted = f"{float(obj.pnl_value):.2f}"
        if obj.pnl_value > 0:
            return format_html('<span style="color: #28a745; font-weight: bold;">₹{}</span>', pnl_formatted)
        elif obj.pnl_value < 0:
            return format_html('<span style="color: #dc3545; font-weight: bold;">₹{}</span>', pnl_formatted)
        return format_html('₹{}', pnl_formatted)
    pnl_display.short_description = 'P&L'
    pnl_display.admin_order_field = 'pnl_value'
    
    def status_badge(self, obj):
        """Display status badge"""
        if obj.is_open:
            return format_html('<span style="background-color: #17a2b8; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">OPEN</span>')
        return format_html('<span style="background-color: #6c757d; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">CLOSED</span>')
    status_badge.short_description = 'Status'
    
    def duration_display(self, obj):
        """Display trade duration"""
        if obj.duration_minutes is None:
            return "-"
        # Convert to int to ensure proper formatting
        duration = int(obj.duration_minutes)
        hours = duration // 60
        minutes = duration % 60
        if hours > 0:
            return format_html("{}h {}m", hours, minutes)
        return format_html("{}m", minutes)
    duration_display.short_description = 'Duration'
    
    def pnl_percentage_display(self, obj):
        """Display P&L percentage"""
        if obj.pnl_percentage is None:
            return "-"
        # Format the number first, then pass to format_html
        pct_formatted = f"{float(obj.pnl_percentage):.2f}"
        return format_html("{}%", pct_formatted)
    pnl_percentage_display.short_description = 'P&L %'


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    """Admin interface for DailyStats"""
    list_display = ['date', 'strategy', 'total_trades', 'winning_trades', 'losing_trades',
                   'total_pnl', 'win_rate', 'max_drawdown']
    list_filter = ['date', 'strategy']
    search_fields = ['strategy__name']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('strategy', 'date')
        }),
        ('Trade Counts', {
            'fields': ('total_trades', 'winning_trades', 'losing_trades')
        }),
        ('P&L', {
            'fields': ('total_pnl', 'gross_profit', 'gross_loss')
        }),
        ('Metrics', {
            'fields': ('win_rate', 'avg_win', 'avg_loss', 'profit_factor')
        }),
        ('Risk Metrics', {
            'fields': ('max_drawdown', 'max_drawdown_time')
        }),
        ('Other', {
            'fields': ('total_commission', 'total_slippage')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(HeikinAshiCandle)
class HeikinAshiCandleAdmin(admin.ModelAdmin):
    """Admin interface for Heikin-Ashi Candles"""
    list_display = ['symbol', 'timestamp', 'color_badge', 'trend', 'ha_open', 'ha_close', 
                   'ha_high', 'ha_low', 'original_close', 'created_at']
    list_filter = ['symbol', 'color', 'trend', 'timestamp']
    search_fields = ['symbol']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('symbol', 'timestamp', 'color', 'trend')
        }),
        ('Original OHLC', {
            'fields': ('original_open', 'original_high', 'original_low', 'original_close')
        }),
        ('Heikin-Ashi Values', {
            'fields': ('ha_open', 'ha_close', 'ha_high', 'ha_low')
        }),
        ('Volume', {
            'fields': ('volume',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def color_badge(self, obj):
        """Display color badge"""
        if obj.color == 'green':
            return format_html('<span style="background-color: #28a745; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">🟢 GREEN</span>')
        else:
            return format_html('<span style="background-color: #dc3545; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">🔴 RED</span>')
    color_badge.short_description = 'Color'

