from .models import TradeConfig, TradeLog
from django.contrib import admin

@admin.register(TradeConfig)
class TradeConfigAdmin(admin.ModelAdmin):
    list_display = ('strategy_name', 'closing_price', 'future_entry_direction', 'trade_start', 'trade_end', 'is_active')

@admin.register(TradeLog)
class TradeLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'option_symbol', 'direction', 'entry_price', 'exit_price', 'pnl', 'status')
    list_filter = ('status', 'direction')
