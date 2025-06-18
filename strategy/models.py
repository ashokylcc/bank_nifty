from django.db import models

DIRECTION_CHOICES = [
    ('BUY', 'Buy (Call Option)'),
    ('SELL', 'Sell (Put Option)'),
]

class TradeConfig(models.Model):
    strategy_name = models.CharField(max_length=100, default="High Frequency Breakout")
    closing_price = models.FloatField()
    lot_size = models.IntegerField(default=15)
    target = models.FloatField(default=500)
    stoploss = models.FloatField(default=250)
    trade_start = models.TimeField(default="09:15")
    trade_end = models.TimeField(default="09:45")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    future_entry_direction = models.CharField(
        max_length=4,
        choices=DIRECTION_CHOICES,
        default='BUY'
    )

    def __str__(self):
        return f"{self.strategy_name} | {self.closing_price} | {self.trade_start}-{self.trade_end}"


class TradeLog(models.Model):
    strategy = models.ForeignKey(TradeConfig, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    option_symbol = models.CharField(max_length=50)
    direction = models.CharField(max_length=10)  # BUY or SELL
    strike_price = models.IntegerField()
    entry_price = models.FloatField()
    exit_price = models.FloatField()
    pnl = models.FloatField()
    status = models.CharField(max_length=50)  # e.g., TARGET HIT, STOPLOSS HIT, TIME EXIT
    message = models.TextField(blank=True)

    def __str__(self):
        return f"{self.timestamp} | {self.option_symbol} | {self.status} | PnL: {self.pnl}"
