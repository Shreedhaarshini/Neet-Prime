from django.contrib import admin
from .models import Subject, TestResult, QuestionLog

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'subject', 'score', 'total_questions', 'date_taken')
    list_filter = ('subject', 'date_taken')
    search_fields = ('user__username', 'subject__name')

@admin.register(QuestionLog)
class QuestionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'subject', 'date_asked')
    list_filter = ('subject', 'date_asked')
    search_fields = ('user__username', 'subject__name', 'question_hash')