from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(name='RequestBudget', fields=[
        ('key', models.CharField(max_length=64, primary_key=True, serialize=False)),
        ('window', models.BigIntegerField()), ('count', models.PositiveIntegerField(default=0))])]
