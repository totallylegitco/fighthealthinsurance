from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    username = models.CharField(max_length=40, unique=True)
    email = models.EmailField()
    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    pass

# Auth-ish-related models
class UserDomain(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(primary_key=False, blank=False, null=False, max_length=300, unique=True)
    active = models.BooleanField()


class ConsumerUser(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    active = models.BooleanField()


class ProfessionalUser(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    npi_number = models.CharField(blank=True, null=True, max_length=20)
    active = models.BooleanField()
