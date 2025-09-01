from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    JobListCreateView,
    JobRetrieveUpdateDestroyView,
    ApplicationListView,
    ApplicationRetrieveUpdateView,
    InterviewListCreateView,
    InterviewRetrieveDestroyView,
    AppointmentListView,
    AdminUserListCreateView,
    AdminUserRetrieveUpdateDestroyView,
    SeekerProfileView,
    AIJobRecommendationView,
)

urlpatterns = [
    path('users/register/', RegisterView.as_view(), name='register'),
    path('users/login/', LoginView.as_view(), name='login'),
    path('users/me/seeker/', SeekerProfileView.as_view(), name='seeker-profile'),
    # System admin - Manage Accounts
    path('system/users/', AdminUserListCreateView.as_view(), name='admin-users-list-create'),
    path('system/users/<int:pk>/', AdminUserRetrieveUpdateDestroyView.as_view(), name='admin-users-rud'),
    path('jobs/', JobListCreateView.as_view(), name='jobs'),
    path('jobs/<int:pk>/', JobRetrieveUpdateDestroyView.as_view(), name='job-detail'),
    # AI recommendation
    path('ai/recommend-job/', AIJobRecommendationView.as_view(), name='ai-recommend-job'),
    # Applications
    path('applications/', ApplicationListView.as_view(), name='applications-list'),
    path('applications/<int:pk>/', ApplicationRetrieveUpdateView.as_view(), name='application-detail'),
    # Interviews
    path('interviews/', InterviewListCreateView.as_view(), name='interviews-list-create'),
    path('interviews/<int:pk>/', InterviewRetrieveDestroyView.as_view(), name='interview-detail'),
    # Appointments
    path('appointments/', AppointmentListView.as_view(), name='appointments-list'),
]