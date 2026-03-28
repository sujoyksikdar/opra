from django.db import migrations


class Migration(migrations.Migration):
    """
    Remove AllocationVoter and AllocationCache from polls ORM state.
    These models now belong to the allocation app (see allocation/migrations/0001_initial.py).
    Uses SeparateDatabaseAndState so NO database changes occur — tables are preserved.
    """

    dependencies = [
        ('polls', '0143_question_results_visible_after'),
        ('allocation', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # no DB changes
            state_operations=[
                migrations.DeleteModel(name='AllocationCache'),
                migrations.DeleteModel(name='AllocationVoter'),
            ],
        ),
    ]
