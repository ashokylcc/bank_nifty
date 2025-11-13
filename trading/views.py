"""
Views for trading app - metrics endpoint
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from trading.models import Strategy, TradeLog, DailyStats
from trading.utils.time_helpers import get_today_date, get_ist_now
from decimal import Decimal


@require_http_methods(["GET"])
def metrics(request):
    """
    Metrics endpoint returning current strategy state
    
    Returns JSON:
    {
        "status": "RUNNING" | "STOPPED",
        "open_trades": N,
        "daily_pnl": X,
        "strategy_enabled": true/false,
        "daily_stats": {...}
    }
    """
    # Get active strategy
    strategy = Strategy.objects.filter(enabled=True).last()
    
    if not strategy:
        return JsonResponse({
            "status": "STOPPED",
            "message": "No active strategy found"
        })
    
    # Get open trades
    open_trades = TradeLog.objects.filter(
        strategy=strategy,
        is_open=True
    ).count()
    
    # Get today's stats
    today = get_today_date()
    daily_stats = DailyStats.objects.filter(
        strategy=strategy,
        date=today
    ).first()
    
    if daily_stats:
        daily_pnl = float(daily_stats.total_pnl)
        total_trades = daily_stats.total_trades
        win_rate = float(daily_stats.win_rate)
    else:
        daily_pnl = 0.0
        total_trades = 0
        win_rate = 0.0
    
    # Determine status
    status = "RUNNING" if strategy.enabled else "STOPPED"
    
    return JsonResponse({
        "status": status,
        "strategy_enabled": strategy.enabled,
        "open_trades": open_trades,
        "daily_pnl": daily_pnl,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "daily_stats": {
            "total_pnl": float(daily_stats.total_pnl) if daily_stats else 0.0,
            "total_trades": daily_stats.total_trades if daily_stats else 0,
            "winning_trades": daily_stats.winning_trades if daily_stats else 0,
            "losing_trades": daily_stats.losing_trades if daily_stats else 0,
            "win_rate": float(daily_stats.win_rate) if daily_stats else 0.0,
            "max_drawdown": float(daily_stats.max_drawdown) if daily_stats else 0.0,
        } if daily_stats else {},
        "timestamp": get_ist_now().isoformat()
    })

