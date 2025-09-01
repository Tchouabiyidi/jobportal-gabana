from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Employer, JobSeeker, Job, Application, Interview, Appointment

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    # Accept both fullName and name for convenience
    fullName = serializers.CharField(write_only=True, required=False, allow_blank=True)
    name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    role = serializers.CharField(write_only=True, required=False, allow_blank=True)
    tel = serializers.CharField(write_only=True, required=False, allow_blank=True)
    gender = serializers.CharField(write_only=True, required=False, allow_blank=True)
    dob = serializers.DateField(write_only=True, required=False, allow_null=True, input_formats=['%Y-%m-%d'])

    class Meta:
        model = User
        fields = ['email', 'password', 'fullName', 'name', 'role', 'tel', 'gender', 'dob']
        extra_kwargs = {
            'password': {'write_only': True},
            'email': {'required': True},
        }

    def validate(self, data):
        # Validate password strength with Django validators
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return data

    def validate_role(self, value):
        if not value:
            return 'seeker'
        value = value.lower()
        if value not in ['seeker', 'provider']:
            raise serializers.ValidationError("Invalid role. Must be 'seeker' or 'provider'.")
        return value

    def validate_gender(self, value):
        if not value:
            return None
        norm = value.upper()
        if norm not in ['MALE', 'FEMALE', 'OTHER']:
            raise serializers.ValidationError("Invalid gender. Must be 'MALE', 'FEMALE', or 'OTHER'.")
        return norm

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        # Names
        full_name = (validated_data.pop('fullName', '') or validated_data.pop('name', '')).strip()
        role = validated_data.pop('role', 'seeker')
        tel = validated_data.pop('tel', '').strip()
        gender = validated_data.pop('gender', None)
        dob = validated_data.pop('dob', None)

        first_name = ''
        last_name = ''
        if full_name:
            parts = full_name.split()
            first_name = parts[0]
            if len(parts) > 1:
                last_name = ' '.join(parts[1:])

        email = validated_data.get('email')
        password = validated_data.get('password')

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            phone=tel or None,
            gender=gender or None,
            dob=dob,
        )

        # Create role-specific profile
        if role == 'provider':
            Employer.objects.create(user=user)
        else:
            JobSeeker.objects.create(user=user)

        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate(self, data):
        # Trim and normalize email; be case-insensitive for lookup
        email = (data.get('email') or '').strip()
        password = data.get('password')
        
        if email and password:
            user = User.objects.filter(email__iexact=email).first()
            
            if user and user.check_password(password):
                if not user.is_active:
                    raise serializers.ValidationError("User account is disabled.")
                data['user'] = user
            else:
                raise serializers.ValidationError("Unable to log in with provided credentials.")
        else:
            raise serializers.ValidationError("Must include 'email' and 'password'.")
        
        return data

class JobSerializer(serializers.ModelSerializer):
    employer = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'description', 'requirement', 'salary', 'location',
            'created_at', 'is_active', 'employer'
        ]
        read_only_fields = ['id', 'created_at', 'employer']

    def get_employer(self, obj):
        u = getattr(obj.employer, 'user', None)
        return {
            'id': obj.employer.id,
            'company_name': obj.employer.company_name,
            'email': getattr(u, 'email', None)
        }

class ApplicationSerializer(serializers.ModelSerializer):
    # Accept job ID when creating; expose minimal nested info when reading
    job = serializers.PrimaryKeyRelatedField(queryset=Job.objects.all(), write_only=True)
    job_info = serializers.SerializerMethodField(read_only=True)
    seeker = serializers.SerializerMethodField(read_only=True)
    seeker_resume_url = serializers.SerializerMethodField(read_only=True)
    seeker_resume_text = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'job', 'job_info', 'seeker',
            'seeker_resume_url', 'seeker_resume_text',
            'status', 'match_score', 'created_at'
        ]
        read_only_fields = ['id', 'job_info', 'seeker', 'seeker_resume_url', 'seeker_resume_text', 'match_score', 'created_at']

    def get_job_info(self, obj):
        return {
            'id': obj.job.id,
            'title': obj.job.title,
        }

    def get_seeker(self, obj):
        u = getattr(obj.seeker, 'user', None)
        return {
            'id': obj.seeker.id,
            'email': getattr(u, 'email', None),
        }

    def get_seeker_resume_url(self, obj):
        return getattr(obj.seeker, 'resume_url', None)

    def get_seeker_resume_text(self, obj):
        return getattr(obj.seeker, 'resume_text', None)

class InterviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interview
        fields = ['id', 'application', 'title', 'date', 'time', 'created_at']
        read_only_fields = ['id', 'created_at']


# ==============================
# Seeker Profile
# ==============================

class JobSeekerSerializer(serializers.ModelSerializer):
    # expose user basics read-only
    user_email = serializers.SerializerMethodField(read_only=True)
    user_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = JobSeeker
        fields = ['id', 'resume_url', 'resume_text', 'created_at', 'user_email', 'user_name']
        read_only_fields = ['id', 'created_at', 'user_email', 'user_name']

    def get_user_email(self, obj):
        return getattr(obj.user, 'email', None)

    def get_user_name(self, obj):
        u = obj.user
        return f"{u.first_name} {u.last_name}".strip()


# ==============================
# Appointments
# ==============================

class AppointmentSerializer(serializers.ModelSerializer):
    application_info = serializers.SerializerMethodField(read_only=True)
    room = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Appointment
        fields = ['id', 'title', 'date', 'time', 'created_at', 'application', 'application_info', 'room']
        read_only_fields = ['id', 'created_at', 'application_info', 'room']

    def get_application_info(self, obj):
        app = obj.application
        job = app.job
        employer = job.employer
        return {
            'application_id': app.id,
            'job_title': job.title,
            'employer_company': employer.company_name,
            'seeker_email': getattr(app.seeker.user, 'email', None),
        }

    def get_room(self, obj):
        # Deterministic room name based on appointment ID and date
        try:
            date_str = obj.date.strftime('%Y%m%d') if obj.date else 'nodate'
        except Exception:
            date_str = 'nodate'
        return f"appt_{obj.id}_{date_str}"


# ==============================
# Admin Manage Accounts
# ==============================

class AdminUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role', 'is_active',
            'is_staff', 'is_superuser', 'phone', 'gender', 'dob', 'date_joined', 'last_login'
        ]
        read_only_fields = fields


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'role', 'is_active',
            'is_staff', 'is_superuser', 'phone', 'gender', 'dob'
        ]

    def validate_role(self, value):
        if value is None:
            return value
        v = value.lower()
        if v not in ['seeker', 'provider']:
            raise serializers.ValidationError("Invalid role. Must be 'seeker' or 'provider'.")
        return v

    def validate(self, attrs):
        request = self.context.get('request')
        # Only superusers can elevate to staff/superuser
        if ('is_staff' in attrs or 'is_superuser' in attrs) and not (request and request.user and request.user.is_superuser):
            raise serializers.ValidationError('Only superusers can modify staff/superuser flags.')
        # Normalize gender if provided
        gender = attrs.get('gender', None)
        if gender:
            g = str(gender).upper()
            if g not in ['MALE', 'FEMALE', 'OTHER']:
                raise serializers.ValidationError({'gender': "Must be 'MALE', 'FEMALE', or 'OTHER'."})
            attrs['gender'] = g
        return attrs