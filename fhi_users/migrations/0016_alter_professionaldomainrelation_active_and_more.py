# Generated by Django 5.1.4 on 2025-02-10 06:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "fhi_users",
            "0005_alter_userdomain_address1_alter_userdomain_city_and_more_squashed_0015_rename_userextraproperties_extrauserproperties_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="professionaldomainrelation",
            name="active",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="professionaldomainrelation",
            name="admin",
            field=models.BooleanField(default=False),
        ),
    ]
