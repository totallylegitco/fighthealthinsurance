# Generated by Django 4.1.6 on 2023-02-23 06:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("fighthealthinsurance", "0002_remove_denial_submissions"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="denial",
            name="regulator",
        ),
        migrations.DeleteModel(
            name="DenialRegulatorRelation",
        ),
    ]
