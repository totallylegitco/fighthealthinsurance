# Generated by Django 5.0.8 on 2024-09-27 19:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fighthealthinsurance", "0018_interestedprofessional"),
    ]

    operations = [
        migrations.AddField(
            model_name="interestedprofessional",
            name="most_common_denial",
            field=models.CharField(default="", max_length=300),
        ),
        migrations.AddField(
            model_name="interestedprofessional",
            name="provider_type",
            field=models.CharField(default="", max_length=300),
        ),
    ]