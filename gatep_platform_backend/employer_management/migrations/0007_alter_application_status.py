# Generated by Django 5.2.3 on 2025-07-21 06:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer_management', '0006_remove_interview_ai_interview_session_data_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='application',
            name='status',
            field=models.CharField(choices=[('APPLIED', 'Applied'), ('REVIEWED', 'Reviewed'), ('SHORTLISTED', 'Shortlisted'), ('INTERVIEW_SCHEDULED', 'Interview Scheduled'), ('INTERVIEWED', 'Interviewed'), ('OFFER_EXTENDED', 'Offer Extended'), ('OFFER_ACCEPTED', 'Offer Accepted'), ('OFFER_REJECTED', 'Offer Rejected'), ('REJECTED', 'Rejected'), ('HIRED', 'Hired'), ('WITHDRAWN', 'Withdrawn'), ('DELETED', 'Deleted')], default='APPLIED', max_length=50),
        ),
    ]
