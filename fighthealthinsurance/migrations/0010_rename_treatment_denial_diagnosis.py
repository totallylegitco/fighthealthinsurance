# Generated by Django 4.1.7 on 2023-06-18 19:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('fighthealthinsurance', '0009_diagnosis_procedures_denial_procedure_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='denial',
            old_name='treatment',
            new_name='diagnosis',
        ),
    ]