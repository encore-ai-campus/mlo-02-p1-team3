from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("frontend", "0007_sitevisit")]

    operations = [
        migrations.AddField(
            model_name="member",
            name="selected_dragon_design",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
