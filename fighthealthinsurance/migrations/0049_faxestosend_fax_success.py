# Generated by Django 5.1.2 on 2024-11-06 21:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fighthealthinsurance", "0048_alter_faxestosend_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="faxestosend",
            name="fax_success",
            field=models.BooleanField(default=False),
        ),
    ]