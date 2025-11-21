"""
Django models for Heikin-Ashi candle tracking
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class HeikinAshiCandle(models.Model):
    """
    Store Heikin-Ashi candles calculated from 15-minute OHLC data
    """
    TREND_CHOICES = [
        ('uptrend_start', 'Uptrend Start'),
        ('downtrend_start', 'Downtrend Start'),
        ('uptrend_continue', 'Uptrend Continue'),
        ('downtrend_continue', 'Downtrend Continue'),
        ('neutral', 'Neutral'),
    ]
    
    COLOR_CHOICES = [
        ('green', 'Green (Bullish)'),
        ('red', 'Red (Bearish)'),
    ]
    
    # Symbol identifier (e.g., "BANKNIFTY", "BANKNIFTY_FUTURES")
    symbol = models.CharField(max_length=50, db_index=True, help_text="Trading symbol")
    
    # Timestamp (15-minute candle end time)
    timestamp = models.DateTimeField(db_index=True, help_text="Candle timestamp (end time)")
    
    # Original OHLC values (for reference)
    original_open = models.DecimalField(max_digits=10, decimal_places=2)
    original_high = models.DecimalField(max_digits=10, decimal_places=2)
    original_low = models.DecimalField(max_digits=10, decimal_places=2)
    original_close = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Heikin-Ashi calculated values
    ha_open = models.DecimalField(max_digits=10, decimal_places=2, help_text="HA_Open = (prev_HA_Open + prev_HA_Close) / 2")
    ha_close = models.DecimalField(max_digits=10, decimal_places=2, help_text="HA_Close = (O + H + L + C) / 4")
    ha_high = models.DecimalField(max_digits=10, decimal_places=2, help_text="HA_High = max(H, HA_Open, HA_Close)")
    ha_low = models.DecimalField(max_digits=10, decimal_places=2, help_text="HA_Low = min(L, HA_Open, HA_Close)")
    
    # Color and trend
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, help_text="green if HA_Close > HA_Open, else red")
    trend = models.CharField(max_length=20, choices=TREND_CHOICES, default='neutral', help_text="Trend direction and reversal status")
    
    # Volume (if available)
    volume = models.BigIntegerField(default=0, null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Heikin-Ashi Candle"
        verbose_name_plural = "Heikin-Ashi Candles"
        unique_together = ['symbol', 'timestamp']  # One HA candle per symbol per timestamp
        indexes = [
            models.Index(fields=['symbol', '-timestamp']),
            models.Index(fields=['symbol', 'color']),
            models.Index(fields=['symbol', 'trend']),
        ]
    
    def __str__(self):
        color_emoji = "🟢" if self.color == 'green' else "🔴"
        return f"{self.symbol} {color_emoji} {self.trend} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def is_bullish(self):
        """Check if candle is bullish (green)"""
        return self.color == 'green'
    
    @property
    def is_bearish(self):
        """Check if candle is bearish (red)"""
        return self.color == 'red'
    
    @property
    def is_uptrend_start(self):
        """Check if this candle marks the start of an uptrend"""
        return self.trend == 'uptrend_start'
    
    @property
    def is_downtrend_start(self):
        """Check if this candle marks the start of a downtrend"""
        return self.trend == 'downtrend_start'

