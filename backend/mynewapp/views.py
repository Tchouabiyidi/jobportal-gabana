from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly, IsAdminUser
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import login
from django.db.models import Q
from .serializers import (
    UserSerializer,
    LoginSerializer,
    JobSerializer,
    ApplicationSerializer,
    InterviewSerializer,
    AppointmentSerializer,
    AdminUserListSerializer,
    AdminUserUpdateSerializer,
    JobSeekerSerializer,
)
from .models import Job, Application, Interview, JobSeeker, Appointment
from django.contrib.auth import get_user_model
User = get_user_model()
from .services.ai_service import recommend_best_job

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token = Token.objects.get(user=user)  # Token is created on user creation via CustomUserManager
            
            return Response({
                'user': {
                    'id': user.pk,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': getattr(user, 'role', None),
                },
                'token': token.key
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'errors': serializer.errors,
            'message': 'Registration failed'
        }, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)
            login(request, user)
            
            return Response({
                'token': token.key,
                'user': {
                    'id': user.pk,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': getattr(user, 'role', None),
                    'is_staff': getattr(user, 'is_staff', False),
                    'is_superuser': getattr(user, 'is_superuser', False),
                }
            }, status=status.HTTP_200_OK)
            
        return Response({
            'errors': serializer.errors,
            'message': 'Login failed'
        }, status=status.HTTP_400_BAD_REQUEST)

class JobListCreateView(generics.ListCreateAPIView):
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Job.objects.filter(is_active=True).order_by('-created_at')
        q = self.request.query_params.get('q')
        location = self.request.query_params.get('location')
        mine = self.request.query_params.get('mine')
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(requirement__icontains=q)
            )
        if location:
            qs = qs.filter(location__icontains=location)
        if mine and self.request.user.is_authenticated and hasattr(self.request.user, 'employer_profile'):
            qs = qs.filter(employer=self.request.user.employer_profile)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        role = getattr(user, 'role', None)
        if not user.is_authenticated or role != 'provider' or not hasattr(user, 'employer_profile'):
            raise PermissionDenied('Only providers can post jobs.')
        serializer.save(employer=user.employer_profile)


class JobRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobSerializer
    queryset = Job.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self):
        obj = super().get_object()
        # Allow anyone to retrieve active jobs
        if self.request.method in ['GET']:
            if obj.is_active:
                return obj


# ==============================
# Appointments
# ==============================

class AppointmentListView(generics.ListAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Appointment.objects.select_related(
            'application__job__employer', 'application__seeker__user'
        ).order_by('-date', '-time', '-created_at')
        mine = self.request.query_params.get('mine') or self.request.query_params.get('my')
        if mine and self.request.user.is_authenticated:
            user = self.request.user
            if hasattr(user, 'seeker_profile'):
                qs = qs.filter(application__seeker=user.seeker_profile)
            elif hasattr(user, 'employer_profile'):
                qs = qs.filter(application__job__employer=user.employer_profile)
        return qs


class ApplicationListView(generics.ListCreateAPIView):
    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Application.objects.select_related('job__employer', 'seeker__user').order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        mine = self.request.query_params.get('mine') or self.request.query_params.get('my')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if mine and self.request.user.is_authenticated:
            user = self.request.user
            if hasattr(user, 'employer_profile'):
                qs = qs.filter(job__employer=user.employer_profile)
            elif hasattr(user, 'seeker_profile'):
                qs = qs.filter(seeker=user.seeker_profile)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        # Only job seekers can apply; auto-provision seeker profile if missing
        if not user.is_authenticated or getattr(user, 'role', None) != 'seeker':
            raise PermissionDenied('Only job seekers can apply.')
        if not hasattr(user, 'seeker_profile'):
            # create a seeker profile for this user to unblock application
            seeker = JobSeeker.objects.create(user=user)
        else:
            seeker = user.seeker_profile
        # job id comes via serializer validated data (PrimaryKeyRelatedField)
        job = serializer.validated_data.get('job')
        if not job or not job.is_active:
            raise PermissionDenied('This job is not available.')
        # Prevent duplicate applications
        exists = Application.objects.filter(job=job, seeker=seeker).exists()
        if exists:
            raise PermissionDenied('You have already applied to this job.')
        serializer.save(job=job, seeker=seeker)


class SeekerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = JobSeekerSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self):
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied('Authentication required.')
        if not hasattr(user, 'seeker_profile'):
            return JobSeeker.objects.create(user=user)
        return user.seeker_profile


class ApplicationRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    serializer_class = ApplicationSerializer
    queryset = Application.objects.select_related('job__employer', 'seeker__user')
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self):
        obj = super().get_object()
        # Allow GET to owners only (optional); for safety we gate GET too
        user = self.request.user
        if not user.is_authenticated or getattr(user, 'role', None) != 'provider' or not hasattr(user, 'employer_profile'):
            raise PermissionDenied('Not allowed.')
        if obj.job.employer_id != user.employer_profile.id:
            raise PermissionDenied('Not allowed.')
        return obj


