from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading', '0008_add_heikin_ashi_parameters'),
    ]

    operations = [
        migrations.AddField(
            model_name='strategy',
            name='trailing_active_after_ha',
            field=models.DecimalField(
                max_digits=12,
                decimal_places=2,
                default=Decimal('4000'),
                help_text="Activate trailing daily profit lock after this total profit in rupees (e.g. ₹4000)",
            ),
        ),
        migrations.AddField(
            model_name='strategy',
            name='trailing_buffer_ha',
            field=models.DecimalField(
                max_digits=12,
                decimal_places=2,
                default=Decimal('1000'),
                help_text="Maximum profit give-back from peak before squaring off (e.g. ₹1000)",
            ),
        ),
    ]


