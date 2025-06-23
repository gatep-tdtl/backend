
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('talent_management', '0014_alter_employerprofile_industry_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='resume',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='email address'),
        ),
    ]
