# Generated by Django 4.1.6 on 2023-03-06 07:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fighthealthinsurance", "0005_denial_regulator"),
    ]

    operations = [
        migrations.AddField(
            model_name="denialtypes",
            name="appeal_text",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
