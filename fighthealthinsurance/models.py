from django.contrib.auth.models import User
from django.db import models

from typing import Optional

class Denials(models.Model):
    denial_id = models.AutoField(primary_key=True)
    hashed_email = models.CharField(max_length=300, primary_key=False)
    denial_text = models.CharField(max_length=30000000, primary_key=False)
    submissions = models.DateField(null=False, blank=False)
    date = models.DateField(auto_now=False, auto_now_add=True)


class FollowUpType(models.Model):
    id = models.AutoField(primary_key=True)
    subject = models.CharField(max_length=300, primary_key=False)
    text = models.CharField(max_length=30000, primary_key=False)
    duration = models.DurationField()


class FollowUpSched(models.Model):
    follow_up_id = models.AutoField(primary_key=True)
    email = models.CharField(max_length=300, primary_key=False)
    follow_up_type = models.ForeignKey(FollowUpType, on_delete=models.CASCADE)
    follow_up_date = models.DateField(auto_now=False)
    initial = models.DateField(auto_now=False, auto_now_add=True)


class PlanType(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=300, primary_key=False)
