from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("frontend", "0008_member_selected_dragon_design"),
    ]

    operations = [
        migrations.CreateModel(
            name="SelectedRecommendation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("facility_name", models.CharField(max_length=200)),
                ("sport", models.CharField(blank=True, max_length=40)),
                ("address", models.CharField(blank=True, max_length=300)),
                ("latitude", models.FloatField(blank=True, null=True)),
                ("longitude", models.FloatField(blank=True, null=True)),
                ("score", models.PositiveSmallIntegerField(default=0)),
                ("recommendation_snapshot", models.JSONField(blank=True, default=dict)),
                ("selected_at", models.DateTimeField(auto_now=True)),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="selected_recommendations", to="frontend.member")),
            ],
            options={"ordering": ["-selected_at"]},
        ),
    ]
