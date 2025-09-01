from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        Token.objects.create(user=user)  # Create token on user creation
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(_('email address'), unique=True)
    phone = models.CharField(_('phone number'), max_length=20, blank=True, null=True)
    accept_terms = models.BooleanField(_('terms accepted'), default=False)
    newsletter = models.BooleanField(_('newsletter subscribed'), default=False)
    class Gender(models.TextChoices):
        MALE = 'MALE', _('Male')
        FEMALE = 'FEMALE', _('Female')
        OTHER = 'OTHER', _('Other')

    gender = models.CharField(_('gender'), max_length=10, choices=Gender.choices, blank=True, null=True)
    dob = models.DateField(_('date of birth'), blank=True, null=True)
    ROLE_CHOICES = (
        ('seeker', 'Seeker'),
        ('provider', 'Provider'),
    )
    role = models.CharField(_('role'), max_length=20, choices=ROLE_CHOICES, default='seeker')
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email


class Employer(models.Model):
    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, related_name='employer_profile')
    company_name = models.CharField(max_length=255, blank=True)
    company_website = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.company_name or f"Employer({self.user.email})"


class JobSeeker(models.Model):
    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, related_name='seeker_profile')
    resume_url = models.URLField(blank=True)
    resume_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"JobSeeker({self.user.email})"


class Job(models.Model):
    employer = models.ForeignKey(Employer, on_delete=models.CASCADE, related_name='jobs')
    title = models.CharField(max_length=255)
    description = models.TextField()
    requirement = models.TextField(blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        REVIEW = 'REVIEW', _('In Review')
        ACCEPTED = 'ACCEPTED', _('Accepted')
        REJECTED = 'REJECTED', _('Rejected')

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    seeker = models.ForeignKey(JobSeeker, on_delete=models.CASCADE, related_name='applications')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    match_score = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Application({self.seeker.user.email} -> {self.job.title})"


class Interview(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interviews')
    title = models.CharField(max_length=255)
    date = models.DateField()
    time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Interview({self.title})"


class Appointment(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='appointment')
    title = models.CharField(max_length=255)
    time = models.TimeField()
    date = models.DateField()
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Appointment({self.title})"


class Payment(models.Model):
    class Method(models.TextChoices):
        MOMO = 'MOMO', _('Mobile Money')
        OM = 'OM', _('Orange Money')

    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='payments')
    time = models.TimeField()
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=Method.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment({self.user.email} - {self.amount})"