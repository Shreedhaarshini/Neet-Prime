from django.db import models
from django.contrib.auth.models import User

class Subject(models.Model):
    name = models.CharField(max_length=50) # e.g., Physics, Chemistry, Maths

    def __str__(self):
        return self.name

class TestResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    score = models.FloatField()
    total_questions = models.IntegerField()
    difficulty = models.CharField(max_length=20, default='Medium')
    questions_data = models.JSONField(null=True, blank=True) # Full list of question objects
    user_answers = models.JSONField(null=True, blank=True) # Choices made by student
    date_taken = models.DateTimeField(auto_now_add=True)
    chapters_covered = models.ManyToManyField('Chapter', blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.subject.name if self.subject else 'Mixed'} - {self.score}/{self.total_questions}"

class QuestionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    question_hash = models.CharField(max_length=256) # Stores a hash of the question to prevent repeats
    date_asked = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Log: {self.user.username} - {self.subject.name}"
class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.subject.name} - {self.name}"