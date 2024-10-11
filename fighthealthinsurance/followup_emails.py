from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from django.contrib.admin.views.decorators import staff_member_required
from django_celery_beat.models import PeriodicTasks
from django.views import View

class ScheduleFollowUps(View):
    """A view to go through and schedule any missing follow ups."""
    @staff_member_required
    def get(self, request):
        denials = Denial.objects().filter(raw_email != None and followupsched__isnull==True).iterator()
        for denial in denials:
            FollowUpSched.create(
                email=denial.raw_email,
                follow_up_date=denial.date.date()+datetime.timedelta(days=15),
                denial_id=denial.denial_id)
