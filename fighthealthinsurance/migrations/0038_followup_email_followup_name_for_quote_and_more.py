# Generated by Django 5.1.2 on 2024-10-12 22:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "fighthealthinsurance",
            "0037_rename_followup_id_followup_followup_result_id_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="followup",
            name="email",
            field=models.CharField(max_length=300, null=True),
        ),
        migrations.AddField(
            model_name="followup",
            name="name_for_quote",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="followup",
            name="quote",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="followup",
            name="use_quote",
            field=models.TextField(default=False),
        ),
    ]