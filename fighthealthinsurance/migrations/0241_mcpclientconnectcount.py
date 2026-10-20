from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fighthealthinsurance", "0240_chooser_vote_flags_and_medical_term_check"),
    ]

    operations = [
        migrations.CreateModel(
            name="McpClientConnectCount",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("hour", models.DateTimeField()),
                ("client", models.CharField(max_length=64)),
                ("count", models.PositiveIntegerField(default=0)),
                ("last_seen_at", models.DateTimeField()),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("hour", "client"),
                        name="mcp_client_connect_count_hour_client",
                    )
                ],
            },
        ),
    ]
