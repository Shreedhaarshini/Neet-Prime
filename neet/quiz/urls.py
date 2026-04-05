from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('accounts/login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('signup/', views.signup_view, name='signup'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('generatetest/', views.quiz_view, name='quiz'),
    path('api/generate/', views.generate_quiz, name='generate_quiz'),
    path('api/submit/', views.submit_quiz_score, name='submit_quiz'),
    path('result/<int:test_id>/', views.result_detail, name='quiz_result'),
    path('api/dashboard/', views.student_dashboard_data),
    path('api/chatbot/', views.chatbot_assistant, name='chatbot_assistant'),
]
