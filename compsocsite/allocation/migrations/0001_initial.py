from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Transfer ORM ownership of AllocationVoter and AllocationCache from polls to allocation.
    Uses SeparateDatabaseAndState so NO database changes occur — the existing
    polls_allocationvoter and polls_allocationcache tables are preserved as-is.
    """

    dependencies = [
        ('polls', '0143_question_results_visible_after'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # no DB changes
            state_operations=[
                migrations.CreateModel(
                    name='AllocationVoter',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='polls.question')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                        ('response', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='polls.response')),
                    ],
                    options={'db_table': 'polls_allocationvoter'},
                ),
                migrations.CreateModel(
                    name='AllocationCache',
                    fields=[
                        ('id', models.BigAutoField(primary_key=True, serialize=False)),
                        ('hash_key', models.CharField(max_length=64, unique=True)),
                        ('allocation_data', models.TextField()),
                        ('timestamp', models.DateTimeField(auto_now=True)),
                        ('hit_count', models.IntegerField(default=0)),
                    ],
                    options={'db_table': 'polls_allocationcache'},
                ),
            ],
        ),
    ]