class InterviewListCreateView(generics.ListCreateAPIView):
    serializer_class = InterviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Interview.objects.select_related('application__job__employer').order_by('-created_at')
        mine = self.request.query_params.get('mine') or self.request.query_params.get('my')
        if mine and self.request.user.is_authenticated:
            user = self.request.user
            if hasattr(user, 'employer_profile'):
                qs = qs.filter(application__job__employer=user.employer_profile)
            elif hasattr(user, 'seeker_profile'):
                qs = qs.filter(application__seeker=user.seeker_profile)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_authenticated or getattr(user, 'role', None) != 'provider' or not hasattr(user, 'employer_profile'):
            raise PermissionDenied('Only providers can schedule interviews.')
        application_id = self.request.data.get('application')
        try:
            app = Application.objects.select_related('job__employer').get(pk=application_id)
        except Application.DoesNotExist:
            raise PermissionDenied('Invalid application.')
        if app.job.employer_id != user.employer_profile.id:
            raise PermissionDenied('Not allowed.')
        interview = serializer.save(application=app)
        # Ensure an Appointment exists/updates for this application so the seeker can see and join
        # Appointment is OneToOne with Application
        Appointment.objects.update_or_create(
            application=app,
            defaults={
                'title': interview.title,
                'date': interview.date,
                'time': interview.time,
                'content': f"Interview: {interview.title}",
            }
        )


class AIJobRecommendationView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def post(self, request):
        # Get resume text from body or seeker profile
        resume_text = (request.data.get('resume_text') or '').strip()
        limit = int(request.data.get('limit') or 25)

        if not resume_text and request.user.is_authenticated and hasattr(request.user, 'seeker_profile'):
            resume_text = request.user.seeker_profile.resume_text or ''

        # Collect active jobs
        jobs_qs = Job.objects.filter(is_active=True).order_by('-created_at')[: max(5, limit)]
        jobs_payload = [
            {
                'id': j.id,
                'title': j.title,
                'description': j.description,
                'requirement': j.requirement,
                'location': j.location,
            }
            for j in jobs_qs
        ]

        if not jobs_payload:
            return Response({'detail': 'No active jobs available.'}, status=status.HTTP_404_NOT_FOUND)

        # If resume_text is empty, still proceed; model may pick based on title/description
        result = recommend_best_job(resume_text or '', jobs_payload)
        best_id = result.get('best_job_id')

        best_job = None
        if best_id:
            best_job = Job.objects.filter(pk=best_id, is_active=True).first()
        # Fallback to first job if model returned invalid id
        if not best_job:
            best_job = jobs_qs[0]

        job_data = JobSerializer(best_job).data
        return Response({
            'recommendation': {
                'score': result.get('score'),
                'reason': result.get('reason'),
            },
            'job': job_data,
        }, status=status.HTTP_200_OK)


class InterviewRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    serializer_class = InterviewSerializer
    queryset = Interview.objects.select_related('application__job__employer')
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if not user.is_authenticated or getattr(user, 'role', None) != 'provider' or not hasattr(user, 'employer_profile'):
            raise PermissionDenied('Not allowed.')
        if obj.application.job.employer_id != user.employer_profile.id:
            raise PermissionDenied('Not allowed.')
        return obj


# ==============================
# Admin Manage Accounts
# ==============================

class AdminUserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = User.objects.all().order_by('-date_joined')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserSerializer  # creation with password validation
        return AdminUserListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get('q')
        role = self.request.query_params.get('role')
        is_active = self.request.query_params.get('is_active')
        is_staff = self.request.query_params.get('is_staff')
        is_superuser = self.request.query_params.get('is_superuser')
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        if role in ['seeker', 'provider']:
            qs = qs.filter(role=role)
        if is_active in ['true', 'false']:
            qs = qs.filter(is_active=(is_active == 'true'))
        if is_staff in ['true', 'false']:
            qs = qs.filter(is_staff=(is_staff == 'true'))
        if is_superuser in ['true', 'false']:
            qs = qs.filter(is_superuser=(is_superuser == 'true'))
        return qs

    def create(self, request, *args, **kwargs):
        # Use UserSerializer for creation, then return AdminUserListSerializer
        create_serializer = UserSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        user = create_serializer.save()
        read_serializer = AdminUserListSerializer(user)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)


class AdminUserRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()

    def get_serializer_class(self):
        if self.request.method in ['GET']:
            return AdminUserListSerializer
        return AdminUserUpdateSerializer

    def destroy(self, request, *args, **kwargs):
        # Soft-deactivate instead of hard delete
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)