# Generated by Django 5.1.1 on 2024-09-22 02:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "fighthealthinsurance",
            "0013_denial_denial_type_text_denial_plan_id_denial_state",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="denial",
            name="appeal_text",
            field=models.TextField(max_length=30000000000, null=True),
        ),
        migrations.AlterField(
            model_name="denial",
            name="denial_text",
            field=models.TextField(max_length=300000000),
        ),
    ]
