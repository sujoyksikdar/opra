"""
Create standalone allocation models so the allocation app no longer depends
on polls models. The polls tables are left completely untouched.

On the fresh DB (postgres_data_sep), 0001_initial ran SeparateDatabaseAndState
with no actual DB operations, so AllocationVoter and AllocationCache exist only
in migration state (pointing to polls tables). This migration:
  - removes those old state entries
  - creates all new allocation tables from scratch
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('allocation', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Remove old state entries (no DB ops needed since 0001 created none) ──
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel('AllocationVoter'),
                migrations.DeleteModel('AllocationCache'),
            ],
        ),

        # ── Create new standalone models ──
        migrations.CreateModel(
            name='AllocationQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question_text', models.CharField(max_length=200)),
                ('question_desc', models.TextField(blank=True, null=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='static/img/items/')),
                ('imageURL', models.CharField(blank=True, max_length=500, null=True)),
                ('pub_date', models.DateTimeField(verbose_name='date published')),
                ('recentCSVText', models.TextField(blank=True, default=None, null=True)),
                ('status', models.IntegerField(default=1)),
                ('display_pref', models.IntegerField(default=1)),
                ('display_user_info', models.IntegerField(default=1)),
                ('creator_pref', models.IntegerField(default=1)),
                ('emailInviteCSV', models.BooleanField(default=False)),
                ('emailInvite', models.BooleanField(default=False)),
                ('emailDelete', models.BooleanField(default=False)),
                ('emailStart', models.BooleanField(default=False)),
                ('emailStop', models.BooleanField(default=False)),
                ('poll_algorithm', models.IntegerField(default=1)),
                ('alloc_res_tables', models.IntegerField(default=6)),
                ('alloc_algorithms', models.IntegerField(default=0)),
                ('first_tier', models.IntegerField(default=0)),
                ('utility_model', models.IntegerField(default=0)),
                ('results_visible_after', models.DateTimeField(blank=True, null=True)),
                ('m_poll', models.BooleanField(default=False)),
                ('next', models.IntegerField(default=-1)),
                ('first', models.IntegerField(default=-1)),
                ('open', models.IntegerField(default=0)),
                ('allow_self_sign_up', models.IntegerField(default=0)),
                ('initial_ui', models.IntegerField(default=1)),
                ('ui_number', models.IntegerField(default=6)),
                ('twocol_enabled', models.BooleanField(default=True)),
                ('onecol_enabled', models.BooleanField(default=True)),
                ('slider_enabled', models.BooleanField(default=True)),
                ('star_enabled', models.BooleanField(default=True)),
                ('yesno_enabled', models.BooleanField(default=True)),
                ('budgetUI_enabled', models.BooleanField(default=False)),
                ('ListUI_enabled', models.BooleanField(default=False)),
                ('infiniteBudgetUI_enabled', models.BooleanField(default=False)),
                ('question_owner', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('question_voters', models.ManyToManyField(related_name='allocation_participated', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='AllocationItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_text', models.CharField(max_length=200)),
                ('item_description', models.CharField(blank=True, max_length=1000, null=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='static/img/items/')),
                ('imageURL', models.CharField(blank=True, max_length=500, null=True)),
                ('imageReference', models.CharField(blank=True, max_length=500, null=True)),
                ('timestamp', models.DateTimeField(verbose_name='item timestamp')),
                ('recently_added', models.BooleanField(default=False)),
                ('utility', models.FloatField(default=0.0)),
                ('self_sign_up_user_id', models.TextField(default='')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationquestion')),
            ],
            options={'ordering': ['timestamp']},
        ),
        migrations.CreateModel(
            name='AllocationResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('resp_str', models.CharField(blank=True, max_length=1000, null=True)),
                ('timestamp', models.DateTimeField(verbose_name='response timestamp')),
                ('anonymous_voter', models.CharField(blank=True, max_length=50, null=True)),
                ('anonymous_id', models.IntegerField(default=0)),
                ('comment', models.CharField(blank=True, max_length=1000, null=True)),
                ('active', models.IntegerField(default=1)),
                ('behavior_data', models.TextField(default='')),
                ('allocation', models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationitem')),
                ('question', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationquestion')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['timestamp']},
        ),
        migrations.CreateModel(
            name='AllocationDictionary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('response', models.ForeignKey(default=None, on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationresponse')),
            ],
        ),
        migrations.CreateModel(
            name='AllocationKeyValuePair',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.IntegerField(db_index=True, default=0)),
                ('container', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationdictionary')),
                ('key', models.ForeignKey(db_index=True, default=None, on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationitem')),
            ],
        ),
        # These tables already exist from a previous partial migration run,
        # so skip the DB creation and only update migration state.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='AllocationVoter',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationquestion')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                        ('response', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='allocation.allocationresponse')),
                    ],
                ),
                migrations.CreateModel(
                    name='AllocationCache',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('hash_key', models.CharField(max_length=64, unique=True)),
                        ('allocation_data', models.TextField()),
                        ('timestamp', models.DateTimeField(auto_now=True)),
                        ('hit_count', models.IntegerField(default=0)),
                    ],
                ),
            ],
        ),
    ]
